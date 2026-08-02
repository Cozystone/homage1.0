from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services import web_search as web_search_module
from app.services.web_search import _normalize_lookup_query, is_fresh_search_query, is_knowledge_lookup_query


def test_korean_lookup_query_normalization_keeps_core_terms() -> None:
    assert _normalize_lookup_query("\uC911\uB825\uC758 \uBC95\uCE59\uC5D0 \uB300\uD574 \uC124\uBA85\uD574\uC918") == "\uC911\uB825 \uBC95\uCE59"


def test_korean_followup_why_query_still_uses_knowledge_lookup() -> None:
    assert is_knowledge_lookup_query("중력의 법칙 왜 그런가요")
    assert is_knowledge_lookup_query("중력은 어떻게 작동하나요")
    assert _normalize_lookup_query("중력의 법칙 그건 왜 그런가요") == "중력 법칙"


def test_visual_event_extraction_uses_source_sentences_only() -> None:
    source_text = (
        "Universal gravitation is a physical law. "
        "Isaac Newton sat under an apple tree. "
        "An apple fell from the tree toward Newton."
    )

    sentences = web_search_module.extract_visual_event_sentences(source_text)

    assert any("apple tree" in sentence for sentence in sentences)
    assert any("fell from the tree" in sentence for sentence in sentences)


def test_visual_event_extraction_does_not_invent_topic_scene() -> None:
    source_text = "Universal gravitation describes attraction between masses and is proportional to mass."

    assert web_search_module.extract_visual_event_sentences(source_text) == []


def test_wikipedia_visual_event_enrichment_marks_source_local_particle_metadata(monkeypatch) -> None:
    base_results = [
        {
            "id": "wikipedia-1",
            "title": "Universal gravitation",
            "url": "https://ko.wikipedia.org/wiki/Universal_gravitation",
            "snippet": "Universal gravitation describes attraction between masses.",
            "provider": "wikipedia",
            "source_type": "encyclopedia_search",
            "search_score": 103,
            "query_terms_matched": 2,
            "normalized_query": "gravity law",
        }
    ]
    monkeypatch.setattr(
        web_search_module,
        "_wikipedia_extract_for_page",
        lambda title: "Isaac Newton sat under an apple tree. An apple fell from the tree toward Newton.",
    )

    enriched = web_search_module._wikipedia_visual_event_results(base_results, limit=1)
    evidence = web_search_module.web_results_to_evidence(enriched)

    assert len(enriched) == 1
    assert enriched[0]["visual_evidence_enrichment"] is True
    assert enriched[0]["topic_scene_templates"] is False
    assert enriched[0]["renderer_may_infer_topic"] is False
    assert enriched[0]["particle_text"] is False
    assert "apple tree" in enriched[0]["snippet"]
    assert evidence[0]["source_type"] == "encyclopedia_visual_event_extract"
    assert evidence[0]["visual_evidence_enrichment"] is True
    assert evidence[0]["topic_scene_templates"] is False
    assert evidence[0]["particle_text"] is False


