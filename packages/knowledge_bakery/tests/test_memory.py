from __future__ import annotations

from pathlib import Path

from knowledge_bakery import activate_memory, build_memory, drift_check, export_graph, memory_status


def test_build_memory_creates_local_transition_graph(tmp_path: Path) -> None:
    cleaned = tmp_path / "data" / "cleaned"
    ontology = tmp_path / "data" / "ontology"
    memory = tmp_path / "data" / "memory"
    cleaned.mkdir(parents=True)
    ontology.mkdir(parents=True)
    (cleaned / "doc.txt").write_text(
        "GraphRAG uses evidence. Evidence reduces hallucination risk. "
        "Guardrail verifies evidence and builds a local memory graph.",
        encoding="utf-8",
    )
    (ontology / "nodes.json").write_text(
        '[{"id":"graphrag","label":"GraphRAG","type":"concept","count":1,"confidence":0.8,"evidence_doc_ids":["doc"]}]',
        encoding="utf-8",
    )
    (ontology / "edges.json").write_text(
        '[{"source":"graphrag","relation":"uses","target":"evidence","confidence":0.8,"evidence_doc_ids":["doc"]}]',
        encoding="utf-8",
    )

    result = build_memory(str(cleaned), str(ontology), str(memory))

    assert result["state"] == "completed"
    assert result["llm_policy"]["external_llm"] is False
    assert result["llm_policy"]["local_quantized_llm"] is False
    assert result["llm_policy"]["pretrained_generation_weights"] is False
    assert result["node_count"] >= 8
    assert result["transition_count"] > 0
    assert result["phrase_count"] > 0
    assert (memory / "homage.db").exists()
    assert (memory / "events.jsonl").exists()

    status = memory_status(str(memory))
    assert status["vector_count"] == status["node_count"]
    assert status["vector_source"] == "local_relation_projection_v1"

    graph = export_graph(str(memory), limit=40)
    assert graph["nodes"]
    assert graph["edges"]
    assert graph["source"] == "ghost_topology_control_plane"
    assert graph["nodes"][0]["projection_source"] == "ghost_shell_content_addressed_v1"
    assert graph["nodes"][0]["type"] == "ghost_hash"
    assert "node_hash" in graph["nodes"][0]

    activation = activate_memory("GraphRAG evidence", str(memory), max_nodes=16, max_depth=3)
    assert activation["state"] == "completed"
    assert activation["active_nodes"]
    assert activation["activation_policy"]["external_llm"] is False
    assert activation["activation_policy"]["local_quantized_llm"] is False
    assert activation["drift_report"]["state"] in {"passed", "warning"}

    report = drift_check(str(memory))
    assert report["constraints"]["external_llm"] is False
    assert "missing_token_transition_graph" not in report["violations"]
