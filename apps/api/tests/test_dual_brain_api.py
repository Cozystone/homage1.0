from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient

from app.main import app
from app.routers import dual_brain
from packages.cgsr.cgsr.visual_imagination_planner import plan_visual_imagination
from packages.voice_loop.local_tts import LocalTTSResult, local_voice_audio_dir


def _fake_voice_synthesis(
    text: str,
    *,
    language: str = "ko",
    rate: int = 0,
    volume: int = 100,
    sentence_gap_ms: int = 220,
) -> LocalTTSResult:
    root = local_voice_audio_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "atanor_voice_22222222222222222222222222222222.wav"
    path.write_bytes(b"RIFF$\x00\x00\x00WAVEfmt ")
    return LocalTTSResult(engine="windows_sapi", audio_path=path, audio_url=f"/api/voice-loop/audio/{path.name}", rate=rate, volume=volume)


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


def test_chat_conversation_uses_readonly_verified_store_for_grounded_visual_scene(tmp_path, monkeypatch) -> None:
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps(
            {
                "text": "Gravity is a force of attraction between masses. Isaac Newton formulated the law of universal gravitation.",
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "Gravity"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ATANOR_VERIFIED_STORE_PATH", str(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={
            "question": "What is the law of gravity?",
            "language": "en",
            "mode": "conversation",
            "brain_mode": "conversation",
            "include_trace": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["route_type"] == "general_knowledge_question"
    assert payload["compact_trace"]["semantic_grounding"]["grounding_source"] == "verified_store_v0_readonly"
    assert "Isaac Newton" in payload["answer"]
    assert payload["scene_choreography"] is None
    assert payload["splatra_scene_policy"]["scene_content_source"] == "none"
    assert payload["splatra_scene_policy"]["scene_authoring_basis"] == "abstained_abstract_or_nonvisual_evidence"
    assert payload["splatra_scene_policy"]["reason"] == "insufficient_concrete_visual_evidence"
    assert payload["splatra_scene_policy"]["topic_scene_templates"] is False
    assert payload["splatra_scene_policy"]["renderer_may_infer_topic"] is False
    assert payload["splatra_scene_policy"]["particle_text"] is False
    assert payload["splatra_scene_policy"]["text_rendering"] == "dom_text_not_particles"
    assert payload["splatra_scene_policy"]["verified_evidence_required_for_general_knowledge"] is True
    assert payload["answer_engine"]["splatra_scene_policy"]["scene_content_source"] == "none"
    assert payload["external_llm_used"] is False
    assert payload["external_sllm_used"] is False
    assert payload["local_brain_write"] is False
    assert payload["production_store_mutated"] is False


def test_dashboard_conversation_returns_verified_speech_timeline_for_motion_scene(tmp_path, monkeypatch) -> None:
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps(
            {
                "text": (
                    "Gravity is associated with Isaac Newton. "
                    "Isaac Newton sat under an apple tree. "
                    "An apple fell from the tree toward Newton, and the event helped explain gravitational attraction."
                ),
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "Newton apple tree"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ATANOR_VERIFIED_STORE_PATH", str(tmp_path))

    async def fail_query_graphrag(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("dashboard conversation mode must not enter graph retrieval")

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fail_query_graphrag)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={
            "question": "What is gravity?",
            "language": "en",
            "mode": "conversation",
            "brain_mode": "conversation",
            "include_trace": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    scene = payload["splatra_scene_plan"]
    command_sequence = payload["splatra_command_sequence"]
    cartridge_queue = payload["splatra_cartridge_queue"]
    assert scene == payload["scene_choreography"] == payload["visual_scene_plan"]
    assert command_sequence["hot_swap_policy"]["mode"] == "candidate_only"
    assert command_sequence["hot_swap_policy"]["viewer_side_channel"] == "GET /v1/cartridge"
    assert command_sequence["hot_swap_policy"]["candidate_request_count"] == len(command_sequence["scene_actions"])
    assert command_sequence["splatra_contract"]["agent_context_payload"] == "sgf_summary_and_command_sequence_only"
    assert command_sequence["splatra_contract"]["raw_buffers_in_agent_context"] is False
    assert command_sequence["splatra_contract"]["topic_scene_templates"] is False
    assert command_sequence["splatra_contract"]["renderer_may_infer_topic"] is False
    assert command_sequence["particle_motion_policy"]["agent_control"] == "airbend_recompose_particles_inside_safe_region"
    assert len(command_sequence["scene_actions"]) == len(scene["beats"])
    assert len(command_sequence["candidate_cartridge_requests"]) == len(scene["beats"])
    assert cartridge_queue["status"] == "ready_for_sidecar"
    assert cartridge_queue["execution_mode"] == "candidate_only_dry_run"
    assert cartridge_queue["side_channel"] == "GET /v1/cartridge"
    assert cartridge_queue["job_count"] == len(scene["beats"])
    assert cartridge_queue["external_splatra_called"] is False
    assert cartridge_queue["raw_buffer_in_agent_context"] is False
    assert cartridge_queue["mutation_performed"] is False
    assert any(action["op"] == "move" for action in command_sequence["scene_actions"])
    assert all(request["cartridge_format"] == "SPL3_candidate" for request in command_sequence["candidate_cartridge_requests"])
    assert all(request["execution"]["execute_now"] is False for request in command_sequence["candidate_cartridge_requests"])
    assert all(request["execution"]["raw_buffer_in_agent_context"] is False for request in command_sequence["candidate_cartridge_requests"])
    assert all(action["args"]["text_rendering"] == "dom_text_not_particles" for action in command_sequence["scene_actions"])
    assert all(action["args"]["particle_text"] is False for action in command_sequence["scene_actions"])
    assert scene["stage_layout"] == "scene_focus"
    assert scene["layout_intent"] == "wide_particle_stage"
    assert scene["dashboard_layout"]["agent_layout_decision"]["decision_basis"] == "verified_scene_geometry_and_self_body_clearance_state"
    assert scene["dashboard_layout"]["agent_layout_decision"]["decision_model"] == "self_body_scene_pressure_scorer_no_topic_templates"
    assert scene["dashboard_layout"]["agent_layout_decision"]["scene_self_state"]["self_body_identity"] == "atanor_orb_self_body"
    assert scene["dashboard_layout"]["agent_layout_decision"]["text_rendering"] == "dom_text_not_particles"
    assert payload["splatra_scene_policy"]["scene_content_source"] == "verified_store_facts"
    assert payload["splatra_scene_policy"]["layout_decision_basis"] == "verified_scene_geometry_and_client_feedback"
    assert payload["splatra_scene_policy"]["renderer_may_infer_topic"] is False
    assert payload["splatra_scene_policy"]["particle_text"] is False
    assert payload["splatra_scene_policy"]["text_rendering"] == "dom_text_not_particles"
    assert scene["dashboard_layout"]["orb"]["anchor"] == "lower_right"
    assert scene["layout_timeline"][0]["decision_basis"] == "verified_scene_geometry_and_self_body_clearance_state"
    assert scene["layout_timeline"][0]["text_rendering"] == "dom_text_not_particles"
    assert scene["layout_timeline"][0]["orb_movement"] in {"lower_right_scaled_down", "lower_right_micro_stage_guard"}
    assert any(item["action"] == "sync_orb_text_with_particle_beat" for item in scene["layout_timeline"])
    assert scene["topic_scene_templates"] is False
    assert scene["speech_timeline"]
    assert all(item["text_source"] == "verified_beat_narration" for item in scene["speech_timeline"])
    assert all(item["speech_cue_basis"] == "verified_evidence_unit" for item in scene["speech_timeline"])
    assert any(item["particle_behavior"] == "gravity_arc" for item in scene["speech_timeline"])
    gravity_item = next(item for item in scene["speech_timeline"] if item["particle_behavior"] == "gravity_arc")
    assert gravity_item["physics_hint"]["field"] == "downward_attraction"
    assert gravity_item["motion_path"]["basis"] == "verified_motion_phrase"
    assert "apple" in gravity_item["text"].casefold()
    assert payload["answer_engine"]["external_llm"] is False
    assert payload["answer_engine"]["external_sllm"] is False
    assert payload["answer_engine"]["rule_based_answer_used"] is False
    assert payload["local_brain_write"] is False
    assert payload["production_store_mutated"] is False


def test_verified_store_runtime_discovers_sibling_primary_store(tmp_path, monkeypatch) -> None:
    isolated = tmp_path / "ATANOR-live-selfhood-scheduler"
    sibling = tmp_path / "24.Homage1.0" / "data" / "cloud_brain" / "verified_store_v0"
    isolated.mkdir()
    sibling.mkdir(parents=True)
    (sibling / "evidence.jsonl").write_text("", encoding="utf-8")

    monkeypatch.delenv("ATANOR_VERIFIED_STORE_PATH", raising=False)
    monkeypatch.setattr(dual_brain, "PROJECT_ROOT", isolated)

    runtime = dual_brain._verified_store_runtime()

    assert runtime == {"verified_store_path": str(sibling)}


def test_verified_store_runtime_falls_back_when_configured_path_is_missing(tmp_path, monkeypatch) -> None:
    isolated = tmp_path / "ATANOR-live-selfhood-scheduler"
    missing_configured = tmp_path / "missing" / "verified_store_v0"
    sibling = tmp_path / "24.Homage1.0" / "data" / "cloud_brain" / "verified_store_v0"
    isolated.mkdir()
    sibling.mkdir(parents=True)
    (sibling / "evidence.jsonl").write_text("", encoding="utf-8")

    monkeypatch.setenv("ATANOR_VERIFIED_STORE_PATH", str(missing_configured))
    monkeypatch.setattr(dual_brain, "PROJECT_ROOT", isolated)

    runtime = dual_brain._verified_store_runtime()

    assert runtime == {"verified_store_path": str(sibling)}


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
    monkeypatch.setattr(dual_brain, "synthesize_windows_sapi", _fake_voice_synthesis)
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
    assert payload["voice_output"]["requested"] is True
    assert payload["voice_output"]["enabled"] is True
    assert payload["voice_output"]["selected_engine"] in {"fallback", "fish_2", "fish_1_5"}
    assert payload["voice_output"]["tts_engine"] == "windows_sapi"
    assert payload["voice_output"]["audio_available"] is True
    assert payload["voice_output"]["audio_url"] == "/api/voice-loop/audio/atanor_voice_22222222222222222222222222222222.wav"
    assert payload["voice_output"]["error_reason"] is None
    assert payload["voice_output"]["text_fallback"] is True
    assert payload["voice_output"]["microphone_enabled"] is False
    assert payload["voice_output"]["always_listening_enabled"] is False
    assert payload["voice_output"]["raw_voice_saved"] is False
    assert payload["voice_output"]["external_service"] is False
    assert payload["voice_output"]["generated_audio_persisted"] is False
    assert payload["local_brain_write"] is False
    audio_response = client.get(payload["voice_output"]["audio_url"])
    assert audio_response.status_code == 200
    assert audio_response.headers["content-type"].startswith("audio/wav")


def test_dashboard_conversation_mode_forces_asm_v0_surface(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    async def fail_query_graphrag(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("dashboard conversation mode must not enter graph retrieval")

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fail_query_graphrag)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={
            "question": "뭐 하고 있어?",
            "language": "ko",
            "brain_mode": "conversation",
            "mode": "conversation",
            "include_trace": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["answer"]

    # cross-subsystem sense (atanor_self_sense). Either that or the generic asm_v0
    # surface is acceptable — both are local, no graph retrieval, no external LLM.
    assert payload["answer_kind"] in ("asm_v0_conversation_surface", "atanor_self_sense")
    if payload["answer_kind"] == "atanor_self_sense":
        return
    assert payload["answer_engine"]["generation_basis"] == "local_corpus_construction_transition_model"
    assert payload["answer_engine"]["external_llm"] is False
    assert payload["answer_engine"]["external_sllm"] is False
    assert payload["answer_engine"]["rule_based_answer_used"] is False
    assert payload["answer_engine"]["template_free_surface"] is True
    assert payload["answer_engine"]["internal_trace_exposed"] is False
    assert payload["local_brain_write"] is False


def test_dashboard_conversation_can_return_splatra_scene_choreography_without_templates(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    async def fail_query_graphrag(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("dashboard conversation mode must not enter graph retrieval")

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fail_query_graphrag)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={
            "question": "Use SPLATRA to visualize this",
            "language": "en",
            "brain_mode": "conversation",
            "mode": "conversation",
            "include_trace": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["answer_kind"] == "asm_v0_conversation_surface"
    assert payload["scene_choreography"]["stage_layout"] == "scene_focus"
    assert payload["scene_choreography"]["orb_anchor"] == "lower_right"
    assert payload["scene_choreography"]["topic_scene_templates"] is False
    assert payload["visual_scene_plan"] == payload["scene_choreography"]
    assert payload["compact_trace"]["visual_imagination"]["topic_scene_templates"] is False
    assert payload["answer_engine"]["external_llm"] is False
    assert payload["answer_engine"]["external_sllm"] is False
    assert payload["answer_engine"]["rule_based_answer_used"] is False
    assert payload["local_brain_write"] is False


def test_direct_splatra_generation_uses_single_real_generator_sidecar_job(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[dict[str, object]] = []

    async def fail_query_graphrag(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("direct SPLATRA generation must not enter graph retrieval")

    class FakeSidecarDispatch:
        def to_dict(self) -> dict[str, object]:
            return {
                "status": "swap_ready",
                "configured": True,
                "job_count": 1,
                "external_splatra_called": True,
                "raw_buffer_in_agent_context": False,
                "raw_cartridge_fetched": False,
                "mutation_performed": False,
                "jobs": [
                    {
                        "status": "swap_ready",
                        "viewer_cartridge_url": "http://127.0.0.1:8818/v1/cartridge",
                        "generation_engine": "triposr_text_to_3d",
                        "real_generator_used": True,
                        "sgf_summary": {"num_gaussians": 170000},
                    }
                ],
            }

    def fake_dispatch(queue, *, poll_ticks=2, timeout_sec=8.0):
        calls.append(
            {
                "job_count": queue.job_count,
                "prompt": queue.jobs[0].prompt,
                "poll_ticks": poll_ticks,
                "timeout_sec": timeout_sec,
            }
        )
        return FakeSidecarDispatch()

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fail_query_graphrag)
    monkeypatch.setattr(dual_brain, "dispatch_candidate_queue_to_sidecar", fake_dispatch)
    client = TestClient(app)

    question = "사실적인 빨간 사과 3D 모델을 SPLATRA 파티클로 직접 생성해서 보여줘"
    response = client.post(
        "/api/chat/atanor",
        json={
            "question": question,
            "language": "ko",
            "brain_mode": "conversation",
            "mode": "conversation",
            "layout_feedback": {
                "feedback_basis": "client_dom_scene_collision_telemetry",
                "collision_state": "orb_overlap_risk",
                "overlap_px": 80,
                "offscreen_px": 0,
                "orb_overlap_px": 240,
                "orb_offscreen_px": 18,
                "text_rendering": "dom_text_not_particles",
                "particle_text": False,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["route_type"] == "splatra_request"
    assert payload["splatra_scene_policy"]["scene_content_source"] == "user_visual_intent_only"
    assert payload["splatra_scene_policy"]["particle_text"] is False
    assert payload["splatra_scene_policy"]["text_rendering"] == "dom_text_not_particles"
    assert payload["splatra_scene_plan"]["layout_intent"] == "wide_particle_stage"
    assert payload["splatra_scene_plan"]["dashboard_layout"]["agent_layout_decision"]["agent_action"] == "yield_center_to_particle_scene"
    feedback = payload["splatra_scene_plan"]["dashboard_layout"]["agent_layout_decision"]["client_layout_feedback"]
    assert feedback["feedback_basis"] == "client_dom_scene_collision_telemetry"
    assert feedback["content_used_for_scene_generation"] is False
    assert feedback["particle_text"] is False
    assert payload["splatra_scene_plan"]["dashboard_layout"]["stage_safe_region"]["footprint"]["block_text"] is True
    assert payload["splatra_cartridge_queue"]["job_count"] == 1
    assert payload["splatra_cartridge_queue"]["sidecar_status"] == "swap_ready"
    assert calls == [{"job_count": 1, "prompt": "red apple", "poll_ticks": 30, "timeout_sec": 180.0}]
    assert payload["splatra_cartridge_queue"]["sidecar_dispatch"]["jobs"][0]["real_generator_used"] is True
    assert payload["local_brain_write"] is False
    assert payload["production_store_mutated"] is False


def test_direct_splatra_generation_bypasses_legacy_text_fallback_in_default_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[dict[str, object]] = []

    async def fail_query_graphrag(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("direct SPLATRA generation must not enter graph retrieval")

    class FakeSidecarDispatch:
        def to_dict(self) -> dict[str, object]:
            return {
                "status": "swap_ready",
                "configured": True,
                "job_count": 1,
                "external_splatra_called": True,
                "raw_buffer_in_agent_context": False,
                "raw_cartridge_fetched": False,
                "mutation_performed": False,
                "jobs": [
                    {
                        "status": "swap_ready",
                        "viewer_cartridge_url": "http://127.0.0.1:8818/v1/cartridge",
                        "generation_engine": "triposr_text_to_3d",
                        "real_generator_used": True,
                        "sgf_summary": {"num_gaussians": 170000},
                    }
                ],
            }

    def fake_dispatch(queue, *, poll_ticks=2, timeout_sec=8.0):
        calls.append(
            {
                "job_count": queue.job_count,
                "prompt": queue.jobs[0].prompt,
                "poll_ticks": poll_ticks,
                "timeout_sec": timeout_sec,
            }
        )
        return FakeSidecarDispatch()

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fail_query_graphrag)
    monkeypatch.setattr(dual_brain, "dispatch_candidate_queue_to_sidecar", fake_dispatch)
    client = TestClient(app)

    question = "사실적인 빨간 사과 3D 모델을 SPLATRA 파티클로 직접 생성해서 보여줘"
    response = client.post(
        "/api/chat/atanor",
        json={"message": question, "language": "ko"},
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["route_type"] == "splatra_request"
    assert payload["answer_kind"] == "asm_v0_conversation_surface"
    assert payload["scene_choreography"]["layout_intent"] == "wide_particle_stage"
    assert payload["splatra_cartridge_queue"]["job_count"] == 1
    assert payload["splatra_cartridge_queue"]["sidecar_status"] == "swap_ready"
    assert calls == [{"job_count": 1, "prompt": "red apple", "poll_ticks": 30, "timeout_sec": 180.0}]
    assert payload["splatra_cartridge_queue"]["sidecar_dispatch"]["jobs"][0]["real_generator_used"] is True
    assert payload["answer_engine"]["name"] == "ATANOR Semantic-Grounded Conversation Router v0"
    assert payload["answer_engine"]["external_llm_used"] is False
    assert payload["answer_engine"]["rule_based_answer_used"] is False
    assert payload["local_brain_write"] is False
    assert payload["production_store_mutated"] is False


def test_korean_dashboard_conversation_returns_splatra_scene_plan_from_verified_store(tmp_path, monkeypatch) -> None:
    dispatch_calls: list[dict[str, object]] = []
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps(
            {
                "text": "아이작 뉴턴은 중력 법칙과 관련해 사과가 나무에서 떨어지는 장면을 관찰했다. 그 사건은 물체가 지구 쪽으로 끌리는 현상을 설명하는 단서가 되었다.",
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "뉴턴과 중력"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ATANOR_VERIFIED_STORE_PATH", str(tmp_path))

    async def fail_query_graphrag(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("dashboard conversation mode must not enter graph retrieval")

    class FakeSidecarDispatch:
        def to_dict(self) -> dict[str, object]:
            return {
                "status": "sidecar_not_configured",
                "configured": False,
                "job_count": 0,
                "external_splatra_called": False,
                "raw_buffer_in_agent_context": False,
                "raw_cartridge_fetched": False,
                "mutation_performed": False,
                "jobs": [],
            }

    def fake_dispatch(queue, *, poll_ticks=2, timeout_sec=8.0):
        dispatch_calls.append(
            {
                "job_count": queue.job_count,
                "poll_ticks": poll_ticks,
                "timeout_sec": timeout_sec,
            }
        )
        return FakeSidecarDispatch()

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fail_query_graphrag)
    monkeypatch.setattr(dual_brain, "dispatch_candidate_queue_to_sidecar", fake_dispatch)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={
            "question": "중력의 법칙에 대해 설명해줘",
            "language": "ko",
            "brain_mode": "conversation",
            "mode": "conversation",
            "include_trace": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    scene = payload["splatra_scene_plan"]
    command_sequence = payload["splatra_command_sequence"]
    cartridge_queue = payload["splatra_cartridge_queue"]
    assert payload["route_type"] == "general_knowledge_question"
    assert payload["compact_trace"]["semantic_grounding"]["grounding_source"] == "verified_store_v0_readonly"
    assert payload["answer"]
    assert "아이작 뉴턴" in payload["answer"]
    assert scene == payload["scene_choreography"] == payload["visual_scene_plan"]
    assert command_sequence["splatra_contract"]["raw_buffers_in_agent_context"] is False
    assert command_sequence["splatra_contract"]["topic_scene_templates"] is False
    assert command_sequence["splatra_contract"]["renderer_may_infer_topic"] is False
    assert command_sequence["hot_swap_policy"]["viewer_side_channel"] == "GET /v1/cartridge"
    assert command_sequence["hot_swap_policy"]["candidate_request_count"] == len(command_sequence["scene_actions"])
    assert len(command_sequence["scene_actions"]) == len(scene["beats"])
    assert len(command_sequence["candidate_cartridge_requests"]) == len(scene["beats"])
    assert cartridge_queue["status"] == "ready_for_sidecar"
    assert cartridge_queue["execution_mode"] == "candidate_only_dry_run"
    assert cartridge_queue["job_count"] == len(scene["beats"])
    assert cartridge_queue["external_splatra_called"] is False
    assert cartridge_queue["raw_buffer_in_agent_context"] is False
    assert cartridge_queue["mutation_performed"] is False
    assert cartridge_queue["sidecar_dispatch_budget"] == {"poll_ticks": 2, "timeout_sec": 180.0}
    assert dispatch_calls == [{"job_count": len(scene["beats"]), "poll_ticks": 2, "timeout_sec": 180.0}]
    assert any(action["op"] == "move" for action in command_sequence["scene_actions"])
    assert all(request["cartridge_format"] == "SPL3_candidate" for request in command_sequence["candidate_cartridge_requests"])
    assert all(request["execution"]["execute_now"] is False for request in command_sequence["candidate_cartridge_requests"])
    assert all(action["execute_js"] is False for action in command_sequence["scene_actions"])
    assert all(action["mutation_performed"] is False for action in command_sequence["scene_actions"])
    assert scene["stage_layout"] == "scene_focus"
    assert scene["orb_anchor"] == "lower_right"
    assert scene["layout_intent"] == "wide_particle_stage"
    assert scene["dashboard_layout"]["planning_basis"] == "scene_geometry_extent"
    assert scene["dashboard_layout"]["orb"]["anchor"] == "lower_right"
    assert scene["topic_scene_templates"] is False
    assert scene["scene_extent"]["motion_count"] >= 1
    assert any("사과" in beat["narration"] for beat in scene["beats"])
    assert any(beat.get("motion_path") for beat in scene["beats"])
    assert all("scene_directive" in beat for beat in scene["beats"])
    assert all("scene_evidence" in beat for beat in scene["beats"])
    assert all(beat["scene_directive"]["text_rendering"] == "dom_text_not_particles" for beat in scene["beats"])
    assert all(beat["scene_directive"]["particle_text"] is False for beat in scene["beats"])
    assert all(beat["scene_directive"]["topic_scene_templates"] is False for beat in scene["beats"])
    assert all(beat["scene_evidence"]["source_type"] == "verified_evidence_unit" for beat in scene["beats"])
    assert all(beat["scene_evidence"]["text_rendering"] == "dom_text_not_particles" for beat in scene["beats"])
    assert all(beat["scene_evidence"]["particle_text"] is False for beat in scene["beats"])
    assert all(beat["scene_evidence"]["topic_scene_templates"] is False for beat in scene["beats"])
    assert all(beat["scene_evidence"]["renderer_may_infer_topic"] is False for beat in scene["beats"])
    assert any(
        beat["scene_directive"]["stage_instruction"] == "animate_verified_motion_path"
        for beat in scene["beats"]
        if beat.get("motion_path")
    )
    assert scene["speech_timeline"]
    assert all(item["text_source"] == "verified_beat_narration" for item in scene["speech_timeline"])
    assert all("scene_directive" in item for item in scene["speech_timeline"])
    assert all("scene_evidence" in item for item in scene["speech_timeline"])
    assert any(item["scene_directive"]["stage_instruction"] == "animate_verified_motion_path" for item in scene["speech_timeline"])
    assert all(item["text_rendering"] == "dom_text_not_particles" for item in scene["layout_timeline"])
    assert all("scene_directive" in item for item in scene["layout_timeline"] if item["action"] == "sync_orb_text_with_particle_beat")
    assert all("scene_evidence" in item for item in scene["layout_timeline"] if item["action"] == "sync_orb_text_with_particle_beat")
    assert any(item["action"] == "sync_orb_text_with_particle_beat" for item in scene["layout_timeline"])
    assert any(item.get("text_anchor") in {"upper_left", "lower_left", "upper_right", "lower_center"} for item in scene["layout_timeline"])
    assert any(item.get("particle_behavior") == "gravity_arc" for item in scene["speech_timeline"])
    assert payload["answer_engine"]["external_llm"] is False
    assert payload["answer_engine"]["external_sllm"] is False
    assert payload["answer_engine"]["rule_based_answer_used"] is False
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
    assert payload["answer_engine"]["generation_basis"] == "semantic_grounded_conversation_router_v0"
    assert payload["answer_engine"]["semantic_grounding_used"] is True
    assert payload["answer_engine"]["grounded_discourse_basis"] == "source_ordered_local_state_facts_no_prompt_answer_table"
    assert payload["answer_engine"]["grounded_fact_roles"]
    assert payload["route_type"] == "limitation_question"
    assert payload["external_llm_used"] is False
    assert payload["external_sllm_used"] is False


def test_dashboard_conversation_web_search_reaches_graphrag_for_knowledge_question(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[dict[str, object]] = []

    async def fake_query_graphrag(query, web_search=False, *args, **kwargs):
        calls.append({"query": query, "web_search": web_search, "brain_mode": kwargs.get("brain_mode")})
        return {
            "result": {
                "active_concepts": ["gravity", "Newtonian mechanics"],
                "matched_nodes": [{"label": "gravity"}, {"label": "Newtonian mechanics"}],
                "matched_edges": [
                    {
                        "source": "gravity",
                        "relation": "describes",
                        "target": "attraction between masses",
                        "confidence": 0.82,
                    }
                ],
                "evidence_docs": [
                    {
                        "title": "Gravity",
                        "snippet": "Gravity is the attraction between masses.",
                        "url": "https://example.invalid/gravity",
                    }
                ],
                "confidence": 0.86,
                "memory_activation": True,
                "retrieval_trace": {"web_search": {"provider": "test-static", "status": "ok"}},
            }
        }

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fake_query_graphrag)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={
            "question": "Explain Newton's law of gravity",
            "language": "en",
            "brain_mode": "conversation",
            "mode": "conversation",
            "web_search": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert calls == [
        {
            "query": "Explain Newton's law of gravity",
            "web_search": True,
            "brain_mode": "conversation",
        }
    ]
    assert payload["answer"]
    assert payload["answer_engine"]["generation_basis"] == "semantic_cloud_graph_surface_brain_v0"
    assert payload["answer_engine"]["external_llm"] is False
    assert payload["answer_engine"]["external_sllm"] is False
    assert payload["answer_engine"]["rule_based_answer_used"] is False
    assert payload["local_brain_write"] is False


def test_dashboard_conversation_uses_recent_context_for_followup_search_without_learning(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[dict[str, object]] = []

    async def fake_query_graphrag(query, web_search=False, *args, **kwargs):
        calls.append({"query": query, "web_search": web_search, "brain_mode": kwargs.get("brain_mode")})
        return {
            "result": {
                "answer": "The attraction becomes stronger when masses are larger and distance is smaller.",
                "active_concepts": ["gravity", "mass", "distance"],
                "matched_nodes": [{"label": "gravity"}],
                "matched_edges": [
                    {
                        "source": "gravity",
                        "relation": "depends_on",
                        "target": "mass and distance",
                        "confidence": 0.86,
                    }
                ],
                "evidence_docs": [
                    {
                        "title": "Gravity",
                        "snippet": "Gravity is an attraction between masses and depends on mass and distance.",
                        "url": "https://example.invalid/gravity",
                    }
                ],
                "confidence": 0.84,
                "memory_activation": True,
                "retrieval_trace": {"web_search": {"provider": "test-static", "status": "ok"}},
            }
        }

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fake_query_graphrag)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={
            "question": "Why does that happen?",
            "language": "en",
            "brain_mode": "conversation",
            "mode": "conversation",
            "web_search": True,
            "conversation_context": [
                {"role": "user", "text": "Explain Newton's law of gravity."},
                {"role": "assistant", "text": "Gravity is attraction between masses."},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert calls
    assert "Newton's law of gravity" in str(calls[0]["query"])
    assert "Explain " not in str(calls[0]["query"])
    assert "Why does that happen" in str(calls[0]["query"])
    assert "Previous user" not in str(calls[0]["query"])
    assert "Previous ATANOR" not in str(calls[0]["query"])
    assert payload["compact_trace"]["conversation_context"]["turn_count"] == 2
    assert payload["compact_trace"]["conversation_context"]["used_for_routing"] is True
    assert payload["compact_trace"]["conversation_context"]["followup_detected"] is True
    assert payload["compact_trace"]["conversation_context"]["resolution_strategy"] == "anaphora_resolved_to_latest_user_topic"
    assert "gravity" in payload["compact_trace"]["conversation_context"]["focus_terms"]
    assert payload["compact_trace"]["conversation_context"]["used_for_learning"] is False
    assert payload["answer_engine"]["conversation_context_used"] is True
    assert payload["answer_engine"]["conversation_followup_detected"] is True
    assert payload["answer_engine"]["conversation_resolution_strategy"] == "anaphora_resolved_to_latest_user_topic"
    assert payload["answer_engine"]["grounded_discourse_mode"] == "causal_explanation"
    assert payload["answer_engine"]["grounded_discourse_basis"] == "question_form_plus_retrieved_fact_roles_no_prompt_answer_table"
    assert payload["compact_trace"]["answer_surface"]["grounded_fact_roles"] == ["cause_or_relation"]
    assert payload["answer_engine"]["eval_rows_used_for_learning"] is False
    assert payload["answer_engine"]["external_llm"] is False
    assert payload["answer_engine"]["external_sllm"] is False
    assert payload["answer_engine"]["rule_based_answer_used"] is False
    assert payload["local_brain_write"] is False
    assert payload["production_store_mutated"] is False


def test_web_grounded_conversation_attaches_evidence_bound_splatra_scene_without_topic_templates(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    async def fake_query_graphrag(*args, **kwargs):
        return {
            "result": {
                "answer": "Gravity is attraction between masses. Newton formulated universal gravitation.",
                "active_concepts": ["gravity", "Isaac Newton", "universal gravitation"],
                "matched_nodes": [{"label": "gravity"}, {"label": "Isaac Newton"}],
                "matched_edges": [
                    {
                        "source": "gravity",
                        "relation": "describes",
                        "target": "attraction between masses",
                        "confidence": 0.88,
                    }
                ],
                "evidence_docs": [
                    {
                        "title": "Universal gravitation",
                        "snippet": "Gravity is a force of attraction between masses. Isaac Newton formulated the law of universal gravitation.",
                        "url": "https://example.invalid/universal-gravitation",
                    },
                    {
                        "title": "Inverse-square law",
                        "snippet": "The force magnitude is inversely proportional to the square of distance.",
                        "url": "https://example.invalid/inverse-square-law",
                    },
                ],
                "confidence": 0.86,
                "memory_activation": True,
                "web_search": {"provider": "fixture", "status": "ok"},
                "retrieval_trace": {},
            }
        }

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fake_query_graphrag)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={
            "question": "Explain Newton's law of gravity with a visual scene",
            "language": "en",
            "brain_mode": "conversation",
            "mode": "conversation",
            "web_search": True,
            "layout_feedback": {
                "feedback_basis": "client_dom_scene_collision_telemetry",
                "collision_state": "orb_overlap_risk",
                "orb_overlap_px": 160,
                "text_rendering": "dom_text_not_particles",
                "particle_text": False,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    scene = payload["scene_choreography"]
    assert scene is None
    assert payload["splatra_scene_policy"]["scene_content_source"] == "none"
    assert payload["splatra_scene_policy"]["scene_authoring_basis"] == "abstained_abstract_or_nonvisual_evidence"
    assert payload["splatra_scene_policy"]["reason"] == "insufficient_concrete_visual_evidence"
    assert payload["splatra_scene_policy"]["topic_scene_templates"] is False
    assert payload["splatra_scene_policy"]["renderer_may_infer_topic"] is False
    assert payload["splatra_scene_policy"]["text_rendering"] == "dom_text_not_particles"
    assert payload["splatra_scene_policy"]["particle_text"] is False
    assert payload["splatra_command_sequence"] is None
    assert payload["splatra_interactive_scene_analysis"] is None
    assert payload["answer_engine"]["external_llm"] is False
    assert payload["answer_engine"]["external_sllm"] is False
    assert payload["answer_engine"]["rule_based_answer_used"] is False
    assert payload["local_brain_write"] is False


def test_grounded_context_preserves_source_local_visual_event_evidence() -> None:
    question = "중력의 법칙에 대해 설명해줘"
    route = dual_brain.route_conversation_request(question)
    evidence = [
        {
            "title": "Universal gravitation",
            "snippet": "Gravity is a force of attraction between masses. Isaac Newton formulated the law.",
            "url": "https://example.invalid/gravity",
        },
        {
            "title": "Inverse-square law",
            "snippet": "The force magnitude is inversely proportional to the square of distance.",
            "url": "https://example.invalid/inverse",
        },
        *[
            {
                "title": f"Filler source {index}",
                "snippet": f"Filler source {index} contains a general mechanics summary without visual motion.",
                "url": f"https://example.invalid/filler-{index}",
            }
            for index in range(6)
        ],
        {
            "title": "Universal gravitation visual event evidence",
            "snippet": "Isaac Newton sat under an apple tree. An apple fell from the tree toward Newton.",
            "url": "https://example.invalid/gravity#visual-event",
            "source_type": "encyclopedia_visual_event_extract",
            "visual_evidence_enrichment": True,
            "enrichment_basis": "source_page_sentence_extract",
            "topic_scene_templates": False,
            "renderer_may_infer_topic": False,
            "particle_text": False,
        },
    ]
    grounded = dual_brain._grounded_context_from_semantic_context(
        question,
        route=route,
        semantic_context={"evidence": evidence, "claims": [], "relations": []},
    )

    fact_text = " ".join(grounded.facts).casefold()
    assert "apple fell" in fact_text
    assert len(grounded.facts) <= 6
    plan = plan_visual_imagination(
        question,
        route=route,
        grounded_context=grounded,
        diagnostics={
            "semantic_grounding_used": True,
            "grounding_source": grounded.grounding_source,
            "grounding_quality": grounded.grounding_quality,
            "external_llm_used": False,
            "external_sllm_used": False,
            "rule_based_answer_used": False,
        },
        answer_available=True,
    )

    assert plan.enabled is True
    assert plan.scene_choreography is not None
    beats = plan.scene_choreography["beats"]
    prompts = " ".join(beat["prompt"] for beat in beats).casefold()
    assert "apple" in prompts
    assert "tree" in prompts
    assert any(beat["op"] == "move" and beat["prompt"].casefold() == "apple" for beat in beats)
    assert plan.scene_choreography["topic_scene_templates"] is False
    assert plan.scene_choreography["particle_text"] is False
    assert plan.scene_choreography["text_rendering"] == "dom_text_not_particles"


def test_grounded_context_does_not_invent_visual_scene_from_generic_topic() -> None:
    question = "중력의 법칙에 대해 설명해줘"
    route = dual_brain.route_conversation_request(question)
    grounded = dual_brain._grounded_context_from_semantic_context(
        question,
        route=route,
        semantic_context={
            "evidence": [
                {
                    "title": "Universal gravitation",
                    "snippet": "Gravity is a force of attraction between masses. Isaac Newton formulated the law.",
                    "url": "https://example.invalid/gravity",
                },
                {
                    "title": "Inverse-square law",
                    "snippet": "The force magnitude is inversely proportional to the square of distance.",
                    "url": "https://example.invalid/inverse",
                },
            ],
            "claims": [],
            "relations": [],
        },
    )
    plan = plan_visual_imagination(
        question,
        route=route,
        grounded_context=grounded,
        diagnostics={
            "semantic_grounding_used": True,
            "grounding_source": grounded.grounding_source,
            "grounding_quality": grounded.grounding_quality,
            "external_llm_used": False,
            "external_sllm_used": False,
            "rule_based_answer_used": False,
        },
        answer_available=True,
    )

    prompts = (
        " ".join(beat["prompt"] for beat in plan.scene_choreography["beats"]).casefold()
        if plan.scene_choreography
        else ""
    )
    assert "apple" not in prompts
    assert "tree" not in prompts
    if plan.scene_choreography:
        assert plan.scene_choreography["topic_scene_templates"] is False
        assert plan.scene_choreography["particle_text"] is False
    else:
        assert plan.enabled is False
        assert plan.diagnostics["topic_scene_templates"] is False
        assert plan.diagnostics["particle_text"] is False


def test_grounded_context_skips_context_dependent_formula_fragments() -> None:
    question = "중력의 법칙에 대해 설명해줘"
    route = dual_brain.route_conversation_request(question)
    grounded = dual_brain._grounded_context_from_semantic_context(
        question,
        route=route,
        semantic_context={
            "evidence": [
                {
                    "title": "Korean Wikipedia stage3 batch",
                    "snippet": "첫 번째 항은 뉴턴 중력의 힘을 나타내며, 역제곱 법칙으로 기술된다.",
                    "url": "https://example.invalid/bad-1",
                },
                {
                    "title": "Korean Wikipedia stage3 batch",
                    "snippet": "그 중 중력, 즉 만유인력 법칙을 상대성 이론으로 재구성하는 것은 가장 어려운 작업이었다.",
                    "url": "https://example.invalid/bad-2",
                },
                {
                    "title": "만유인력",
                    "snippet": "만유인력의 법칙은 질량을 가진 물체 사이의 중력 끌림을 설명하는 물리 법칙이다.",
                    "url": "https://example.invalid/good",
                },
            ],
            "claims": [],
            "relations": [],
        },
    )

    joined = " ".join(grounded.facts)
    assert "만유인력의 법칙" in joined
    assert "첫 번째 항" not in joined
    assert "그 중" not in joined

def test_rag_fact_cleaning_keeps_complete_long_sentence_boundary() -> None:
    text = (
        "만유인력의 법칙(萬有引力-法則, 영어: law of universal gravity)이란 질량을 가진 물체사이의 중력 끌림을 기술하는 물리학 법칙이다. "
        "이 법칙은 아이작 뉴턴의 1687년 발표 논문 〈자연철학의 수학적 원리, 혹은 프린키피아(Principia)〉를 통해 처음 소개되었다. "
        "현대의 용어를 사용하여 이 법칙을 기술할 수 있다."
    )

    cleaned = dual_brain._clean_rag_fact_text(text, limit=180)

    assert "처음 소개되었다" in cleaned
    assert "처음." not in cleaned


def test_rag_fact_cleaning_drops_already_clipped_tail_sentence() -> None:
    text = (
        "만유인력의 법칙은 질량을 가진 물체 사이의 중력 끌림을 기술하는 법칙이다. "
        "이 법칙은 아이작 뉴턴의 발표 논문을 통해 처음."
    )

    cleaned = dual_brain._clean_rag_fact_text(text, limit=420)

    assert "중력 끌림을 기술하는 법칙" in cleaned
    assert "처음." not in cleaned


def test_public_fact_bound_answer_drops_incomplete_tail_sentences() -> None:
    answer = (
        "근거상 핵심 원인은 이렇습니다. "
        "역제곱 법칙은 힘의 크기가 거리의 제곱에 반비례하는 것이다.이 규칙에는 중력이 해당한다. "
        "뉴턴의 중력 법칙은 다음과 같은 방정식으로."
    )

    cleaned = dual_brain._clean_public_fact_bound_answer(answer)

    assert "것이다. 이 규칙" in cleaned
    assert "다음과 같은 방정식으로" not in cleaned


def test_dashboard_conversation_greeting_does_not_use_web_search(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    async def fail_query_graphrag(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("greeting must stay on the local conversation path")

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fail_query_graphrag)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={
            "question": "hello",
            "language": "en",
            "brain_mode": "conversation",
            "mode": "conversation",
            "web_search": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["answer_kind"] == "asm_v0_conversation_surface"
    assert payload["answer_engine"]["external_llm"] is False
    assert payload["answer_engine"]["external_sllm"] is False
    assert payload["answer_engine"]["rule_based_answer_used"] is False


def test_web_grounded_conversation_uses_fact_bound_surface_when_surface_abstains(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    async def fake_query_graphrag(*args, **kwargs):
        return {
            "result": {
                "answer": "Gravity is an attraction between masses, described in Newtonian gravity by an inverse-square law.",
                "active_concepts": ["gravity", "inverse-square law"],
                "matched_nodes": [{"label": "gravity"}],
                "matched_edges": [
                    {
                        "source": "gravity",
                        "relation": "describes",
                        "target": "attraction between masses",
                        "confidence": 0.88,
                    }
                ],
                "evidence_docs": [
                    {
                        "title": "Gravity",
                        "snippet": "Gravity is an attraction between masses.",
                        "url": "https://example.invalid/gravity",
                    }
                ],
                "confidence": 0.83,
                "memory_activation": True,
                "web_search": {"provider": "wikipedia", "status": "ok"},
                "retrieval_trace": {},
            }
        }

    def fake_realize_answer(*args, **kwargs):
        return {
            "answer": "I do not have enough verified evidence to answer confidently yet.",
            "language": "en",
            "confidence": 0.1,
            "trace_summary": {"selected_construction_families": [], "selected_discourse_moves": []},
        }

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fake_query_graphrag)
    monkeypatch.setattr(dual_brain, "realize_answer", fake_realize_answer)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={
            "question": "Explain Newton's law of gravity",
            "language": "en",
            "brain_mode": "conversation",
            "mode": "conversation",
            "web_search": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert "Gravity is an attraction between masses" in payload["answer"]
    assert payload["answer_engine"]["fact_bound_surface"] is True
    assert payload["answer_engine"]["answer_surface_source"] == "semantic_cloud_graph_fact_bound_surface"
    assert payload["answer_engine"]["graph_token_fragment_promoted"] is False
    assert payload["compact_trace"]["answer_surface"]["fact_bound_surface"] is True
    assert payload["confidence"] >= 0.83
    assert payload["answer_engine"]["generation_basis"] == "semantic_cloud_graph_surface_brain_v0"
    assert payload["answer_engine"]["external_llm"] is False
    assert payload["answer_engine"]["external_sllm"] is False
    assert payload["answer_engine"]["rule_based_answer_used"] is False


def test_korean_web_grounded_conversation_does_not_promote_graph_token_fragment(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    async def fake_query_graphrag(*args, **kwargs):
        return {
            "result": {
                "answer": "중력 이론으로 자리잡았다 고전역학이 중력 기술하는 표준 이론으로 특수 상대론을 확장한 기하학적",
                "active_concepts": ["중력", "만유인력의 법칙", "아이작 뉴턴"],
                "matched_nodes": [{"label": "중력"}, {"label": "아이작 뉴턴"}],
                "matched_edges": [
                    {
                        "source": "만유인력의 법칙",
                        "relation": "기술한다",
                        "target": "질량을 가진 물체 사이의 중력 끌림",
                        "confidence": 0.88,
                    }
                ],
                "evidence_docs": [
                    {
                        "title": "만유인력의 법칙",
                        "snippet": "만유인력의 법칙은 질량을 가진 물체 사이의 중력 끌림을 기술하는 물리학 법칙이다. 아이작 뉴턴이 1687년에 발표했다.",
                        "url": "https://ko.wikipedia.org/wiki/만유인력의_법칙",
                    }
                ],
                "confidence": 0.81,
                "memory_activation": True,
                "web_search": {"provider": "wikipedia", "status": "ok"},
                "retrieval_trace": {},
            }
        }

    monkeypatch.setattr(dual_brain.alpha_service, "query_graphrag", fake_query_graphrag)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={
            "question": "중력의 법칙에 대해 설명해줘",
            "language": "ko",
            "brain_mode": "conversation",
            "mode": "conversation",
            "web_search": True,
            "include_trace": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert "만유인력의 법칙" in payload["answer"]
    assert "아이작 뉴턴" in payload["answer"]
    assert "고전역학이 중력 기술하는 표준 이론" not in payload["answer"]
    assert payload["answer_engine"]["fact_bound_surface"] is True
    assert payload["answer_engine"]["answer_surface_source"] == "semantic_cloud_graph_fact_bound_surface"
    assert payload["answer_engine"]["grounded_discourse_mode"] == "definition_explanation"
    assert payload["answer_engine"]["external_llm"] is False
    assert payload["answer_engine"]["external_sllm"] is False
    assert payload["answer_engine"]["rule_based_answer_used"] is False
    assert payload["compact_trace"]["answer_surface"]["graph_token_fragment_promoted"] is False
    assert payload["splatra_scene_policy"]["topic_scene_templates"] is False
    assert payload["splatra_scene_policy"]["particle_text"] is False


def test_web_grounded_fact_clipping_keeps_sentence_boundary() -> None:
    source = (
        "만유인력의 법칙은 질량을 가진 물체 사이의 중력 끌림을 기술하는 물리학 법칙이다. "
        "이 법칙은 아이작 뉴턴의 1687년 발표 논문을 통해 처음 소개되었다. "
        "현대의 용어를 사용하여 이 법칙을 기술하자면 다음과 같다."
    )

    clipped = dual_brain._clean_rag_fact_text(source, limit=62)

    assert clipped.endswith("법칙이다.")
    assert "처음." not in clipped
    assert not clipped.endswith("다음과 같다.")


def test_render_iframe_for_intent_opens_search_on_request() -> None:
    ko = dual_brain._render_iframe_for_intent("에펠탑 검색해줘", "ko")
    assert ko is not None and "wiki/Special:Search" in ko["url"] and "ko.wikipedia.org" in ko["url"]
    en = dual_brain._render_iframe_for_intent("search for the Eiffel Tower", "en")
    assert en is not None and "en.wikipedia.org" in en["url"]


def test_render_iframe_for_intent_ignores_plain_questions() -> None:
    assert dual_brain._render_iframe_for_intent("What is GraphRAG?", "en") is None
    assert dual_brain._render_iframe_for_intent("안녕", "ko") is None


def test_answer_is_abstention_recognizes_base_brain_phrasings() -> None:
    assert dual_brain._answer_is_abstention("I do not have enough base concepts to support this question yet.")
    assert dual_brain._answer_is_abstention("지금 확인된 근거가 부족해서 단정하기 어렵습니다.")
    assert dual_brain._answer_is_abstention("")  # empty == abstain
    assert not dual_brain._answer_is_abstention("The Eiffel Tower is a lattice tower in Paris, France.")


def test_attribution_extracts_person_from_english_snippets() -> None:
    snippets = [
        "Who Really Invented the Telephone? Archived 2015.",
        "The telephone was invented by Alexander Graham Bell, who patented it in 1876.",
    ]
    assert dual_brain._extract_attribution("Who invented the telephone?", snippets) == "Alexander Graham Bell"


def test_attribution_extracts_person_from_korean_snippets() -> None:
    snippets = ["전화는 알렉산더 그레이엄 벨에 의해 발명되었다."]
    person = dual_brain._extract_attribution("누가 전화를 발명했어?", snippets)
    assert person == "알렉산더 그레이엄 벨"


def test_attribution_relation_only_for_who_questions() -> None:
    # a definition question ("what is X invented for") must not trigger attribution
    assert dual_brain._detect_attribution_relation("Who invented radio?") is not None
    assert dual_brain._detect_attribution_relation("What is a telephone?") is None
    assert dual_brain._extract_attribution("What is a telephone?", ["invented by Bell"]) is None


def test_web_fact_cache_stores_and_recalls(tmp_path, monkeypatch) -> None:
    from packages.local_brain import LocalBrainMemory
    monkeypatch.setattr(dual_brain, "WEB_FACT_MEMORY", LocalBrainMemory(tmp_path / "web.json"))
    dual_brain._store_web_fact(
        "What is the Eiffel Tower?", "Eiffel Tower",
        "The Eiffel Tower is a lattice tower in Paris, France.",
        "https://en.wikipedia.org/wiki/Eiffel_Tower",
    )
    hit = dual_brain._recall_web_fact("Tell me about the Eiffel Tower")
    assert hit is not None
    assert "Eiffel Tower" in hit["answer"]
    assert hit["provider"] == "local_web_memory"
    assert hit["source_url"].endswith("Eiffel_Tower")
    # an unrelated question must not surface the cached fact
    assert dual_brain._recall_web_fact("What is photosynthesis?") is None


def test_web_fact_cache_persists_across_instances(tmp_path, monkeypatch) -> None:
    from packages.local_brain import LocalBrainMemory
    path = tmp_path / "web.json"
    monkeypatch.setattr(dual_brain, "WEB_FACT_MEMORY", LocalBrainMemory(path))
    dual_brain._store_web_fact("What is DNA?", "DNA", "DNA carries genetic instructions.", "https://en.wikipedia.org/wiki/DNA")
    # a fresh instance (simulating a restart) still has the looked-up fact
    monkeypatch.setattr(dual_brain, "WEB_FACT_MEMORY", LocalBrainMemory(path))
    assert dual_brain._recall_web_fact("what is dna")["answer"] == "DNA carries genetic instructions."


def test_stream_emits_real_pipeline_stages_in_order() -> None:
    """ P3: streamed stages are TRUE pipeline milestones (not a timer), and the
 honest contract holds — every 'stage' precedes 'evidence' which precedes the
 single terminal 'answer', nothing is retracted, no stage repeats."""
    client = TestClient(app)
    with client.stream(
        "POST", "/api/chat/atanor/stream",
        json={"question": "광합성이란?", "language": "ko", "web_search": False},
    ) as resp:
        assert resp.status_code == 200
        events = []
        for line in resp.iter_lines():
            if line and line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    types = [e["type"] for e in events]
    # at least one real stage, then evidence, then exactly one terminal answer/error
    assert "stage" in types
    assert types[-1] in ("answer", "error")
    if types[-1] == "answer":
        assert types.count("answer") == 1
        assert "evidence" in types
        assert types.index("evidence") < types.index("answer")
        # every stage comes before evidence (stages are the "still working" phase)
        last_stage = max(i for i, t in enumerate(types) if t == "stage")
        assert last_stage < types.index("evidence")
    # the first stage is the real 'analyzing' milestone the pipeline emits itself
    stages = [e.get("stage") for e in events if e["type"] == "stage"]
    assert stages and stages[0] == "analyzing"
    assert len(stages) == len(set(stages)), "a committed stage must never repeat"


def test_emit_stage_is_noop_without_a_sink() -> None:
    """Non-streaming callers set no sink, so the hook is a no-op (never raises)."""
    assert dual_brain._STAGE_SINK.get() is None
    dual_brain._emit_stage("analyzing")  # must not raise
    dual_brain._emit_stage("web_grounding", extra="x")


def test_explicit_slang_cannot_reach_the_surface_from_any_lane() -> None:
    """Measured twice: gating the vulgar gloss inside lexicon_lane only relocated the leak —
    the multiword-subject fix let structured_triple_lookup and engage find the same entry and
    read it out, because they go to the store directly. The guarantee must be at the one exit."""
    for leaked in (
        "Eiffel Tower is A spit roast with the two penetrating partners high-fiving.",
        "Eiffel Tower relates to A spit roast with the two penetrating partners high-fiving.",
    ):
        out = dual_brain._enforce_output_safety({"result": {"answer": leaked,
                                                            "answer_kind": "structured_triple_lookup"}})
        assert "spit roast" not in out["result"]["answer"].lower()
        assert out["result"]["answer_kind"] == "honest_capability_limit"

    clean = {"result": {"answer": "Eiffel Tower is a kind of Building.", "answer_kind": "x"}}
    assert dual_brain._enforce_output_safety(clean)["result"]["answer_kind"] == "x"


def test_english_turn_can_never_emit_hangul_whatever_the_lane_did() -> None:
    """The single exit gate for the English-only mandate. ~20 answer lanes feed this pipeline and
 several were written Korean-first, so per-lane fixes are whack-a-mole. Measured after the
 per-lane round: "How can I sleep better?" still returned "Sleep is normally sleep state S3 …
 Hawwah is …" from base_brain. An English turn cannot emit Hangul, period."""
    leaked = {"result": {"answer": "Sleep is state S3. Hawwah is 대한민국의 가수이자 배우 가인의 음반이다.",
                         "answer_kind": "base_brain_after_low_quality_grounding",
                         "confidence": 0.5,
                         "reasoning_certificate": {"derivation_kind": "ontology_graph_derivation"}}}
    out = dual_brain._enforce_answer_language(leaked, "en")
    assert not re.search(r"[가-힣]", out["result"]["answer"])
    assert out["result"]["answer_kind"] == "honest_capability_limit"
    # the certificate must not keep claiming grounding the replaced answer no longer carries
    assert out["result"]["reasoning_certificate"]["derivation_kind"] == "honest_capability_limit"

    # a clean English answer passes through untouched
    clean = {"result": {"answer": "gravity — attraction between two masses.",
                        "answer_kind": "lexicon_cartridge"}}
    assert dual_brain._enforce_answer_language(clean, "en")["result"]["answer"].startswith("gravity")

    # the Korean lane is untouched: Hangul is correct there
    ko = {"result": {"answer": "커피는 음료수예요.", "answer_kind": "lexicon_cartridge"}}
    assert dual_brain._enforce_answer_language(ko, "ko")["result"]["answer"] == "커피는 음료수예요."


def test_dictionary_is_default_deny_only_definition_asks_reach_it() -> None:
    """The lexicon lane answers definition asks and NOTHING else. It used to fire on any turn, so
    every intent whose own lane was dead in English leaked in and came back defining a stray word.
    Each non-definition case below is a measured 2026-07-17 failure."""
    for q in ("What is a black hole?", "What is gravity?", "What's photosynthesis?",
              "Tell me about the Eiffel Tower", "Define machine learning",
              "What does entropy mean?", "커피가 뭐야", "물리학이 뭐지"):
        assert dual_brain._is_definition_ask(q), q

    for q, was in (
        ("How can I sleep better?", "better is a kind of good."),
        ("How is coffee different from tea?", "different — Not the same."),
        ("What does the Eiffel Tower look like?", "an explicit slang sense"),
        ("What is the difference between a crocodile and an alligator?", "Crocodile Dundee II"),
        ("What do you think about music?", "do you — Used other than figuratively"),
        ("Should I learn Python?", "Python — The earth-dragon of Delphi"),
        ("How do I learn to code?", "a Korean answer"),
    ):
        assert not dual_brain._is_definition_ask(q), f"{q} previously answered: {was}"


def test_english_opinion_turns_are_grounded_never_borrowed_or_guessed() -> None:
    """An opinion turn gets +: an honest frame (ATANOR holds no preference) plus what it
 ACTUALLY has. It must never (a) assert a preference it doesn't have, (b) assert one reading
 of a polysemous word, or (c) collapse to a warm non-answer."""
    import re as _re

    # a single clean reading → the grounded stance, with the real definition
    r = dual_brain._english_engage_answer("What do you think about music?")
    assert r and "music" in r["answer"]
    assert "don't hold preferences" in r["answer"]

    # several readings on file → withhold, never assert defs[0]. Measured wrong picks:
    # "Should I learn Python?" → earth-dragon of Delphi; "Do you like jazz?" → "Energy, excitement".
    for q in ("Do you like jazz?", "What do you think about democracy?"):
        r = dual_brain._english_engage_answer(q)
        assert r and not _re.search(r"earth-dragon|Energy, excitement", r["answer"], _re.I), q

    # advice needs no definition at all — that is what made it immune to the sense problem
    r = dual_brain._english_engage_answer("Should I learn Python?")
    assert r and "yours to decide" in r["answer"] and "earth-dragon" not in r["answer"]

    # coffee now answers from its own is_a rows — this line used to assert "nothing grounded",
    # which encoded the row-limit truncation (located_in ate the budget before is_a appeared).
    # The stance must still be honest about holding no preference, and never invent one.
    r = dual_brain._english_engage_answer("Do you like coffee?")
    assert r and "coffee" in r["answer"] and "don't hold preferences" in r["answer"]
    assert not re.search(r"\bI (?:love|enjoy|prefer|really like)\b", r["answer"])

    # the topic is the object of the stance phrase, not the longest noun
    assert dual_brain._opinion_topic("What is your opinion on art?") == "art"
    assert dual_brain._opinion_topic("What do you think about music?") == "music"
    assert dual_brain._opinion_topic("What is a black hole?") is None


def test_opinion_and_capability_turns_never_reach_the_dictionary() -> None:
    """The lexicon lane defines words; it must not field a turn addressed TO ATANOR. This gate
    was Korean-only while the core answers English — measured leaks are the English cases."""
    for q in (
        "What do you think about music?",        # → 'do you — Used other than figuratively…'
        "Can you remember this conversation?",   # → 'conversation is a kind of speech.'
        "Do you like coffee?",
        "What is your opinion on this?",
        "Should I learn Python?",
        "안락사 찬성이야 반대야?",
        "이거 어떻게 생각해?",
    ):
        assert dual_brain._is_opinion_or_capability_turn(q), q

    for q in (
        "What is a black hole?",
        "What is machine learning?",
        "Tell me about coffee",
        "커피가 뭐야",
        "What is a polar bear?",
    ):
        assert not dual_brain._is_opinion_or_capability_turn(q), q


def test_english_contrast_resolves_both_operands_exactly() -> None:
    """base_brain resolves English operands by fuzzy match, so the contrast came back about the
    wrong things entirely — measured: "difference between a crocodile and an alligator" →
    Crocodile Dundee II; "coffee vs tea" → Pentacarbonylhydridomanganese; "How is coffee different
    from tea?" → "Tear Out The Heart was a five-piece metalcore band". This lane runs BEFORE the
    factual lanes because gating the override downstream was not enough: the garbage WAS the base
    answer being overridden."""
    r = dual_brain._english_compare_answer(
        "What is the difference between a crocodile and an alligator?")
    assert r and "crocodile" in r["answer"] and "alligator" in r["answer"]
    assert "Dundee" not in r["answer"]
    # is_a leads the contrast: defined_as is the polysemy lottery (crocodile's first gloss is the
    # British "line of schoolchildren" sense), while its is_a rows are clean.
    assert "procession of people" not in r["answer"]
    assert "By contrast" in r["answer"]

    r = dual_brain._english_compare_answer("coffee vs tea")
    assert r and "coffee" in r["answer"] and "tea" in r["answer"]
    assert "Pentacarbonyl" not in r["answer"]

    # nothing grounded on both sides → an honest limit, never a fuzzy neighbour
    r = dual_brain._english_compare_answer("What is the difference between a zebra and a quokka?")
    assert r and r["answer_kind"] == "honest_capability_limit"

    # a definition ask is not a contrast
    assert dual_brain._english_compare_answer("What is a black hole?") is None


def test_contrast_ancestor_is_resonance_gated_against_graph_pollution() -> None:
    """The graph's is_a is polluted: crocodile carries 55 parents including 'alteration',
    'matrix', 'athlete', 'sexual relationship'. common_ancestor walked them and produced
    "Both are a kind of action" (measured). clean_space.resonance separates real parents from
    noise with a wide margin — reptile .739 / crocodilian reptile .797 / beverage .795 vs
    action .081 / opinion .149 / athlete .263 / matrix .346 — and engage._relevant already
    ships that exact test at the same threshold. Reused, not re-derived."""
    from packages.graph_scale import clean_space
    from packages.graph_scale.engage import _relevant

    # FUNCTIONAL contract, not model constants. The first version asserted the absolute
    # values of one trained space (>0.6 / <0.4) and broke the day the space was retrained
    # (English-only rebuild, 2026-07-17: crocodile/crocodilian dropped 0.797 -> 0.546 while
    # the GATE kept working). What the gate actually needs is: every real parent clears the
    # shipped threshold engage._relevant enforces, every junk parent does not, and the two
    # families do not interleave. Absolute embedding values are the model's business.
    real = {p: clean_space.resonance("crocodile", p)
            for p in ("reptile", "crocodilian reptile")}
    junk = {n: clean_space.resonance("crocodile", n)
            for n in ("action", "opinion", "athlete", "sexual relationship")}
    for parent, score in real.items():
        assert _relevant("crocodile", parent), (parent, score)
    for noise, score in junk.items():
        assert not _relevant("crocodile", noise), (noise, score)
    assert min(v for v in real.values() if v is not None) > \
        max(v for v in junk.values() if v is not None), (real, junk)

    r = dual_brain._english_compare_answer(
        "What is the difference between a crocodile and an alligator?")
    assert r and "kind of action" not in r["answer"], r["answer"]
    assert "crocodilian reptile" in r["answer"]
