"""Fresh-process, CPU-only EAD-0 signal worker.

The request deliberately contains no labels, gates, folds, or decision
thresholds.  It contains only question/evidence tuples and an exact contiguous
candidate-answer character span.  The worker loads the already-shipped
``ace_hotpot.pt`` reader and emits its raw answerability and support-head
signals.  It neither decides ACCEPT/REJECT nor touches the live path.
"""

from __future__ import annotations

import json
import math
import os
import platform
import re
import sys
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


REQUEST_SCHEMA = "atanor.ead0-signal-request.v1"
RESULT_SCHEMA = "atanor.ead0-signal-result.v1"
_CHECKPOINT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,255}\.pt$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "answerability_checkpoint",
        "support_checkpoint",
        "device_policy",
        "items",
    }
)
_ITEM_FIELDS = frozenset(
    {
        "index",
        "item_key",
        "question",
        "evidence",
        "answer_start",
        "answer_end",
    }
)
_MAX_REQUEST_BYTES = 4 * 1024 * 1024
_MAX_ITEMS = 256
_MAX_TEXT = 32_768


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= _MAX_TEXT


def validate_request(value: dict[str, Any]) -> dict[str, Any]:
    if frozenset(value) != _ROOT_FIELDS:
        raise BenchmarkEvidenceError("EAD-0 worker request fields mismatch")
    if value.get("schema_version") != REQUEST_SCHEMA:
        raise BenchmarkEvidenceError("EAD-0 worker request schema mismatch")
    for field in ("answerability_checkpoint", "support_checkpoint"):
        checkpoint = value.get(field)
        if (
            not isinstance(checkpoint, str)
            or _CHECKPOINT_RE.fullmatch(checkpoint) is None
        ):
            raise BenchmarkEvidenceError(
                f"EAD-0 {field} must be a safe .pt basename"
            )
    if (
        value["answerability_checkpoint"] != "ace_hotpot.pt"
        or value["support_checkpoint"] != "ace_support.pt"
    ):
        raise BenchmarkEvidenceError("EAD-0 frozen reader assignment mismatch")
    if value.get("device_policy") != "cpu_only":
        raise BenchmarkEvidenceError("EAD-0 worker is CPU-only")
    items = value.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= _MAX_ITEMS:
        raise BenchmarkEvidenceError("EAD-0 worker items invalid")
    seen: set[str] = set()
    for expected, row in enumerate(items):
        if not isinstance(row, dict) or frozenset(row) != _ITEM_FIELDS:
            raise BenchmarkEvidenceError(f"EAD-0 worker item {expected} fields mismatch")
        if row.get("index") != expected:
            raise BenchmarkEvidenceError(f"EAD-0 worker item {expected} index mismatch")
        key = row.get("item_key")
        if (
            not isinstance(key, str)
            or _SHA256_RE.fullmatch(key) is None
            or key in seen
        ):
            raise BenchmarkEvidenceError(f"EAD-0 worker item {expected} key invalid")
        seen.add(key)
        question, evidence = row.get("question"), row.get("evidence")
        if not _text(question) or not _text(evidence):
            raise BenchmarkEvidenceError(f"EAD-0 worker item {expected} text invalid")
        start, end = row.get("answer_start"), row.get("answer_end")
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(evidence)
            or not evidence[start:end].strip()
        ):
            raise BenchmarkEvidenceError(
                f"EAD-0 worker item {expected} answer span is not exact contiguous text"
            )
    return value


def evaluate(value: dict[str, Any]) -> dict[str, Any]:
    request = validate_request(value)
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
        raise BenchmarkEvidenceError(
            "EAD-0 requires CUDA_VISIBLE_DEVICES=-1 before torch import"
        )
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise BenchmarkEvidenceError(
            "EAD-0 requires PYTHONHASHSEED=0 before model import"
        )
    from packages.reasoning_vm.deliberator.planner import MultiHopReader
    import numpy as np

    answerability_reader = MultiHopReader(
        ckpt=request["answerability_checkpoint"]
    )
    support_reader = MultiHopReader(ckpt=request["support_checkpoint"])
    if str(answerability_reader.dev) != "cpu" or str(support_reader.dev) != "cpu":
        raise BenchmarkEvidenceError(
            "EAD-0 CPU-only policy violated by one of the frozen readers"
        )

    rows = []
    for row in request["items"]:
        question = row["question"]
        evidence = row["evidence"]
        answer = evidence[row["answer_start"] : row["answer_end"]]
        # ace_hotpot.pt supplies the trained Hotpot answerability/ranking head.
        # Its support head was not trained, so support MUST come from the
        # separately trained and byte-bound ace_support.pt reader.
        p_ans = float(answerability_reader._relevance(question, [evidence])[0])
        support = support_reader._support(question + " " + answer, [evidence])[0]
        p_support, p_nei, p_refute = (float(x) for x in support)
        values = (p_ans, p_support, p_nei, p_refute)
        if any(not math.isfinite(x) or not 0.0 <= x <= 1.0 for x in values):
            raise BenchmarkEvidenceError("EAD-0 model emitted a non-probability")
        rows.append(
            {
                "index": row["index"],
                "item_key": row["item_key"],
                "p_ans": p_ans,
                "p_support": p_support,
                "p_nei": p_nei,
                "p_refute": p_refute,
                "p_sup_net": p_support - p_refute,
            }
        )
    return {
        "schema_version": RESULT_SCHEMA,
        "device": "cpu",
        "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
        "versions": {
            "python": platform.python_version(),
            "torch": str(answerability_reader.torch.__version__),
            "numpy": str(np.__version__),
        },
        "items": rows,
    }


def main() -> int:
    payload = sys.stdin.buffer.read(_MAX_REQUEST_BYTES + 1)
    if len(payload) > _MAX_REQUEST_BYTES:
        raise BenchmarkEvidenceError("EAD-0 worker request too large")
    request = strict_json_bytes(payload, label="EAD-0 worker request")
    sys.stdout.buffer.write(canonical_json_bytes(evaluate(request)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        raise SystemExit(2)
