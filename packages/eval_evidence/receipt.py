"""Bounded, unsigned, item-level benchmark measurement receipts.

This module deliberately does *not* create evaluation authority.  A receipt
binds declared source, candidate, and dataset bytes; records one outcome per
declared item; derives a small fixed metric set; and carries a recomputable
checksum.  It is useful for reproducing local measurements and detecting
accidental drift.  It is not a signature, a hidden-set attestation, an E5
result, or proof that the bound files are the code that executed.

Schema v2 makes those limitations structural.  The legacy v1 reader remains
available so already-written evidence does not disappear when the contract is
strengthened.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


LEGACY_BENCHMARK_EVIDENCE_SCHEMA = "atanor.benchmark-evidence.v1"
BENCHMARK_EVIDENCE_SCHEMA = "atanor.benchmark-evidence.v2"
BENCHMARK_EVIDENCE_KIND = "unsigned_self_measured_checksum_receipt"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,255}$")
_STATUSES = frozenset({"correct", "wrong", "abstain", "error"})
_MAX_MANIFEST_BYTES = 128 * 1024 * 1024
_MAX_ITEMS = 100_000
_MAX_BOUND_FILES = 100_000
_MAX_METADATA_BYTES = 32 * 1024
_MAX_DESCRIPTOR_BYTES = 128 * 1024
_MAX_LATENCY_MS = 86_400_000

_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_kind",
        "run_id",
        "started_at",
        "completed_at",
        "benchmark",
        "config",
        "environment",
        "source",
        "candidate",
        "dataset",
        "selection",
        "evaluator",
        "metrics",
        "items",
        "integrity",
        "manifest_checksum_sha256",
    }
)
_LEGACY_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_kind",
        "run_id",
        "started_at",
        "completed_at",
        "benchmark",
        "config",
        "environment",
        "source",
        "dataset",
        "evaluator",
        "metrics",
        "items",
        "integrity",
        "manifest_hash",
    }
)
_FILE_SCOPE_FIELDS = frozenset({"files", "content_sha256"})
_FILE_FIELDS = frozenset({"path", "bytes", "sha256"})
_SELECTION_FIELDS = frozenset(
    {
        "coverage_scope",
        "expected_item_count",
        "item_ids",
        "item_ids_sha256",
    }
)
_ITEM_FIELDS = frozenset(
    {
        "item_id",
        "status",
        "fired",
        "correct",
        "output_sha256",
        "latency_ms",
        "metadata",
    }
)
_METRIC_FIELDS = frozenset(
    {
        "n",
        "correct",
        "wrong",
        "abstain",
        "error",
        "fired",
        "strict_accuracy",
        "coverage",
        "fired_accuracy",
        "outcome_digest_sha256",
    }
)
_LEGACY_METRIC_FIELDS = _METRIC_FIELDS | {"extra"}
_EVALUATOR_FIELDS = frozenset(
    {
        "identity",
        "source_digest_sha256",
        "independent",
        "externally_signed",
        "limitations",
    }
)
_INTEGRITY_FIELDS = frozenset(
    {
        "source_same_before_after",
        "candidate_same_before_after",
        "dataset_same_before_after",
        "network_isolation_enforced",
        "shipped_state_isolation_enforced",
        "production_authority",
        "e5_claimed",
        "limitations",
    }
)
_LEGACY_INTEGRITY_FIELDS = frozenset(
    {
        "source_unchanged_during_run",
        "dataset_unchanged_during_run",
        "network_used",
        "shipped_state_mutated",
        "production_authority",
        "e5_claimed",
        "limitations",
    }
)
_ENVIRONMENT_FIELDS = frozenset(
    {
        "python",
        "implementation",
        "platform",
        "machine",
        "processor",
        "logical_cpu_count",
        "python_hash_seed",
    }
)


class BenchmarkEvidenceError(RuntimeError):
    """Raised when local measurement evidence is unsafe or malformed."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise BenchmarkEvidenceError("value is not bounded finite canonical JSON") from exc


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BenchmarkEvidenceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise BenchmarkEvidenceError(f"non-finite JSON number: {token}")


