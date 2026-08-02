from __future__ import annotations

import hashlib
import json
from pathlib import Path

from packages.promotion_gate.dry_run import run_promotion_dry_run


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provenance(source_id: str = "src1") -> dict:
    return {
        "source_id": source_id,
        "license": "CC BY-SA 4.0",
        "usage_allowed": True,
    }


def verification(status: str = "verified") -> dict:
    return {"status": status, "method": "fixture"}


def make_store(root: Path) -> None:
    write_jsonl(root / "concepts.jsonl", [])
    write_jsonl(root / "relations.jsonl", [])
    write_jsonl(root / "evidence.jsonl", [])
    write_jsonl(root / "case_frames.jsonl", [])


def test_dry_run_estimates_candidates_without_mutating_verified(tmp_path):
    verified = tmp_path / "verified"
    candidate = tmp_path / "candidate"
    make_store(verified)
    make_store(candidate)
    write_jsonl(verified / "concepts.jsonl", [{"dedupe_key": "concept_existing", "canonical_name": "Existing"}])
    before = sha(verified / "concepts.jsonl")
    write_jsonl(
        candidate / "concepts.jsonl",
        [
            {"dedupe_key": "concept_new", "concept_id": "c1", "canonical_name": "New", "provenance": provenance(), "verification": verification()},
            {"dedupe_key": "concept_existing", "concept_id": "c2", "canonical_name": "Existing", "provenance": provenance(), "verification": verification()},
        ],
    )
    write_jsonl(
        candidate / "evidence.jsonl",
        [{"dedupe_key": "ev1", "source_hash": "h1", "source_id": "src1", "provenance": provenance(), "verification": verification()}],
    )

    report = run_promotion_dry_run(candidate, verified)

    assert report.new_verified_nodes == 1
    assert report.merged_existing_nodes == 1
    assert report.new_evidence == 1
    assert report.actual_promotion_enabled is False
    assert report.actual_promotion_performed is False
    assert report.dry_run_only is True
    assert report.manual_approval_required is True
    assert report.production_store_mutated is False
    assert report.local_brain_write is False
    assert report.candidate_promotion is False
    assert report.external_llm_used is False
    assert report.real_p2p_used is False
    assert report.generated_code_executed is False
    assert sha(verified / "concepts.jsonl") == before


def test_missing_provenance_candidate_rejected(tmp_path):
    verified = tmp_path / "verified"
    candidate = tmp_path / "candidate"
    make_store(verified)
    make_store(candidate)
    write_jsonl(
        candidate / "concepts.jsonl",
        [{"dedupe_key": "concept_bad", "concept_id": "c1", "canonical_name": "Bad", "verification": verification()}],
    )

    report = run_promotion_dry_run(candidate, verified)

    assert report.rejected_candidates == 1
    assert report.rejected_no_source == 1
    assert any(issue.reason == "missing_provenance" for issue in report.issues)


def test_flat_evidence_source_fields_count_as_provenance(tmp_path):
    verified = tmp_path / "verified"
    candidate = tmp_path / "candidate"
    make_store(verified)
    make_store(candidate)
    write_jsonl(
        candidate / "evidence.jsonl",
        [
            {
                "dedupe_key": "ev_flat",
                "source_hash": "h1",
                "source_id": "src1",
                "license": "CC BY-SA 4.0",
                "usage_allowed": True,
                "verification": verification(),
            }
        ],
    )

    report = run_promotion_dry_run(candidate, verified)

    assert report.new_evidence == 1
    assert not any(issue.item_key == "ev_flat" and issue.severity == "blocker" for issue in report.issues)


def test_conflicting_candidate_values_rejected(tmp_path):
    verified = tmp_path / "verified"
    candidate = tmp_path / "candidate"
    make_store(verified)
    make_store(candidate)
    write_jsonl(
        candidate / "concepts.jsonl",
        [
            {"dedupe_key": "same", "concept_id": "c1", "canonical_name": "Alpha", "provenance": provenance(), "verification": verification()},
            {"dedupe_key": "same", "concept_id": "c2", "canonical_name": "Beta", "provenance": provenance(), "verification": verification()},
        ],
    )

    report = run_promotion_dry_run(candidate, verified)

    assert report.conflicts == 1
    assert report.rejected_conflicts == 1
    assert any(issue.reason == "conflicting_candidate_values" for issue in report.issues)


