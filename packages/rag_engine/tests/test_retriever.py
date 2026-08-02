import json

from knowledge_bakery import build_memory
from rag_engine import query_graphrag


def _build_query_memory(cleaned, ontology):
    memory = cleaned.parent / "memory"
    build_memory(str(cleaned), str(ontology), str(memory))
    return str(memory)


def test_query_graphrag_matches_docs_and_graph(tmp_path):
    cleaned = tmp_path / "cleaned"
    ontology = tmp_path / "ontology"
    cleaned.mkdir()
    ontology.mkdir()
    (cleaned / "doc.txt").write_text("GraphRAG uses KnowledgeGraph for Evidence.", encoding="utf-8")
    (ontology / "nodes.json").write_text(json.dumps([{"id": "graphrag", "label": "GraphRAG"}]), encoding="utf-8")
    (ontology / "edges.json").write_text(json.dumps([{"source": "graphrag", "relation": "uses", "target": "knowledgegraph"}]), encoding="utf-8")

    memory = _build_query_memory(cleaned, ontology)
    result = query_graphrag("GraphRAG evidence", str(cleaned), str(ontology), memory)

    assert result["evidence_docs"]
    assert result["matched_nodes"]
    assert result["answer"]
    assert result["citations"]
    assert result["retrieval_trace"]["ranked_chunk_ids"]
    assert result["method"] == "atanor-graph-token-rag-v1"
    assert result["answer_engine"]["external_llm"] is False
    assert result["answer_engine"]["mode"] == "native-graph-token-alpha"
    assert result["answer_kind"] == "native_graph_token_generation"
    assert result["answer_engine"]["prediction_basis"] == "token_transition_edge_cooccurrence_graph_path"
    assert result["answer_engine"]["network_barrier"] == "sealed_for_generation"
    assert result["answer_engine"]["diagnostics"]["outbound_http_calls"] == 0
    assert result["confidence"] > 0
    assert result["raw_native_output"] == result["answer"]


def test_query_graphrag_does_not_route_greeting_to_canned_identity(tmp_path):
    cleaned = tmp_path / "cleaned"
    ontology = tmp_path / "ontology"
    cleaned.mkdir()
    ontology.mkdir()
    (cleaned / "doc.txt").write_text("GraphRAG uses KnowledgeGraph for Evidence.", encoding="utf-8")
    (ontology / "nodes.json").write_text(json.dumps([{"id": "evidence", "label": "Evidence"}]), encoding="utf-8")
    (ontology / "edges.json").write_text(json.dumps([]), encoding="utf-8")

    result = query_graphrag("hello", str(cleaned), str(ontology))

    assert result["method"] in {"atanor-research-no-evidence-v1", "atanor-graph-token-rag-v1"}
    assert result["answer_engine"]["external_llm"] is False
    assert result["answer_engine"]["surface_generation"] == "native_graph_token_generation"
    assert "CONTROL_INTENT" not in result["answer"]
    assert "ATANOR online" not in result["answer"]
    assert result["answer_kind"] == "native_graph_token_generation"


def test_query_graphrag_node_question_uses_native_path_not_inspection_shortcut(tmp_path):
    cleaned = tmp_path / "cleaned"
    ontology = tmp_path / "ontology"
    cleaned.mkdir()
    ontology.mkdir()
    (cleaned / "doc.txt").write_text("GraphRAG uses KnowledgeGraph for Evidence.", encoding="utf-8")
    (ontology / "nodes.json").write_text(
        json.dumps(
            [
                {"id": "graphrag", "label": "GraphRAG", "type": "concept", "confidence": 0.9},
                {"id": "evidence", "label": "Evidence", "type": "keyword", "confidence": 0.8},
            ]
        ),
        encoding="utf-8",
    )
    (ontology / "edges.json").write_text(json.dumps([{"source": "graphrag", "relation": "uses", "target": "evidence"}]), encoding="utf-8")

    memory = _build_query_memory(cleaned, ontology)
    result = query_graphrag("show all nodes", str(cleaned), str(ontology), memory)

    assert result["method"] in {"atanor-research-no-evidence-v1", "atanor-graph-token-rag-v1"}
    assert result["answer_engine"]["external_llm"] is False
    assert result["answer_kind"] == "native_graph_token_generation"
    assert result["answer_engine"]["surface_generation"] == "native_graph_token_generation"
    assert result["answer_kind"] != "inspection"
    assert "visible nodes" not in result["answer"]


def test_query_graphrag_color_question_uses_native_path_not_legend_shortcut(tmp_path):
    cleaned = tmp_path / "cleaned"
    ontology = tmp_path / "ontology"
    cleaned.mkdir()
    ontology.mkdir()
    (cleaned / "doc.txt").write_text("GraphRAG uses KnowledgeGraph for Evidence.", encoding="utf-8")
    (ontology / "nodes.json").write_text(
        json.dumps(
            [
                {"id": "graphrag", "label": "GraphRAG", "type": "retrieval", "confidence": 0.9},
                {"id": "guardrail", "label": "Guardrail", "type": "guardrail", "confidence": 0.8},
            ]
        ),
        encoding="utf-8",
    )
    (ontology / "edges.json").write_text(json.dumps([{"source": "graphrag", "relation": "checks", "target": "guardrail"}]), encoding="utf-8")

    memory = _build_query_memory(cleaned, ontology)
    result = query_graphrag("color legend", str(cleaned), str(ontology), memory)

    assert result["method"] in {"atanor-research-no-evidence-v1", "atanor-graph-token-rag-v1"}
    assert result["answer_engine"]["external_llm"] is False
    assert result["answer_kind"] == "native_graph_token_generation"
    assert result["answer_engine"]["surface_generation"] == "native_graph_token_generation"
    assert "graph colors indicate" not in result["answer"]


def test_query_graphrag_unknown_external_entity_uses_no_external_llm(tmp_path):
    cleaned = tmp_path / "cleaned"
    ontology = tmp_path / "ontology"
    cleaned.mkdir()
    ontology.mkdir()
    (cleaned / "doc.txt").write_text("GraphRAG uses KnowledgeGraph for Evidence.", encoding="utf-8")
    (ontology / "nodes.json").write_text(json.dumps([{"id": "graphrag", "label": "GraphRAG", "type": "retrieval", "confidence": 0.9}]), encoding="utf-8")
    (ontology / "edges.json").write_text(json.dumps([]), encoding="utf-8")

    memory = _build_query_memory(cleaned, ontology)
    result = query_graphrag("unknown external person", str(cleaned), str(ontology), memory)

    assert result["method"] == "atanor-research-no-evidence-v1"
    assert result["answer_engine"]["external_llm"] is False
    assert result["answer_engine"]["mode"] == "native-graph-token-alpha"
    assert result["answer_kind"] == "native_graph_token_generation"
    assert result["evidence_docs"] == []
    assert result["citations"] == []
    assert "raw_no_node::" not in result["answer"]
    assert result["raw_native_output"] == result["answer"]
    assert result["follow_up_questions"] == []
