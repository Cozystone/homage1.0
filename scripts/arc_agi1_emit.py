"""Emit one-attempt ARC-AGI-1 predictions without scoring against test gold.

This is the candidate side of a two-process evidence boundary.  It passes only
training pairs and test inputs to the solver, writes every test prediction (or
an explicit abstention/error), and never assigns correctness.  The public
evaluation split is already contamination-exposed development material.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from packages.eval_evidence.receipt import (  # noqa: E402
    BenchmarkEvidenceError,
    bind_files,
    canonical_json_bytes,
    ensure_safe_report_output,
    item_id,
    utc_now,
)
from packages.eval_evidence.arc_agi1_prediction import (  # noqa: E402
    ARC_CANDIDATE_PATHS,
    OFFICIAL_EVALUATION_CONTENT_SHA256,
    OFFICIAL_EVALUATION_COUNT,
    SCHEMA,
    prediction_manifest_checksum,
    validate_prediction_manifest,
)


DEFAULT_DATASET = (
    REPO / "data" / "arc_agi" / "ARC-AGI-master" / "data" / "evaluation"
)
REPORTS = REPO / "reports" / "benchmarks"
def _new_run_id() -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{stamp}.arc-agi1.{uuid.uuid4().hex[:12]}"


def _dataset_files(dataset: Path) -> tuple[str, ...]:
    try:
        resolved = dataset.resolve(strict=True)
        if resolved != DEFAULT_DATASET.resolve(strict=True):
            raise BenchmarkEvidenceError(
                "only the pinned repository ARC-AGI-1 evaluation inventory is allowed"
            )
        relative_root = resolved.relative_to(REPO.resolve())
    except (OSError, ValueError) as exc:
        raise BenchmarkEvidenceError("dataset must be a repository directory") from exc
    files = sorted(dataset.glob("*.json"))
    if len(files) != OFFICIAL_EVALUATION_COUNT:
        raise BenchmarkEvidenceError("official ARC inventory must contain 400 tasks")
    return tuple((relative_root / path.name).as_posix() for path in files)


def _load_task(path: Path) -> dict[str, Any]:
    try:
        task = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BenchmarkEvidenceError(
            f"ARC task is unreadable: {path.name}: {type(exc).__name__}"
        ) from exc
    if not isinstance(task, dict):
        raise BenchmarkEvidenceError(f"ARC task root is not an object: {path.name}")
    train = task.get("train")
    tests = task.get("test")
    if not isinstance(train, list) or not train or not isinstance(tests, list) or not tests:
        raise BenchmarkEvidenceError(f"ARC task train/test invalid: {path.name}")
    for pair in train:
        if (
            not isinstance(pair, dict)
            or "input" not in pair
            or "output" not in pair
        ):
            raise BenchmarkEvidenceError(f"ARC train pair invalid: {path.name}")
    for case in tests:
        if not isinstance(case, dict) or "input" not in case:
            raise BenchmarkEvidenceError(f"ARC test input invalid: {path.name}")
    return task


def _predict_task(task: Mapping[str, Any], time_budget: float) -> dict[str, Any]:
    """Predict every test input; correctness is intentionally unavailable here."""
    from packages.arc_agi.solver import _safe, _valid_grid, synthesize

    started = time.perf_counter()
    error_type: str | None = None
    predictions: list[list[list[int]]] | None = None
    valid_count = 0
    try:
        train = [
            (pair["input"], pair["output"])
            for pair in task["train"]
        ]
        deadline = time.monotonic() + time_budget
        program = synthesize(train, deadline=deadline)
        if program is not None:
            generated = [_safe(program, case["input"]) for case in task["test"]]
            valid_count = sum(_valid_grid(grid) for grid in generated)
            if valid_count == len(generated):
                predictions = generated
    except Exception as exc:
        error_type = type(exc).__name__
    latency_ms = round((time.perf_counter() - started) * 1000.0, 6)
    if error_type is not None:
        status = "error"
    elif predictions is None:
        status = "abstain"
    else:
        status = "emitted"
    return {
        "status": status,
        "predictions": predictions,
        "latency_ms": latency_ms,
        "test_case_count": len(task["test"]),
        "valid_prediction_count": valid_count,
        "error_type": error_type,
    }


def run(
    *,
    dataset: Path,
    limit: int,
    time_budget: float,
    output: Path | None,
) -> tuple[dict[str, Any], Path]:
    if limit < 0 or limit > 400:
        raise ValueError("limit must be 0 (all) or in [1, 400]")
    if (
        type(time_budget) not in (int, float)
        or not math.isfinite(float(time_budget))
        or not 0.01 <= float(time_budget) <= 60.0
    ):
        raise ValueError("time_budget must be finite and in [0.01, 60]")
    inventory = _dataset_files(dataset)
    source_before = bind_files(REPO, ARC_CANDIDATE_PATHS)
    dataset_before = bind_files(REPO, inventory)
    if dataset_before["content_sha256"] != OFFICIAL_EVALUATION_CONTENT_SHA256:
        raise BenchmarkEvidenceError(
            "ARC inventory bytes do not match the pinned official baseline"
        )
    selected = inventory if limit == 0 else inventory[:limit]
    records = {
        record["path"]: record for record in dataset_before["files"]
    }
    selected_ids = [
        item_id(
            {
                "dataset_path": relative,
                "dataset_file_sha256": records[relative]["sha256"],
            }
        )
        for relative in selected
    ]
    started_at = utc_now()
    rows = []
    for index, relative in enumerate(selected, start=1):
        path = REPO / relative
        task = _load_task(path)
        prediction = _predict_task(task, float(time_budget))
        row = {
            "task_id": path.stem,
            "dataset_path": relative,
            "item_id": selected_ids[index - 1],
            **prediction,
        }
        rows.append(row)
        print(
            f"{index:03d}/{len(selected):03d} {path.stem} "
            f"{row['status']} tests={row['test_case_count']} "
            f"valid={row['valid_prediction_count']}",
            flush=True,
        )
    source_after = bind_files(REPO, ARC_CANDIDATE_PATHS)
    dataset_after = bind_files(REPO, inventory)
    manifest = {
        "schema_version": SCHEMA,
        "run_id": _new_run_id(),
        "started_at": started_at,
        "completed_at": utc_now(),
        "split": "public_evaluation",
        "claim_scope": "contamination_exposed_public_evaluation_development",
        "config": {
            "time_budget_seconds_per_task": float(time_budget),
            "limit": limit,
            "attempts_per_test_input": 1,
            "gold_in_candidate_payload": False,
        },
        "source": source_before,
        "dataset": dataset_before,
        "selection": {
            "full_official_inventory": limit == 0,
            "selected_dataset_paths": list(selected),
            "selected_item_ids": selected_ids,
            "selected_item_ids_sha256": hashlib.sha256(
                canonical_json_bytes(selected_ids)
            ).hexdigest(),
        },
        "items": rows,
        "integrity": {
            "source_same_before_after": source_before == source_after,
            "dataset_same_before_after": dataset_before == dataset_after,
            "network_isolation_enforced": False,
            "gold_filesystem_isolated": False,
            "scored_in_emitter": False,
            "externally_anchored": False,
            "limitations": [
                "The checksum is recomputable and does not authenticate the producer.",
                "Candidate filesystem and network isolation are not enforced.",
                "The public evaluation set is contamination-exposed development data.",
            ],
        },
    }
    manifest["manifest_checksum_sha256"] = prediction_manifest_checksum(manifest)
    findings = validate_prediction_manifest(manifest)
    if findings:
        raise BenchmarkEvidenceError("; ".join(findings))
    destination = output or REPORTS / f"arc_agi1_predictions_{manifest['run_id']}.json"
    destination = ensure_safe_report_output(REPO, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as handle:
            handle.write(canonical_json_bytes(manifest) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise BenchmarkEvidenceError(f"prediction path already exists: {destination}") from exc
    return manifest, destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--time-budget", type=float, default=8.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest, path = run(
            dataset=args.dataset,
            limit=args.limit,
            time_budget=args.time_budget,
            output=args.output,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps({"error": str(exc), "type": type(exc).__name__}),
            file=sys.stderr,
        )
        return 2
    counts = {
        status: sum(row["status"] == status for row in manifest["items"])
        for status in ("emitted", "abstain", "error")
    }
    print(
        json.dumps(
            {
                "predictions": str(path.resolve()),
                "manifest_checksum_sha256": manifest[
                    "manifest_checksum_sha256"
                ],
                "n": len(manifest["items"]),
                **counts,
                "scored": False,
            },
            sort_keys=True,
        )
    )
    return 0 if counts["error"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
