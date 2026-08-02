from __future__ import annotations

from packages.cloud_brain.graph_exchange import run_local_cloud_exchange
from packages.cloud_brain.semantic_growth import ingest_semantic_source


def test_local_miss_attaches_real_cloud_chunk_then_auto_detaches(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    ingest_semantic_source(
        "Kubernetes is an open-source platform that manages containerized applications and automates deployment.",
        source_id="exchange-proof-001",
        language="en",
        usage_allowed=False,
    )

    result = run_local_cloud_exchange("Kubernetes가 뭐야?", pin_context=False, allow_web=False)

    assert result["local_graph_request"]["state"] == "local_miss"
    assert "cloud_hit" in result["states"]
    assert result["cloud_graph_chunk"]["source"] == "cloud_brain"
    assert result["cloud_graph_chunk"]["temporary"] is True
    assert result["cloud_graph_chunk"]["local_write"] is False
    assert result["cloud_graph_chunk"]["independent_source_attestation"] is False
    assert result["cloud_graph_chunk"]["authoritative_for_answer"] is False
    assert result["working_memory"]["temporary_context_count"] > 0
    assert result["working_memory"]["auto_detached"] is True
    assert result["working_memory"]["overlay_final"]["working_memory_overlay"]["cloud_attached_nodes"] == 0
    assert result["predictive_frontier"]["count"] > 0
    assert result["predictive_frontier"]["creates_permanent_nodes"] is False
    assert result["truth"]["fake_counts"] is False
    assert result["truth"]["full_store_scan"] is False
    assert result["truth"]["pair_edges_sent"] == 0


def test_pinned_context_stays_in_working_memory_without_local_write(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    ingest_semantic_source(
        "GraphRAG connects claims to evidence and verifies answers through retrieved context.",
        source_id="exchange-proof-002",
        language="en",
        usage_allowed=False,
    )

    result = run_local_cloud_exchange("GraphRAG evidence verification", pin_context=True)

    assert result["working_memory"]["pinned"] is True
    assert result["working_memory"]["auto_detached"] is False
    assert result["working_memory"]["overlay_final"]["working_memory_overlay"]["cloud_attached_nodes"] > 0
    assert result["working_memory"]["local_write"] is False
    assert result["promotion"]["cloud_promotion"] == "manual_required"


def test_cloud_miss_returns_honest_unconfigured_web_evidence_not_fake_results(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_local_cloud_exchange("zzxqv blorf nosemanticmatch", allow_web=True)

    assert "cloud_miss" in result["states"]
    assert result["cloud_graph_chunk"] is None
    assert result["evidence_bundle"]["source"] == "web"
    assert result["evidence_bundle"]["extraction_status"] == "not_configured"
    assert result["evidence_bundle"]["snippets"] == []
    assert result["evidence_bundle"]["verified"] is False
    assert result["candidate_fragment"] is None
    assert result["truth"]["web_results_faked"] is False
    assert result["truth"]["local_brain_write"] is False
