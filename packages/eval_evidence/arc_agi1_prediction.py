"""Strict neutral contract for ARC-AGI-1 candidate prediction artifacts.

The schema proves only that an unsigned artifact is internally consistent with
the pinned public ARC-AGI-1 evaluation inventory.  It does not authenticate the
producer or isolate candidate code from public gold files.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any, Mapping

from .receipt import canonical_json_bytes, item_id


LEGACY_SCHEMA = "atanor.arc-agi1.predictions.v1"
SCHEMA = "atanor.arc-agi1.predictions.v2"
OFFICIAL_EVALUATION_COUNT = 400
OFFICIAL_EVALUATION_CONTENT_SHA256 = (
    "1d8b78d6922fd88e22cc73a7da462564493868b0ecf24a4445f6564134c24eff"
)
OFFICIAL_EVALUATION_PREFIX = (
    "data/arc_agi/ARC-AGI-master/data/evaluation/"
)
ARC_CANDIDATE_PATHS = (
    "packages/__init__.py",
    "packages/arc_agi/__init__.py",
    "packages/arc_agi/application.py",
    "packages/arc_agi/legend.py",
    "packages/arc_agi/objects.py",
    "packages/arc_agi/oe_search.py",
    "packages/arc_agi/solver.py",
    "packages/eval_evidence/__init__.py",
    "packages/eval_evidence/arc_agi1_prediction.py",
    "packages/eval_evidence/receipt.py",
    "packages/evolution/abstraction.py",
    "packages/evolution/code_evolver.py",
    "packages/evolution/compression_progress.py",
    "scripts/arc_agi1_emit.py",
)

ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "started_at",
        "completed_at",
        "split",
        "claim_scope",
        "config",
        "source",
        "dataset",
        "selection",
        "items",
        "integrity",
        "manifest_checksum_sha256",
    }
)
CONFIG_FIELDS = frozenset(
    {
        "time_budget_seconds_per_task",
        "limit",
        "attempts_per_test_input",
        "gold_in_candidate_payload",
    }
)
SELECTION_FIELDS = frozenset(
    {
        "full_official_inventory",
        "selected_dataset_paths",
        "selected_item_ids",
        "selected_item_ids_sha256",
    }
)
ITEM_FIELDS = frozenset(
    {
        "task_id",
        "dataset_path",
        "item_id",
        "status",
        "predictions",
        "latency_ms",
        "test_case_count",
        "valid_prediction_count",
        "error_type",
    }
)
INTEGRITY_FIELDS = frozenset(
    {
        "source_same_before_after",
        "dataset_same_before_after",
        "network_isolation_enforced",
        "gold_filesystem_isolated",
        "scored_in_emitter",
        "externally_anchored",
        "limitations",
    }
)
_FILE_SCOPE_FIELDS = frozenset({"files", "content_sha256"})
_FILE_FIELDS = frozenset({"path", "bytes", "sha256"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ARC_NAME_RE = re.compile(r"^[0-9a-f]{8}\.json$")


def prediction_manifest_checksum(value: Mapping[str, Any]) -> str:
    detached = dict(value)
    detached.pop("manifest_checksum_sha256", None)
    return hashlib.sha256(canonical_json_bytes(detached)).hexdigest()


def _valid_grid(grid: Any) -> bool:
    return (
        isinstance(grid, list)
        and 1 <= len(grid) <= 30
        and isinstance(grid[0], list)
        and 1 <= len(grid[0]) <= 30
        and all(
            isinstance(row, list)
            and len(row) == len(grid[0])
            and all(type(cell) is int and 0 <= cell <= 9 for cell in row)
            for row in grid
        )
    )


def _scope_paths(scope: Any, label: str, findings: list[str]) -> list[str]:
    if not isinstance(scope, dict) or frozenset(scope) != _FILE_SCOPE_FIELDS:
        findings.append(f"{label} fields mismatch")
        return []
    files = scope.get("files")
    if not isinstance(files, list) or not files:
        findings.append(f"{label}.files invalid")
        return []
    paths: list[str] = []
    for index, record in enumerate(files):
        if not isinstance(record, dict) or frozenset(record) != _FILE_FIELDS:
            findings.append(f"{label}.files[{index}] fields mismatch")
            continue
        path = record.get("path")
        if (
            not isinstance(path, str)
            or not path
            or "\\" in path
            or Path(path).is_absolute()
            or "." in Path(path).parts
            or ".." in Path(path).parts
        ):
            findings.append(f"{label}.files[{index}].path invalid")
        else:
            paths.append(path)
        if type(record.get("bytes")) is not int or record["bytes"] < 0:
            findings.append(f"{label}.files[{index}].bytes invalid")
        digest = record.get("sha256")
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            findings.append(f"{label}.files[{index}].sha256 invalid")
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        findings.append(f"{label}.files must be sorted and unique")
    try:
        expected = hashlib.sha256(canonical_json_bytes(files)).hexdigest()
    except Exception:
        findings.append(f"{label}.files not canonical")
    else:
        if scope.get("content_sha256") != expected:
            findings.append(f"{label}.content_sha256 mismatch")
    return paths


def _record_map(scope: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(record["path"]): record
        for record in scope["files"]
        if isinstance(record, Mapping) and isinstance(record.get("path"), str)
    }


def validate_prediction_manifest(value: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    if not isinstance(value, Mapping) or frozenset(value) != ROOT_FIELDS:
        return ["prediction manifest fields mismatch"]
    if value.get("schema_version") != SCHEMA:
        findings.append("prediction schema mismatch")
    if value.get("split") != "public_evaluation":
        findings.append("prediction split mismatch")
    if value.get("claim_scope") != (
        "contamination_exposed_public_evaluation_development"
    ):
        findings.append("prediction claim_scope mismatch")

    config = value.get("config")
    if not isinstance(config, dict) or frozenset(config) != CONFIG_FIELDS:
        findings.append("prediction config fields mismatch")
        config = {}
    limit = config.get("limit")
    if type(limit) is not int or not 0 <= limit <= OFFICIAL_EVALUATION_COUNT:
        findings.append("prediction config.limit invalid")
        limit = -1
    budget = config.get("time_budget_seconds_per_task")
    if (
        type(budget) not in (int, float)
        or not math.isfinite(float(budget))
        or not 0.01 <= float(budget) <= 60.0
    ):
        findings.append("prediction time budget invalid")
    if config.get("attempts_per_test_input") != 1:
        findings.append("prediction attempts must equal one")
    if config.get("gold_in_candidate_payload") is not False:
        findings.append("gold_in_candidate_payload must be false")

    source_paths = _scope_paths(value.get("source"), "source", findings)
    if tuple(source_paths) != ARC_CANDIDATE_PATHS:
        findings.append("candidate source scope is not the canonical closure")
    dataset_paths = _scope_paths(value.get("dataset"), "dataset", findings)
    if (
        len(dataset_paths) != OFFICIAL_EVALUATION_COUNT
        or any(
            not path.startswith(OFFICIAL_EVALUATION_PREFIX)
            or _ARC_NAME_RE.fullmatch(path.removeprefix(OFFICIAL_EVALUATION_PREFIX))
            is None
            for path in dataset_paths
        )
        or value.get("dataset", {}).get("content_sha256")
        != OFFICIAL_EVALUATION_CONTENT_SHA256
    ):
        findings.append("dataset is not the pinned official 400-task inventory")

    selected_count = (
        OFFICIAL_EVALUATION_COUNT if limit == 0 else max(limit, 0)
    )
    expected_paths = dataset_paths[:selected_count]
    records = _record_map(value.get("dataset", {}))
    expected_ids = [
        item_id(
            {
                "dataset_path": path,
                "dataset_file_sha256": records[path]["sha256"],
            }
        )
        for path in expected_paths
        if path in records
    ]
    selection = value.get("selection")
    if not isinstance(selection, dict) or frozenset(selection) != SELECTION_FIELDS:
        findings.append("prediction selection fields mismatch")
        selection = {}
    if selection.get("full_official_inventory") is not (limit == 0):
        findings.append("prediction full_official_inventory mismatch")
    if selection.get("selected_dataset_paths") != expected_paths:
        findings.append("prediction selected paths do not match config/inventory")
    if selection.get("selected_item_ids") != expected_ids:
        findings.append("prediction selected item IDs mismatch")
    try:
        expected_id_digest = hashlib.sha256(
            canonical_json_bytes(expected_ids)
        ).hexdigest()
    except Exception:
        expected_id_digest = None
    if selection.get("selected_item_ids_sha256") != expected_id_digest:
        findings.append("prediction selected item digest mismatch")

    rows = value.get("items")
    if not isinstance(rows, list) or not rows:
        findings.append("prediction items must be non-empty")
        rows = []
    if len(rows) != selected_count:
        findings.append("prediction item count does not match selection")
    for index, row in enumerate(rows):
        label = f"items[{index}]"
        if not isinstance(row, dict) or frozenset(row) != ITEM_FIELDS:
            findings.append(f"{label} fields mismatch")
            continue
        if index >= len(expected_paths):
            findings.append(f"{label} exceeds declared selection")
            continue
        expected_path = expected_paths[index]
        if row.get("dataset_path") != expected_path:
            findings.append(f"{label}.dataset_path mismatch")
        if row.get("task_id") != Path(expected_path).stem:
            findings.append(f"{label}.task_id mismatch")
        if row.get("item_id") != expected_ids[index]:
            findings.append(f"{label}.item_id mismatch")
        status = row.get("status")
        if status not in {"emitted", "abstain", "error"}:
            findings.append(f"{label}.status invalid")
        test_count = row.get("test_case_count")
        valid_count = row.get("valid_prediction_count")
        if (
            type(test_count) is not int
            or not 1 <= test_count <= 64
            or type(valid_count) is not int
            or not 0 <= valid_count <= test_count
        ):
            findings.append(f"{label} test counts invalid")
        latency = row.get("latency_ms")
        if (
            type(latency) not in (int, float)
            or not math.isfinite(float(latency))
            or not 0 <= float(latency) <= 86_400_000
        ):
            findings.append(f"{label} latency invalid")
        predictions = row.get("predictions")
        if status == "emitted":
            if (
                not isinstance(predictions, list)
                or type(test_count) is not int
                or len(predictions) != test_count
                or valid_count != test_count
                or any(not _valid_grid(grid) for grid in predictions)
                or row.get("error_type") is not None
            ):
                findings.append(f"{label} emitted payload invalid")
        else:
            if predictions is not None:
                findings.append(f"{label} non-emitted predictions must be null")
            if status == "abstain" and row.get("error_type") is not None:
                findings.append(f"{label} abstention error_type must be null")
            if status == "error" and not isinstance(row.get("error_type"), str):
                findings.append(f"{label} error requires error_type")

    integrity = value.get("integrity")
    if not isinstance(integrity, dict) or frozenset(integrity) != INTEGRITY_FIELDS:
        findings.append("prediction integrity fields mismatch")
    else:
        expected_literals = {
            "source_same_before_after": True,
            "dataset_same_before_after": True,
            "network_isolation_enforced": False,
            "gold_filesystem_isolated": False,
            "scored_in_emitter": False,
            "externally_anchored": False,
        }
        for field, expected in expected_literals.items():
            if integrity.get(field) is not expected:
                findings.append(f"prediction integrity.{field} mismatch")
        limitations = integrity.get("limitations")
        if (
            not isinstance(limitations, list)
            or not limitations
            or any(not isinstance(item, str) or not item.strip() for item in limitations)
        ):
            findings.append("prediction integrity.limitations invalid")

    digest = value.get("manifest_checksum_sha256")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        findings.append("prediction manifest checksum invalid")
    else:
        try:
            expected = prediction_manifest_checksum(value)
        except Exception:
            findings.append("prediction manifest is not canonical")
        else:
            if digest != expected:
                findings.append("prediction manifest checksum mismatch")
    return findings
