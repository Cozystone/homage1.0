from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.routers import dual_brain


def test_dual_brain_ingest_links_semantic_and_surface(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/dual-brain/ingest",
        json={"text": "쉽게 말하면, 쿠버네티스는 많은 컨테이너를 자동으로 배치하고 관리하는 운영 관리자에 가깝습니다."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["semantic_projection"]["source_hash"] == payload["surface_projection"]["source_hash"]
    assert payload["stored_raw_text"] is False
    assert payload["external_llm_used"] is False


def test_chat_uses_base_brain_when_rag_has_concepts_without_grounding(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    async def fake_query_graphrag(*args, **kwargs):
        return {
            "result": {
                "active_concepts": ["Kubernetes"],
                "matched_nodes": [{"label": "Kubernetes"}],
                "matched_edges": [],
                "evidence_docs": [],
                "confidence": 0.1,
                "retrieval_trace": {},
            }
        }

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fake_query_graphrag)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={"question": "쿠버네티스가 뭐야?", "language": "ko", "brain_mode": "local", "include_trace": True},
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert "쿠버네티스" in payload["answer"]
    assert "컨테이너" in payload["answer"]
    assert "Cloud Brain" not in payload["answer"]
    assert "source_hash" not in payload["answer"]
    assert payload["compact_trace"]["local_coverage"] == "base_brain"
    assert payload["external_llm_used"] is False
    assert payload["external_sllm_used"] is False
    assert payload["local_brain_write"] is False


def test_chat_accepts_query_alias_and_blocks_internal_leakage(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    async def fake_query_graphrag(*args, **kwargs):
        return {
            "result": {
                "active_concepts": ["GraphRAG"],
                "matched_nodes": [{"label": "GraphRAG"}],
                "matched_edges": [
                    {
                        "source_hash": "87eba76e7f3164534045ba922e7770fb58bbd14ad732bbf5ba6f11cc56989e6e",
                        "relation": "relates_to",
                        "target_hash": "084943ae838283848e9e4b5e0c66b0743414d7198b2bfa8f47a5f88db823f969",
                    }
                ],
                "evidence_docs": [{"source_hash": "abcdef1234567890abcdef1234567890", "snippet": ""}],
                "confidence": 0.2,
                "retrieval_trace": {},
            }
        }

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fake_query_graphrag)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={"query": "GraphRAG가 근거 문서를 어떻게 사용해서 답변을 검증하나요?", "language": "ko"},
    )

    assert response.status_code == 200
    answer = response.json()["result"]["answer"]
    assert "GraphRAG" in answer
    assert "근거" in answer
    assert "source_hash" not in answer


def test_chat_default_path_attaches_hidden_three_core_trace(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    async def fake_query_graphrag(*args, **kwargs):
        return {
            "result": {
                "active_concepts": ["Kubernetes", "containers"],
                "matched_nodes": [{"label": "Kubernetes"}, {"label": "containers"}],
                "matched_edges": [{"source": "Kubernetes", "relation": "manages", "target": "containers", "confidence": 0.8}],
                "evidence_docs": [{"title": "seed", "snippet": "Kubernetes manages containers."}],
                "confidence": 0.7,
                "retrieval_trace": {},
            }
        }

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fake_query_graphrag)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={"question": "Explain Kubernetes in simple English.", "language": "en"},
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    answer = payload["answer"]
    assert payload["trace"] is None
    assert payload["default_trace_visible"] is False
    assert payload["compact_trace"]["three_core"]["used"] is True
    assert payload["compact_trace"]["three_core"]["sqc"]["used"] is True
    assert payload["compact_trace"]["three_core"]["fractal_seed_rail"]["used"] is True
    assert payload["compact_trace"]["three_core"]["holographic_wave"]["used"] is True
    assert payload["answer_engine"]["three_core_trace_attached"] is True
    assert payload["answer_engine"]["three_core_answer_source"] == "hidden_trace_only"
    assert "SQC" not in answer
    assert "Fractal" not in answer
    assert "Wave" not in answer
    assert "Q-Cortex" not in answer
    assert "Local Brain" not in answer
    assert "Cloud Brain" not in answer
    assert "source_hash" not in answer
    assert payload["external_llm_used"] is False
    assert payload["external_sllm_used"] is False
    assert payload["local_brain_write"] is False


def test_chat_trace_mode_exposes_compact_three_core_summary(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    async def fake_query_graphrag(*args, **kwargs):
        return {
            "result": {
                "active_concepts": ["ATANOR", "symbolic reasoning"],
                "matched_nodes": [{"label": "ATANOR"}, {"label": "symbolic reasoning"}],
                "matched_edges": [{"source": "ATANOR", "relation": "uses", "target": "symbolic reasoning", "confidence": 0.75}],
                "evidence_docs": [{"title": "seed", "snippet": "ATANOR uses symbolic reasoning."}],
                "confidence": 0.7,
                "retrieval_trace": {},
            }
        }

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fake_query_graphrag)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={"question": "Explain ATANOR as one sentence.", "language": "en", "mode": "trace"},
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert isinstance(payload["trace"], dict)
    assert payload["trace"]["three_core"]["used"] is True
    assert payload["trace"]["three_core"]["honesty"]["external_llm_used"] is False
    assert payload["trace"]["three_core"]["honesty"]["external_sllm_used"] is False
    assert payload["trace"]["three_core"]["honesty"]["local_brain_write"] is False
    assert "source_hash" not in payload["answer"]


def test_local_graph_status_questions_do_not_fall_through_to_base_brain(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    def fail_base_brain(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("status questions must not call Base Brain fallback")

    monkeypatch.setattr(dual_brain, "answer_with_base_brain", fail_base_brain)
    client = TestClient(app)

    for question in (
        "내 로컬 메모리 총 노드 수",
        "내 로컬 메모리 총 연결선 수",
        "내 로컬 메모리 총 엣지 수",
        "내 개인 메모리 관계 수 알려줘",
        "화면에 표시 중인 로컬 그래프 노드 수",
        "렌더링된 연결선 수",
        "기본 시드 앵커까지 포함하면 몇 개야?",
    ):
        response = client.post(
            "/api/chat/atanor",
            json={"question": question, "language": "ko", "brain_mode": "local", "include_trace": True},
        )
        assert response.status_code == 200
        payload = response.json()["result"]
        assert "RAM" not in payload["answer"]
        assert "SSD" not in payload["answer"]
        assert "연결선" in payload["answer"] or "논리 노드" in payload["answer"]
        assert payload["compact_trace"]["local_coverage"] == "status_question"
        assert payload["compact_trace"]["graph_status"]["selected_scope"] == "local"
        assert "personal_local_memory_count" in payload["compact_trace"]["graph_status"]
        assert "local_viewport_materialized_count" in payload["compact_trace"]["graph_status"]
        assert "seed_anchor_count" in payload["compact_trace"]["graph_status"]
        assert payload["external_llm_used"] is False
        assert payload["external_sllm_used"] is False
        assert payload["local_brain_write"] is False


def test_cloud_graph_status_question_uses_status_router(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    def fail_base_brain(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("status questions must not call Base Brain fallback")

    monkeypatch.setattr(dual_brain, "answer_with_base_brain", fail_base_brain)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={"question": "cloud graph relation count", "language": "en", "brain_mode": "cloud", "include_trace": True},
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert "relations" in payload["answer"]
    assert payload["compact_trace"]["local_coverage"] == "status_question"
    assert payload["compact_trace"]["graph_status"]["selected_scope"] == "cloud"
    assert payload["external_llm_used"] is False
    assert payload["external_sllm_used"] is False


def test_cloud_status_read_failure_does_not_use_general_knowledge(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    def fail_status(self):
        raise RuntimeError("status unavailable")

    def fail_base_brain(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("status read failure must not call Base Brain fallback")

    monkeypatch.setattr(dual_brain.SemanticCloudStore, "status", fail_status)
    monkeypatch.setattr(dual_brain, "answer_with_base_brain", fail_base_brain)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={"question": "클라우드 브레인 관계 수", "language": "ko", "brain_mode": "cloud", "include_trace": True},
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert "상태를 읽을 수 없습니다" in payload["answer"]
    assert "RAM" not in payload["answer"]
    assert payload["compact_trace"]["graph_status"]["status_unavailable"] is True
    assert payload["external_llm_used"] is False
    assert payload["external_sllm_used"] is False


def test_computer_memory_questions_still_use_base_brain(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)

    ram_response = client.post(
        "/api/chat/atanor",
        json={"question": "RAM은 뭐야?", "language": "ko", "brain_mode": "local", "include_trace": True},
    )
    assert ram_response.status_code == 200
    ram_payload = ram_response.json()["result"]
    assert "RAM" in ram_payload["answer"]
    assert ram_payload["compact_trace"]["local_coverage"] == "base_brain"
    assert ram_payload["external_llm_used"] is False
    assert ram_payload["external_sllm_used"] is False
    assert ram_payload["local_brain_write"] is False

    comparison_response = client.post(
        "/api/chat/atanor",
        json={"question": "컴퓨터 메모리와 SSD 차이", "language": "ko", "brain_mode": "local", "include_trace": True},
    )
    assert comparison_response.status_code == 200
    comparison_payload = comparison_response.json()["result"]
    assert "RAM" in comparison_payload["answer"]
    assert "SSD" in comparison_payload["answer"]
    assert comparison_payload["compact_trace"]["local_coverage"] == "base_brain"


def test_live_selfhood_greeting_uses_native_conversation_surface(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    async def fail_query_graphrag(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("short live conversation must not enter graph retrieval")

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fail_query_graphrag)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={"question": "안녕", "language": "ko", "brain_mode": "unified", "include_trace": True},
    )

    assert response.status_code == 200
    body = response.json()
    payload = body["result"]
    assert body["state"] == "completed"
    assert payload["answer"]
    assert "먼저 의도와 경계" not in payload["answer"]
    assert "내부적으로 점검" not in payload["answer"]
    assert payload["answer_kind"] == "asm_v0_conversation_surface"
    assert payload["speech_act"] == "greeting"
    assert payload["can_speak"] is True
    assert payload["final_answer_generation_claimed"] is True
    assert payload["compact_trace"]["local_coverage"] == "live_selfhood_conversation"
    assert payload["compact_trace"]["selfhood_loop"]["internal_scratchpad_visible"] is False
    assert payload["compact_trace"]["selfhood_loop"]["rule_based_answer_blocked"] is True
    assert payload["compact_trace"]["selfhood_loop"]["requires_learned_generator"] is False
    assert payload["compact_trace"]["surface_graph"]["conversation_surface"]["generation_basis"] == "local_corpus_construction_transition_model"
    assert payload["answer_engine"]["rule_based_answer_used"] is False
    assert payload["answer_engine"]["template_free_surface"] is True
    assert payload["answer_engine"]["external_llm"] is False
    assert payload["answer_engine"]["external_sllm"] is False
    assert payload["answer_engine"]["production_store_mutated"] is False
    assert payload["answer_engine"]["candidate_promotion"] is False
    assert payload["answer_engine"]["internal_trace_exposed"] is False
    assert payload["voice_output"]["tts_engine"] == "fish_2"
    assert payload["voice_output"]["external_service"] is False
    assert payload["voice_output"]["generated_audio_persisted"] is False
    assert payload["local_brain_write"] is False


def test_live_selfhood_self_model_generates_without_scratchpad_or_rule_answer(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    async def fail_query_graphrag(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("short self-model conversation must not enter graph retrieval")

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fail_query_graphrag)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={"question": "지금 자기 모델을 설명해줘", "language": "ko", "brain_mode": "unified", "include_trace": False},
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["answer"]
    assert "자기 모델" in payload["answer"]
    assert "먼저 의도와 경계" not in payload["answer"]
    assert "내부적으로 점검" not in payload["answer"]
    assert payload["answer_kind"] == "asm_v0_conversation_surface"
    assert payload["speech_act"] == "self_model"
    assert payload["can_speak"] is True
    assert payload["trace"] is None
    assert payload["compact_trace"]["selfhood_loop"]["internal_scratchpad_visible"] is False
    assert payload["compact_trace"]["selfhood_loop"]["rule_based_answer_blocked"] is True
    assert payload["answer_engine"]["rule_based_answer_used"] is False
    assert payload["answer_engine"]["generation_basis"] == "local_corpus_construction_transition_model"
    assert payload["external_llm_used"] is False
    assert payload["external_sllm_used"] is False
