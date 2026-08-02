from __future__ import annotations

import ast
import copy
import hashlib
from pathlib import Path

import pytest

from packages.eval_evidence.arc_agi1_prediction import (
    OFFICIAL_EVALUATION_COUNT,
    prediction_manifest_checksum,
    validate_prediction_manifest,
)
from packages.eval_evidence.receipt import BenchmarkEvidenceError, verify_manifest
from scripts import arc_agi1_emit as emitter
from scripts import arc_agi1_score as scorer


def _identity_task() -> dict:
    return {
        "train": [
            {
                "input": [[1, 0], [0, 1]],
                "output": [[1, 0], [0, 1]],
            }
        ],
        "test": [
            {"input": [[2]], "output": [[9]]},
            {"input": [[3, 3]], "output": [[8, 8]]},
        ],
    }


def test_emitter_candidate_call_never_receives_test_gold(monkeypatch) -> None:
    import packages.arc_agi.solver as solver

    observed = {}

    def synthesize(train, *, deadline):
        observed["train"] = train
        return lambda grid: grid

    monkeypatch.setattr(solver, "synthesize", synthesize)
    result = emitter._predict_task(_identity_task(), 1.0)

    assert observed["train"] == [
        ([[1, 0], [0, 1]], [[1, 0], [0, 1]])
    ]
    assert result["predictions"] == [[[2]], [[3, 3]]]
    assert result["predictions"] != [[[9]], [[8, 8]]]
    assert "correct" not in result


def test_scorer_requires_all_test_outputs_for_task_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task_path = tmp_path / "task.json"
    task_path.write_text(
        '{"train":[],"test":['
        '{"input":[[0]],"output":[[2]]},'
        '{"input":[[0]],"output":[[3]]}'
        "]}",
        encoding="utf-8",
    )
    monkeypatch.setattr(scorer, "REPO", tmp_path)
    base = {
        "task_id": "task",
        "dataset_path": "task.json",
        "item_id": "a" * 64,
        "status": "emitted",
        "predictions": [[[2]], [[9]]],
        "latency_ms": 1.0,
        "test_case_count": 2,
        "valid_prediction_count": 2,
        "error_type": None,
    }

    result = scorer._score_item(base)

    assert result["status"] == "wrong"
    assert result["fired"] is True
    assert result["correct"] is False


def test_prediction_rows_are_bijective_with_pinned_inventory(
    tmp_path: Path,
) -> None:
    manifest, path = emitter.run(
        dataset=emitter.DEFAULT_DATASET,
        limit=1,
        time_budget=0.01,
        output=tmp_path / "predictions.json",
    )
    assert len(manifest["dataset"]["files"]) == OFFICIAL_EVALUATION_COUNT
    assert validate_prediction_manifest(manifest) == []

    forged = copy.deepcopy(manifest)
    forged["items"][0]["dataset_path"] = manifest["dataset"]["files"][1]["path"]
    forged["manifest_checksum_sha256"] = prediction_manifest_checksum(forged)
    findings = validate_prediction_manifest(forged)
    assert any("dataset_path mismatch" in finding for finding in findings)

    forged = copy.deepcopy(manifest)
    forged["config"]["limit"] = 0
    forged["selection"]["full_official_inventory"] = True
    forged["manifest_checksum_sha256"] = prediction_manifest_checksum(forged)
    findings = validate_prediction_manifest(forged)
    assert any("item count" in finding for finding in findings)

    forged = copy.deepcopy(manifest)
    forged["config"]["attempts_per_test_input"] = 999
    forged["config"]["gold_in_candidate_payload"] = True
    forged["manifest_checksum_sha256"] = prediction_manifest_checksum(forged)
    findings = validate_prediction_manifest(forged)
    assert "prediction attempts must equal one" in findings
    assert "gold_in_candidate_payload must be false" in findings
    assert path.exists()


def test_score_requires_operator_supplied_artifact_digest(
    tmp_path: Path,
) -> None:
    manifest, predictions = emitter.run(
        dataset=emitter.DEFAULT_DATASET,
        limit=1,
        time_budget=0.01,
        output=tmp_path / "predictions.json",
    )
    digest = hashlib.sha256(predictions.read_bytes()).hexdigest()

    score, destination = scorer.score(
        predictions_path=predictions,
        expected_prediction_sha256=digest,
        output=tmp_path / "score.json",
    )

    assert score["metrics"]["n"] == 1
    assert score["integrity"]["e5_claimed"] is False
    assert verify_manifest(
        destination,
        repo_root=scorer.REPO,
        require_current=True,
    )["valid"] is True

    with pytest.raises(BenchmarkEvidenceError, match="operator-supplied"):
        scorer.score(
            predictions_path=predictions,
            expected_prediction_sha256="0" * 64,
            output=tmp_path / "never.json",
        )


def test_scorer_source_does_not_import_candidate_packages() -> None:
    source_path = Path(scorer.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )

    assert not any(name.startswith("packages.arc_agi") for name in imported)
    assert "scripts.arc_agi1_emit" not in imported
    assert "packages.eval_evidence.arc_agi1_prediction" in imported
