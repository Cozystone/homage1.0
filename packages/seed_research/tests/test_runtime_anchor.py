from __future__ import annotations

import json
from pathlib import Path

from seed_research import run_seed_iteration
from seed_research.prove_runtime_anchor import write_runtime_anchor_proof
from seed_research.runtime_anchor import align_cloud_candidates, resolve_seed_concepts, seed_anchor_trace


def test_seed_concepts_resolve_from_aliases(tmp_path) -> None:
    root = tmp_path / "seed_research"
    run_seed_iteration(root)

    trace = resolve_seed_concepts("How does evidence verify a claim?", root)

    assert trace["seed_anchor_ready"] is True
    assert trace["matched_seed_concepts"]
    labels = {item["label"].casefold() for item in trace["matched_seed_concepts"]}
    assert "evidence" in labels or "claim" in labels


def test_seed_edges_return_when_related_concepts_match(tmp_path) -> None:
    root = tmp_path / "seed_research"
    run_seed_iteration(root)

    trace = resolve_seed_concepts("Local Brain Cloud Brain private public boundary", root)

    assert trace["matched_seed_concepts"]
    assert trace["matched_seed_edges"]


def test_no_evidence_seed_anchor_resolves_from_korean_alias(tmp_path) -> None:
    root = tmp_path / "seed_research"
    run_seed_iteration(root)

    trace = resolve_seed_concepts("근거가 없으면 어떻게 답해야 해?", root)

    concept_ids = {item["concept_id"] for item in trace["matched_seed_concepts"]}
    assert "seed.core.no_evidence" in concept_ids
    assert "seed.core.grounding" in concept_ids
    relations = {item["relation"] for item in trace["matched_seed_edges"]}
    assert "weakens" in relations or "requires" in relations


def test_local_cloud_query_expands_relation_context(tmp_path) -> None:
    root = tmp_path / "seed_research"
    run_seed_iteration(root)

    trace = resolve_seed_concepts("Local Brain과 Cloud Brain은 어떻게 분리돼?", root)

    concept_ids = {item["concept_id"] for item in trace["matched_seed_concepts"]}
    assert "seed.core.local_brain" in concept_ids
    assert "seed.core.cloud_brain" in concept_ids
    assert "seed.core.privacy_scope" in concept_ids
    relations = {item["relation"] for item in trace["matched_seed_edges"]}
    assert "belongs_to_layer" in relations
    assert "depends_on" in relations


def test_seed_anchor_trace_has_no_generation_or_external_model_claims(tmp_path) -> None:
    root = tmp_path / "seed_research"
    run_seed_iteration(root)

    trace = seed_anchor_trace("GraphRAG evidence claim verification", root)

    assert trace["enabled"] is True
    assert trace["final_answer_generation_claimed"] is False
    assert trace["external_llm_used"] is False
    assert trace["external_sllm_used"] is False
    assert trace["rule_based_answer_engine"] is False


def test_cloud_fragment_alignment_does_not_fake_counts_when_empty(tmp_path) -> None:
    root = tmp_path / "seed_research"
    cloud_root = tmp_path / "cloud_brain"
    run_seed_iteration(root)
    trace = resolve_seed_concepts("evidence claim", root)

    alignment = align_cloud_candidates(trace, cloud_root)

    assert alignment["cloud_checked"] is True
    assert alignment["candidate_fragments_checked"] == 0
    assert alignment["fragments_aligned_to_seed"] == 0


def test_runtime_anchor_proof_command_outputs_md_and_json_without_local_memory(tmp_path) -> None:
    root = tmp_path / "seed_research"
    run_seed_iteration(root)

    result = write_runtime_anchor_proof(root, tmp_path / "cloud_brain")

    json_path = Path(result["json_path"])
    markdown_path = Path(result["markdown_path"])
    assert json_path.exists()
    assert markdown_path.exists()
    proof = json.loads(json_path.read_text(encoding="utf-8"))
    assert proof["local_graph_state"]["local_brain_initialized"] is False
    assert proof["local_graph_state"]["local_total_nodes"] == 0
    assert proof["local_graph_state"]["local_total_edges"] == 0
    assert proof["claims"]["external_llm_used"] is False
    assert proof["claims"]["external_sllm_used"] is False
    assert proof["claims"]["rule_based_answer_engine"] is False
    assert not (tmp_path / "data" / "memory").exists()
