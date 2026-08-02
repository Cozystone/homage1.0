from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from packages.eval_evidence.receipt import BenchmarkEvidenceError, item_id, verify_manifest
from scripts import babi_external_harness as harness


def test_grade_contract_names_normalized_rule_and_keeps_abstention_separate() -> None:
    assert harness.grade(None, "kitchen") == "abstain"
    assert harness.grade("hallway", "kitchen") == "wrong"
    assert harness.grade("the kitchen.", "kitchen") == "correct"
    assert harness.grade("Yes ??supported.", "yes") == "correct"
    assert harness.grade("apple, milk", "milk,apple") == "correct"
    assert "punctuation/articles removed" in harness.GRADING_RULE
    assert harness._output_digest("the kitchen.") != harness._output_digest("kitchen")


def test_test_split_and_repository_source_output_are_refused_before_model_work(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="SEALED"):
        harness.run(cap=1, split="test", output=tmp_path / "forbidden.json")
    forbidden = harness.REPO / "packages" / "forbidden_babi_receipt.json"
    with pytest.raises(BenchmarkEvidenceError, match="reports/benchmarks"):
        harness.run(cap=1, split="train", output=forbidden)
    assert not forbidden.exists()


@pytest.mark.parametrize("split", ["train", "valid"])
def test_one_item_per_task_uses_fresh_worker_and_semantic_census(
    tmp_path: Path,
    split: str,
) -> None:
    output = tmp_path / f"babi_{split}.json"
    manifest, written = harness.run(cap=1, split=split, output=output)

    assert written == output.resolve()
    assert manifest["metrics"]["n"] == 20
    assert len(manifest["items"]) == 20
    assert manifest["benchmark"]["split"] == split
    assert manifest["config"]["candidate_process"] == "fresh_subprocess"
    assert manifest["config"]["gold_in_candidate_payload"] is False
    assert manifest["integrity"]["network_isolation_enforced"] is False
    assert manifest["integrity"]["shipped_state_isolation_enforced"] is False
    assert manifest["integrity"]["production_authority"] is False
    assert manifest["integrity"]["e5_claimed"] is False
    assert all("question" not in item["metadata"] for item in manifest["items"])
    assert all("gold" not in item["metadata"] for item in manifest["items"])
    assert any(
        record["path"] == "data/lexicon/english_vocab.json"
        for record in manifest["candidate"]["files"]
    )
    assert harness.validate_babi_semantics(manifest) == []
    assert verify_manifest(output, repo_root=harness.REPO)["valid"] is True


def test_worker_result_contract_rejects_malformed_non_dict_answers() -> None:
    malformed = {
        "schema_version": harness.WORKER_RESULT_SCHEMA,
        "items": [
            {
                "index": 0,
                "emitted": False,
                "answer": "candidate produced text despite non-emitted",
                "error_type": "InvalidCandidateResult",
                "latency_ms": 1.0,
            }
        ],
    }
    with pytest.raises(BenchmarkEvidenceError, match="row 0 invalid"):
        harness._validate_worker_result(malformed, 1)


def test_semantic_verifier_rejects_declared_full_run_and_item_census_forgery(
    tmp_path: Path,
) -> None:
    manifest, _ = harness.run(
        cap=1,
        split="train",
        output=tmp_path / "babi.json",
    )
    forged = copy.deepcopy(manifest)
    forged["config"]["cap_per_task"] = None
    forged["config"]["all_items"] = True
    findings = harness.validate_babi_semantics(forged)
    assert any("census" in finding for finding in findings)

    forged = copy.deepcopy(manifest)
    forged["items"][0]["item_id"] = "0" * 64
    findings = harness.validate_babi_semantics(forged)
    assert any("census" in finding for finding in findings)


def _metric_item(task: int, ordinal: int, status: str) -> dict:
    fired = status in {"correct", "wrong"}
    return {
        "item_id": item_id({"task": task, "ordinal": ordinal}),
        "status": status,
        "fired": fired,
        "correct": status == "correct",
        "output_sha256": (
            hashlib.sha256(f"{task}:{ordinal}".encode()).hexdigest()
            if fired
            else None
        ),
        "latency_ms": 1.0,
        "metadata": {"task": task, "ordinal": ordinal},
    }


def test_macro_and_micro_are_separately_labelled_for_unequal_task_sizes() -> None:
    items = [
        _metric_item(1, 0, "correct"),
        _metric_item(1, 1, "wrong"),
        *[
            _metric_item(task, 0, "wrong")
            for task in range(2, 21)
        ],
    ]
    _, macro = harness._task_metrics(items)
    micro = sum(row["correct"] for row in items) / len(items)

    assert macro == 0.025
    assert round(micro, 12) == round(1 / 21, 12)
    assert macro != round(micro, 12)
