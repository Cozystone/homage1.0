"""Preregistered paired OFF/ON evaluation for LiveMemory -> RealTimeThinker.

This harness measures one narrow claim: whether a frozen RealTimeThinker can
use newly supplied, verified, synthetic single-hop facts in fresh isolated
processes.  It does not measure general reasoning, multi-hop inference, model
learning, benchmark transfer, or production authority.

The preregistration fixes all facts, questions, gold answers, metrics, gates,
candidate paths, device policy, hash seed, and two counterbalanced replays
before any result subprocess is launched.  Gold answers and grading stay in
this parent process.  Receipts are unsigned local checksums, not E5 evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import unicodedata
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

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
    item_id,
    selection_record,
    strict_json_bytes,
    utc_now,
    verify_manifest,
    write_manifest_exclusive,
)
from scripts.live_memory_realtime_candidate_worker import (  # noqa: E402
    REQUEST_SCHEMA as WORKER_REQUEST_SCHEMA,
    RESULT_SCHEMA as WORKER_RESULT_SCHEMA,
)


PREREGISTRATION_SCHEMA = "atanor.live-memory-realtime-preregister.v1"
ATTEMPT_SCHEMA = "atanor.live-memory-realtime-attempt.v1"
FAILURE_SCHEMA = "atanor.live-memory-realtime-failure.v1"
NORMALIZATION_SPEC = (
    "unicode-nfkc-alphanumeric-casefold-article-drop-token-f1-and-em.v1"
)
WORKER = REPO / "scripts" / "live_memory_realtime_candidate_worker.py"
REPORTS = REPO / "reports" / "benchmarks"

_EVALUATOR_PATHS = tuple(
    sorted(
        {
            "packages/__init__.py",
            "packages/eval_evidence/__init__.py",
            "packages/eval_evidence/receipt.py",
            "scripts/live_memory_realtime_candidate_worker.py",
            "scripts/live_memory_realtime_preregistered_eval.py",
        }
    )
)
_REQUIRED_CANDIDATE_PATHS = frozenset(
    {
        "packages/__init__.py",
        "packages/reasoning_vm/__init__.py",
        "packages/reasoning_vm/live_memory.py",
        "packages/reasoning_vm/consolidation.py",
        "packages/reasoning_vm/deliberator/__init__.py",
        "packages/reasoning_vm/deliberator/doubt_gate.py",
        "packages/reasoning_vm/deliberator/planner.py",
        "packages/reasoning_vm/deliberator/realtime.py",
    }
)
_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "preregistration_id",
        "frozen_at",
        "claim_boundary",
        "candidate",
        "protocol",
        "exposure_audit",
        "items",
        "unknown_controls",
        "static_paragraphs",
    }
)
_CLAIM_FIELDS = frozenset(
    {
        "measurement",
        "single_hop_recall_only",
        "general_reasoning_improvement_claimed",
        "cross_benchmark_capability_claimed",
        "evidence_level",
        "limitations",
    }
)
_CANDIDATE_FIELDS = frozenset(
    {"paths", "content_sha256", "checkpoint_path"}
)
_PROTOCOL_FIELDS = frozenset(
    {
        "replays",
        "device_policy",
        "python_hash_seed",
        "worker_timeout_seconds",
        "candidate_config",
        "scoring",
        "gates",
        "rerun_policy",
    }
)
_CANDIDATE_CONFIG_FIELDS = frozenset(
    {"checkpoint", "threshold", "k", "min_overlap", "k_live"}
)
_SCORING_FIELDS = frozenset(
    {
        "normalization",
        "bootstrap_resamples",
        "bootstrap_seed",
        "bootstrap_confidence",
    }
)
_GATE_FIELDS = frozenset({"mechanism", "capability", "safety"})
_MECHANISM_GATE_FIELDS = frozenset(
    {"on_recall_at_1_min", "on_exact_support_source_provenance_rate_min"}
)
_CAPABILITY_GATE_FIELDS = frozenset(
    {
        "on_mean_token_f1_min",
        "on_exact_match_rate_min",
        "paired_exact_match_lift_min",
        "mcnemar_exact_p_max",
        "bootstrap_paired_em_lift_lower_exclusive_min",
        "replay_exact_match_required",
    }
)
_SAFETY_GATE_FIELDS = frozenset(
    {
        "unknown_false_grounded_rate_max",
        "unknown_false_used_live_rate_max",
        "worker_error_count_max",
        "candidate_unchanged_required",
        "source_unchanged_required",
        "preregistration_unchanged_required",
        "temporary_state_isolation_required",
    }
)
_RERUN_FIELDS = frozenset(
    {
        "result_run_limit",
        "mechanical_retry_limit",
        "post_result_tuning_prohibited",
        "new_preregistration_required_after_candidate_or_protocol_change",
    }
)
_EXPOSURE_FIELDS = frozenset(
    {
        "prior_examples_excluded",
        "full_string_repo_scan_performed_before_freeze",
        "new_entity_repo_scan_performed_before_freeze",
        "full_string_hit_count_before_freeze",
        "new_entity_hit_count_before_freeze",
        "public_same_repo_items",
        "hidden_holdout",
        "independent_evaluator",
        "repeated_tuning_risk",
        "limitations",
    }
)
_POSITIVE_FIELDS = frozenset(
    {"item_id", "family", "fact", "question", "gold", "source_id"}
)
_UNKNOWN_FIELDS = frozenset({"item_id", "family", "question"})
_WORKER_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "condition",
        "device",
        "python_hash_seed",
        "isolation",
        "learned",
        "items",
    }
)
_WORKER_ITEM_FIELDS = frozenset(
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
_ISOLATION_FIELDS = frozenset(
    {
        "temporary_state_initially_empty",
        "hippocampus_path_is_temporary",
        "cortex_path_is_temporary",
        "miss_path_is_temporary",
        "record_misses",
        "include_unverified",
        "learned_verified",
        "learned_count",
        "cortex_write_detected",
        "miss_write_detected",
        "unexpected_temporary_files",
        "temporary_files",
    }
)
_LEARNED_RESULT_FIELDS = frozenset(
    {"source_id", "fact_sha256", "candidate_item_id"}
)
_REPORT_CONFIG_FIELDS = frozenset(
    {
        "preregistration_id",
        "preregistered_at",
        "candidate_payload",
        "gold_in_candidate_payload",
        "candidate_process",
        "fresh_process_arm_count",
        "request_sha256",
        "protocol",
        "exposure_audit",
        "arm_receipts",
        "measured_summary",
        "gate_results",
    }
)
_ARM_RECEIPT_FIELDS = frozenset(
    {
        "process_ordinal",
        "replay_id",
        "condition",
        "request_sha256",
        "device",
        "python_hash_seed",
        "isolation",
        "learned",
    }
)
_REPORT_ITEM_METADATA_FIELDS = frozenset(
    {
        "preregistered_item_id",
        "kind",
        "family",
        "replay_id",
        "condition",
        "candidate_emitted",
        "candidate_answer",
        "normalized_token_f1",
        "normalized_exact_match",
        "unknown_safety_pass",
        "used_live",
        "grounded",
        "confidence",
        "recall_top_source",
        "recall_top_fact_sha256",
        "recall_at_1_match",
        "support",
        "evidence",
        "support_evidence_includes_exact_source",
        "candidate_error_type",
        "support_sha256",
        "evidence_sha256",
    }
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}$")
_SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,255}$")
_HASH_SEED_RE = re.compile(r"^(0|[1-9][0-9]{0,9})$")
_TOKEN_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)
_ARTICLES = frozenset({"a", "an", "the"})
_DEVICE_POLICIES = frozenset({"cpu_only", "native_auto", "cuda_required"})
_MAX_TEXT = 16_384
_MAX_RESULT_LIST = 64

Runner = Callable[[dict[str, Any], int, str, str, Path], dict[str, Any]]
ArmCallback = Callable[[dict[str, Any]], None]


def _bounded_text(value: Any, *, maximum: int = _MAX_TEXT) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _ratio_value(value: Any) -> bool:
    return (
        type(value) in (int, float)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    )


def _limitations(value: Any, *, minimum: int = 1) -> bool:
    return (
        isinstance(value, list)
        and minimum <= len(value) <= 100
        and all(_bounded_text(row, maximum=2_000) for row in value)
    )


def _safe_repo_relative(path: Path) -> str:
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(REPO.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise BenchmarkEvidenceError(
            "preregistration must be an existing regular file inside the repository"
        ) from exc
    if path.is_symlink() or not resolved.is_file():
        raise BenchmarkEvidenceError("preregistration must be a regular file")
    result = relative.as_posix()
    if "\\" in result or "." in Path(result).parts or ".." in Path(result).parts:
        raise BenchmarkEvidenceError("preregistration path is unsafe")
    return result


def preregistered_item_id(
    preregistration_id: str,
    kind: str,
    row_without_id: Mapping[str, Any],
) -> str:
    """Return the frozen content-derived ID expected in the preregistration."""

    return item_id(
        {
            "preregistration_id": preregistration_id,
            "kind": kind,
            **dict(row_without_id),
        }
    )


def _validate_claim_boundary(value: Any) -> None:
    if not isinstance(value, dict) or frozenset(value) != _CLAIM_FIELDS:
        raise BenchmarkEvidenceError("claim_boundary fields mismatch")
    if value.get("measurement") != "novel_synthetic_single_hop_recall_reconfirmation":
        raise BenchmarkEvidenceError("claim_boundary measurement mismatch")
    if value.get("single_hop_recall_only") is not True:
        raise BenchmarkEvidenceError("claim must be limited to single-hop recall")
    if value.get("general_reasoning_improvement_claimed") is not False:
        raise BenchmarkEvidenceError("general reasoning improvement must not be claimed")
    if value.get("cross_benchmark_capability_claimed") is not False:
        raise BenchmarkEvidenceError("cross-benchmark capability must not be claimed")
    if value.get("evidence_level") != "unsigned_local_development":
        raise BenchmarkEvidenceError("claim evidence level mismatch")
    if not _limitations(value.get("limitations"), minimum=3):
        raise BenchmarkEvidenceError("claim limitations are incomplete")


def _validate_candidate(value: Any) -> None:
    if not isinstance(value, dict) or frozenset(value) != _CANDIDATE_FIELDS:
        raise BenchmarkEvidenceError("candidate fields mismatch")
    paths = value.get("paths")
    if (
        not isinstance(paths, list)
        or not paths
        or len(paths) > 10_000
        or any(not isinstance(path, str) or not path for path in paths)
        or paths != sorted(paths)
        or len(paths) != len(set(paths))
        or len(paths) != len({path.casefold() for path in paths})
    ):
        raise BenchmarkEvidenceError(
            "candidate paths must be a sorted identity-unique non-empty list"
        )
    if not _REQUIRED_CANDIDATE_PATHS.issubset(set(paths)):
        missing = sorted(_REQUIRED_CANDIDATE_PATHS - set(paths))
        raise BenchmarkEvidenceError(
            f"candidate closure omits required core paths: {missing}"
        )
    digest = value.get("content_sha256")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise BenchmarkEvidenceError("candidate content digest invalid")
    checkpoint = value.get("checkpoint_path")
    if (
        not isinstance(checkpoint, str)
        or checkpoint not in paths
        or Path(checkpoint).parent.as_posix() != "data/graph_scale"
        or Path(checkpoint).suffix != ".pt"
    ):
        raise BenchmarkEvidenceError("candidate checkpoint path is not bound")


def _validate_replays(value: Any) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise BenchmarkEvidenceError("protocol requires exactly two replays")
    seen_ids: set[str] = set()
    orders = []
    for index, replay in enumerate(value):
        if (
            not isinstance(replay, dict)
            or frozenset(replay) != {"id", "condition_order"}
            or not isinstance(replay.get("id"), str)
            or _ID_RE.fullmatch(replay["id"]) is None
            or replay["id"] in seen_ids
            or replay.get("condition_order") not in (["OFF", "ON"], ["ON", "OFF"])
        ):
            raise BenchmarkEvidenceError(f"protocol replay {index} invalid")
        seen_ids.add(replay["id"])
        orders.append(tuple(replay["condition_order"]))
    if Counter(orders) != Counter({("OFF", "ON"): 1, ("ON", "OFF"): 1}):
        raise BenchmarkEvidenceError("protocol replays are not counterbalanced")


def _validate_protocol(value: Any, candidate: Mapping[str, Any]) -> None:
    if not isinstance(value, dict) or frozenset(value) != _PROTOCOL_FIELDS:
        raise BenchmarkEvidenceError("protocol fields mismatch")
    _validate_replays(value.get("replays"))
    if value.get("device_policy") not in _DEVICE_POLICIES:
        raise BenchmarkEvidenceError("protocol device policy invalid")
    seed = value.get("python_hash_seed")
    if not isinstance(seed, str) or _HASH_SEED_RE.fullmatch(seed) is None:
        raise BenchmarkEvidenceError("protocol PYTHONHASHSEED invalid")
    timeout = value.get("worker_timeout_seconds")
    if type(timeout) is not int or not 60 <= timeout <= 86_400:
        raise BenchmarkEvidenceError("protocol worker timeout invalid")

    config = value.get("candidate_config")
    if not isinstance(config, dict) or frozenset(config) != _CANDIDATE_CONFIG_FIELDS:
        raise BenchmarkEvidenceError("protocol candidate config fields mismatch")
    checkpoint = config.get("checkpoint")
    if checkpoint != Path(str(candidate["checkpoint_path"])).name:
        raise BenchmarkEvidenceError("protocol checkpoint does not match candidate binding")
    if not _ratio_value(config.get("threshold")):
        raise BenchmarkEvidenceError("protocol threshold invalid")
    for field, maximum in (("k", 64), ("min_overlap", 64), ("k_live", 64)):
        item = config.get(field)
        if type(item) is not int or not 1 <= item <= maximum:
            raise BenchmarkEvidenceError(f"protocol {field} invalid")

    scoring = value.get("scoring")
    if not isinstance(scoring, dict) or frozenset(scoring) != _SCORING_FIELDS:
        raise BenchmarkEvidenceError("protocol scoring fields mismatch")
    if scoring.get("normalization") != NORMALIZATION_SPEC:
        raise BenchmarkEvidenceError("protocol normalization mismatch")
    resamples = scoring.get("bootstrap_resamples")
    seed = scoring.get("bootstrap_seed")
    confidence = scoring.get("bootstrap_confidence")
    if type(resamples) is not int or not 1_000 <= resamples <= 100_000:
        raise BenchmarkEvidenceError("protocol bootstrap_resamples invalid")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise BenchmarkEvidenceError("protocol bootstrap_seed invalid")
    if (
        type(confidence) not in (int, float)
        or isinstance(confidence, bool)
        or not math.isfinite(float(confidence))
        or not 0.8 <= float(confidence) < 1.0
    ):
        raise BenchmarkEvidenceError("protocol bootstrap_confidence invalid")

    gates = value.get("gates")
    if not isinstance(gates, dict) or frozenset(gates) != _GATE_FIELDS:
        raise BenchmarkEvidenceError("protocol gate groups mismatch")
    mechanism = gates.get("mechanism")
    capability = gates.get("capability")
    safety = gates.get("safety")
    if (
        not isinstance(mechanism, dict)
        or frozenset(mechanism) != _MECHANISM_GATE_FIELDS
        or not all(_ratio_value(mechanism.get(key)) for key in mechanism)
    ):
        raise BenchmarkEvidenceError("mechanism gates invalid")
    if (
        not isinstance(capability, dict)
        or frozenset(capability) != _CAPABILITY_GATE_FIELDS
        or not all(
            _ratio_value(capability.get(key))
            for key in _CAPABILITY_GATE_FIELDS
            if key != "replay_exact_match_required"
        )
        or type(capability.get("replay_exact_match_required")) is not bool
    ):
        raise BenchmarkEvidenceError("capability gates invalid")
    if (
        not isinstance(safety, dict)
        or frozenset(safety) != _SAFETY_GATE_FIELDS
        or not _ratio_value(safety.get("unknown_false_grounded_rate_max"))
        or not _ratio_value(safety.get("unknown_false_used_live_rate_max"))
        or type(safety.get("worker_error_count_max")) is not int
        or not 0 <= safety["worker_error_count_max"] <= 10_000
        or any(
            type(safety.get(key)) is not bool
            for key in (
                "candidate_unchanged_required",
                "source_unchanged_required",
                "preregistration_unchanged_required",
                "temporary_state_isolation_required",
            )
        )
    ):
        raise BenchmarkEvidenceError("safety gates invalid")

    rerun = value.get("rerun_policy")
    if not isinstance(rerun, dict) or frozenset(rerun) != _RERUN_FIELDS:
        raise BenchmarkEvidenceError("rerun policy fields mismatch")
    if rerun.get("result_run_limit") != 1 or rerun.get("mechanical_retry_limit") != 0:
        raise BenchmarkEvidenceError("rerun policy must permit one result run and no retry")
    if rerun.get("post_result_tuning_prohibited") is not True:
        raise BenchmarkEvidenceError("post-result tuning must be prohibited")
    if (
        rerun.get("new_preregistration_required_after_candidate_or_protocol_change")
        is not True
    ):
        raise BenchmarkEvidenceError(
            "candidate/protocol changes must require a new preregistration"
        )


def _validate_exposure_audit(value: Any) -> None:
    if not isinstance(value, dict) or frozenset(value) != _EXPOSURE_FIELDS:
        raise BenchmarkEvidenceError("exposure_audit fields mismatch")
    required_true = (
        "prior_examples_excluded",
        "full_string_repo_scan_performed_before_freeze",
        "new_entity_repo_scan_performed_before_freeze",
        "public_same_repo_items",
    )
    if any(value.get(field) is not True for field in required_true):
        raise BenchmarkEvidenceError("exposure audit required assertions missing")
    if value.get("hidden_holdout") is not False:
        raise BenchmarkEvidenceError("same-repository items cannot claim hidden holdout")
    if value.get("independent_evaluator") is not False:
        raise BenchmarkEvidenceError("local evaluator cannot claim independence")
    if value.get("full_string_hit_count_before_freeze") != 0:
        raise BenchmarkEvidenceError("new full strings had pre-freeze repository exposure")
    if value.get("new_entity_hit_count_before_freeze") != 0:
        raise BenchmarkEvidenceError("new entities had pre-freeze repository exposure")
    if value.get("repeated_tuning_risk") not in {"high", "very_high"}:
        raise BenchmarkEvidenceError("repeated-tuning risk must be explicit")
    if not _limitations(value.get("limitations"), minimum=4):
        raise BenchmarkEvidenceError("exposure limitations are incomplete")


def _validate_items(
    preregistration_id: str,
    positives: Any,
    unknowns: Any,
) -> None:
    if not isinstance(positives, list) or len(positives) != 48:
        raise BenchmarkEvidenceError("preregistration requires exactly 48 positive items")
    if not isinstance(unknowns, list) or len(unknowns) != 12:
        raise BenchmarkEvidenceError("preregistration requires exactly 12 unknown controls")

    identifiers: list[str] = []
    sources: list[str] = []
    facts: list[str] = []
    questions: list[str] = []
    for index, row in enumerate(positives):
        if not isinstance(row, dict) or frozenset(row) != _POSITIVE_FIELDS:
            raise BenchmarkEvidenceError(f"positive item {index} fields mismatch")
        for field in ("family", "fact", "question", "gold"):
            if not _bounded_text(row.get(field)):
                raise BenchmarkEvidenceError(f"positive item {index} {field} invalid")
        source = row.get("source_id")
        if not isinstance(source, str) or _SOURCE_ID_RE.fullmatch(source) is None:
            raise BenchmarkEvidenceError(f"positive item {index} source invalid")
        expected = preregistered_item_id(
            preregistration_id,
            "positive",
            {key: row[key] for key in sorted(_POSITIVE_FIELDS - {"item_id"})},
        )
        if row.get("item_id") != expected:
            raise BenchmarkEvidenceError(f"positive item {index} item_id mismatch")
        identifiers.append(row["item_id"])
        sources.append(source)
        facts.append(row["fact"])
        questions.append(row["question"])

    for index, row in enumerate(unknowns):
        if not isinstance(row, dict) or frozenset(row) != _UNKNOWN_FIELDS:
            raise BenchmarkEvidenceError(f"unknown control {index} fields mismatch")
        for field in ("family", "question"):
            if not _bounded_text(row.get(field)):
                raise BenchmarkEvidenceError(f"unknown control {index} {field} invalid")
        expected = preregistered_item_id(
            preregistration_id,
            "unknown",
            {key: row[key] for key in sorted(_UNKNOWN_FIELDS - {"item_id"})},
        )
        if row.get("item_id") != expected:
            raise BenchmarkEvidenceError(f"unknown control {index} item_id mismatch")
        identifiers.append(row["item_id"])
        questions.append(row["question"])

    for label, values in (
        ("item IDs", identifiers),
        ("source IDs", sources),
        ("positive facts", facts),
        ("questions", questions),
    ):
        if len(values) != len(set(values)):
            raise BenchmarkEvidenceError(f"preregistered {label} are not unique")


def validate_preregistration(value: dict[str, Any]) -> dict[str, Any]:
    if frozenset(value) != _ROOT_FIELDS:
        raise BenchmarkEvidenceError("preregistration fields mismatch")
    if value.get("schema_version") != PREREGISTRATION_SCHEMA:
        raise BenchmarkEvidenceError("preregistration schema mismatch")
    preregistration_id = value.get("preregistration_id")
    if (
        not isinstance(preregistration_id, str)
        or _ID_RE.fullmatch(preregistration_id) is None
    ):
        raise BenchmarkEvidenceError("preregistration_id invalid")
    frozen_at = value.get("frozen_at")
    if (
        not isinstance(frozen_at, str)
        or not frozen_at.endswith("Z")
        or len(frozen_at) > 64
    ):
        raise BenchmarkEvidenceError("frozen_at must be a UTC timestamp")
    try:
        from datetime import datetime

        datetime.fromisoformat(frozen_at[:-1] + "+00:00")
    except ValueError as exc:
        raise BenchmarkEvidenceError("frozen_at timestamp invalid") from exc

    _validate_claim_boundary(value.get("claim_boundary"))
    candidate = value.get("candidate")
    _validate_candidate(candidate)
    _validate_protocol(value.get("protocol"), candidate)
    _validate_exposure_audit(value.get("exposure_audit"))
    _validate_items(
        preregistration_id,
        value.get("items"),
        value.get("unknown_controls"),
    )
    if value.get("static_paragraphs") != []:
        raise BenchmarkEvidenceError("static_paragraphs must be preregistered as []")
    return value


def load_preregistration(path: Path) -> tuple[dict[str, Any], str]:
    relative = _safe_repo_relative(path)
    try:
        payload = (REPO / relative).read_bytes()
    except OSError as exc:  # pragma: no cover - _safe_repo_relative read race
        raise BenchmarkEvidenceError("preregistration became unreadable") from exc
    value = strict_json_bytes(payload, label="LiveMemory preregistration")
    return validate_preregistration(value), relative


def _normalize_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", str(text)).casefold()
    return [
        token
        for token in _TOKEN_RE.findall(normalized)
        if token not in _ARTICLES
    ]


def token_f1(prediction: str | None, gold: str) -> float:
    if not isinstance(prediction, str):
        return 0.0
    predicted = _normalize_tokens(prediction)
    expected = _normalize_tokens(gold)
    if not predicted or not expected:
        return 1.0 if predicted == expected else 0.0
    common = Counter(predicted) & Counter(expected)
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(predicted)
    recall = overlap / len(expected)
    return round(2.0 * precision * recall / (precision + recall), 12)


def normalized_exact_match(prediction: str | None, gold: str) -> bool:
    if not isinstance(prediction, str):
        return False
    return _normalize_tokens(prediction) == _normalize_tokens(gold)


def _fact_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _output_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_worker_request(
    preregistration: Mapping[str, Any],
    condition: str,
) -> dict[str, Any]:
    if condition not in {"OFF", "ON"}:
        raise BenchmarkEvidenceError("condition must be OFF or ON")
    config = preregistration["protocol"]["candidate_config"]
    learn = (
        [
            {"fact": row["fact"], "source_id": row["source_id"]}
            for row in preregistration["items"]
        ]
        if condition == "ON"
        else []
    )
    questions = [
        {"index": index, "question": row["question"]}
        for index, row in enumerate(
            [*preregistration["items"], *preregistration["unknown_controls"]]
        )
    ]
    return {
        "schema_version": WORKER_REQUEST_SCHEMA,
        "condition": condition,
        "checkpoint": config["checkpoint"],
        "device_policy": preregistration["protocol"]["device_policy"],
        "config": {
            "threshold": config["threshold"],
            "k": config["k"],
            "min_overlap": config["min_overlap"],
            "k_live": config["k_live"],
        },
        "learn": learn,
        "questions": questions,
        "static_paragraphs": [],
    }


def _contains_gold_key(value: Any) -> bool:
    forbidden = {"gold", "answer_key", "expected_answer", "label"}
    if isinstance(value, Mapping):
        return any(
            str(key).casefold() in forbidden or _contains_gold_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_gold_key(child) for child in value)
    return False


def dry_run_record(
    preregistration: Mapping[str, Any],
    *,
    preregistration_relative: str,
) -> dict[str, Any]:
    """Validate bindings and requests without launching/importing the candidate."""

    source = bind_files(REPO, _EVALUATOR_PATHS)
    candidate = bind_files(REPO, preregistration["candidate"]["paths"])
    dataset = bind_files(REPO, [preregistration_relative])
    requests = []
    for replay in preregistration["protocol"]["replays"]:
        for condition in replay["condition_order"]:
            request = build_worker_request(preregistration, condition)
            if _contains_gold_key(request):
                raise BenchmarkEvidenceError("gold-like key crossed candidate boundary")
            requests.append(
                {
                    "replay_id": replay["id"],
                    "condition": condition,
                    "request_sha256": hashlib.sha256(
                        canonical_json_bytes(request)
                    ).hexdigest(),
                    "learn_count": len(request["learn"]),
                    "question_count": len(request["questions"]),
                    "static_paragraph_count": 0,
                    "gold_key_present": False,
                }
            )
    return {
        "schema_version": "atanor.live-memory-realtime-dry-run.v1",
        "candidate_executed": False,
        "candidate_imported_by_harness": False,
        "source": source,
        "candidate": candidate,
        "candidate_matches_preregistered_digest": (
            candidate["content_sha256"]
            == preregistration["candidate"]["content_sha256"]
        ),
        "preregistration": dataset,
        "requests": requests,
        "arm_count": len(requests),
        "positive_count": len(preregistration["items"]),
        "unknown_control_count": len(preregistration["unknown_controls"]),
        "claim_boundary": "narrow_synthetic_single_hop_recall_only",
    }


def _run_worker(
    request: dict[str, Any],
    timeout_seconds: int,
    device_policy: str,
    hash_seed: str,
    worker_path: Path = WORKER,
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONHASHSEED"] = hash_seed
    if device_policy == "cpu_only":
        # On Windows/PyTorch, an empty value can leave availability reporting
        # inconsistent with device_count().  "-1" is the verified no-GPU
        # sentinel and keeps checkpoint map_location on CPU.
        environment["CUDA_VISIBLE_DEVICES"] = "-1"
    try:
        completed = subprocess.run(
            [sys.executable, "-B", str(worker_path)],
            cwd=REPO,
            env=environment,
            input=canonical_json_bytes(request),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BenchmarkEvidenceError(
            f"candidate worker failed to launch: {type(exc).__name__}"
        ) from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-2_000:]
        raise BenchmarkEvidenceError(
            f"candidate worker exited {completed.returncode}: {detail}"
        )
    return strict_json_bytes(
        completed.stdout,
        label="LiveMemory candidate result",
    )


def _finite_latency(value: Any) -> bool:
    return (
        type(value) in (int, float)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 86_400_000
    )


def _validate_worker_result(
    value: dict[str, Any],
    *,
    request: Mapping[str, Any],
    expected_hash_seed: str,
) -> dict[str, Any]:
    if frozenset(value) != _WORKER_RESULT_FIELDS:
        raise BenchmarkEvidenceError("candidate worker result fields mismatch")
    if value.get("schema_version") != WORKER_RESULT_SCHEMA:
        raise BenchmarkEvidenceError("candidate worker result schema mismatch")
    if value.get("condition") != request["condition"]:
        raise BenchmarkEvidenceError("candidate worker condition mismatch")
    if not isinstance(value.get("device"), str) or not value["device"]:
        raise BenchmarkEvidenceError("candidate worker device invalid")
    if value.get("python_hash_seed") != expected_hash_seed:
        raise BenchmarkEvidenceError("candidate worker PYTHONHASHSEED mismatch")

    isolation = value.get("isolation")
    if not isinstance(isolation, dict) or frozenset(isolation) != _ISOLATION_FIELDS:
        raise BenchmarkEvidenceError("candidate isolation result fields mismatch")
    boolean_fields = (
        "temporary_state_initially_empty",
        "hippocampus_path_is_temporary",
        "cortex_path_is_temporary",
        "miss_path_is_temporary",
        "record_misses",
        "include_unverified",
        "learned_verified",
        "cortex_write_detected",
        "miss_write_detected",
    )
    if any(type(isolation.get(field)) is not bool for field in boolean_fields):
        raise BenchmarkEvidenceError("candidate isolation booleans invalid")
    if type(isolation.get("learned_count")) is not int:
        raise BenchmarkEvidenceError("candidate learned count invalid")
    for field in ("unexpected_temporary_files", "temporary_files"):
        rows = isolation.get(field)
        if (
            not isinstance(rows, list)
            or len(rows) > 100
            or any(not isinstance(row, str) or len(row) > 1_024 for row in rows)
        ):
            raise BenchmarkEvidenceError(f"candidate isolation {field} invalid")

    expected_learn = request["learn"]
    learned = value.get("learned")
    if not isinstance(learned, list) or len(learned) != len(expected_learn):
        raise BenchmarkEvidenceError("candidate learned receipt count mismatch")
    for index, (actual, expected) in enumerate(zip(learned, expected_learn)):
        if (
            not isinstance(actual, dict)
            or frozenset(actual) != _LEARNED_RESULT_FIELDS
            or actual.get("source_id") != expected["source_id"]
            or actual.get("fact_sha256") != _fact_digest(expected["fact"])
            or (
                actual.get("candidate_item_id") is not None
                and type(actual.get("candidate_item_id")) is not int
            )
        ):
            raise BenchmarkEvidenceError(
                f"candidate learned receipt {index} mismatch"
            )

    rows = value.get("items")
    if not isinstance(rows, list) or len(rows) != len(request["questions"]):
        raise BenchmarkEvidenceError("candidate worker item count mismatch")
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or frozenset(row) != _WORKER_ITEM_FIELDS:
            raise BenchmarkEvidenceError(f"candidate worker row {index} fields mismatch")
        if row.get("index") != index:
            raise BenchmarkEvidenceError(f"candidate worker row {index} index mismatch")
        if type(row.get("emitted")) is not bool:
            raise BenchmarkEvidenceError(f"candidate worker row {index} emitted invalid")
        answer = row.get("answer")
        if answer is not None and (
            not isinstance(answer, str) or len(answer) > _MAX_TEXT
        ):
            raise BenchmarkEvidenceError(f"candidate worker row {index} answer invalid")
        if row["emitted"] is not (isinstance(answer, str) and bool(answer.strip())):
            raise BenchmarkEvidenceError(
                f"candidate worker row {index} answer/emitted mismatch"
            )
        if type(row.get("used_live")) is not bool or type(row.get("grounded")) is not bool:
            raise BenchmarkEvidenceError(
                f"candidate worker row {index} booleans invalid"
            )
        if not _ratio_value(row.get("confidence")):
            raise BenchmarkEvidenceError(
                f"candidate worker row {index} confidence invalid"
            )
        for field in ("support", "evidence"):
            child = row.get(field)
            if (
                not isinstance(child, list)
                or len(child) > _MAX_RESULT_LIST
                or len(canonical_json_bytes(child)) > 256 * 1024
            ):
                raise BenchmarkEvidenceError(
                    f"candidate worker row {index} {field} invalid"
                )
        source = row.get("recall_top_source")
        if source is not None and (
            not isinstance(source, str) or len(source) > 1_024
        ):
            raise BenchmarkEvidenceError(
                f"candidate worker row {index} recall source invalid"
            )
        digest = row.get("recall_top_fact_sha256")
        if digest is not None and (
            not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None
        ):
            raise BenchmarkEvidenceError(
                f"candidate worker row {index} recall digest invalid"
            )
        error = row.get("error_type")
        if error is not None and (
            not isinstance(error, str) or not error or len(error) > 256
        ):
            raise BenchmarkEvidenceError(
                f"candidate worker row {index} error type invalid"
            )
        if error is not None and (row["emitted"] or answer is not None):
            raise BenchmarkEvidenceError(
                f"candidate worker row {index} error/output mismatch"
            )
        if not _finite_latency(row.get("latency_ms")):
            raise BenchmarkEvidenceError(
                f"candidate worker row {index} latency invalid"
            )
    return value


def collect_arms(
    preregistration: Mapping[str, Any],
    *,
    runner: Runner = _run_worker,
    worker_path: Path = WORKER,
    on_arm_complete: ArmCallback | None = None,
) -> list[dict[str, Any]]:
    """Launch exactly four fresh workers in the frozen counterbalanced order."""

    protocol = preregistration["protocol"]
    arms = []
    process_ordinal = 0
    for replay in protocol["replays"]:
        for condition in replay["condition_order"]:
            request = build_worker_request(preregistration, condition)
            if _contains_gold_key(request):
                raise BenchmarkEvidenceError("gold-like key crossed candidate boundary")
            raw = runner(
                request,
                int(protocol["worker_timeout_seconds"]),
                str(protocol["device_policy"]),
                str(protocol["python_hash_seed"]),
                worker_path,
            )
            result = _validate_worker_result(
                raw,
                request=request,
                expected_hash_seed=str(protocol["python_hash_seed"]),
            )
            arm = {
                "process_ordinal": process_ordinal,
                "replay_id": replay["id"],
                "condition": condition,
                "request_sha256": hashlib.sha256(
                    canonical_json_bytes(request)
                ).hexdigest(),
                "result": result,
            }
            arms.append(arm)
            if on_arm_complete is not None:
                on_arm_complete(arm)
            process_ordinal += 1
    if process_ordinal != 4:
        raise BenchmarkEvidenceError("protocol did not launch exactly four arms")
    return arms


def _mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 12) if values else 0.0


def _mcnemar_exact_p(off: Sequence[bool], on: Sequence[bool]) -> tuple[int, int, float]:
    if len(off) != len(on) or not off:
        raise BenchmarkEvidenceError("McNemar inputs invalid")
    off_only = sum(1 for left, right in zip(off, on) if left and not right)
    on_only = sum(1 for left, right in zip(off, on) if not left and right)
    discordant = off_only + on_only
    if discordant == 0:
        return off_only, on_only, 1.0
    tail = min(off_only, on_only)
    probability = sum(
        math.comb(discordant, index) for index in range(tail + 1)
    ) / (2**discordant)
    return off_only, on_only, round(min(1.0, 2.0 * probability), 12)


def _bootstrap_paired_em_lift_lower(
    off: Sequence[bool],
    on: Sequence[bool],
    *,
    resamples: int,
    seed: int,
    confidence: float,
) -> float:
    """Deterministic paired-item percentile lower bound.

    The same sampled item indices are used for OFF and ON.  The lower endpoint
    is the two-sided ``(1-confidence)/2`` empirical percentile, selected by a
    frozen floor-index rule.
    """

    if len(off) != len(on) or not off:
        raise BenchmarkEvidenceError("bootstrap inputs invalid")
    generator = random.Random(seed)
    count = len(off)
    lifts = []
    for _ in range(resamples):
        indices = [generator.randrange(count) for _ in range(count)]
        off_rate = sum(bool(off[index]) for index in indices) / count
        on_rate = sum(bool(on[index]) for index in indices) / count
        lifts.append(on_rate - off_rate)
    lifts.sort()
    alpha = (1.0 - confidence) / 2.0
    lower_index = max(0, min(resamples - 1, math.floor(alpha * (resamples - 1))))
    return round(float(lifts[lower_index]), 12)


def _isolation_pass(
    result: Mapping[str, Any],
    *,
    condition: str,
    expected_learned: int,
) -> bool:
    isolation = result["isolation"]
    expected_files = ["hippocampus.jsonl"] if condition == "ON" else []
    return all(
        (
            isolation["temporary_state_initially_empty"] is True,
            isolation["hippocampus_path_is_temporary"] is True,
            isolation["cortex_path_is_temporary"] is True,
            isolation["miss_path_is_temporary"] is True,
            isolation["record_misses"] is False,
            isolation["include_unverified"] is False,
            isolation["learned_verified"] is True,
            isolation["learned_count"] == expected_learned,
            isolation["cortex_write_detected"] is False,
            isolation["miss_write_detected"] is False,
            isolation["unexpected_temporary_files"] == [],
            isolation["temporary_files"] == expected_files,
        )
    )


def _replay_projection(row: Mapping[str, Any], device: str) -> dict[str, Any]:
    return {
        "device": device,
        "emitted": row["emitted"],
        "answer": row["answer"],
        "used_live": row["used_live"],
        "grounded": row["grounded"],
        "confidence": row["confidence"],
        "support": row["support"],
        "evidence": row["evidence"],
        "recall_top_source": row["recall_top_source"],
        "recall_top_fact_sha256": row["recall_top_fact_sha256"],
        "error_type": row["error_type"],
    }


def score_arms(
    preregistration: Mapping[str, Any],
    arms: Sequence[Mapping[str, Any]],
    *,
    integrity: Mapping[str, bool],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    positives = preregistration["items"]
    unknowns = preregistration["unknown_controls"]
    scoring = preregistration["protocol"]["scoring"]
    expected_rows = [*positives, *unknowns]
    measured_items: list[dict[str, Any]] = []
    arm_metrics: list[dict[str, Any]] = []
    projections: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for arm in arms:
        replay_id = str(arm["replay_id"])
        condition = str(arm["condition"])
        result = arm["result"]
        rows = result["items"]
        projections[(replay_id, condition)] = [
            _replay_projection(row, str(result["device"])) for row in rows
        ]
        positive_f1: list[float] = []
        positive_exact_match: list[bool] = []
        recall_matches: list[bool] = []
        exact_source_inclusions: list[bool] = []
        used_live_positive: list[bool] = []
        false_grounded: list[bool] = []
        false_used_live: list[bool] = []
        error_count = 0

        for index, (registered, prediction) in enumerate(zip(expected_rows, rows)):
            kind = "positive" if index < len(positives) else "unknown"
            answer = prediction["answer"]
            error = prediction["error_type"]
            if error is not None:
                error_count += 1
            if kind == "positive":
                f1 = token_f1(answer, registered["gold"])
                exact_match = (
                    error is None
                    and prediction["emitted"]
                    and normalized_exact_match(answer, registered["gold"])
                )
                positive_f1.append(f1)
                positive_exact_match.append(exact_match)
                expected_source = registered["source_id"]
                expected_fact_digest = _fact_digest(registered["fact"])
                expected_title = f"live:{expected_source}"
                recall_match = (
                    prediction["recall_top_source"] == expected_source
                    and prediction["recall_top_fact_sha256"]
                    == expected_fact_digest
                )
                exact_source_inclusion = (
                    expected_title in prediction["support"]
                    and any(
                        isinstance(receipt, Mapping)
                        and receipt.get("origin") == "live"
                        and receipt.get("title") == expected_title
                        for receipt in prediction["evidence"]
                    )
                )
                recall_matches.append(recall_match)
                exact_source_inclusions.append(exact_source_inclusion)
                used_live_positive.append(prediction["used_live"])
                safety_pass = None
            else:
                f1 = None
                exact_match = False
                recall_match = None
                exact_source_inclusion = None
                false_grounded.append(bool(prediction["grounded"]))
                false_used_live.append(bool(prediction["used_live"]))
                safety_pass = (
                    error is None
                    and not prediction["grounded"]
                    and not prediction["used_live"]
                )

            if error is not None:
                status = "error"
                fired = False
                correct = False
                output_sha256 = None
            elif prediction["emitted"]:
                status = (
                    "correct"
                    if (exact_match if kind == "positive" else safety_pass)
                    else "wrong"
                )
                fired = True
                correct = status == "correct"
                output_sha256 = _output_digest(str(answer))
            else:
                status = "abstain"
                fired = False
                correct = False
                output_sha256 = None

            measured_items.append(
                {
                    "item_id": item_id(
                        {
                            "preregistered_item_id": registered["item_id"],
                            "replay_id": replay_id,
                            "condition": condition,
                        }
                    ),
                    "status": status,
                    "fired": fired,
                    "correct": correct,
                    "output_sha256": output_sha256,
                    "latency_ms": prediction["latency_ms"],
                    "metadata": {
                        "preregistered_item_id": registered["item_id"],
                        "kind": kind,
                        "family": registered["family"],
                        "replay_id": replay_id,
                        "condition": condition,
                        "candidate_emitted": prediction["emitted"],
                        "candidate_answer": answer,
                        "normalized_token_f1": f1,
                        "normalized_exact_match": exact_match
                        if kind == "positive"
                        else None,
                        "unknown_safety_pass": safety_pass,
                        "used_live": prediction["used_live"],
                        "grounded": prediction["grounded"],
                        "confidence": prediction["confidence"],
                        "recall_top_source": prediction["recall_top_source"],
                        "recall_top_fact_sha256": prediction[
                            "recall_top_fact_sha256"
                        ],
                        "recall_at_1_match": recall_match,
                        "support": prediction["support"],
                        "evidence": prediction["evidence"],
                        "support_evidence_includes_exact_source": (
                            exact_source_inclusion
                        ),
                        "candidate_error_type": error,
                        "support_sha256": hashlib.sha256(
                            canonical_json_bytes(prediction["support"])
                        ).hexdigest(),
                        "evidence_sha256": hashlib.sha256(
                            canonical_json_bytes(prediction["evidence"])
                        ).hexdigest(),
                    },
                }
            )

        arm_metrics.append(
            {
                "process_ordinal": arm["process_ordinal"],
                "replay_id": replay_id,
                "condition": condition,
                "device": result["device"],
                "request_sha256": arm["request_sha256"],
                "positive_mean_f1": _mean(positive_f1),
                "positive_exact_match_rate": _mean(
                    [float(row) for row in positive_exact_match]
                ),
                "positive_exact_match_vector": positive_exact_match,
                "recall_at_1_rate": _mean(
                    [float(row) for row in recall_matches]
                ),
                "support_evidence_exact_source_inclusion_rate": _mean(
                    [float(row) for row in exact_source_inclusions]
                ),
                "used_live_positive_rate": _mean(
                    [float(row) for row in used_live_positive]
                ),
                "unknown_false_grounded_rate": _mean(
                    [float(row) for row in false_grounded]
                ),
                "unknown_false_used_live_rate": _mean(
                    [float(row) for row in false_used_live]
                ),
                "worker_error_count": error_count,
                "temporary_state_isolation_pass": _isolation_pass(
                    result,
                    condition=condition,
                    expected_learned=len(positives) if condition == "ON" else 0,
                ),
            }
        )

    replay_ids = [row["id"] for row in preregistration["protocol"]["replays"]]
    by_key = {
        (row["replay_id"], row["condition"]): row for row in arm_metrics
    }
    replay_stats = []
    for replay_id in replay_ids:
        off = by_key[(replay_id, "OFF")]
        on = by_key[(replay_id, "ON")]
        off_only, on_only, p_value = _mcnemar_exact_p(
            off["positive_exact_match_vector"],
            on["positive_exact_match_vector"],
        )
        bootstrap_lower = _bootstrap_paired_em_lift_lower(
            off["positive_exact_match_vector"],
            on["positive_exact_match_vector"],
            resamples=int(scoring["bootstrap_resamples"]),
            seed=int(scoring["bootstrap_seed"]),
            confidence=float(scoring["bootstrap_confidence"]),
        )
        replay_stats.append(
            {
                "replay_id": replay_id,
                "off_mean_token_f1": off["positive_mean_f1"],
                "on_mean_token_f1": on["positive_mean_f1"],
                "off_exact_match_rate": off["positive_exact_match_rate"],
                "on_exact_match_rate": on["positive_exact_match_rate"],
                "paired_exact_match_lift": round(
                    on["positive_exact_match_rate"]
                    - off["positive_exact_match_rate"],
                    12,
                ),
                "bootstrap_paired_em_lift_lower": bootstrap_lower,
                "bootstrap_resamples": int(scoring["bootstrap_resamples"]),
                "bootstrap_seed": int(scoring["bootstrap_seed"]),
                "bootstrap_confidence": float(scoring["bootstrap_confidence"]),
                "mcnemar_off_only": off_only,
                "mcnemar_on_only": on_only,
                "mcnemar_exact_two_sided_p": p_value,
            }
        )

    replay_mismatches = []
    for condition in ("OFF", "ON"):
        left = projections[(replay_ids[0], condition)]
        right = projections[(replay_ids[1], condition)]
        for index, (first, second) in enumerate(zip(left, right)):
            if first != second:
                replay_mismatches.append(
                    {
                        "condition": condition,
                        "question_index": index,
                        "first_sha256": hashlib.sha256(
                            canonical_json_bytes(first)
                        ).hexdigest(),
                        "second_sha256": hashlib.sha256(
                            canonical_json_bytes(second)
                        ).hexdigest(),
                    }
                )

    on_arms = [row for row in arm_metrics if row["condition"] == "ON"]
    off_arms = [row for row in arm_metrics if row["condition"] == "OFF"]
    summary = {
        "claim_boundary": "narrow_synthetic_single_hop_recall_only",
        "general_reasoning_improvement_claimed": False,
        "positive_item_count": len(positives),
        "unknown_control_count": len(unknowns),
        "replay_count": len(replay_ids),
        "fresh_process_arm_count": len(arms),
        "arm_metrics": [
            {
                key: value
                for key, value in row.items()
                if key != "positive_exact_match_vector"
            }
            for row in arm_metrics
        ],
        "replay_metrics": replay_stats,
        "mechanism": {
            "on_recall_at_1_min_observed": min(
                row["recall_at_1_rate"] for row in on_arms
            ),
            "on_support_evidence_exact_source_inclusion_rate_min_observed": min(
                row["support_evidence_exact_source_inclusion_rate"]
                for row in on_arms
            ),
            "on_used_live_rate_min_observed_diagnostic": min(
                row["used_live_positive_rate"] for row in on_arms
            ),
        },
        "capability": {
            "off_mean_token_f1_max_observed_diagnostic": max(
                row["positive_mean_f1"] for row in off_arms
            ),
            "on_mean_token_f1_min_observed": min(
                row["positive_mean_f1"] for row in on_arms
            ),
            "off_exact_match_rate_max_observed_diagnostic": max(
                row["positive_exact_match_rate"] for row in off_arms
            ),
            "on_exact_match_rate_min_observed": min(
                row["positive_exact_match_rate"] for row in on_arms
            ),
            "paired_exact_match_lift_min_observed": min(
                row["paired_exact_match_lift"] for row in replay_stats
            ),
            "bootstrap_paired_em_lift_lower_min_observed": min(
                row["bootstrap_paired_em_lift_lower"] for row in replay_stats
            ),
            "mcnemar_exact_p_max_observed": max(
                row["mcnemar_exact_two_sided_p"] for row in replay_stats
            ),
            "replay_exact_match": not replay_mismatches,
            "replay_mismatch_count": len(replay_mismatches),
            "replay_mismatches": replay_mismatches,
        },
        "safety": {
            "unknown_false_grounded_rate_max_observed": max(
                row["unknown_false_grounded_rate"] for row in arm_metrics
            ),
            "unknown_false_used_live_rate_max_observed": max(
                row["unknown_false_used_live_rate"] for row in arm_metrics
            ),
            "worker_error_count": sum(
                row["worker_error_count"] for row in arm_metrics
            ),
            "temporary_state_isolation_all_arms": all(
                row["temporary_state_isolation_pass"] for row in arm_metrics
            ),
            **dict(integrity),
        },
    }

    gates = preregistration["protocol"]["gates"]
    mechanism_checks = {
        "on_recall_at_1": (
            summary["mechanism"]["on_recall_at_1_min_observed"]
            >= gates["mechanism"]["on_recall_at_1_min"]
        ),
        "on_support_evidence_exact_source_inclusion": (
            summary["mechanism"][
                "on_support_evidence_exact_source_inclusion_rate_min_observed"
            ]
            >= gates["mechanism"][
                "on_exact_support_source_provenance_rate_min"
            ]
        ),
    }
    capability_checks = {
        "on_mean_token_f1": (
            summary["capability"]["on_mean_token_f1_min_observed"]
            >= gates["capability"]["on_mean_token_f1_min"]
        ),
        "on_exact_match_rate": (
            summary["capability"]["on_exact_match_rate_min_observed"]
            >= gates["capability"]["on_exact_match_rate_min"]
        ),
        "paired_exact_match_lift": (
            summary["capability"]["paired_exact_match_lift_min_observed"]
            >= gates["capability"]["paired_exact_match_lift_min"]
        ),
        "mcnemar_exact_p": (
            summary["capability"]["mcnemar_exact_p_max_observed"]
            <= gates["capability"]["mcnemar_exact_p_max"]
        ),
        "bootstrap_paired_em_lift_lower": (
            summary["capability"][
                "bootstrap_paired_em_lift_lower_min_observed"
            ]
            > gates["capability"][
                "bootstrap_paired_em_lift_lower_exclusive_min"
            ]
        ),
        "replay_exact_match": (
            summary["capability"]["replay_exact_match"]
            if gates["capability"]["replay_exact_match_required"]
            else True
        ),
    }
    safety_checks = {
        "unknown_false_grounded_rate": (
            summary["safety"]["unknown_false_grounded_rate_max_observed"]
            <= gates["safety"]["unknown_false_grounded_rate_max"]
        ),
        "unknown_false_used_live_rate": (
            summary["safety"]["unknown_false_used_live_rate_max_observed"]
            <= gates["safety"]["unknown_false_used_live_rate_max"]
        ),
        "worker_error_count": (
            summary["safety"]["worker_error_count"]
            <= gates["safety"]["worker_error_count_max"]
        ),
        "candidate_unchanged": (
            summary["safety"]["candidate_same_before_after"]
            if gates["safety"]["candidate_unchanged_required"]
            else True
        ),
        "source_unchanged": (
            summary["safety"]["source_same_before_after"]
            if gates["safety"]["source_unchanged_required"]
            else True
        ),
        "preregistration_unchanged": (
            summary["safety"]["preregistration_same_before_after"]
            if gates["safety"]["preregistration_unchanged_required"]
            else True
        ),
        "temporary_state_isolation": (
            summary["safety"]["temporary_state_isolation_all_arms"]
            if gates["safety"]["temporary_state_isolation_required"]
            else True
        ),
    }
    gate_results = {
        "mechanism": {
            "checks": mechanism_checks,
            "green": all(mechanism_checks.values()),
        },
        "capability": {
            "checks": capability_checks,
            "green": all(capability_checks.values()),
        },
        "safety": {
            "checks": safety_checks,
            "green": all(safety_checks.values()),
        },
    }
    gate_results["overall_green"] = all(
        gate_results[group]["green"]
        for group in ("mechanism", "capability", "safety")
    )
    return measured_items, summary, gate_results


def _new_run_id(preregistration_id: str) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{stamp}.live-recall.{preregistration_id}.{uuid.uuid4().hex[:12]}"


def _report_destination(preregistration_id: str) -> Path:
    return ensure_safe_report_output(
        REPO,
        REPORTS / f"live_memory_realtime_{preregistration_id}.json",
    )


def _attempt_destination(preregistration_id: str) -> Path:
    return ensure_safe_report_output(
        REPO,
        REPORTS / f"live_memory_realtime_{preregistration_id}.attempt.json",
    )


def _failure_destination(preregistration_id: str) -> Path:
    return ensure_safe_report_output(
        REPO,
        REPORTS / f"live_memory_realtime_{preregistration_id}.failure.json",
    )


def _write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise BenchmarkEvidenceError(f"write-once path already exists: {path}") from exc


def _arm_receipt(arm: Mapping[str, Any]) -> dict[str, Any]:
    result = arm["result"]
    return {
        "process_ordinal": arm["process_ordinal"],
        "replay_id": arm["replay_id"],
        "condition": arm["condition"],
        "request_sha256": arm["request_sha256"],
        "device": result["device"],
        "python_hash_seed": result["python_hash_seed"],
        "isolation": result["isolation"],
        "learned": result["learned"],
    }


def _failure_payload(
    *,
    preregistration_id: str,
    started_at: str,
    result_path: Path,
    error: Exception,
    completed_arms: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": FAILURE_SCHEMA,
        "preregistration_id": preregistration_id,
        "started_at": started_at,
        "failed_at": utc_now(),
        "status": "failed",
        "error_type": type(error).__name__,
        "error_message": str(error)[-2_000:],
        "completed_arm_count": len(completed_arms),
        "completed_arm_shards": [
            {
                "process_ordinal": arm["process_ordinal"],
                "replay_id": arm["replay_id"],
                "condition": arm["condition"],
                "request_sha256": arm["request_sha256"],
                "result_sha256": hashlib.sha256(
                    canonical_json_bytes(arm["result"])
                ).hexdigest(),
            }
            for arm in completed_arms
        ],
        "result_path": result_path.relative_to(REPO.resolve()).as_posix(),
    }


def run(
    *,
    preregistration_path: Path,
) -> tuple[dict[str, Any], Path]:
    preregistration, preregistration_relative = load_preregistration(
        preregistration_path
    )
    preregistration_id = preregistration["preregistration_id"]
    destination = _report_destination(preregistration_id)
    attempt_path = _attempt_destination(preregistration_id)
    failure_path = _failure_destination(preregistration_id)
    if destination.exists() or attempt_path.exists() or failure_path.exists():
        raise BenchmarkEvidenceError(
            "a fixed report/attempt/failure receipt already exists; another result run is forbidden"
        )

    source_before = bind_files(REPO, _EVALUATOR_PATHS)
    candidate_before = bind_files(REPO, preregistration["candidate"]["paths"])
    dataset_before = bind_files(REPO, [preregistration_relative])
    if (
        candidate_before["content_sha256"]
        != preregistration["candidate"]["content_sha256"]
    ):
        raise BenchmarkEvidenceError(
            "candidate bytes do not match the preregistered frozen digest"
        )

    # Freeze and inspect every request before the first subprocess is launched.
    requests = [
        build_worker_request(preregistration, condition)
        for replay in preregistration["protocol"]["replays"]
        for condition in replay["condition_order"]
    ]
    if any(_contains_gold_key(request) for request in requests):
        raise BenchmarkEvidenceError("gold-like key crossed candidate boundary")
    request_digests = [
        hashlib.sha256(canonical_json_bytes(request)).hexdigest()
        for request in requests
    ]

    # This is the last operation before the first worker launch.  Once written,
    # the attempt remains forever and blocks every retry, including after a
    # crash that produced no aggregate report.
    started_at = utc_now()
    _write_json_exclusive(
        attempt_path,
        {
            "schema_version": ATTEMPT_SCHEMA,
            "preregistration_id": preregistration_id,
            "started_at": started_at,
            "status": "started",
            "preregistration_content_sha256": dataset_before["content_sha256"],
            "candidate_content_sha256": candidate_before["content_sha256"],
            "evaluator_content_sha256": source_before["content_sha256"],
            "result_path": destination.relative_to(REPO.resolve()).as_posix(),
        },
    )
    completed_arms: list[dict[str, Any]] = []
    try:
        arms = collect_arms(
            preregistration,
            runner=_run_worker,
            worker_path=WORKER,
            on_arm_complete=completed_arms.append,
        )
        source_after = bind_files(REPO, _EVALUATOR_PATHS)
        candidate_after = bind_files(REPO, preregistration["candidate"]["paths"])
        dataset_after = bind_files(REPO, [preregistration_relative])
        integrity = {
            "source_same_before_after": source_before == source_after,
            "candidate_same_before_after": candidate_before == candidate_after,
            "preregistration_same_before_after": dataset_before == dataset_after,
        }
        items, measured_summary, gate_results = score_arms(
            preregistration,
            arms,
            integrity=integrity,
        )

        payload = {
            "schema_version": BENCHMARK_EVIDENCE_SCHEMA,
            "evidence_kind": BENCHMARK_EVIDENCE_KIND,
            "run_id": _new_run_id(preregistration["preregistration_id"]),
            "started_at": started_at,
            "completed_at": utc_now(),
            "benchmark": {
                "id": "atanor-live-memory-realtime-novel-single-hop-v1",
                "version": "1",
                "split": "fixed_public_same_repo_preregistration",
                "protocol": (
                    "48 novel synthetic single-hop facts + 12 unknown controls; "
                    "paired OFF/ON; two counterbalanced fresh-process replays"
                ),
                "claim_boundary": (
                    "narrow_single_hop_recall_reconfirmation_only"
                ),
            },
            "config": {
                "preregistration_id": preregistration["preregistration_id"],
                "preregistered_at": preregistration["frozen_at"],
                "candidate_payload": (
                    "condition-specific facts/source IDs/questions; no gold "
                    "fields; static evidence fixed empty"
                ),
                "gold_in_candidate_payload": False,
                "candidate_process": "fresh_subprocess_per_arm",
                "fresh_process_arm_count": 4,
                "request_sha256": request_digests,
                "protocol": preregistration["protocol"],
                "exposure_audit": preregistration["exposure_audit"],
                "arm_receipts": [_arm_receipt(arm) for arm in arms],
                "measured_summary": measured_summary,
                "gate_results": gate_results,
            },
            "environment": environment_record(),
            "source": source_before,
            "candidate": candidate_before,
            "dataset": dataset_before,
            "selection": selection_record(items),
            "evaluator": {
                "identity": "live_memory_realtime_preregistered_eval.v1",
                "source_digest_sha256": source_before["content_sha256"],
                "independent": False,
                "externally_signed": False,
                "limitations": [
                    "Evaluator, preregistered items, and candidate share one "
                    "local repository.",
                    "Fresh subprocesses and temporary paths are not OS-level "
                    "filesystem or network isolation.",
                    "The candidate can ambiently read public repository files "
                    "even though gold is absent from requests.",
                    "Synthetic single-hop lexical recall does not establish "
                    "general reasoning improvement.",
                    "Prior demos and repeated tuning create high template and "
                    "researcher-overfitting risk.",
                    "The checksum is reproducibility evidence, not an external "
                    "signature or E5 attestation.",
                ],
            },
            "metrics": aggregate_items(items),
            "items": items,
            "integrity": {
                "source_same_before_after": integrity[
                    "source_same_before_after"
                ],
                "candidate_same_before_after": integrity[
                    "candidate_same_before_after"
                ],
                "dataset_same_before_after": integrity[
                    "preregistration_same_before_after"
                ],
                "network_isolation_enforced": False,
                "shipped_state_isolation_enforced": False,
                "production_authority": False,
                "e5_claimed": False,
                "limitations": [
                    "Candidate/source/preregistration path hashes are "
                    "descriptive and do not prove executed-code identity.",
                    "Only declared candidate paths are hashed; completeness of "
                    "the transitive closure is preregistered and audited, not "
                    "remotely attested.",
                    "Temporary state-path observations are self-reported by "
                    "the local worker.",
                    "No hidden holdout, independent evaluator, external nonce, "
                    "signature, or network sandbox is present.",
                ],
            },
        }
        manifest = finalize_manifest(payload)
        write_manifest_exclusive(destination, manifest)
        return manifest, destination
    except Exception as exc:
        try:
            _write_json_exclusive(
                failure_path,
                _failure_payload(
                    preregistration_id=preregistration_id,
                    started_at=started_at,
                    result_path=destination,
                    error=exc,
                    completed_arms=completed_arms,
                ),
            )
        except Exception as failure_error:
            if hasattr(exc, "add_note"):
                exc.add_note(
                    f"failure receipt could not be written: {type(failure_error).__name__}: "
                    f"{failure_error}"
                )
        raise


def _bound_preregistration_from_manifest(
    manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    dataset = manifest.get("dataset")
    files = dataset.get("files") if isinstance(dataset, Mapping) else None
    if (
        not isinstance(files, list)
        or len(files) != 1
        or not isinstance(files[0], Mapping)
        or not isinstance(files[0].get("path"), str)
    ):
        raise BenchmarkEvidenceError(
            "LiveMemory receipt must bind exactly one preregistration"
        )
    relative = files[0]["path"]
    current = bind_files(REPO, [relative])
    if current != dataset:
        raise BenchmarkEvidenceError(
            "LiveMemory preregistration bytes differ from the receipt binding"
        )
    preregistration, loaded_relative = load_preregistration(REPO / relative)
    if loaded_relative != relative:
        raise BenchmarkEvidenceError("LiveMemory preregistration path alias mismatch")
    return preregistration, relative


def _reconstruct_arms_from_manifest(
    manifest: Mapping[str, Any],
    preregistration: Mapping[str, Any],
) -> list[dict[str, Any]]:
    config = manifest["config"]
    receipts = config.get("arm_receipts")
    measured = manifest.get("items")
    if not isinstance(receipts, list) or len(receipts) != 4:
        raise BenchmarkEvidenceError("LiveMemory arm receipts must contain four arms")
    if not isinstance(measured, list) or len(measured) != 240:
        raise BenchmarkEvidenceError("LiveMemory receipt must contain exactly 240 items")

    expected_arms = [
        (replay["id"], condition)
        for replay in preregistration["protocol"]["replays"]
        for condition in replay["condition_order"]
    ]
    rows_per_arm = len(preregistration["items"]) + len(
        preregistration["unknown_controls"]
    )
    arms = []
    for process_ordinal, (receipt, expected) in enumerate(
        zip(receipts, expected_arms)
    ):
        if (
            not isinstance(receipt, Mapping)
            or frozenset(receipt) != _ARM_RECEIPT_FIELDS
            or receipt.get("process_ordinal") != process_ordinal
            or (receipt.get("replay_id"), receipt.get("condition")) != expected
        ):
            raise BenchmarkEvidenceError(
                f"LiveMemory arm receipt {process_ordinal} census mismatch"
            )
        replay_id, condition = expected
        request = build_worker_request(preregistration, condition)
        request_digest = hashlib.sha256(
            canonical_json_bytes(request)
        ).hexdigest()
        if receipt.get("request_sha256") != request_digest:
            raise BenchmarkEvidenceError(
                f"LiveMemory arm receipt {process_ordinal} request mismatch"
            )

        start = process_ordinal * rows_per_arm
        report_rows = measured[start : start + rows_per_arm]
        worker_rows = []
        for item_index, report_row in enumerate(report_rows):
            if not isinstance(report_row, Mapping):
                raise BenchmarkEvidenceError(
                    f"LiveMemory measured item {start + item_index} invalid"
                )
            metadata = report_row.get("metadata")
            if (
                not isinstance(metadata, Mapping)
                or frozenset(metadata) != _REPORT_ITEM_METADATA_FIELDS
                or metadata.get("replay_id") != replay_id
                or metadata.get("condition") != condition
            ):
                raise BenchmarkEvidenceError(
                    f"LiveMemory measured item {start + item_index} metadata mismatch"
                )
            worker_rows.append(
                {
                    "index": item_index,
                    "emitted": metadata["candidate_emitted"],
                    "answer": metadata["candidate_answer"],
                    "used_live": metadata["used_live"],
                    "grounded": metadata["grounded"],
                    "confidence": metadata["confidence"],
                    "support": metadata["support"],
                    "evidence": metadata["evidence"],
                    "recall_top_source": metadata["recall_top_source"],
                    "recall_top_fact_sha256": metadata[
                        "recall_top_fact_sha256"
                    ],
                    "error_type": metadata["candidate_error_type"],
                    "latency_ms": report_row["latency_ms"],
                }
            )
        result = {
            "schema_version": WORKER_RESULT_SCHEMA,
            "condition": condition,
            "device": receipt["device"],
            "python_hash_seed": receipt["python_hash_seed"],
            "isolation": receipt["isolation"],
            "learned": receipt["learned"],
            "items": worker_rows,
        }
        _validate_worker_result(
            result,
            request=request,
            expected_hash_seed=str(
                preregistration["protocol"]["python_hash_seed"]
            ),
        )
        arms.append(
            {
                "process_ordinal": process_ordinal,
                "replay_id": replay_id,
                "condition": condition,
                "request_sha256": request_digest,
                "result": result,
            }
        )
    return arms


def validate_report_semantics(manifest: Mapping[str, Any]) -> list[str]:
    """Fail-closed reconstruction of every result and every declared gate."""

    findings: list[str] = []
    try:
        benchmark = manifest.get("benchmark")
        config = manifest.get("config")
        if (
            not isinstance(benchmark, Mapping)
            or benchmark.get("id")
            != "atanor-live-memory-realtime-novel-single-hop-v1"
        ):
            raise BenchmarkEvidenceError("LiveMemory benchmark identity mismatch")
        if (
            not isinstance(config, Mapping)
            or frozenset(config) != _REPORT_CONFIG_FIELDS
        ):
            raise BenchmarkEvidenceError("LiveMemory config fields mismatch")

        preregistration, _relative = _bound_preregistration_from_manifest(
            manifest
        )
        if config.get("preregistration_id") != preregistration[
            "preregistration_id"
        ]:
            raise BenchmarkEvidenceError("LiveMemory preregistration ID mismatch")
        if config.get("preregistered_at") != preregistration["frozen_at"]:
            raise BenchmarkEvidenceError("LiveMemory freeze timestamp mismatch")
        if config.get("protocol") != preregistration["protocol"]:
            raise BenchmarkEvidenceError("LiveMemory frozen protocol mismatch")
        if config.get("exposure_audit") != preregistration["exposure_audit"]:
            raise BenchmarkEvidenceError("LiveMemory exposure audit mismatch")
        if config.get("gold_in_candidate_payload") is not False:
            raise BenchmarkEvidenceError("LiveMemory gold boundary mismatch")
        if config.get("candidate_process") != "fresh_subprocess_per_arm":
            raise BenchmarkEvidenceError("LiveMemory process boundary mismatch")
        if config.get("fresh_process_arm_count") != 4:
            raise BenchmarkEvidenceError(
                "LiveMemory fresh-process arm count mismatch"
            )
        attempt_path = _attempt_destination(
            preregistration["preregistration_id"]
        )
        if not attempt_path.is_file():
            raise BenchmarkEvidenceError(
                "LiveMemory write-once attempt tombstone is missing"
            )
        attempt = strict_json_bytes(
            attempt_path.read_bytes(),
            label="LiveMemory attempt tombstone",
        )
        expected_attempt_fields = {
            "schema_version",
            "preregistration_id",
            "started_at",
            "status",
            "preregistration_content_sha256",
            "candidate_content_sha256",
            "evaluator_content_sha256",
            "result_path",
        }
        if (
            frozenset(attempt) != expected_attempt_fields
            or attempt.get("schema_version") != ATTEMPT_SCHEMA
            or attempt.get("preregistration_id")
            != preregistration["preregistration_id"]
            or attempt.get("started_at") != manifest.get("started_at")
            or attempt.get("status") != "started"
            or attempt.get("preregistration_content_sha256")
            != manifest["dataset"]["content_sha256"]
            or attempt.get("candidate_content_sha256")
            != manifest["candidate"]["content_sha256"]
            or attempt.get("evaluator_content_sha256")
            != manifest["source"]["content_sha256"]
            or attempt.get("result_path")
            != _report_destination(
                preregistration["preregistration_id"]
            ).relative_to(REPO.resolve()).as_posix()
        ):
            raise BenchmarkEvidenceError(
                "LiveMemory attempt tombstone does not bind the result"
            )
        if _failure_destination(
            preregistration["preregistration_id"]
        ).exists():
            raise BenchmarkEvidenceError(
                "LiveMemory success receipt conflicts with a failure receipt"
            )

        expected_requests = [
            build_worker_request(preregistration, condition)
            for replay in preregistration["protocol"]["replays"]
            for condition in replay["condition_order"]
        ]
        expected_request_digests = [
            hashlib.sha256(canonical_json_bytes(request)).hexdigest()
            for request in expected_requests
        ]
        if config.get("request_sha256") != expected_request_digests:
            raise BenchmarkEvidenceError("LiveMemory request digest census mismatch")
        if any(_contains_gold_key(request) for request in expected_requests):
            raise BenchmarkEvidenceError("LiveMemory reconstructed request leaks gold")

        candidate = manifest.get("candidate")
        candidate_files = (
            candidate.get("files") if isinstance(candidate, Mapping) else None
        )
        candidate_paths = [
            row.get("path")
            for row in candidate_files
            if isinstance(row, Mapping)
        ] if isinstance(candidate_files, list) else []
        if not isinstance(candidate, Mapping) or (
            candidate_paths != preregistration["candidate"]["paths"]
            or candidate.get("content_sha256")
            != preregistration["candidate"]["content_sha256"]
        ):
            raise BenchmarkEvidenceError("LiveMemory candidate closure mismatch")
        source = manifest.get("source")
        source_files = source.get("files") if isinstance(source, Mapping) else None
        source_paths = [
            row.get("path")
            for row in source_files
            if isinstance(row, Mapping)
        ] if isinstance(source_files, list) else []
        if source_paths != list(_EVALUATOR_PATHS):
            raise BenchmarkEvidenceError("LiveMemory evaluator closure mismatch")

        arms = _reconstruct_arms_from_manifest(manifest, preregistration)
        integrity = manifest.get("integrity")
        if not isinstance(integrity, Mapping):
            raise BenchmarkEvidenceError("LiveMemory integrity record missing")
        recomputed_items, recomputed_summary, recomputed_gates = score_arms(
            preregistration,
            arms,
            integrity={
                "source_same_before_after": integrity.get(
                    "source_same_before_after"
                ),
                "candidate_same_before_after": integrity.get(
                    "candidate_same_before_after"
                ),
                "preregistration_same_before_after": integrity.get(
                    "dataset_same_before_after"
                ),
            },
        )
        if recomputed_items != manifest.get("items"):
            raise BenchmarkEvidenceError(
                "LiveMemory 240-item census or item-level scoring mismatch"
            )
        if recomputed_summary != config.get("measured_summary"):
            raise BenchmarkEvidenceError(
                "LiveMemory measured summary does not recompute"
            )
        if recomputed_gates != config.get("gate_results"):
            raise BenchmarkEvidenceError(
                "LiveMemory mechanism/capability/safety gates do not recompute"
            )
        if aggregate_items(recomputed_items) != manifest.get("metrics"):
            raise BenchmarkEvidenceError("LiveMemory aggregate metrics mismatch")
        if selection_record(recomputed_items) != manifest.get("selection"):
            raise BenchmarkEvidenceError("LiveMemory selection census mismatch")
    except (
        BenchmarkEvidenceError,
        AttributeError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        findings.append(str(exc))
    return findings


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate",
        help="validate preregistration and bindings without candidate execution",
    )
    validate_parser.add_argument("preregistration", type=Path)

    run_parser = subparsers.add_parser(
        "run",
        help="perform the single write-once result run (launches candidate)",
    )
    run_parser.add_argument("preregistration", type=Path)

    verify_parser = subparsers.add_parser(
        "verify",
        help="verify an already-written unsigned receipt",
    )
    verify_parser.add_argument("manifest", type=Path)
    verify_parser.add_argument("--historical", action="store_true")

    parsed = parser.parse_args(arguments)
    try:
        if parsed.command == "validate":
            preregistration, relative = load_preregistration(
                parsed.preregistration
            )
            record = dry_run_record(
                preregistration,
                preregistration_relative=relative,
            )
            print(json.dumps(record, ensure_ascii=False, sort_keys=True))
            return 0 if record["candidate_matches_preregistered_digest"] else 2

        if parsed.command == "run":
            manifest, destination = run(
                preregistration_path=parsed.preregistration
            )
            result = {
                "manifest": str(destination.resolve()),
                "manifest_checksum_sha256": manifest[
                    "manifest_checksum_sha256"
                ],
                "mechanism_green": manifest["config"]["gate_results"][
                    "mechanism"
                ]["green"],
                "capability_green": manifest["config"]["gate_results"][
                    "capability"
                ]["green"],
                "safety_green": manifest["config"]["gate_results"]["safety"][
                    "green"
                ],
                "overall_green": manifest["config"]["gate_results"][
                    "overall_green"
                ],
                "general_reasoning_improvement_claimed": False,
                "e5_claimed": False,
            }
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0

        result = verify_manifest(
            parsed.manifest,
            repo_root=REPO,
            require_current=not parsed.historical,
        )
        semantic = []
        if result.get("structure_valid"):
            try:
                value = strict_json_bytes(
                    parsed.manifest.read_bytes(),
                    label="LiveMemory receipt",
                )
                semantic = validate_report_semantics(value)
            except (BenchmarkEvidenceError, OSError) as exc:
                semantic = [str(exc)]
        else:
            semantic = [
                "structural receipt validation failed; semantic recomputation "
                "was not attempted"
            ]
        result["semantic_findings"] = semantic
        result["semantic_valid"] = not semantic
        result["valid"] = bool(result.get("valid")) and not semantic
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["valid"] else 2
    except (BenchmarkEvidenceError, OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {"error": str(exc), "type": type(exc).__name__},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
