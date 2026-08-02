"""Fresh-process bAbI candidate worker.

The parent sends only context and question text.  Gold answers and grading
logic are not present in the request payload.  OS-level filesystem/network
isolation is intentionally *not* claimed.
"""

from __future__ import annotations

import json
import sys
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


SCHEMA = "atanor.babi-candidate-request.v1"
RESULT_SCHEMA = "atanor.babi-candidate-result.v1"
_MAX_REQUEST_BYTES = 96 * 1024 * 1024
_MAX_ITEMS = 25_000
_MAX_TEXT = 1_000_000
_MAX_ANSWER = 10_000


def _validate_request(value: dict[str, Any]) -> list[dict[str, Any]]:
    if frozenset(value) != {"schema_version", "items"}:
        raise BenchmarkEvidenceError("worker request fields mismatch")
    if value.get("schema_version") != SCHEMA:
        raise BenchmarkEvidenceError("worker request schema mismatch")
    items = value.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= _MAX_ITEMS:
        raise BenchmarkEvidenceError("worker request items invalid")
    for expected_index, row in enumerate(items):
        if (
            not isinstance(row, dict)
            or frozenset(row) != {"index", "context", "question"}
            or row.get("index") != expected_index
            or not isinstance(row.get("context"), str)
            or not isinstance(row.get("question"), str)
            or len(row["context"]) > _MAX_TEXT
            or len(row["question"]) > _MAX_TEXT
        ):
            raise BenchmarkEvidenceError(
                f"worker request item {expected_index} invalid"
            )
    return items


def evaluate(value: dict[str, Any]) -> dict[str, Any]:
    items = _validate_request(value)
    from packages.situation_model.builder import build
    from packages.situation_model.reasoner import answer as sit_answer

    results = []
    for row in items:
        started = time.perf_counter()
        emitted = False
        answer: str | None = None
        error_type: str | None = None
        try:
            situation = build(row["context"])
            result = sit_answer(row["question"], situation)
            if not isinstance(result, dict):
                error_type = "InvalidCandidateResult"
            else:
                candidate_answer = result.get("answer")
                if candidate_answer is None:
                    pass
                elif not isinstance(candidate_answer, str):
                    error_type = "InvalidCandidateAnswerType"
                elif len(candidate_answer) > _MAX_ANSWER:
                    error_type = "CandidateAnswerTooLarge"
                else:
                    answer = candidate_answer
                    emitted = True
        except Exception as exc:
            error_type = type(exc).__name__
        results.append(
            {
                "index": row["index"],
                "emitted": emitted,
                "answer": answer,
                "error_type": error_type,
                "latency_ms": round(
                    (time.perf_counter() - started) * 1000.0,
                    6,
                ),
            }
        )
    return {"schema_version": RESULT_SCHEMA, "items": results}


def main() -> int:
    try:
        payload = sys.stdin.buffer.read(_MAX_REQUEST_BYTES + 1)
        if len(payload) > _MAX_REQUEST_BYTES:
            raise BenchmarkEvidenceError("worker request too large")
        request = strict_json_bytes(payload, label="bAbI worker request")
        result = evaluate(request)
        sys.stdout.buffer.write(canonical_json_bytes(result) + b"\n")
        sys.stdout.buffer.flush()
    except (BenchmarkEvidenceError, OSError, RuntimeError, ValueError) as exc:
        sys.stderr.write(
            json.dumps(
                {"error": str(exc), "type": type(exc).__name__},
                sort_keys=True,
            )
            + "\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
