from __future__ import annotations

import json
import socket
from pathlib import Path

from knowledge_bakery import build_memory
from rag_engine import LocalSynthesizer, degeneration_metrics, query_graphrag, record_user_correction


def test_native_synthesizer_preserves_raw_output_and_records_trace(tmp_path: Path) -> None:
    result = LocalSynthesizer().synthesize(
        "What is GraphRAG?",
        [{"chunk_id": "doc#1", "doc_id": "doc", "text": "GraphRAG uses KnowledgeGraph for grounded retrieval."}],
        [{"id": "graphrag", "label": "GraphRAG"}, {"id": "knowledgegraph", "label": "KnowledgeGraph"}],
        [{"source": "graphrag", "relation": "uses", "target": "knowledgegraph"}],
        [["graphrag", "uses", "knowledgegraph"]],
        memory_dir=tmp_path,
    )

    assert result["answer_engine"]["name"] == "ATANOR NativeGraphTokenDecoder"
    assert result["answer_engine"]["external_llm"] is False
    assert result["answer_engine"]["surface_generation"] == "native_graph_token_generation"
    assert result["answer_engine"]["template_fallback"] is False
    assert result["answer_kind"] == "native_graph_token_generation"
    assert result["raw_native_output"] == result["answer"]
    assert "raw_no_node::" not in result["answer"]
    assert "CONTROL_INTENT" not in result["answer"]
    trace_path = tmp_path / "generation_traces.jsonl"
    assert trace_path.exists()
    trace = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[-1])
    assert trace["query"] == "What is GraphRAG?"
    assert trace["raw_answer"] == result["answer"]
    assert trace["user_feedback"] is None


def test_degenerate_output_is_not_replaced_with_template(tmp_path: Path) -> None:
    repetitive = "loop loop loop loop loop loop"
    result = LocalSynthesizer().synthesize(
        "?덈뒗 ?꾧뎄??",
        [{"chunk_id": "bad#1", "doc_id": "bad", "text": repetitive}],
        [],
        [],
        [],
        memory_dir=tmp_path,
    )

    assert "loop" in result["answer"]
    assert result["native_generation_failed_quality_check"] is True
    assert result["degeneration"]["loop_detected"] is True
    assert result["training_feedback_recorded"] is True
    assert "ATANOR online" not in result["answer"]
    assert "Local Ghost Shell and Payload Vault are ready" not in result["answer"]


def test_loop_suppression_changes_scoring_not_final_template(tmp_path: Path) -> None:
    result = LocalSynthesizer().synthesize(
        "loop",
        [{"chunk_id": "loop#1", "doc_id": "loop", "text": "alpha beta beta beta beta beta gamma"}],
        [],
        [],
        [],
        memory_dir=tmp_path,
    )

    scores = result["decoder_scores"]
    assert scores
    assert any(score["loop_penalty"] > 0 for score in scores)
    assert result["native_stop_reason"] in {"loop_risk", "no_candidate", "max_tokens"}
    assert result["answer_engine"]["template_fallback"] is False


def test_ghost_lazy_fetch_generation_does_not_open_network_socket(tmp_path: Path, monkeypatch) -> None:
    cleaned = tmp_path / "data" / "cleaned"
    ontology = tmp_path / "data" / "ontology"
    memory = tmp_path / "data" / "memory"
    cleaned.mkdir(parents=True)
    ontology.mkdir(parents=True)
    (cleaned / "ghost.md").write_text(
        "GhostTopology signals hashes first. PayloadVault resolves raw text from local SQLite WAL only.",
        encoding="utf-8",
    )
    (ontology / "nodes.json").write_text("[]", encoding="utf-8")
    (ontology / "edges.json").write_text("[]", encoding="utf-8")
    build_memory(str(cleaned), str(ontology), str(memory))

    def blocked_connect(*_args, **_kwargs):
        raise AssertionError("generation path attempted an outbound socket connection")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    result = query_graphrag("How does PayloadVault resolve text?", memory_dir=str(memory))

    assert result["answer_kind"] == "native_graph_token_generation"
    assert result["answer_engine"]["external_llm"] is False
    assert result["answer_engine"]["surface_generation"] == "native_graph_token_generation"
    assert result["answer_engine"]["diagnostics"]["outbound_http_calls"] == 0
    assert result["retrieval_trace"]["fetch_sequence"]


def test_user_correction_is_stored_as_native_training_data(tmp_path: Path) -> None:
    path = record_user_correction(
        "?덈뒗 ?꾧뎄??",
        "broken raw output",
        "ATANOR correction text supplied by user",
        memory_dir=tmp_path,
    )
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert record["accepted"] is True
    assert record["bad_answer"] == "broken raw output"
    assert record["user_correction"] == "ATANOR correction text supplied by user"


def test_degeneration_metrics_report_repetition() -> None:
    metrics = degeneration_metrics("alpha beta alpha beta alpha beta")
    assert metrics["repeated_bigram_ratio"] > 0
    assert metrics["loop_detected"] is True