def test_alpha_endpoints_smoke(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cleaned = tmp_path / "data" / "cleaned"
    cleaned.mkdir(parents=True)
    (cleaned / "doc1.txt").write_text(
        "# GraphRAG\nGraphRAG uses KnowledgeGraph. Evidence reduces HallucinationRisk. Guardrail requires Evidence.",
        encoding="utf-8",
    )
    (cleaned / "atanor_internal.txt").write_text(
        "ATANOR Ghost Shell is the lightweight SHA-256 topology map. Payload Vault stores private raw payloads locally with SQLite WAL. Working Memory temporarily fuses Local Brain and Cloud Brain fragments.",
        encoding="utf-8",
    )
    client = TestClient(app)

    ontology = client.post("/api/ontology/run")
    assert ontology.status_code == 200
    assert ontology.json()["node_count"] > 0

    graph = client.get("/api/ontology/graph")
    assert graph.status_code == 200
    assert graph.json()["nodes"]

    memory = client.get("/api/memory/status")
    assert memory.status_code == 200
    assert memory.json()["state"] == "completed"
    assert memory.json()["transition_count"] > 0
    assert memory.json()["phrase_count"] > 0

    memory_graph = client.get("/api/memory/graph?limit=80")
    assert memory_graph.status_code == 200
    assert memory_graph.json()["nodes"]

    memory_activation = client.post("/api/memory/activate", json={"query": "GraphRAG evidence", "max_nodes": 16})
    assert memory_activation.status_code == 200
    assert memory_activation.json()["active_nodes"]

    drift = client.get("/api/memory/drift-check")
    assert drift.status_code == 200
    assert drift.json()["constraints"]["external_llm"] is False

    rag = client.post("/api/graphrag/query", json={"query": "GraphRAG evidence"})
    assert rag.status_code == 200
    assert rag.json()["result"]["evidence_docs"]
    assert rag.json()["result"]["answer"]
    assert rag.json()["result"]["citations"]
    assert rag.json()["result"]["method"] == "atanor-graph-token-rag-v1"
    assert rag.json()["result"]["answer_kind"] == "native_graph_token_generation"
    assert rag.json()["result"]["answer_engine"]["external_llm"] is False
    assert rag.json()["result"]["answer_engine"]["prediction_basis"] == "token_transition_edge_cooccurrence_graph_path"
    assert rag.json()["result"]["answer_engine"]["network_barrier"] == "sealed_for_generation"
    assert rag.json()["result"]["memory_activation"]["active_nodes"]

    web_rag = client.post("/api/graphrag/query", json={"query": "Grounding with Bing architecture", "web_search": True})
    assert web_rag.status_code == 200
    web_result = web_rag.json()["result"]
    assert web_result["method"] == "atanor-graph-token-web-rag-v1"
    assert web_result["web_search"]["provider"] == "static"
    assert web_result["evidence_docs"]
    assert web_result["answer_kind"] == "native_graph_token_generation"
    assert web_result["answer_engine"]["external_llm"] is False
    assert web_result["answer_engine"]["prediction_basis"] == "token_transition_edge_cooccurrence_graph_path"
    assert web_result["answer_engine"]["cloud_fragment_role"] == "evidence_only"

    fresh_query = "\uC624\uB298 \uB274\uC2A4 \uC54C\uB824\uC918"
    assert is_fresh_search_query(fresh_query)
    fresh_rag = client.post("/api/graphrag/query", json={"query": fresh_query})
    assert fresh_rag.status_code == 200
    fresh_result = fresh_rag.json()["result"]
    assert fresh_result["method"] == "atanor-graph-token-web-rag-v1"
    assert "raw_no_node::" not in fresh_result["answer"]
    assert fresh_result["web_search"]["provider"] in {"news-rss", "static"}
    assert fresh_result["answer_engine"]["external_llm"] is False

    person_query = "\uC720\uC7AC\uC11D\uC774 \uB204\uAD6C\uC57C"
    assert is_knowledge_lookup_query(person_query)

    def fake_wikipedia_search(query: str, count: int = 5) -> list[dict]:
        return [
            {
                "id": "wikipedia-1",
                "title": "\uC720\uC7AC\uC11D",
                "url": "https://ko.wikipedia.org/wiki/%EC%9C%A0%EC%9E%AC%EC%84%9D",
                "snippet": "\uC720\uC7AC\uC11D\uC740 \uB300\uD55C\uBBFC\uAD6D\uC758 \uBC29\uC1A1\uC778\uC774\uC790 MC\uC774\uB2E4.",
                "provider": "wikipedia",
                "source_type": "encyclopedia_search",
                "license_status": "reference_only",
                "search_score": 5,
            }
        ]

    monkeypatch.setattr(web_search_module, "wikipedia_search", fake_wikipedia_search)
    person_rag = client.post("/api/graphrag/query", json={"query": person_query})
    assert person_rag.status_code == 200
    person_result = person_rag.json()["result"]
    assert person_result["method"] == "atanor-graph-token-web-rag-v1"
    assert person_result["web_search"]["provider"] == "wikipedia"
    assert person_result["answer_kind"] == "native_graph_token_generation"
    assert "provider" not in person_result["answer"]
    assert person_result["answer_engine"]["external_llm"] is False

    greeting = client.post("/api/graphrag/query", json={"query": "hello"})
    assert greeting.status_code == 200
    greeting_result = greeting.json()["result"]
    assert greeting_result["method"] in {"atanor-research-no-evidence-v1", "atanor-graph-token-rag-v1", "atanor-graph-token-web-rag-v1"}
    assert greeting_result["answer_kind"] == "native_graph_token_generation"
    assert greeting_result["answer_engine"]["surface_generation"] == "native_graph_token_generation"
    assert "ATANOR online" not in greeting_result["answer"]

    greeting_with_search_toggle = client.post("/api/graphrag/query", json={"query": "hello", "web_search": True})
    assert greeting_with_search_toggle.status_code == 200
    greeting_with_search_result = greeting_with_search_toggle.json()["result"]
    assert greeting_with_search_result["answer_kind"] == "native_graph_token_generation"
    assert greeting_with_search_result["answer_engine"]["surface_generation"] == "native_graph_token_generation"

    inventory = client.post("/api/graphrag/query", json={"query": "show all nodes"})
    assert inventory.status_code == 200
    inventory_result = inventory.json()["result"]
    assert inventory_result["method"] in {"atanor-research-no-evidence-v1", "atanor-graph-token-rag-v1"}
    assert inventory_result["method"] != "atanor-graph-token-web-rag-v1"
    assert inventory_result["answer_engine"]["external_llm"] is False
    assert inventory_result["answer_kind"] == "native_graph_token_generation"

    legend = client.post("/api/graphrag/query", json={"query": "color legend"})
    assert legend.status_code == 200
    legend_result = legend.json()["result"]
    assert legend_result["method"] in {"atanor-research-no-evidence-v1", "atanor-graph-token-rag-v1"}
    assert legend_result["method"] != "atanor-graph-token-web-rag-v1"
    assert legend_result["answer_engine"]["external_llm"] is False
    assert legend_result["answer_kind"] == "native_graph_token_generation"
    assert "graph colors indicate" not in legend_result["answer"]

    ghost_shell = client.post("/api/graphrag/query", json={"query": "What is Ghost Shell?"})
    assert ghost_shell.status_code == 200
    ghost_shell_result = ghost_shell.json()["result"]
    assert ghost_shell_result["method"] in {"atanor-research-no-evidence-v1", "atanor-graph-token-rag-v1"}
    assert ghost_shell_result["method"] != "atanor-graph-token-web-rag-v1"
    assert "web_search" not in ghost_shell_result
    assert ghost_shell_result["answer_engine"]["external_llm"] is False

    local_mode = client.post("/api/graphrag/query", json={"query": "유재석이 누구야", "brain_mode": "local", "web_search": True})
    assert local_mode.status_code == 200
    local_result = local_mode.json()["result"]
    assert local_result["brain_mode"] == "local"
    assert local_result["cloud_weight"] == 0
    assert local_result["route_state"] == "local_private_route"
    assert "web_search" not in local_result

    cloud_mode = client.post("/api/graphrag/query", json={"query": "유재석이 누구야", "brain_mode": "cloud"})
    assert cloud_mode.status_code == 200
    cloud_result = cloud_mode.json()["result"]
    assert cloud_result["brain_mode"] == "cloud"
    assert cloud_result["local_weight"] == 0
    assert cloud_result["cloud_state"] in {"connected", "stub"}

    unified_mode = client.post("/api/graphrag/query", json={"query": "What is Ghost Shell?", "brain_mode": "unified"})
    assert unified_mode.status_code == 200
    unified_result = unified_mode.json()["result"]
    assert unified_result["brain_mode"] == "unified"
    assert "working_memory_active" in unified_result

    legacy_alias = client.post("/api/graphrag/query", json={"query": "What is Ghost Shell?", "brain_mode": "dual"})
    assert legacy_alias.status_code == 200
    alias_result = legacy_alias.json()["result"]
    assert alias_result["brain_mode"] == "unified"
    alias_surface = json.dumps(alias_result, ensure_ascii=False)
    assert "Dual Graph" not in alias_surface
    assert "dual_graph" not in alias_surface

    guard = client.post("/api/guard/check", json={"draft_answer": "GraphRAG always guarantees perfect answers."})
    assert guard.status_code == 200
    assert guard.json()["overall_guard_score"] < 100

    oven = client.post("/api/oven/dry-run")
    assert oven.status_code == 200
    assert oven.json()["last_loss"] > 0

    gpu = client.get("/api/telemetry/gpu")
    assert gpu.status_code == 200
    assert "available" in gpu.json()

    pipeline = client.get("/api/pipeline/status")
    assert pipeline.status_code == 200
    assert len(pipeline.json()["stages"]) == 8