def test_relation_quality_blocks_missing_endpoint(tmp_path):
    verified = tmp_path / "verified"
    candidate = tmp_path / "candidate"
    make_store(verified)
    make_store(candidate)
    write_jsonl(
        candidate / "relations.jsonl",
        [{"dedupe_key": "rel_bad", "relation_id": "r1", "relation": "SUBJ_OF", "source_concept_id": "c1", "provenance": provenance(), "verification": verification()}],
    )

    report = run_promotion_dry_run(candidate, verified)

    assert any(issue.reason == "missing_relation_endpoint" for issue in report.issues)
    assert report.rejected_low_quality == 1


def test_case_frame_generic_predicate_requires_review(tmp_path):
    verified = tmp_path / "verified"
    candidate = tmp_path / "candidate"
    make_store(verified)
    make_store(candidate)
    write_jsonl(
        candidate / "case_frames.jsonl",
        [
            {
                "dedupe_key": "frame1",
                "frame_id": "f1",
                "predicate": "be",
                "case_roles": [{"role": "SUBJ", "head": "April"}],
                "provenance": provenance(),
                "verification": verification(),
            }
        ],
    )

    report = run_promotion_dry_run(candidate, verified)

    assert report.risky_items == 1
    assert report.requires_manual_review == 1
    assert any(issue.reason == "generic_predicate_requires_review" for issue in report.issues)


def test_sample_size_and_partial_run_metadata_are_reported(tmp_path):
    verified = tmp_path / "verified"
    candidate = tmp_path / "candidate"
    make_store(verified)
    make_store(candidate)
    write_jsonl(
        candidate / "concepts.jsonl",
        [
            {"dedupe_key": "concept_1", "concept_id": "c1", "canonical_name": "One", "provenance": provenance("s1"), "verification": verification()},
            {"dedupe_key": "concept_2", "concept_id": "c2", "canonical_name": "Two", "provenance": provenance("s2"), "verification": verification()},
        ],
    )

    report = run_promotion_dry_run(
        candidate,
        verified,
        sample_size=1,
        source_run_id="candidate_daemon_partial",
        source_run_status="user_stopped_partial",
    )

    assert report.new_verified_nodes == 1
    assert report.sample_size == 1
    assert report.source_run_id == "candidate_daemon_partial"
    assert report.source_run_status == "user_stopped_partial"
    assert report.candidate_input_counts["concept"] == 2


def test_duplicate_candidates_are_rejected_not_counted_as_new(tmp_path):
    verified = tmp_path / "verified"
    candidate = tmp_path / "candidate"
    make_store(verified)
    make_store(candidate)
    write_jsonl(
        candidate / "concepts.jsonl",
        [
            {"dedupe_key": "same", "concept_id": "c1", "canonical_name": "Same", "provenance": provenance(), "verification": verification()},
            {"dedupe_key": "same", "concept_id": "c1b", "canonical_name": "Same", "provenance": provenance(), "verification": verification()},
        ],
    )

    report = run_promotion_dry_run(candidate, verified)

    assert report.new_verified_nodes == 0
    assert report.rejected_duplicates == 1
    assert any(issue.reason == "duplicate_candidate_in_sample" for issue in report.issues)


def test_low_quality_verification_status_rejected(tmp_path):
    verified = tmp_path / "verified"
    candidate = tmp_path / "candidate"
    make_store(verified)
    make_store(candidate)
    write_jsonl(
        candidate / "concepts.jsonl",
        [
            {
                "dedupe_key": "rejected_concept",
                "concept_id": "c1",
                "canonical_name": "Rejected",
                "provenance": provenance(),
                "verification": verification("rejected"),
            }
        ],
    )

    report = run_promotion_dry_run(candidate, verified)

    assert report.new_verified_nodes == 0
    assert report.rejected_low_quality == 1
    assert any(issue.reason == "verification_status_not_promotable" for issue in report.issues)
