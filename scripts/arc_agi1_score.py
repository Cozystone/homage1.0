"""Score ARC-AGI-1 prediction artifacts without importing candidate code.

A task is correct only when the single emitted attempt exactly matches every
public test output.  The split is explicitly contamination-exposed development
material, so even a valid receipt is not a sealed holdout or E5 claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from packages.eval_evidence.receipt import (  # noqa: E402
    BENCHMARK_EVIDENCE_KIND,
    BENCHMARK_EVIDENCE_SCHEMA,
    BenchmarkEvidenceError,
    aggregate_items,
    bind_files,
    canonical_json_bytes,
    ensure_safe_report_output,
    environment_record,
    finalize_manifest,
    selection_record,
    strict_json_bytes,
    utc_now,
    verify_manifest,
    write_manifest_exclusive,
)
from packages.eval_evidence.arc_agi1_prediction import (  # noqa: E402
    ARC_CANDIDATE_PATHS,
    SCHEMA as PREDICTION_SCHEMA,
    validate_prediction_manifest,
)


REPORTS = REPO / "reports" / "benchmarks"
_SOURCE_PATHS = (
    "packages/__init__.py",
    "scripts/arc_agi1_score.py",
    "packages/eval_evidence/__init__.py",
    "packages/eval_evidence/arc_agi1_prediction.py",
    "packages/eval_evidence/receipt.py",
)


def _load_json_bytes(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        return strict_json_bytes(payload, label=label)
    except BenchmarkEvidenceError:
        raise


def _load_bound_task(path: Path, expected_sha256: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise BenchmarkEvidenceError(
            f"ARC task unreadable: {path.name}: {type(exc).__name__}"
        ) from exc
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise BenchmarkEvidenceError(
            f"ARC task bytes do not match bound dataset: {path.name}"
        )
    return _load_json_bytes(payload, label=f"ARC task {path.name}")


def _valid_grid(grid: Any) -> bool:
    if not isinstance(grid, list) or not grid:
        return False
    if not isinstance(grid[0], list) or not grid[0]:
        return False
    width = len(grid[0])
    return all(
        isinstance(row, list)
        and len(row) == width
        and all(type(cell) is int and 0 <= cell <= 9 for cell in row)
        for row in grid
    )


def _prediction_output_digest(predictions: list[Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(predictions)).hexdigest()


def _repo_relative_or_none(path: Path) -> str | None:
    try:
        return path.resolve(strict=True).relative_to(REPO.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _score_item(
    row: dict[str, Any],
    *,
    expected_dataset_sha256: str | None = None,
) -> dict[str, Any]:
    task_path = REPO / row["dataset_path"]
    if expected_dataset_sha256 is None:
        try:
            payload = task_path.read_bytes()
        except OSError as exc:
            raise BenchmarkEvidenceError(
                f"ARC task unreadable: {task_path.name}: {type(exc).__name__}"
            ) from exc
        expected_dataset_sha256 = hashlib.sha256(payload).hexdigest()
    task = _load_bound_task(task_path, expected_dataset_sha256)
    tests = task.get("test")
    if not isinstance(tests, list) or not tests:
        raise BenchmarkEvidenceError(f"test cases missing: {task_path.name}")
    expected = [case.get("output") for case in tests]
    if any(not _valid_grid(grid) for grid in expected):
        raise BenchmarkEvidenceError(f"test gold invalid: {task_path.name}")

    status = row["status"]
    predictions = row["predictions"]
    if status == "emitted":
        if (
            not isinstance(predictions, list)
            or len(predictions) != len(expected)
            or any(not _valid_grid(grid) for grid in predictions)
        ):
            raise BenchmarkEvidenceError(
                f"emitted predictions invalid: {task_path.name}"
            )
        correct = predictions == expected
        outcome = "correct" if correct else "wrong"
        output_digest = _prediction_output_digest(predictions)
        fired = True
    elif status == "abstain":
        outcome = "abstain"
        correct = False
        output_digest = None
        fired = False
    elif status == "error":
        outcome = "error"
        correct = False
        output_digest = None
        fired = False
    else:
        raise BenchmarkEvidenceError(f"prediction status invalid: {status!r}")
    return {
        "item_id": row["item_id"],
        "status": outcome,
        "fired": fired,
        "correct": correct,
        "output_sha256": output_digest,
        "latency_ms": row["latency_ms"],
        "metadata": {
            "task_id": row["task_id"],
            "test_case_count": len(expected),
            "valid_prediction_count": row["valid_prediction_count"],
            "contamination_exposed": True,
        },
    }


def score(
    *,
    predictions_path: Path,
    expected_prediction_sha256: str,
    output: Path | None,
) -> tuple[dict[str, Any], Path]:
    if (
        not isinstance(expected_prediction_sha256, str)
        or len(expected_prediction_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_prediction_sha256)
    ):
        raise BenchmarkEvidenceError(
            "expected prediction SHA-256 must be 64 lowercase hex characters"
        )
    prediction_bytes = predictions_path.read_bytes()
    observed_prediction_sha256 = hashlib.sha256(prediction_bytes).hexdigest()
    if observed_prediction_sha256 != expected_prediction_sha256:
        raise BenchmarkEvidenceError(
            "prediction artifact does not match the operator-supplied SHA-256"
        )
    prediction_manifest = _load_json_bytes(
        prediction_bytes,
        label="prediction artifact",
    )
    if prediction_manifest.get("schema_version") != PREDICTION_SCHEMA:
        raise BenchmarkEvidenceError("prediction schema mismatch")
    prediction_findings = validate_prediction_manifest(prediction_manifest)
    if prediction_findings:
        raise BenchmarkEvidenceError("; ".join(prediction_findings))

    source_before = bind_files(REPO, _SOURCE_PATHS)
    dataset_paths = [
        record["path"] for record in prediction_manifest["dataset"]["files"]
    ]
    dataset_before = bind_files(REPO, dataset_paths)
    if dataset_before != prediction_manifest["dataset"]:
        raise BenchmarkEvidenceError("prediction dataset no longer matches current bytes")
    candidate_paths = [record["path"] for record in prediction_manifest["source"]["files"]]
    if tuple(candidate_paths) != ARC_CANDIDATE_PATHS:
        raise BenchmarkEvidenceError("prediction candidate closure is non-canonical")
    if bind_files(REPO, candidate_paths) != prediction_manifest["source"]:
        raise BenchmarkEvidenceError("prediction candidate source no longer matches current bytes")

    started_at = utc_now()
    dataset_records = {
        record["path"]: record for record in dataset_before["files"]
    }
    items = [
        _score_item(
            row,
            expected_dataset_sha256=dataset_records[row["dataset_path"]]["sha256"],
        )
        for row in prediction_manifest["items"]
    ]
    source_after = bind_files(REPO, _SOURCE_PATHS)
    dataset_after = bind_files(REPO, dataset_paths)
    payload = {
        "schema_version": BENCHMARK_EVIDENCE_SCHEMA,
        "evidence_kind": BENCHMARK_EVIDENCE_KIND,
        "run_id": f"{prediction_manifest['run_id']}.score",
        "started_at": started_at,
        "completed_at": utc_now(),
        "benchmark": {
            "id": "arc-agi-1",
            "version": "public-2019",
            "split": "public_evaluation_development_exposed",
            "protocol": "all test inputs exact; one emitted attempt",
            "claim_scope": "contamination_exposed_development_score",
            "official_inventory_count": len(dataset_paths),
        },
        "config": {
            **prediction_manifest["config"],
            "prediction_manifest_checksum_sha256": prediction_manifest[
                "manifest_checksum_sha256"
            ],
            "prediction_artifact_sha256": observed_prediction_sha256,
            "prediction_artifact_repo_path": _repo_relative_or_none(
                predictions_path
            ),
            "prediction_digest_supplied_out_of_band": True,
            "gold_in_candidate_payload": False,
            "gold_filesystem_isolation_enforced": False,
        },
        "environment": environment_record(),
        "source": source_before,
        "candidate": prediction_manifest["source"],
        "dataset": dataset_before,
        "evaluator": {
            "identity": "arc_agi1_score.all_test_exact.v1",
            "source_digest_sha256": source_before["content_sha256"],
            "independent": False,
            "externally_signed": False,
            "limitations": [
                "The scorer is source-separated but remains in the same repository.",
                "The public evaluation split has repeatedly influenced candidate development.",
                "No external evaluator signature or fresh hidden ARC set is present.",
                "The supplied artifact digest is a handoff check, not a signature.",
            ],
        },
        "selection": selection_record(items),
        "metrics": aggregate_items(items),
        "items": items,
        "integrity": {
            "source_same_before_after": source_before == source_after,
            "candidate_same_before_after": (
                bind_files(REPO, candidate_paths) == prediction_manifest["source"]
            ),
            "dataset_same_before_after": dataset_before == dataset_after,
            "network_isolation_enforced": False,
            "shipped_state_isolation_enforced": False,
            "production_authority": False,
            "e5_claimed": False,
            "limitations": [
                "Network, filesystem, and shipped-state isolation are not enforced.",
                "Candidate source contains evaluation-informed task targeting.",
                "This freezes a development baseline and cannot establish transfer.",
                "The receipt checksum is recomputable and does not authenticate the scorer.",
            ],
        },
    }
    manifest = finalize_manifest(payload)
    destination = output or REPORTS / (
        f"arc_agi1_score_{prediction_manifest['run_id']}.json"
    )
    destination = ensure_safe_report_output(REPO, destination)
    write_manifest_exclusive(destination, manifest)
    return manifest, destination


def validate_arc_score_semantics(
    manifest: dict[str, Any],
    *,
    require_prediction_artifact: bool = True,
) -> list[str]:
    """Re-open the bound prediction artifact and reproduce every scored item."""
    findings: list[str] = []
    benchmark = manifest.get("benchmark")
    config = manifest.get("config")
    if not isinstance(benchmark, dict) or benchmark.get("id") != "arc-agi-1":
        return ["ARC score benchmark identity mismatch"]
    if not isinstance(config, dict):
        return ["ARC score config missing"]
    if config.get("attempts_per_test_input") != 1:
        findings.append("ARC score attempts must equal one")
    if config.get("gold_in_candidate_payload") is not False:
        findings.append("ARC score gold payload boundary mismatch")
    relative = config.get("prediction_artifact_repo_path")
    if relative is None:
        if require_prediction_artifact:
            findings.append("ARC prediction artifact is not repository-addressable")
        return findings
    if (
        not isinstance(relative, str)
        or "\\" in relative
        or Path(relative).is_absolute()
        or "." in Path(relative).parts
        or ".." in Path(relative).parts
    ):
        return [*findings, "ARC prediction artifact path invalid"]
    try:
        prediction_path = REPO / relative
        prediction_bytes = prediction_path.read_bytes()
        observed = hashlib.sha256(prediction_bytes).hexdigest()
        if observed != config.get("prediction_artifact_sha256"):
            findings.append("ARC prediction artifact SHA-256 mismatch")
            return findings
        prediction = _load_json_bytes(
            prediction_bytes,
            label="ARC prediction artifact",
        )
    except (OSError, BenchmarkEvidenceError) as exc:
        findings.append(f"ARC prediction artifact unreadable: {type(exc).__name__}")
        return findings
    prediction_findings = validate_prediction_manifest(prediction)
    if prediction_findings:
        findings.extend(
            f"ARC prediction: {finding}" for finding in prediction_findings
        )
        return findings
    if prediction.get("manifest_checksum_sha256") != config.get(
        "prediction_manifest_checksum_sha256"
    ):
        findings.append("ARC prediction manifest checksum binding mismatch")
    if prediction.get("dataset") != manifest.get("dataset"):
        findings.append("ARC score dataset differs from prediction inventory")
    if prediction.get("source") != manifest.get("candidate"):
        findings.append("ARC score candidate differs from prediction source")
    dataset = manifest.get("dataset")
    if not isinstance(dataset, dict) or not isinstance(dataset.get("files"), list):
        findings.append("ARC score dataset scope missing")
        return findings
    records = {
        record["path"]: record
        for record in dataset["files"]
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    }
    try:
        expected_items = [
            _score_item(
                row,
                expected_dataset_sha256=records[row["dataset_path"]]["sha256"],
            )
            for row in prediction["items"]
        ]
    except (BenchmarkEvidenceError, KeyError, TypeError) as exc:
        findings.append(f"ARC score replay failed: {type(exc).__name__}")
        return findings
    if expected_items != manifest.get("items"):
        findings.append("ARC score items do not reproduce from prediction artifact")
    return findings


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if arguments and arguments[0] == "verify":
        parser = argparse.ArgumentParser(description="Verify ARC evidence")
        parser.add_argument("command")
        parser.add_argument("manifest", type=Path)
        parser.add_argument("--historical", action="store_true")
        parsed = parser.parse_args(arguments)
        result = verify_manifest(
            parsed.manifest,
            repo_root=REPO,
            require_current=not parsed.historical,
        )
        if result["structure_valid"]:
            try:
                value = _load_json_bytes(
                    parsed.manifest.read_bytes(),
                    label="ARC score receipt",
                )
                semantic = validate_arc_score_semantics(
                    value,
                    require_prediction_artifact=not parsed.historical,
                )
            except (BenchmarkEvidenceError, OSError) as exc:
                semantic = [str(exc)]
            result["semantic_findings"] = semantic
            result["semantic_valid"] = not semantic
            result["valid"] = result["valid"] and not semantic
        print(json.dumps(result, sort_keys=True))
        return 0 if result["valid"] else 2

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--expected-prediction-sha256", required=True)
    parser.add_argument("--output", type=Path)
    parsed = parser.parse_args(arguments)
    try:
        manifest, path = score(
            predictions_path=parsed.predictions,
            expected_prediction_sha256=parsed.expected_prediction_sha256,
            output=parsed.output,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps({"error": str(exc), "type": type(exc).__name__}),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "manifest": str(path.resolve()),
                "manifest_checksum_sha256": manifest[
                    "manifest_checksum_sha256"
                ],
                "n": manifest["metrics"]["n"],
                "correct": manifest["metrics"]["correct"],
                "wrong": manifest["metrics"]["wrong"],
                "abstain": manifest["metrics"]["abstain"],
                "strict_accuracy": manifest["metrics"]["strict_accuracy"],
                "coverage": manifest["metrics"]["coverage"],
                "e5_claimed": False,
            },
            sort_keys=True,
        )
    )
    return 0 if manifest["metrics"]["error"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