def strict_json_bytes(payload: bytes, *, label: str = "evidence") -> dict[str, Any]:
    """Parse one bounded JSON object from the exact supplied bytes."""
    if not isinstance(payload, bytes) or len(payload) > _MAX_MANIFEST_BYTES:
        raise BenchmarkEvidenceError(f"{label} exceeds the bounded JSON size")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_nonfinite,
        )
    except BenchmarkEvidenceError:
        raise
    except (
        UnicodeError,
        json.JSONDecodeError,
        RecursionError,
        OverflowError,
    ) as exc:
        raise BenchmarkEvidenceError(
            f"{label} is not strict readable JSON: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise BenchmarkEvidenceError(f"{label} root must be an object")
    return value


def _strict_json(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
        if size > _MAX_MANIFEST_BYTES:
            raise BenchmarkEvidenceError("evidence exceeds the bounded JSON size")
        payload = path.read_bytes()
    except BenchmarkEvidenceError:
        raise
    except OSError as exc:
        raise BenchmarkEvidenceError(
            f"evidence is not readable: {type(exc).__name__}"
        ) from exc
    return strict_json_bytes(payload)


def _safe_repo_file(repo_root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise BenchmarkEvidenceError("bound paths must be non-empty POSIX paths")
    lexical = Path(relative)
    if (
        lexical.is_absolute()
        or "." in lexical.parts
        or ".." in lexical.parts
        or any(
            ":" in part or part.endswith(".") or part.endswith(" ")
            for part in lexical.parts
        )
    ):
        raise BenchmarkEvidenceError(f"unsafe bound path: {relative}")
    repo = repo_root.resolve(strict=True)
    candidate = repo / lexical
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(repo)
    except (OSError, ValueError) as exc:
        raise BenchmarkEvidenceError(
            f"bound path is missing or escapes repository: {relative}"
        ) from exc
    if candidate.is_symlink() or not resolved.is_file():
        raise BenchmarkEvidenceError(f"bound path is not a regular file: {relative}")
    return resolved


def _hash_open_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise BenchmarkEvidenceError(
            f"bound file could not be hashed: {path.name}: {type(exc).__name__}"
        ) from exc
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise BenchmarkEvidenceError(f"bound file changed while hashing: {path.name}")
    return int(after.st_size), digest.hexdigest()


def bind_files(repo_root: Path, paths: Iterable[str]) -> dict[str, Any]:
    """Bind sorted repository files to one descriptive content digest."""
    try:
        normalized = sorted(paths)
    except TypeError as exc:
        raise BenchmarkEvidenceError("bound file list is not sortable") from exc
    identity_keys = [str(path).casefold() for path in normalized]
    if (
        not normalized
        or len(normalized) > _MAX_BOUND_FILES
        or len(normalized) != len(set(normalized))
        or len(identity_keys) != len(set(identity_keys))
    ):
        raise BenchmarkEvidenceError(
            "bound file list must be bounded, non-empty, and identity-unique"
        )
    records = []
    resolved_identities: set[str] = set()
    for relative in normalized:
        path = _safe_repo_file(repo_root, relative)
        resolved_key = os.path.normcase(str(path))
        if resolved_key in resolved_identities:
            raise BenchmarkEvidenceError("bound files alias the same resolved path")
        resolved_identities.add(resolved_key)
        size, digest = _hash_open_file(path)
        records.append({"path": relative, "bytes": size, "sha256": digest})
    return {
        "files": records,
        "content_sha256": hashlib.sha256(canonical_json_bytes(records)).hexdigest(),
    }


def item_id(value: Mapping[str, Any]) -> str:
    """Create a content-derived pseudonymous identifier."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def selection_record(
    items: Sequence[Mapping[str, Any]],
    *,
    coverage_scope: str = "declared_selection_only",
) -> dict[str, Any]:
    identifiers = []
    for index, row in enumerate(items):
        if not isinstance(row, Mapping):
            raise BenchmarkEvidenceError(f"items[{index}] is not an object")
        identifier = row.get("item_id")
        if not isinstance(identifier, str) or _SHA256_RE.fullmatch(identifier) is None:
            raise BenchmarkEvidenceError(f"items[{index}].item_id invalid")
        identifiers.append(identifier)
    if not identifiers or len(identifiers) != len(set(identifiers)):
        raise BenchmarkEvidenceError("selection item IDs must be non-empty and unique")
    return {
        "coverage_scope": coverage_scope,
        "expected_item_count": len(identifiers),
        "item_ids": identifiers,
        "item_ids_sha256": hashlib.sha256(
            canonical_json_bytes(identifiers)
        ).hexdigest(),
    }


def _round_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 12)


def outcome_digest(items: Sequence[Mapping[str, Any]]) -> str:
    deterministic = []
    for index, row in enumerate(items):
        if not isinstance(row, Mapping):
            raise BenchmarkEvidenceError(f"items[{index}] is not an object")
        deterministic.append(
            {
                "item_id": row.get("item_id"),
                "status": row.get("status"),
                "fired": row.get("fired"),
                "correct": row.get("correct"),
                "output_sha256": row.get("output_sha256"),
                "metadata": row.get("metadata"),
            }
        )
    return hashlib.sha256(canonical_json_bytes(deterministic)).hexdigest()


def aggregate_items(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise BenchmarkEvidenceError("items must be a sequence of objects")
    if not items or len(items) > _MAX_ITEMS:
        raise BenchmarkEvidenceError("items must be non-empty and bounded")
    counts = {status: 0 for status in sorted(_STATUSES)}
    fired = 0
    for index, row in enumerate(items):
        if not isinstance(row, Mapping):
            raise BenchmarkEvidenceError(f"items[{index}] is not an object")
        status = row.get("status")
        if status not in _STATUSES:
            raise BenchmarkEvidenceError(f"invalid item status: {status!r}")
        counts[str(status)] += 1
        fired += int(row.get("fired") is True)
    n = len(items)
    return {
        "n": n,
        "correct": counts["correct"],
        "wrong": counts["wrong"],
        "abstain": counts["abstain"],
        "error": counts["error"],
        "fired": fired,
        "strict_accuracy": _round_ratio(counts["correct"], n),
        "coverage": _round_ratio(fired, n),
        "fired_accuracy": _round_ratio(counts["correct"], fired),
        "outcome_digest_sha256": outcome_digest(items),
    }


def environment_record() -> dict[str, Any]:
    return {
        "python": sys.version,
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
    }


def _manifest_checksum(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_checksum_sha256", None)
    return hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()


def _legacy_manifest_hash(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_hash", None)
    return hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()


def finalize_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a v2 receipt with a recomputable checksum, not a signature."""
    try:
        detached = json.loads(canonical_json_bytes(payload))
    except (json.JSONDecodeError, RecursionError) as exc:  # pragma: no cover
        raise BenchmarkEvidenceError("payload detach failed") from exc
    if (
        not isinstance(detached, dict)
        or "manifest_checksum_sha256" in detached
        or detached.get("schema_version") != BENCHMARK_EVIDENCE_SCHEMA
    ):
        raise BenchmarkEvidenceError(
            "payload must be a v2 object without manifest_checksum_sha256"
        )
    detached["manifest_checksum_sha256"] = _manifest_checksum(detached)
    findings = validate_manifest(detached)
    if findings:
        raise BenchmarkEvidenceError("; ".join(findings))
    return detached


def write_manifest_exclusive(path: Path, manifest: Mapping[str, Any]) -> None:
    """Write once at this path; this does not make the bytes append-only."""
    payload = canonical_json_bytes(manifest) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise BenchmarkEvidenceError(f"evidence path already exists: {path}") from exc


def ensure_safe_report_output(repo_root: Path, output: Path) -> Path:
    """Reject outputs inside the repository except reports/benchmarks."""
    repo = repo_root.resolve(strict=True)
    resolved = output.resolve(strict=False)
    try:
        relative = resolved.relative_to(repo)
    except ValueError:
        return resolved
    allowed = Path("reports") / "benchmarks"
    if relative == allowed or allowed not in relative.parents:
        raise BenchmarkEvidenceError(
            "repository-local evidence output must stay under reports/benchmarks"
        )
    return resolved


def _nonempty_text(value: Any, *, maximum: int = 4096) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _finite_nonnegative(value: Any) -> bool:
    if type(value) is int:
        return 0 <= value <= _MAX_LATENCY_MS
    if type(value) is float:
        return math.isfinite(value) and 0.0 <= value <= _MAX_LATENCY_MS
    return False


def _bounded_descriptor(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        return len(canonical_json_bytes(value)) <= _MAX_DESCRIPTOR_BYTES
    except BenchmarkEvidenceError:
        return False


def _valid_limitations(value: Any) -> bool:
    return (
        isinstance(value, list)
        and 1 <= len(value) <= 100
        and all(_nonempty_text(item, maximum=2000) for item in value)
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if not _nonempty_text(value, maximum=64) or not str(value).endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(str(value)[:-1] + "+00:00")
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        return None
    return parsed


def _validate_file_scope(scope: Any, label: str, findings: list[str]) -> None:
    if not isinstance(scope, dict) or frozenset(scope) != _FILE_SCOPE_FIELDS:
        findings.append(f"{label} fields mismatch")
        return
    files = scope.get("files")
    if (
        not isinstance(files, list)
        or not files
        or len(files) > _MAX_BOUND_FILES
    ):
        findings.append(f"{label}.files must be a bounded non-empty list")
        return
    paths: list[str] = []
    identity_keys: list[str] = []
    for index, record in enumerate(files):
        if not isinstance(record, dict) or frozenset(record) != _FILE_FIELDS:
            findings.append(f"{label}.files[{index}] fields mismatch")
            continue
        relative = record.get("path")
        if (
            not _nonempty_text(relative)
            or "\\" in str(relative)
            or Path(str(relative)).is_absolute()
            or "." in Path(str(relative)).parts
            or ".." in Path(str(relative)).parts
            or any(
                ":" in part or part.endswith(".") or part.endswith(" ")
                for part in Path(str(relative)).parts
            )
        ):
            findings.append(f"{label}.files[{index}].path invalid")
        else:
            paths.append(str(relative))
            identity_keys.append(str(relative).casefold())
        if type(record.get("bytes")) is not int or record["bytes"] < 0:
            findings.append(f"{label}.files[{index}].bytes invalid")
        digest = record.get("sha256")
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            findings.append(f"{label}.files[{index}].sha256 invalid")
    if (
        paths != sorted(paths)
        or len(paths) != len(set(paths))
        or len(identity_keys) != len(set(identity_keys))
    ):
        findings.append(f"{label}.files must be sorted and identity-unique")
    try:
        expected = hashlib.sha256(canonical_json_bytes(files)).hexdigest()
    except BenchmarkEvidenceError:
        findings.append(f"{label}.files are not canonical")
    else:
        if scope.get("content_sha256") != expected:
            findings.append(f"{label}.content_sha256 mismatch")


def _validate_item(row: Any, index: int, findings: list[str]) -> None:
    label = f"items[{index}]"
    if not isinstance(row, dict) or frozenset(row) != _ITEM_FIELDS:
        findings.append(f"{label} fields mismatch")
        return
    identifier = row.get("item_id")
    if not isinstance(identifier, str) or _SHA256_RE.fullmatch(identifier) is None:
        findings.append(f"{label}.item_id invalid")
    status = row.get("status")
    if status not in _STATUSES:
        findings.append(f"{label}.status invalid")
        return
    if type(row.get("fired")) is not bool or type(row.get("correct")) is not bool:
        findings.append(f"{label} booleans must be literal")
        return
    expected = {
        "correct": (True, True),
        "wrong": (True, False),
        "abstain": (False, False),
        "error": (False, False),
    }[status]
    if (row["fired"], row["correct"]) != expected:
        findings.append(f"{label} status/boolean combination invalid")
    output_digest = row.get("output_sha256")
    if row["fired"]:
        if not isinstance(output_digest, str) or _SHA256_RE.fullmatch(
            output_digest
        ) is None:
            findings.append(f"{label}.output_sha256 required when fired")
    elif output_digest is not None:
        findings.append(f"{label}.output_sha256 must be null when not fired")
    if not _finite_nonnegative(row.get("latency_ms")):
        findings.append(f"{label}.latency_ms invalid")
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        findings.append(f"{label}.metadata must be an object")
    else:
        try:
            if len(canonical_json_bytes(metadata)) > _MAX_METADATA_BYTES:
                findings.append(f"{label}.metadata too large")
        except BenchmarkEvidenceError:
            findings.append(f"{label}.metadata is not bounded canonical JSON")


def _validate_selection(
    selection: Any,
    items: Sequence[Any],
    findings: list[str],
) -> None:
    if not isinstance(selection, dict) or frozenset(selection) != _SELECTION_FIELDS:
        findings.append("selection fields mismatch")
        return
    if selection.get("coverage_scope") != "declared_selection_only":
        findings.append("selection.coverage_scope must be declared_selection_only")
    identifiers = [
        row.get("item_id")
        for row in items
        if isinstance(row, dict) and isinstance(row.get("item_id"), str)
    ]
    supplied = selection.get("item_ids")
    if (
        not isinstance(supplied, list)
        or not supplied
        or len(supplied) > _MAX_ITEMS
        or any(
            not isinstance(identifier, str)
            or _SHA256_RE.fullmatch(identifier) is None
            for identifier in supplied
        )
        or len(supplied) != len(set(supplied))
    ):
        findings.append("selection.item_ids invalid")
        return
    if type(selection.get("expected_item_count")) is not int:
        findings.append("selection.expected_item_count invalid")
    elif selection["expected_item_count"] != len(supplied):
        findings.append("selection.expected_item_count mismatch")
    if supplied != identifiers:
        findings.append("selection does not exactly match item order")
    try:
        expected = hashlib.sha256(canonical_json_bytes(supplied)).hexdigest()
    except BenchmarkEvidenceError:
        findings.append("selection.item_ids not canonical")
    else:
        if selection.get("item_ids_sha256") != expected:
            findings.append("selection.item_ids_sha256 mismatch")


def _validate_v2_manifest(manifest: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    if not isinstance(manifest, Mapping) or frozenset(manifest) != _ROOT_FIELDS:
        return ["manifest fields mismatch"]
    if manifest.get("schema_version") != BENCHMARK_EVIDENCE_SCHEMA:
        findings.append("schema_version mismatch")
    if manifest.get("evidence_kind") != BENCHMARK_EVIDENCE_KIND:
        findings.append("evidence_kind mismatch")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        findings.append("run_id invalid")
    started = _parse_timestamp(manifest.get("started_at"))
    completed = _parse_timestamp(manifest.get("completed_at"))
    if started is None:
        findings.append("started_at invalid")
    if completed is None:
        findings.append("completed_at invalid")
    if started is not None and completed is not None and completed < started:
        findings.append("completed_at precedes started_at")
    for field in ("benchmark", "config"):
        if not _bounded_descriptor(manifest.get(field)):
            findings.append(f"{field} must be a bounded object")
    environment = manifest.get("environment")
    if (
        not isinstance(environment, dict)
        or frozenset(environment) != _ENVIRONMENT_FIELDS
        or not _bounded_descriptor(environment)
    ):
        findings.append("environment fields mismatch")
    _validate_file_scope(manifest.get("source"), "source", findings)
    _validate_file_scope(manifest.get("candidate"), "candidate", findings)
    _validate_file_scope(manifest.get("dataset"), "dataset", findings)

    evaluator = manifest.get("evaluator")
    if not isinstance(evaluator, dict) or frozenset(evaluator) != _EVALUATOR_FIELDS:
        findings.append("evaluator fields mismatch")
    else:
        if not _nonempty_text(evaluator.get("identity")):
            findings.append("evaluator.identity invalid")
        digest = evaluator.get("source_digest_sha256")
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            findings.append("evaluator.source_digest_sha256 invalid")
        elif digest != manifest.get("source", {}).get("content_sha256"):
            findings.append("evaluator source digest is not bound to source scope")
        if evaluator.get("independent") is not False:
            findings.append("evaluator.independent must be literal false")
        if evaluator.get("externally_signed") is not False:
            findings.append("evaluator.externally_signed must be literal false")
        if not _valid_limitations(evaluator.get("limitations")):
            findings.append("evaluator.limitations invalid")

    items = manifest.get("items")
    if not isinstance(items, list) or not items or len(items) > _MAX_ITEMS:
        findings.append("items must be a bounded non-empty list")
        items = []
    for index, row in enumerate(items):
        _validate_item(row, index, findings)
    identifiers = [
        row.get("item_id")
        for row in items
        if isinstance(row, dict) and isinstance(row.get("item_id"), str)
    ]
    if len(identifiers) != len(set(identifiers)):
        findings.append("item_id values must be unique")
    _validate_selection(manifest.get("selection"), items, findings)

    metrics = manifest.get("metrics")
    if not isinstance(metrics, dict) or frozenset(metrics) != _METRIC_FIELDS:
        findings.append("metrics fields mismatch")
    elif items:
        try:
            expected_metrics = aggregate_items(items)
        except BenchmarkEvidenceError as exc:
            findings.append(str(exc))
        else:
            if metrics != expected_metrics:
                findings.append("metrics do not derive from item outcomes")

    integrity = manifest.get("integrity")
    if not isinstance(integrity, dict) or frozenset(integrity) != _INTEGRITY_FIELDS:
        findings.append("integrity fields mismatch")
    else:
        required_true = (
            "source_same_before_after",
            "candidate_same_before_after",
            "dataset_same_before_after",
        )
        required_false = (
            "network_isolation_enforced",
            "shipped_state_isolation_enforced",
            "production_authority",
            "e5_claimed",
        )
        for field in (*required_true, *required_false):
            if type(integrity.get(field)) is not bool:
                findings.append(f"integrity.{field} must be literal boolean")
        for field in required_true:
            if integrity.get(field) is not True:
                findings.append(f"integrity.{field} must be true")
        for field in required_false:
            if integrity.get(field) is not False:
                findings.append(f"integrity.{field} must be false")
        if not _valid_limitations(integrity.get("limitations")):
            findings.append("integrity.limitations invalid")

    digest = manifest.get("manifest_checksum_sha256")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        findings.append("manifest_checksum_sha256 invalid")
    else:
        try:
            expected_digest = _manifest_checksum(manifest)
        except BenchmarkEvidenceError:
            findings.append("manifest is not canonical")
        else:
            if digest != expected_digest:
                findings.append("manifest checksum mismatch")
    return findings


def _legacy_aggregate(
    items: Sequence[Mapping[str, Any]],
    extra: Mapping[str, Any],
) -> dict[str, Any]:
    value = aggregate_items(items)
    value["extra"] = dict(extra)
    return value


def _validate_legacy_manifest(manifest: Mapping[str, Any]) -> list[str]:
    """Strictly read the two v1 shapes that were already emitted."""
    findings: list[str] = []
    fields = frozenset(manifest) if isinstance(manifest, Mapping) else frozenset()
    allowed = {_LEGACY_ROOT_FIELDS, _LEGACY_ROOT_FIELDS | {"candidate"}}
    if fields not in allowed:
        return ["legacy manifest fields mismatch"]
    if manifest.get("schema_version") != LEGACY_BENCHMARK_EVIDENCE_SCHEMA:
        findings.append("legacy schema_version mismatch")
    if manifest.get("evidence_kind") != "unsigned_source_bound_measurement":
        findings.append("legacy evidence_kind mismatch")
    _validate_file_scope(manifest.get("source"), "source", findings)
    _validate_file_scope(manifest.get("dataset"), "dataset", findings)
    if "candidate" in manifest:
        _validate_file_scope(manifest.get("candidate"), "candidate", findings)
    items = manifest.get("items")
    if not isinstance(items, list) or not items or len(items) > _MAX_ITEMS:
        findings.append("legacy items must be a bounded non-empty list")
        items = []
    for index, row in enumerate(items):
        _validate_item(row, index, findings)
    metrics = manifest.get("metrics")
    if not isinstance(metrics, dict) or frozenset(metrics) != _LEGACY_METRIC_FIELDS:
        findings.append("legacy metrics fields mismatch")
    elif items and isinstance(metrics.get("extra"), dict):
        try:
            expected = _legacy_aggregate(items, metrics["extra"])
        except BenchmarkEvidenceError as exc:
            findings.append(str(exc))
        else:
            if metrics != expected:
                findings.append("legacy metrics do not derive from item outcomes")
    else:
        findings.append("legacy metrics.extra must be an object")
    integrity = manifest.get("integrity")
    allowed_integrity = {
        _LEGACY_INTEGRITY_FIELDS,
        _LEGACY_INTEGRITY_FIELDS | {"candidate_unchanged_during_run"},
    }
    if not isinstance(integrity, dict) or frozenset(integrity) not in allowed_integrity:
        findings.append("legacy integrity fields mismatch")
    digest = manifest.get("manifest_hash")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        findings.append("legacy manifest_hash invalid")
    else:
        try:
            expected_digest = _legacy_manifest_hash(manifest)
        except BenchmarkEvidenceError:
            findings.append("legacy manifest is not canonical")
        else:
            if digest != expected_digest:
                findings.append("legacy manifest_hash mismatch")
    return findings


def validate_manifest(manifest: Mapping[str, Any]) -> list[str]:
    """Validate v2 or historical v1 without authenticating the producer."""
    try:
        if (
            isinstance(manifest, Mapping)
            and manifest.get("schema_version") == LEGACY_BENCHMARK_EVIDENCE_SCHEMA
        ):
            return _validate_legacy_manifest(manifest)
        return _validate_v2_manifest(manifest)
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        RecursionError,
        BenchmarkEvidenceError,
    ) as exc:
        return [f"manifest validation failed closed: {type(exc).__name__}"]


def _scope_matches_current(scope: Any, *, repo_root: Path) -> bool:
    if not isinstance(scope, Mapping):
        return False
    try:
        files = scope.get("files")
        if not isinstance(files, list):
            return False
        current = bind_files(
            repo_root,
            [record["path"] for record in files if isinstance(record, Mapping)],
        )
    except (BenchmarkEvidenceError, KeyError, TypeError, ValueError):
        return False
    return current == scope


def verify_manifest(
    path: Path,
    *,
    repo_root: Path,
    require_current: bool = True,
) -> dict[str, Any]:
    """Verify structure/checksum and, by default, all current file bindings."""
    try:
        manifest = _strict_json(path)
        findings = validate_manifest(manifest)
    except BenchmarkEvidenceError as exc:
        return {
            "valid": False,
            "structure_valid": False,
            "matches_current": False,
            "authenticity_established": False,
            "checksum_sha256": None,
            "source_matches_current": False,
            "candidate_matches_current": False,
            "dataset_matches_current": False,
            "findings": [str(exc)],
        }
    structure_valid = not findings
    source_current = _scope_matches_current(manifest.get("source"), repo_root=repo_root)
    candidate_scope = manifest.get("candidate", manifest.get("source"))
    candidate_current = _scope_matches_current(candidate_scope, repo_root=repo_root)
    dataset_current = _scope_matches_current(
        manifest.get("dataset"),
        repo_root=repo_root,
    )
    matches_current = source_current and candidate_current and dataset_current
    if require_current:
        if not source_current:
            findings.append("source does not match current tree")
        if not candidate_current:
            findings.append("candidate does not match current tree")
        if not dataset_current:
            findings.append("dataset does not match current tree")
    checksum = manifest.get(
        "manifest_checksum_sha256",
        manifest.get("manifest_hash"),
    )
    return {
        "valid": not findings,
        "structure_valid": structure_valid,
        "matches_current": matches_current,
        "authenticity_established": False,
        "checksum_sha256": checksum,
        "source_matches_current": source_current,
        "candidate_matches_current": candidate_current,
        "dataset_matches_current": dataset_current,
        "findings": findings,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )
