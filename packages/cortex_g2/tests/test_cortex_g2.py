from __future__ import annotations

from pathlib import Path

from packages.cortex_g2.activation_engine import MAX_ACTIVATION_EDGES, MAX_ACTIVATION_NODES, run_graph_activation
from packages.cortex_g2.creative_walk import run_creative_walk
from packages.cortex_g2.dream_loop import run_self_dream_cycle
from packages.cortex_g2.pipeline import run_cortex_cycle, summarize_cortex_cycle
from packages.cortex_g2.proof import write_living_neuromorphic_loop_proof
from packages.cortex_g2.salience_gate import select_global_workspace
from packages.cortex_g2.storage import DEFAULT_CORTEX_ROOT, append_jsonl


def _evidence_graph() -> dict:
    nodes = [
        {"id": "seed_evidence", "label": "Evidence", "visual_layer": "seed_anchor", "source_scope": "seed"},
        {"id": "seed_claim", "label": "Claim", "visual_layer": "seed_anchor", "source_scope": "seed"},
        {"id": "seed_source", "label": "Source", "visual_layer": "seed_anchor", "source_scope": "seed"},
        {"id": "seed_verification", "label": "Verification", "visual_layer": "seed_anchor", "source_scope": "seed"},
        {"id": "cloud_context", "label": "GraphRAG evidence context", "visual_layer": "cloud_attached", "source_scope": "cloud"},
    ]
    edges = [
        {"id": "e1", "source": "seed_evidence", "relation": "supports", "target": "seed_claim", "source_type": "cloud_attached"},
        {"id": "e2", "source": "seed_source", "relation": "provides", "target": "seed_evidence", "source_type": "cloud_attached"},
        {"id": "e3", "source": "seed_evidence", "relation": "has_source", "target": "seed_source", "source_type": "cloud_attached"},
        {"id": "e4", "source": "seed_verification", "relation": "verifies", "target": "seed_claim", "source_type": "cloud_attached"},
        {"id": "e5", "source": "cloud_context", "relation": "supports", "target": "seed_evidence", "source_type": "cloud_attached"},
    ]
    return {
        "local_nodes": [],
        "local_edges": [],
        "seed_anchor_nodes": nodes[:4],
        "cloud_attached_nodes": nodes[4:],
        "cloud_attached_edges": edges,
        "working_memory_overlay": {"active": True, "writes_to_local_brain": False},
    }


def test_activation_respects_budget_and_never_writes_local_brain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    graph = {
        "nodes": [{"id": f"n{i}", "label": f"Evidence Claim {i}"} for i in range(MAX_ACTIVATION_NODES + 100)],
        "edges": [
            {"id": f"e{i}", "source": f"n{i % MAX_ACTIVATION_NODES}", "relation": "supports", "target": f"n{(i + 1) % MAX_ACTIVATION_NODES}"}
            for i in range(MAX_ACTIVATION_EDGES + 100)
        ],
    }

    result = run_graph_activation("Evidence와 Claim의 차이를 설명해줘.", graph)

    assert result["activation_budget_used"]["nodes_seen"] == MAX_ACTIVATION_NODES
    assert result["activation_budget_used"]["edges_seen"] == MAX_ACTIVATION_EDGES
    assert len(result["activated_nodes"]) <= 128
    assert len(result["activated_edges"]) <= 256
    assert result["local_write"] is False
    assert result["external_llm_used"] is False
    assert result["external_sllm_used"] is False


def test_salience_gate_and_prediction_cycle_are_bounded_and_evidence_backed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    cycle = run_cortex_cycle("Evidence와 Claim의 차이를 설명해줘.", _evidence_graph(), top_k_nodes=3, top_k_edges=3)
    summary = summarize_cortex_cycle(cycle)

    assert cycle["enabled"] is True
    assert cycle["local_brain_write"] is False
    assert summary["salience_nodes"] <= 3
    assert summary["salience_edges"] <= 3
    assert summary["prediction_paths"] > 0
    assert "mean_prediction_error" in cycle["prediction_trace"]
    assert cycle["knowledge_crystal"]["self_generated_truth_saved"] is False
    assert cycle["retrieval_trace"]["cortex_g2"]["local_brain_write"] is False


def test_salience_gate_returns_bounded_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    activation = run_graph_activation("Evidence Claim", _evidence_graph())

    workspace = select_global_workspace(activation, top_k_nodes=2, top_k_edges=1)

    assert workspace["bounded"] is True
    assert len(workspace["active_nodes"]) <= 2
    assert len(workspace["active_edges"]) <= 1
    assert workspace["local_write"] is False


def test_dream_loop_is_bounded_and_rejects_no_evidence_self_answers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    append_jsonl(
        DEFAULT_CORTEX_ROOT / "prediction_traces.jsonl",
        {
            "trace_id": "ptr_no_evidence",
            "query": "unsupported path",
            "observed_paths": [],
            "prediction_errors": [{"source_concept": "Evidence", "target_concept": "Claim", "error_reason": "expected_path_missing"}],
        },
    )

    result = run_self_dream_cycle(max_questions=1)

    assert result["question_count"] == 1
    assert result["questions"][0]["status"] == "rejected_no_evidence"
    assert result["self_generated_truth_saved"] is False
    assert result["local_brain_write"] is False


def test_creative_walk_stores_candidates_not_truth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_creative_walk("bounded graph planning", mode="analogy_walk")

    assert result["candidates"]
    assert result["stored_as_truth"] is False
    assert result["stored_as_idea_candidate"] is True
    assert all(candidate["stored_as_truth"] is False for candidate in result["candidates"])


def test_living_neuromorphic_loop_proof_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = write_living_neuromorphic_loop_proof()
    proof = result["proof"]

    assert proof["result"] == "PASS"
    assert proof["local_brain_before"]["local_total_nodes"] == 0
    assert proof["local_brain_after_detach"]["local_total_nodes"] == 0
    assert proof["self_generated_truth_saved"] is False
    assert proof["external_llm_used"] is False
    assert proof["external_sllm_used"] is False
    assert Path("data/cortex_g2/proofs/living_neuromorphic_loop_proof.json").exists()
    assert Path("data/cortex_g2/proofs/living_neuromorphic_loop_proof.md").exists()
