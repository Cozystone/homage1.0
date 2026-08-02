"""Fresh-process LiveMemory -> RealTimeThinker candidate worker.

The parent sends facts, source identifiers, questions, and an explicitly empty
static-evidence list.  It does not send gold answers or grading logic.  Every
invocation creates fresh temporary hippocampus, cortex, and miss-log paths.

This worker is part of an unsigned, local development measurement.  The
subprocess still has ambient repository/filesystem/network access; the
temporary paths are state-isolation hygiene, not an OS sandbox or attestation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from packages.eval_evidence.receipt import (  # noqa: E402
    BenchmarkEvidenceError,
    canonical_json_bytes,
    strict_json_bytes,
)


REQUEST_SCHEMA = "atanor.live-memory-realtime-candidate-request.v1"
RESULT_SCHEMA = "atanor.live-memory-realtime-candidate-result.v1"

_MAX_REQUEST_BYTES = 16 * 1024 * 1024
_MAX_ITEMS = 2_000
_MAX_TEXT = 16_384
_MAX_ANSWER = 16_384
_MAX_SUPPORT = 64
_SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,255}$")
_CHECKPOINT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,255}\.pt$")
_DEVICE_POLICIES = frozenset({"cpu_only", "native_auto", "cuda_required"})

_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "condition",
        "checkpoint",
        "device_policy",
        "config",
        "learn",
        "questions",
        "static_paragraphs",
    }
)
_CONFIG_FIELDS = frozenset({"threshold", "k", "min_overlap", "k_live"})
_LEARN_FIELDS = frozenset({"fact", "source_id"})
_QUESTION_FIELDS = frozenset({"index", "question"})
_RESULT_FIELDS = frozenset(
    {
        "index",
        "emitted",
        "answer",
        "used_live",
        "grounded",
        "confidence",
        "support",
        "evidence",
        "recall_top_source",
        "recall_top_fact_sha256",
        "error_type",
        "latency_ms",
    }
)


def _bounded_text(value: Any, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= _MAX_TEXT
        and (allow_empty or bool(value.strip()))
    )


def _finite_between(value: Any, low: float, high: float) -> bool:
    return (
        type(value) in (int, float)
        and not isinstance(value, bool)
        and float(value) == float(value)
        and low <= float(value) <= high
    )


def _validate_request(value: dict[str, Any]) -> dict[str, Any]:
    if frozenset(value) != _ROOT_FIELDS:
        raise BenchmarkEvidenceError("worker request fields mismatch")
    if value.get("schema_version") != REQUEST_SCHEMA:
        raise BenchmarkEvidenceError("worker request schema mismatch")

    condition = value.get("condition")
    if condition not in {"OFF", "ON"}:
        raise BenchmarkEvidenceError("worker condition must be OFF or ON")
    checkpoint = value.get("checkpoint")
    if not isinstance(checkpoint, str) or _CHECKPOINT_RE.fullmatch(checkpoint) is None:
        raise BenchmarkEvidenceError("worker checkpoint must be a safe .pt basename")
    device_policy = value.get("device_policy")
    if device_policy not in _DEVICE_POLICIES:
        raise BenchmarkEvidenceError("worker device policy invalid")

    config = value.get("config")
    if not isinstance(config, dict) or frozenset(config) != _CONFIG_FIELDS:
        raise BenchmarkEvidenceError("worker config fields mismatch")
    if not _finite_between(config.get("threshold"), 0.0, 1.0):
        raise BenchmarkEvidenceError("worker threshold invalid")
    for field, maximum in (("k", 64), ("min_overlap", 64), ("k_live", 64)):
        candidate = config.get(field)
        if type(candidate) is not int or not 1 <= candidate <= maximum:
            raise BenchmarkEvidenceError(f"worker {field} invalid")

    learn = value.get("learn")
    if not isinstance(learn, list) or len(learn) > _MAX_ITEMS:
        raise BenchmarkEvidenceError("worker learn list invalid")
    if condition == "OFF" and learn:
        raise BenchmarkEvidenceError("OFF worker request must not contain learned facts")
    if condition == "ON" and not learn:
        raise BenchmarkEvidenceError("ON worker request must contain learned facts")
    seen_sources: set[str] = set()
    for index, row in enumerate(learn):
        if not isinstance(row, dict) or frozenset(row) != _LEARN_FIELDS:
            raise BenchmarkEvidenceError(f"worker learn row {index} fields mismatch")
        if not _bounded_text(row.get("fact")):
            raise BenchmarkEvidenceError(f"worker learn row {index} fact invalid")
        source_id = row.get("source_id")
        if (
            not isinstance(source_id, str)
            or _SOURCE_ID_RE.fullmatch(source_id) is None
            or source_id in seen_sources
        ):
            raise BenchmarkEvidenceError(f"worker learn row {index} source invalid")
        seen_sources.add(source_id)

    questions = value.get("questions")
    if not isinstance(questions, list) or not 1 <= len(questions) <= _MAX_ITEMS:
        raise BenchmarkEvidenceError("worker questions invalid")
    for expected_index, row in enumerate(questions):
        if (
            not isinstance(row, dict)
            or frozenset(row) != _QUESTION_FIELDS
            or row.get("index") != expected_index
            or not _bounded_text(row.get("question"))
        ):
            raise BenchmarkEvidenceError(
                f"worker question row {expected_index} invalid"
            )

    static_paragraphs = value.get("static_paragraphs")
    if static_paragraphs != []:
        raise BenchmarkEvidenceError(
            "preregistered worker requires an explicitly empty static evidence list"
        )
    return value


def _fact_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bounded_result_list(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, list) or len(value) > _MAX_SUPPORT:
        raise BenchmarkEvidenceError(f"candidate {label} invalid")
    # Detach candidate-owned mutable values and enforce bounded canonical JSON.
    detached = json.loads(canonical_json_bytes(value))
    if len(canonical_json_bytes(detached)) > 256 * 1024:
        raise BenchmarkEvidenceError(f"candidate {label} too large")
    return detached


def _actual_device(thinker: Any) -> str:
    reader = getattr(thinker, "reader", None)
    device = str(getattr(reader, "dev", "unknown"))
    if device.startswith("cuda"):
        return "cuda"
    if device == "cpu":
        return "cpu"
    return device


def _check_device_policy(policy: str, actual: str) -> None:
    if policy == "cpu_only" and actual != "cpu":
        raise BenchmarkEvidenceError(
            f"cpu_only policy violated by candidate device {actual!r}"
        )
    if policy == "cuda_required" and actual != "cuda":
        raise BenchmarkEvidenceError(
            f"cuda_required policy violated by candidate device {actual!r}"
        )


def _isolated_files(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )


def evaluate(value: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one OFF or ON arm.

    Candidate imports occur only here, after request validation and after the
    fresh temporary paths exist.  Structural/dry-run validation never calls
    this function.
    """

    request = _validate_request(value)
    condition = str(request["condition"])
    config = request["config"]

    with tempfile.TemporaryDirectory(prefix="atanor-live-eval-") as temporary:
        root = Path(temporary).resolve()
        try:
            root.relative_to(REPO.resolve())
        except ValueError:
            pass
        else:
            raise BenchmarkEvidenceError(
                "candidate temporary state unexpectedly resides inside repository"
            )

        hippocampus = root / "hippocampus.jsonl"
        cortex = root / "cortex.jsonl"
        miss_path = root / "misses.jsonl"
        initially_empty = not any(path.exists() for path in (hippocampus, cortex, miss_path))
        if not initially_empty:  # pragma: no cover - TemporaryDirectory invariant
            raise BenchmarkEvidenceError("candidate temporary state was not empty")

        from packages.reasoning_vm.consolidation import MissLog
        from packages.reasoning_vm.deliberator.realtime import RealTimeThinker

        thinker = RealTimeThinker(
            ckpt=request["checkpoint"],
            store=hippocampus,
            threshold=float(config["threshold"]),
            k=int(config["k"]),
            min_overlap=int(config["min_overlap"]),
            cortex_path=cortex,
            misslog=MissLog(path=miss_path),
            record_misses=False,
        )
        actual_device = _actual_device(thinker)
        _check_device_policy(str(request["device_policy"]), actual_device)

        learned = []
        for row in request["learn"]:
            receipt = thinker.learn(
                row["fact"],
                source=row["source_id"],
            )
            # This isolated evaluator owns its fixed fixture and may promote it
            # only after the public learn boundary has stored it unverified.
            # Keeping the steps separate prevents fixture convenience from
            # recreating caller-attested verification in production adapters.
            if not thinker.promote_verified(receipt["id"]):
                raise BenchmarkEvidenceError("fixture verification promotion failed")
            learned.append(
                {
                    "source_id": row["source_id"],
                    "fact_sha256": _fact_digest(row["fact"]),
                    "candidate_item_id": receipt.get("id")
                    if isinstance(receipt, dict)
                    else None,
                }
            )

        results: list[dict[str, Any]] = []
        for row in request["questions"]:
            started = time.perf_counter()
            answer: str | None = None
            emitted = False
            used_live = False
            grounded = False
            confidence = 0.0
            support: list[Any] = []
            evidence: list[Any] = []
            recall_source: str | None = None
            recall_digest: str | None = None
            error_type: str | None = None
            try:
                recalled = thinker.mem.recall(
                    row["question"],
                    k=int(config["k_live"]),
                    include_unverified=False,
                )
                if recalled:
                    first = recalled[0]
                    if isinstance(first, dict):
                        source = first.get("source")
                        text = first.get("text")
                        recall_source = str(source) if source is not None else ""
                        if isinstance(text, str):
                            recall_digest = _fact_digest(text)

                output = thinker.think(
                    row["question"],
                    static_paragraphs=[],
                    k_live=int(config["k_live"]),
                    include_unverified=False,
                )
                if not isinstance(output, dict):
                    raise BenchmarkEvidenceError("candidate output is not an object")
                raw_answer = output.get("answer")
                if raw_answer is not None and not isinstance(raw_answer, str):
                    raise BenchmarkEvidenceError("candidate answer is not text")
                if isinstance(raw_answer, str) and len(raw_answer) > _MAX_ANSWER:
                    raise BenchmarkEvidenceError("candidate answer too large")
                answer = raw_answer
                emitted = isinstance(answer, str) and bool(answer.strip())
                if type(output.get("used_live")) is not bool:
                    raise BenchmarkEvidenceError("candidate used_live is not boolean")
                if type(output.get("grounded")) is not bool:
                    raise BenchmarkEvidenceError("candidate grounded is not boolean")
                if not _finite_between(output.get("confidence"), 0.0, 1.0):
                    raise BenchmarkEvidenceError("candidate confidence invalid")
                used_live = output["used_live"]
                grounded = output["grounded"]
                confidence = float(output["confidence"])
                support = _bounded_result_list(output.get("support"), label="support")
                evidence = _bounded_result_list(output.get("evidence"), label="evidence")
            except Exception as exc:  # candidate faults are item-level evidence
                error_type = type(exc).__name__
                answer = None
                emitted = False
                used_live = False
                grounded = False
                confidence = 0.0
                support = []
                evidence = []
            results.append(
                {
                    "index": row["index"],
                    "emitted": emitted,
                    "answer": answer,
                    "used_live": used_live,
                    "grounded": grounded,
                    "confidence": round(confidence, 12),
                    "support": support,
                    "evidence": evidence,
                    "recall_top_source": recall_source,
                    "recall_top_fact_sha256": recall_digest,
                    "error_type": error_type,
                    "latency_ms": round(
                        (time.perf_counter() - started) * 1000.0,
                        6,
                    ),
                }
            )

        files_after = _isolated_files(root)
        allowed_files = {"hippocampus.jsonl"} if condition == "ON" else set()
        isolation = {
            "temporary_state_initially_empty": initially_empty,
            "hippocampus_path_is_temporary": hippocampus.parent == root,
            "cortex_path_is_temporary": cortex.parent == root,
            "miss_path_is_temporary": miss_path.parent == root,
            "record_misses": False,
            "include_unverified": False,
            "learned_verified": True,
            "learned_count": len(learned),
            "cortex_write_detected": cortex.exists(),
            "miss_write_detected": miss_path.exists(),
            "unexpected_temporary_files": sorted(set(files_after) - allowed_files),
            "temporary_files": files_after,
        }

    return {
        "schema_version": RESULT_SCHEMA,
        "condition": condition,
        "device": actual_device,
        "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
        "isolation": isolation,
        "learned": learned,
        "items": results,
    }


