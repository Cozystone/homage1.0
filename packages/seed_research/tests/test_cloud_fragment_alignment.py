from __future__ import annotations

import json
from pathlib import Path

from seed_research import run_seed_iteration
from seed_research.cloud_fragment_alignment import (
    align_cloud_fragment_to_seed,
    align_public_candidate_fragments,
    deterministic_fixture,
    ensure_deterministic_fixture,
    load_candidate_fragments,
)
from seed_research.prove_cloud_fragment_alignment import write_cloud_fragment_alignment_proof


def test_deterministic_fixture_is_created_and_loaded(tmp_path) -> None:
    inbox = tmp_path / "cloud_brain" / "inbox"
    fixture_path = ensure_deterministic_fixture(inbox / "test_seed_alignment_fragment.json")

    assert fixture_path.exists()
    fragments = load_candidate_fragments(inbox)
    assert len(fragments) == 1
    assert fragments[0]["fragment_id"] == "candidate_seed_alignment_001"
    assert fragments[0]["fixture"] is True
    assert fragments[0]["not_real_web_crawling"] is True


def test_private_fragment_is_rejected(tmp_path) -> None:
    root = tmp_path / "seed_research"
    run_seed_iteration(root)
    private_fragment = {
        **deterministic_fixture(),
        "fragment_id": "private",
        "privacy_scope": "private",
        "raw_text": "C:\\Users\\private\\payload",
    }

    alignment = align_cloud_fragment_to_seed(private_fragment, root)

    assert alignment["rejected"] is True
    assert alignment["alignment_attempted"] is False
    assert alignment["writes_to_local_brain"] is False


def test_public_fragment_aligns_to_seed_concepts_and_edges(tmp_path) -> None:
    root = tmp_path / "seed_research"
    run_seed_iteration(root)

    alignment = align_cloud_fragment_to_seed(deterministic_fixture(), root)

    assert alignment["rejected"] is False
    assert alignment["alignment_success"] is True
    labels = {item["label"] for item in alignment["matched_seed_concepts"]}
    assert {"Evidence", "Claim", "Source", "Verification"}.intersection(labels)
    relations = {item["relation"] for item in alignment["matched_seed_edges"]}
    assert "supports" in relations
    assert "requires" in relations or "has_source" in relations or "verifies" in relations
    assert alignment["external_llm_used"] is False
    assert alignment["external_sllm_used"] is False
    assert alignment["rule_based_answer_engine"] is False
    assert alignment["final_answer_generation_claimed"] is False


def test_alignment_summary_does_not_fake_counts_when_inbox_empty(tmp_path) -> None:
    root = tmp_path / "seed_research"
    inbox = tmp_path / "cloud_brain" / "inbox"
    run_seed_iteration(root)

    summary = align_public_candidate_fragments(root, inbox)

    assert summary["candidate_fragments_checked"] == 0
    assert summary["public_fragments_checked"] == 0
    assert summary["fragments_aligned_to_seed"] == 0
    assert summary["concepts_aligned_total"] == 0
    assert summary["edges_aligned_total"] == 0


def test_cloud_fragment_alignment_proof_outputs_md_and_json_without_local_memory(tmp_path) -> None:
    root = tmp_path / "seed_research"
    inbox = tmp_path / "cloud_brain" / "inbox"
    run_seed_iteration(root)

    result = write_cloud_fragment_alignment_proof(root, inbox)

    json_path = Path(result["json_path"])
    markdown_path = Path(result["markdown_path"])
    assert json_path.exists()
    assert markdown_path.exists()
    proof = json.loads(json_path.read_text(encoding="utf-8"))
    assert proof["summary"]["candidate_fragments_checked"] == 1
    assert proof["summary"]["public_fragments_checked"] == 1
    assert proof["summary"]["fragments_aligned_to_seed"] == 1
    assert proof["summary"]["concepts_aligned_total"] >= 3
    assert proof["summary"]["edges_aligned_total"] >= 1
    assert proof["local_brain_state"]["local_total_nodes"] == 0
    assert proof["local_brain_state"]["local_total_edges"] == 0
    assert proof["claims"]["external_llm_used"] is False
    assert proof["claims"]["external_sllm_used"] is False
    assert proof["claims"]["rule_based_answer_engine"] is False
    assert proof["claims"]["final_answer_generation_claimed"] is False
    assert not (tmp_path / "data" / "memory").exists()
