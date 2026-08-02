from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app
from knowledge_bakery import build_memory
from rag_engine import query_graphrag


def test_seed_runtime_trace_endpoint_is_read_only_and_honest(monkeypatch) -> None:
    monkeypatch.delenv("ATANOR_LOCAL_BRAIN_INITIALIZED", raising=False)
    client = TestClient(app)

    response = client.get("/api/seed-research/runtime-trace", params={"q": "Evidence Claim"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["local_graph_state"]["local_brain_initialized"] is False
    assert payload["local_graph_state"]["local_total_nodes"] == 0
    assert payload["local_graph_state"]["local_total_edges"] == 0
    assert payload["local_graph_state"]["seed_written_to_local_brain"] is False
    assert payload["local_graph_state"]["seed_counted_as_learned_memory"] is False
    assert payload["seed_anchor_trace"]["final_answer_generation_claimed"] is False
    assert payload["seed_anchor_trace"]["external_llm_used"] is False
    assert payload["seed_anchor_trace"]["external_sllm_used"] is False
    assert payload["seed_anchor_trace"]["rule_based_answer_engine"] is False
    assert payload["cloud_alignment_trace"]["candidate_fragments_checked"] >= 0
    assert payload["cloud_alignment_trace"]["fragments_aligned_to_seed"] >= 0


def test_seed_anchor_is_added_to_graphrag_retrieval_trace(tmp_path) -> None:
    cleaned = tmp_path / "cleaned"
    ontology = tmp_path / "ontology"
    cleaned.mkdir()
    ontology.mkdir()
    (cleaned / "doc.txt").write_text("GraphRAG uses KnowledgeGraph for Evidence.", encoding="utf-8")
    (ontology / "nodes.json").write_text(json.dumps([{"id": "graphrag", "label": "GraphRAG"}]), encoding="utf-8")
    (ontology / "edges.json").write_text(json.dumps([{"source": "graphrag", "relation": "uses", "target": "evidence"}]), encoding="utf-8")
    memory = cleaned.parent / "memory"
    build_memory(str(cleaned), str(ontology), str(memory))

    result = query_graphrag("GraphRAG evidence", str(cleaned), str(ontology), str(memory))

    seed_anchor = result["retrieval_trace"]["seed_anchor"]
    assert seed_anchor["enabled"] is True
    assert "matched_concepts" in seed_anchor
    assert "matched_edges" in seed_anchor
    assert seed_anchor["final_answer_generation_claimed"] is False
    assert seed_anchor["external_llm_used"] is False
    assert seed_anchor["external_sllm_used"] is False
    assert seed_anchor["rule_based_answer_engine"] is False