def _validate_result_shape(value: dict[str, Any], expected_items: int) -> None:
    """Internal output check before emitting bytes to the parent."""

    if frozenset(value) != {
        "schema_version",
        "condition",
        "device",
        "python_hash_seed",
        "isolation",
        "learned",
        "items",
    }:
        raise BenchmarkEvidenceError("worker result fields mismatch")
    if value.get("schema_version") != RESULT_SCHEMA:
        raise BenchmarkEvidenceError("worker result schema mismatch")
    items = value.get("items")
    if not isinstance(items, list) or len(items) != expected_items:
        raise BenchmarkEvidenceError("worker result item count mismatch")
    for index, row in enumerate(items):
        if not isinstance(row, dict) or frozenset(row) != _RESULT_FIELDS:
            raise BenchmarkEvidenceError(f"worker result row {index} fields mismatch")
        if row.get("index") != index:
            raise BenchmarkEvidenceError(f"worker result row {index} index mismatch")


def main() -> int:
    try:
        payload = sys.stdin.buffer.read(_MAX_REQUEST_BYTES + 1)
        if len(payload) > _MAX_REQUEST_BYTES:
            raise BenchmarkEvidenceError("worker request too large")
        request = strict_json_bytes(payload, label="LiveMemory worker request")
        validated = _validate_request(request)
        result = evaluate(validated)
        _validate_result_shape(result, len(validated["questions"]))
        sys.stdout.buffer.write(canonical_json_bytes(result) + b"\n")
        sys.stdout.buffer.flush()
    except (BenchmarkEvidenceError, OSError, RuntimeError, ValueError) as exc:
        sys.stderr.write(
            json.dumps(
                {"error": str(exc), "type": type(exc).__name__},
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
