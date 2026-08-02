"""Fresh-process EAD-2/3 counterbalanced block worker.

The request is deliberately label-blind.  It carries only opaque item
identities and the text needed to exercise the already-sealed EAD-1 live
boundary.  Gold labels, relation families, negative modes, metrics, gates, and
thresholds never enter this process.

One production ``RealTimeThinker`` is constructed per block.  Its answer
producer is then replaced by a deterministic proposal reader so the experiment
measures only whether the proposed answer is bound to the verified evidence.
The ON arm leaves the production ``DoubtGate`` object untouched; the OFF arm
replaces only that semantic gate with a non-empty-proposal counterfactual.

Every case gets a fresh one-row, server-promoted ``LiveMemory`` under a
temporary directory outside the repository.  No shipped memory, cortex,
miss-log, staging, or graph path is read or written by this harness.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
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


REQUEST_SCHEMA = "atanor.ead23-worker-request.v1"
RESULT_SCHEMA = "atanor.ead23-worker-result.v1"
PREREGISTRATION_ID = "ead23-fresh-counterbalanced-v1-20260726"
CANDIDATE_CONTENT_SHA256 = (
    "819e0ff07cfb968109d7d219e6bb86c35c9b2c21565af8263b13c3486d6f0425"
)

_MAX_REQUEST_BYTES = 4 * 1024 * 1024
_MAX_ITEMS = 30
_MAX_TEXT = 32_768
_MAX_ANSWER = 4_096
_MAX_COLLECTION_BYTES = 32 * 1024
_MAX_SIGNALS_BYTES = 16 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BLOCK_CONDITIONS = {
    "A_OFF": "OFF",
    "B_ON": "ON",
    "A_ON": "ON",
    "B_OFF": "OFF",
}
_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "preregistration_id",
        "block_id",
        "condition",
        "device_policy",
        "python_hash_seed",
        "candidate_content_sha256",
        "answerability_checkpoint",
        "support_checkpoint",
        "answerability_threshold",
        "support_net_threshold",
        "items",
    }
)
_ITEM_FIELDS = frozenset(
    {
        "index",
        "item_key",
        "question",
        "evidence",
        "proposed_answer",
        "source_id",
    }
)
_RESULT_FIELDS = frozenset(
    {
        "index",
        "item_key",
        "condition",
        "answer",
        "grounded",
        "confidence",
        "grounding_reason",
        "grounding_signals",
        "used_live",
        "support",
        "evidence",
        "type",
        "selected_source_id",
        "selected_fact_sha256",
        "error",
        "latency_ms",
    }
)


def _bounded_text(
    value: Any,
    *,
    maximum: int = _MAX_TEXT,
    allow_empty: bool = False,
) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= maximum
        and (allow_empty or bool(value.strip()))
    )


def _validate_request(value: dict[str, Any]) -> dict[str, Any]:
    if frozenset(value) != _ROOT_FIELDS:
        raise BenchmarkEvidenceError("EAD-2/3 worker request fields mismatch")
    if value.get("schema_version") != REQUEST_SCHEMA:
        raise BenchmarkEvidenceError("EAD-2/3 worker request schema mismatch")
    if value.get("preregistration_id") != PREREGISTRATION_ID:
        raise BenchmarkEvidenceError(
            "EAD-2/3 worker preregistration identity mismatch"
        )

    block_id = value.get("block_id")
    condition = value.get("condition")
    if block_id not in _BLOCK_CONDITIONS:
        raise BenchmarkEvidenceError("EAD-2/3 worker block identity mismatch")
    if condition != _BLOCK_CONDITIONS[block_id]:
        raise BenchmarkEvidenceError("EAD-2/3 worker block/condition mismatch")
    if value.get("device_policy") != "cpu_only":
        raise BenchmarkEvidenceError("EAD-2/3 worker device policy mismatch")
    if value.get("python_hash_seed") != "0":
        raise BenchmarkEvidenceError("EAD-2/3 worker hash-seed policy mismatch")
    if value.get("candidate_content_sha256") != CANDIDATE_CONTENT_SHA256:
        raise BenchmarkEvidenceError("EAD-2/3 worker candidate binding mismatch")
    if (
        value.get("answerability_checkpoint") != "ace_hotpot.pt"
        or value.get("support_checkpoint") != "ace_support.pt"
    ):
        raise BenchmarkEvidenceError("EAD-2/3 worker checkpoint assignment mismatch")
    if (
        type(value.get("answerability_threshold")) not in (int, float)
        or isinstance(value.get("answerability_threshold"), bool)
        or float(value["answerability_threshold"]) != 0.90
        or type(value.get("support_net_threshold")) not in (int, float)
        or isinstance(value.get("support_net_threshold"), bool)
        or float(value["support_net_threshold"]) != 0.90
    ):
        raise BenchmarkEvidenceError("EAD-2/3 worker threshold contract mismatch")

    items = value.get("items")
    if not isinstance(items, list) or len(items) != _MAX_ITEMS:
        raise BenchmarkEvidenceError(
            f"EAD-2/3 worker block must contain exactly {_MAX_ITEMS} items"
        )
    seen_keys: set[str] = set()
    seen_sources: set[str] = set()
    for index, row in enumerate(items):
        if not isinstance(row, dict) or frozenset(row) != _ITEM_FIELDS:
            raise BenchmarkEvidenceError(
                f"EAD-2/3 worker item {index} fields mismatch"
            )
        if row.get("index") != index:
            raise BenchmarkEvidenceError(
                f"EAD-2/3 worker item {index} index mismatch"
            )
        item_key = row.get("item_key")
        if (
            not isinstance(item_key, str)
            or _SHA256_RE.fullmatch(item_key) is None
            or item_key in seen_keys
        ):
            raise BenchmarkEvidenceError(
                f"EAD-2/3 worker item {index} opaque key invalid"
            )
        seen_keys.add(item_key)
        source_id = row.get("source_id")
        if (
            not isinstance(source_id, str)
            or _SHA256_RE.fullmatch(source_id) is None
            or source_id in seen_sources
        ):
            raise BenchmarkEvidenceError(
                f"EAD-2/3 worker item {index} source identity invalid"
            )
        seen_sources.add(source_id)
        question = row.get("question")
        evidence = row.get("evidence")
        answer = row.get("proposed_answer")
        if not _bounded_text(question) or not _bounded_text(evidence):
            raise BenchmarkEvidenceError(
                f"EAD-2/3 worker item {index} question/evidence invalid"
            )
        if not _bounded_text(answer, maximum=_MAX_ANSWER):
            raise BenchmarkEvidenceError(
                f"EAD-2/3 worker item {index} proposed answer invalid"
            )
        if answer not in evidence:
            raise BenchmarkEvidenceError(
                f"EAD-2/3 worker item {index} proposal is not an exact evidence span"
            )
    return value


def _assert_frozen_environment() -> None:
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
        raise BenchmarkEvidenceError(
            "EAD-2/3 requires CUDA_VISIBLE_DEVICES=-1 before model import"
        )
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise BenchmarkEvidenceError(
            "EAD-2/3 requires PYTHONHASHSEED=0 before model import"
        )


def _fact_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _detached_bounded(value: Any, *, label: str, limit: int) -> Any:
    try:
        payload = canonical_json_bytes(value)
    except (TypeError, ValueError) as exc:
        raise BenchmarkEvidenceError(
            f"EAD-2/3 candidate {label} is not canonical JSON"
        ) from exc
    if len(payload) > limit:
        raise BenchmarkEvidenceError(f"EAD-2/3 candidate {label} is too large")
    return json.loads(payload)


def _bounded_support(value: Any) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) > 4
        or not all(_bounded_text(row, maximum=512) for row in value)
    ):
        raise BenchmarkEvidenceError("EAD-2/3 candidate support invalid")
    detached = _detached_bounded(
        value,
        label="support",
        limit=_MAX_COLLECTION_BYTES,
    )
    return [str(row) for row in detached]


def _bounded_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 4:
        raise BenchmarkEvidenceError("EAD-2/3 candidate evidence invalid")
    rows: list[dict[str, Any]] = []
    expected_fields = frozenset(
        {"origin", "title", "verified", "candidate_index"}
    )
    for index, row in enumerate(value):
        if not isinstance(row, dict) or frozenset(row) != expected_fields:
            raise BenchmarkEvidenceError(
                f"EAD-2/3 candidate evidence row {index} fields mismatch"
            )
        if row.get("origin") not in {"live", "cortex", "static"}:
            raise BenchmarkEvidenceError(
                f"EAD-2/3 candidate evidence row {index} origin invalid"
            )
        if not _bounded_text(row.get("title"), maximum=512):
            raise BenchmarkEvidenceError(
                f"EAD-2/3 candidate evidence row {index} title invalid"
            )
        if type(row.get("verified")) is not bool:
            raise BenchmarkEvidenceError(
                f"EAD-2/3 candidate evidence row {index} authority invalid"
            )
        candidate_index = row.get("candidate_index")
        if type(candidate_index) is not int or not 0 <= candidate_index <= 3:
            raise BenchmarkEvidenceError(
                f"EAD-2/3 candidate evidence row {index} index invalid"
            )
        rows.append(dict(row))
    return _detached_bounded(
        rows,
        label="evidence",
        limit=_MAX_COLLECTION_BYTES,
    )


def _bounded_signals(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BenchmarkEvidenceError("EAD-2/3 candidate signals invalid")
    detached = _detached_bounded(
        value,
        label="signals",
        limit=_MAX_SIGNALS_BYTES,
    )
    if not isinstance(detached, dict):
        raise BenchmarkEvidenceError("EAD-2/3 detached signals invalid")
    return detached


def _finite_probability(value: Any) -> float:
    if (
        type(value) not in (int, float)
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise BenchmarkEvidenceError("EAD-2/3 candidate confidence invalid")
    return float(value)


class _FixedProposalReader:
    """Deterministic answer producer bound to the sole candidate row."""

    def __init__(self) -> None:
        self.question = ""
        self.evidence = ""
        self.answer_text = ""
        self.title = ""

    def bind(
        self,
        *,
        question: str,
        evidence: str,
        answer: str,
        title: str,
    ) -> None:
        self.question = question
        self.evidence = evidence
        self.answer_text = answer
        self.title = title

    def answer(
        self,
        question: str,
        paragraphs: list[tuple[str, str]],
        *,
        k: int,
        chain: bool,
        rank: str,
    ) -> dict[str, Any]:
        if (
            question != self.question
            or paragraphs != [(self.title, self.evidence)]
            or k != 1
            or chain is not False
            or rank != "ans"
            or not self.answer_text.strip()
        ):
            raise BenchmarkEvidenceError(
                "EAD-2/3 fixed proposal producer identity mismatch"
            )
        return {
            "answer": self.answer_text,
            "support": [self.title],
            "support_indices": [0],
            "answer_index": 0,
            "type": "span",
        }


class _NonemptyProposalGate:
    """Evaluator-only OFF gate; source authority remains in RealTimeThinker."""

    def __init__(self) -> None:
        self.question = ""
        self.evidence = ""
        self.answer_text = ""

    def bind(self, *, question: str, evidence: str, answer: str) -> None:
        self.question = question
        self.evidence = evidence
        self.answer_text = answer

    def judge_answer(
        self,
        question: str,
        answer: str,
        evidence: list[str],
    ) -> dict[str, Any]:
        if (
            question != self.question
            or answer != self.answer_text
            or evidence != [self.evidence]
        ):
            raise BenchmarkEvidenceError(
                "EAD-2/3 OFF gate producer/evidence identity mismatch"
            )
        accepted = bool(answer.strip()) and bool(evidence[0].strip())
        return {
            "accepted": accepted,
            "confidence": 1.0 if accepted else 0.0,
            "reason": (
                "counterfactual_nonempty_proposal"
                if accepted
                else "counterfactual_empty_proposal"
            ),
            "signals": {
                "evidence_index": 0,
                "evidence_count": 1,
                "counterfactual_semantic_gate": "OFF",
            },
        }


def _actual_device(reader: Any) -> str:
    value = str(getattr(reader, "dev", "unknown"))
    if value == "cpu":
        return "cpu"
    if value.startswith("cuda"):
        return "cuda"
    return value


def _isolated_files(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )


def _empty_result(
    *,
    index: int,
    row: dict[str, Any],
    condition: str,
    error: str,
    latency_ms: float,
) -> dict[str, Any]:
    return {
        "index": index,
        "item_key": row["item_key"],
        "condition": condition,
        "answer": row["proposed_answer"],
        "grounded": False,
        "confidence": 0.0,
        "grounding_reason": "worker_item_error",
        "grounding_signals": {},
        "used_live": False,
        "support": [],
        "evidence": [],
        "type": "span",
        "selected_source_id": row["source_id"],
        "selected_fact_sha256": _fact_sha256(row["evidence"]),
        "error": error[:1000],
        "latency_ms": round(latency_ms, 6),
    }


def evaluate(value: dict[str, Any]) -> dict[str, Any]:
    """Run one frozen block after label-blind validation."""

    request = _validate_request(value)
    _assert_frozen_environment()

    with tempfile.TemporaryDirectory(prefix="atanor-ead23-") as temporary:
        root = Path(temporary).resolve()
        try:
            root.relative_to(REPO.resolve(strict=True))
        except ValueError:
            outside_repository = True
        else:  # pragma: no cover - TemporaryDirectory location invariant
            outside_repository = False
        if not outside_repository:
            raise BenchmarkEvidenceError(
                "EAD-2/3 temporary state unexpectedly resides in repository"
            )

        bootstrap_store = root / "bootstrap-memory.jsonl"
        cortex_path = root / "cortex.jsonl"
        miss_path = root / "misses.jsonl"
        if any(path.exists() for path in (bootstrap_store, cortex_path, miss_path)):
            raise BenchmarkEvidenceError(
                "EAD-2/3 temporary state was not initially empty"
            )

        # Candidate imports occur only after strict request and environment
        # validation.  This is the sole RealTimeThinker construction.
        from packages.reasoning_vm.consolidation import MissLog
        from packages.reasoning_vm.deliberator.realtime import RealTimeThinker
        from packages.reasoning_vm.live_memory import LiveMemory

        thinker = RealTimeThinker(
            ckpt=request["answerability_checkpoint"],
            support_ckpt=request["support_checkpoint"],
            store=bootstrap_store,
            cortex_path=cortex_path,
            misslog=MissLog(path=miss_path),
            record_misses=False,
            answerability_threshold=float(request["answerability_threshold"]),
            support_net_threshold=float(request["support_net_threshold"]),
        )
        production_gate = thinker.gate
        answerability_device = _actual_device(production_gate.r)
        support_reader = getattr(production_gate, "support_reader", None)
        support_device = _actual_device(support_reader)
        if answerability_device != "cpu" or support_device != "cpu":
            raise BenchmarkEvidenceError(
                "EAD-2/3 CPU-only policy violated by production readers"
            )
        if (
            float(getattr(production_gate, "answerability_threshold", -1.0))
            != 0.90
            or float(getattr(production_gate, "support_net_threshold", -1.0))
            != 0.90
        ):
            raise BenchmarkEvidenceError(
                "EAD-2/3 production discriminator threshold drift"
            )

        proposal_reader = _FixedProposalReader()
        thinker.reader = proposal_reader
        off_gate = _NonemptyProposalGate()
        if request["condition"] == "OFF":
            thinker.gate = off_gate
        elif thinker.gate is not production_gate:  # pragma: no cover
            raise BenchmarkEvidenceError(
                "EAD-2/3 ON production gate identity changed"
            )

        rows: list[dict[str, Any]] = []
        verified_one_row_count = 0
        for index, row in enumerate(request["items"]):
            started = time.perf_counter()
            case_root = root / f"case-{index:02d}"
            case_store = case_root / "live-memory.jsonl"
            try:
                if case_root.exists():
                    raise BenchmarkEvidenceError(
                        "EAD-2/3 case state was not initially empty"
                    )
                thinker.mem = LiveMemory(path=case_store)
                if thinker.mem.stats() != {"items": 0, "verified": 0, "vocab": 0}:
                    raise BenchmarkEvidenceError(
                        "EAD-2/3 case memory did not start empty"
                    )
                receipt = thinker.learn(row["evidence"], source=row["source_id"])
                if (
                    not isinstance(receipt, dict)
                    or receipt.get("id") != 0
                    or receipt.get("source") != row["source_id"]
                    or receipt.get("text") != row["evidence"]
                    or receipt.get("verified") is not False
                    or thinker.mem.stats()["items"] != 1
                ):
                    raise BenchmarkEvidenceError(
                        "EAD-2/3 untrusted one-row ingress mismatch"
                    )
                if not thinker.promote_verified(0):
                    raise BenchmarkEvidenceError(
                        "EAD-2/3 server-owned fixture promotion failed"
                    )
                if (
                    thinker.mem.stats()["items"] != 1
                    or thinker.mem.stats()["verified"] != 1
                    or len(thinker.mem.items) != 1
                    or thinker.mem.items[0].get("verified") is not True
                    or thinker.mem.items[0].get("source") != row["source_id"]
                    or thinker.mem.items[0].get("text") != row["evidence"]
                ):
                    raise BenchmarkEvidenceError(
                        "EAD-2/3 verified one-row memory invariant failed"
                    )
                verified_one_row_count += 1

                title = f"live:{row['source_id']}"
                proposal_reader.bind(
                    question=row["question"],
                    evidence=row["evidence"],
                    answer=row["proposed_answer"],
                    title=title,
                )
                if request["condition"] == "OFF":
                    off_gate.bind(
                        question=row["question"],
                        evidence=row["evidence"],
                        answer=row["proposed_answer"],
                    )
                elif thinker.gate is not production_gate:
                    raise BenchmarkEvidenceError(
                        "EAD-2/3 ON production gate was replaced"
                    )

                output = thinker.think(
                    row["question"],
                    static_paragraphs=[],
                    k_live=1,
                    include_unverified=False,
                )
                if not isinstance(output, dict):
                    raise BenchmarkEvidenceError(
                        "EAD-2/3 candidate output is not an object"
                    )
                answer = output.get("answer")
                if answer is not None and not _bounded_text(
                    answer,
                    maximum=_MAX_ANSWER,
                    allow_empty=True,
                ):
                    raise BenchmarkEvidenceError(
                        "EAD-2/3 candidate answer invalid"
                    )
                if type(output.get("grounded")) is not bool:
                    raise BenchmarkEvidenceError(
                        "EAD-2/3 candidate grounded flag invalid"
                    )
                if type(output.get("used_live")) is not bool:
                    raise BenchmarkEvidenceError(
                        "EAD-2/3 candidate used_live flag invalid"
                    )
                if output.get("type") != "span":
                    raise BenchmarkEvidenceError(
                        "EAD-2/3 candidate answer type invalid"
                    )
                confidence = _finite_probability(output.get("confidence"))
                support = _bounded_support(output.get("support"))
                evidence = _bounded_evidence(output.get("evidence"))
                reason = output.get("grounding_reason")
                if reason is not None and not _bounded_text(reason, maximum=256):
                    raise BenchmarkEvidenceError(
                        "EAD-2/3 grounding reason invalid"
                    )
                signals = _bounded_signals(output.get("grounding_signals"))

                # A result remains observable even when ON rejects it, but its
                # answer producer and selected authority must be the sole
                # server-promoted row in both conditions.
                if (
                    answer != row["proposed_answer"]
                    or support != [title]
                    or evidence
                    != [
                        {
                            "origin": "live",
                            "title": title,
                            "verified": True,
                            "candidate_index": 0,
                        }
                    ]
                    or output["used_live"] is not True
                ):
                    raise BenchmarkEvidenceError(
                        "EAD-2/3 selected producer provenance mismatch"
                    )

                rows.append(
                    {
                        "index": index,
                        "item_key": row["item_key"],
                        "condition": request["condition"],
                        "answer": answer,
                        "grounded": output["grounded"],
                        "confidence": round(confidence, 12),
                        "grounding_reason": reason,
                        "grounding_signals": signals,
                        "used_live": output["used_live"],
                        "support": support,
                        "evidence": evidence,
                        "type": output.get("type"),
                        "selected_source_id": row["source_id"],
                        "selected_fact_sha256": _fact_sha256(row["evidence"]),
                        "error": None,
                        "latency_ms": round(
                            (time.perf_counter() - started) * 1000.0,
                            6,
                        ),
                    }
                )
            except Exception as exc:
                rows.append(
                    _empty_result(
                        index=index,
                        row=row,
                        condition=request["condition"],
                        error=type(exc).__name__,
                        latency_ms=(time.perf_counter() - started) * 1000.0,
                    )
                )

        files_after = _isolated_files(root)
        expected_files = {
            f"case-{index:02d}/live-memory.jsonl"
            for index in range(len(request["items"]))
        }
        if (
            set(files_after) != expected_files
            or bootstrap_store.exists()
            or cortex_path.exists()
            or miss_path.exists()
            or thinker.cortex.stats()["items"] != 0
            or verified_one_row_count != len(request["items"])
            or (
                request["condition"] == "ON"
                and thinker.gate is not production_gate
            )
            or (
                request["condition"] == "OFF"
                and (
                    thinker.gate is not off_gate
                    or production_gate is off_gate
                )
            )
        ):
            raise BenchmarkEvidenceError(
                "EAD-2/3 temporary isolation or treatment identity failed"
            )
        temp_isolation = {
            "temp_root_outside_repository": outside_repository,
            "cortex_items": 0,
            "miss_log_written": False,
        }

    return {
        "schema_version": RESULT_SCHEMA,
        "block_id": request["block_id"],
        "condition": request["condition"],
        "device": "cpu",
        "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
        "versions": {
            "python": platform.python_version(),
            "torch": str(production_gate.r.torch.__version__),
        },
        "temp_isolation": temp_isolation,
        "items": rows,
    }


def _validate_result_shape(
    value: dict[str, Any],
    request: dict[str, Any],
) -> None:
    if frozenset(value) != {
        "schema_version",
        "block_id",
        "condition",
        "device",
        "python_hash_seed",
        "versions",
        "temp_isolation",
        "items",
    }:
        raise BenchmarkEvidenceError("EAD-2/3 worker result fields mismatch")
    if (
        value.get("schema_version") != RESULT_SCHEMA
        or value.get("block_id") != request["block_id"]
        or value.get("condition") != request["condition"]
        or value.get("device") != "cpu"
        or value.get("python_hash_seed") != "0"
        or value.get("temp_isolation")
        != {
            "temp_root_outside_repository": True,
            "cortex_items": 0,
            "miss_log_written": False,
        }
        or not isinstance(value.get("versions"), dict)
    ):
        raise BenchmarkEvidenceError(
            "EAD-2/3 worker result identity/isolation mismatch"
        )
    items = value.get("items")
    if not isinstance(items, list) or len(items) != len(request["items"]):
        raise BenchmarkEvidenceError("EAD-2/3 worker result item count mismatch")
    for index, (row, asked) in enumerate(zip(items, request["items"])):
        if not isinstance(row, dict) or frozenset(row) != _RESULT_FIELDS:
            raise BenchmarkEvidenceError(
                f"EAD-2/3 worker result item {index} fields mismatch"
            )
        if (
            row.get("index") != index
            or row.get("item_key") != asked["item_key"]
            or row.get("condition") != request["condition"]
            or row.get("answer") != asked["proposed_answer"]
            or type(row.get("grounded")) is not bool
            or type(row.get("used_live")) is not bool
            or row.get("type") != "span"
            or row.get("selected_source_id") != asked["source_id"]
            or row.get("selected_fact_sha256")
            != _fact_sha256(asked["evidence"])
            or not _bounded_text(row.get("grounding_reason"), maximum=256)
            or (
                row.get("error") is not None
                and not _bounded_text(row.get("error"), maximum=1000)
            )
        ):
            raise BenchmarkEvidenceError(
                f"EAD-2/3 worker result item {index} identity mismatch"
            )
        _finite_probability(row.get("confidence"))
        latency = row.get("latency_ms")
        if (
            type(latency) not in (int, float)
            or isinstance(latency, bool)
            or not math.isfinite(float(latency))
            or float(latency) < 0.0
        ):
            raise BenchmarkEvidenceError(
                f"EAD-2/3 worker result item {index} latency invalid"
            )
        _bounded_support(row.get("support"))
        _bounded_evidence(row.get("evidence"))
        _bounded_signals(row.get("grounding_signals"))


def main() -> int:
    try:
        payload = sys.stdin.buffer.read(_MAX_REQUEST_BYTES + 1)
        if len(payload) > _MAX_REQUEST_BYTES:
            raise BenchmarkEvidenceError("EAD-2/3 worker request too large")
        request = strict_json_bytes(payload, label="EAD-2/3 worker request")
        validated = _validate_request(request)
        result = evaluate(validated)
        _validate_result_shape(result, validated)
        sys.stdout.buffer.write(canonical_json_bytes(result) + b"\n")
        sys.stdout.buffer.flush()
    except Exception as exc:
        sys.stderr.write(
            json.dumps(
                {
                    "error": str(exc)[-2000:],
                    "type": type(exc).__name__,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
