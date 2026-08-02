"""EAD-2 preregistration verifier and EAD-3 one-shot paired evaluator.

The model worker is label-blind.  This parent owns labels, metrics, immutable
closures, the attempt tombstone, and the final outcome taxonomy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from packages.eval_evidence.receipt import (  # noqa: E402
    BenchmarkEvidenceError,
    bind_files,
    canonical_json_bytes,
    ensure_safe_report_output,
    environment_record,
    strict_json_bytes,
    utc_now,
)


PREREG = (
    REPO / "data" / "eval" / "evidence_answer_discrimination_ead23_preregister_v1.json"
)
DATASET = (
    REPO / "data" / "eval" / "evidence_answer_discrimination_ead23_dataset_v1.json"
)
WORKER = REPO / "scripts" / "evidence_answer_discrimination_ead23_worker.py"
REPORT = ensure_safe_report_output(
    REPO,
    REPO / "reports" / "benchmarks" / "ead23_fresh_counterbalanced_v1_20260726.json",
)
ATTEMPT = REPORT.with_name(REPORT.stem + ".attempt.json")
FAILURE = REPORT.with_name(REPORT.stem + ".failure.json")

PREREG_SCHEMA = "atanor.ead23-preregister.v1"
DATASET_SCHEMA = "atanor.ead23-dataset.v1"
WORKER_REQUEST_SCHEMA = "atanor.ead23-worker-request.v1"
WORKER_RESULT_SCHEMA = "atanor.ead23-worker-result.v1"
REPORT_SCHEMA = "atanor.ead23-report.v1"
ATTEMPT_SCHEMA = "atanor.ead23-attempt.v1"
FAILURE_SCHEMA = "atanor.ead23-failure.v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ITEM_FIELDS = frozenset(
    {
        "item_key",
        "kind",
        "relation_id",
        "question",
        "evidence",
        "proposed_answer",
        "gold_answer",
        "negative_mode",
        "source_id",
    }
)
_REQUEST_ITEM_FIELDS = frozenset(
    {
        "index",
        "item_key",
        "question",
        "evidence",
        "proposed_answer",
        "source_id",
    }
)
_RESULT_ITEM_FIELDS = frozenset(
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
_BLOCKS = (
    ("A_OFF", "A", "OFF", "forward"),
    ("B_ON", "B", "ON", "forward"),
    ("A_ON", "A", "ON", "reverse"),
    ("B_OFF", "B", "OFF", "reverse"),
)


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        return strict_json_bytes(path.read_bytes(), label=label)
    except OSError as exc:
        raise BenchmarkEvidenceError(f"{label} unreadable") from exc


def _raw_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise BenchmarkEvidenceError("EAD-2/3 bound file unreadable") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _opaque_item_key(item_key: str) -> str:
    """Return the label-blind identifier exposed to the worker."""

    return hashlib.sha256(b"ead23-item-v1\0" + item_key.encode("utf-8")).hexdigest()


def _opaque_source_id(item_key: str) -> str:
    """Return a label-blind producer id for the temporary LiveMemory row."""

    return hashlib.sha256(b"ead23-source-v1\0" + item_key.encode("utf-8")).hexdigest()


def _text(value: Any, maximum: int = 32_768) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _validate_sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise BenchmarkEvidenceError(f"{label} must be lowercase SHA-256")


def load_preregistration(path: Path = PREREG) -> tuple[dict[str, Any], str]:
    value = _load(path.resolve(strict=True), "EAD-2/3 preregistration")
    expected = {
        "schema_version",
        "preregistration_id",
        "frozen_at",
        "time_budget",
        "claim_boundary",
        "sealed_dataset",
        "candidate",
        "runtime_assets",
        "evaluator_source_paths",
        "protocol",
        "metrics",
        "diagnostic_floor",
        "capability_lift_gates",
        "regression_gates",
        "integrity_gates",
        "outcome_rule",
        "rerun_policy",
    }
    if frozenset(value) != expected:
        raise BenchmarkEvidenceError("EAD-2/3 preregistration fields mismatch")
    if (
        value.get("schema_version") != PREREG_SCHEMA
        or value.get("preregistration_id")
        != "ead23-fresh-counterbalanced-v1-20260726"
    ):
        raise BenchmarkEvidenceError("EAD-2/3 preregistration identity mismatch")
    if value.get("time_budget") != {
        "checkpoint_hours": 3,
        "hard_cap_hours": 6,
    }:
        raise BenchmarkEvidenceError("EAD-2/3 time budget drift")
    if value.get("claim_boundary") != {
        "measurement": "fresh_local_synthetic_single_hop_evidence_answer_discrimination",
        "capability_claimed_if_lift_gate_passes": True,
        "production_activation_authorized": False,
        "limitations": [
            "The proposed answer is fixed before inference, so this measures evidence-answer discrimination rather than answer generation.",
            "The cohort is fresh and result-blind but synthetic, locally authored, locally evaluated, and not independently signed.",
            "The OFF condition is an evaluator-only counterfactual that preserves EAD-1 identity and source-authority checks while bypassing only semantic discrimination.",
            "Current production source contains no discriminator feature flag; this run neither changes nor authorizes production state.",
            "No general reasoning, multihop, public benchmark, GPQA, ARC, E5, authenticity, or independent-evaluator claim is permitted.",
        ],
    }:
        raise BenchmarkEvidenceError("EAD-2/3 claim boundary drift")
    candidate = value.get("candidate")
    if (
        not isinstance(candidate, dict)
        or candidate.get("content_sha256")
        != "819e0ff07cfb968109d7d219e6bb86c35c9b2c21565af8263b13c3486d6f0425"
        or candidate.get("ead1_preregistration_id")
        != "ead1-live-wiring-authority-v2-20260726"
        or candidate.get("paths") != sorted(candidate.get("paths", []))
    ):
        raise BenchmarkEvidenceError("EAD-2/3 candidate binding mismatch")
    runtime = value.get("runtime_assets")
    if (
        not isinstance(runtime, dict)
        or runtime.get("content_sha256")
        != "cc1ae6ce61eab2282130eea142b1de9ca538b1cab0743c5714d05caf4cdcf539"
        or runtime.get("paths") != sorted(runtime.get("paths", []))
        or runtime.get("checkpoint_raw_sha256")
        != {
            "ace_hotpot.pt": "87134bd43971cfd43f6ea488d9088d686bee70bf977dcf8be19190d4b6906137",
            "ace_support.pt": "eef7b80905fa3e2c065643fdb21e4caf78a9be5cefbceb07db832227c42b3448",
        }
    ):
        raise BenchmarkEvidenceError("EAD-2/3 runtime asset binding mismatch")
    source_paths = value.get("evaluator_source_paths")
    if (
        not isinstance(source_paths, list)
        or not source_paths
        or source_paths != sorted(source_paths)
        or len(source_paths) != len(set(source_paths))
    ):
        raise BenchmarkEvidenceError("EAD-2/3 evaluator source paths invalid")
    protocol = value.get("protocol")
    if protocol != {
        "device_policy": "cpu_only",
        "python_hash_seed": "0",
        "network_use": "none",
        "worker_process_count": 4,
        "worker_result_run_limit": 1,
        "mechanical_retry_limit": 0,
        "input_mode": "fixed_oracle_proposal_through_realtime_ead1_boundary",
        "evidence_authority": "every row is promoted by evaluator-owned server promotion before both conditions",
        "memory_isolation": "one temporary LiveMemory row per case; no shipped store, cortex, misslog, staging, or graph write",
        "off_condition": "replace only thinker.gate with a harness gate accepting any nonempty fixed proposal over the verified producer row",
        "on_condition": "unmodified production DoubtGate.judge_answer at answerability_threshold=0.90 and support_net_threshold=0.90",
        "condition_order": "sort item_key by sha256 into A(first 30) and B(last 30); execute A_OFF forward, B_ON forward, A_ON reverse, B_OFF reverse",
        "condition_order_sha256": "6e567aada46d2fa97fc2e83a996ac2205f0588270ce561e075fd63f959c9787d",
        "treatment_isolation": "normalized answer, support indices, selected evidence source, used_live, and verified producer identity must be exact across OFF and ON",
        "worker_visibility": "worker receives opaque item_key, question, evidence, proposed_answer, source_id, block_id, and condition only; no kind, gold, negative_mode, metrics, gates, or labels",
    }:
        raise BenchmarkEvidenceError("EAD-2/3 fixed protocol mismatch")
    if value.get("metrics") != {
        "supported_accept_rate": "accepted POS / 24",
        "wrong_source_adoption_rate": "accepted WRONG_SOURCE / 24",
        "unknown_false_grounding_rate": "accepted UNKNOWN / 12",
        "aggregate_false_grounding_rate": "accepted (WRONG_SOURCE + UNKNOWN) / 36",
        "decision_accuracy": "(accepted POS + rejected WRONG_SOURCE + rejected UNKNOWN) / 60",
        "balanced_decision_accuracy": "0.5 * (supported_accept_rate + 1 - aggregate_false_grounding_rate)",
        "accepted_precision": "accepted POS / all accepted rows",
        "paired_exact_mcnemar": "two-sided exact binomial McNemar over per-item OFF/ON decision correctness",
    }:
        raise BenchmarkEvidenceError("EAD-2/3 metric contract drift")
    if value.get("diagnostic_floor") != {
        "off_supported_accept": 24,
        "off_wrong_source_accept": 24,
        "off_unknown_accept": 12,
        "off_total_accept": 60,
    }:
        raise BenchmarkEvidenceError("EAD-2/3 diagnostic floor drift")
    if value.get("capability_lift_gates") != {
        "on_supported_accept_min": 21,
        "on_wrong_source_accept_max": 4,
        "on_unknown_accept_max": 2,
        "on_aggregate_hard_negative_accept_max": 6,
        "on_balanced_decision_accuracy_min": 0.85,
        "balanced_decision_accuracy_lift_min": 0.3,
        "on_accepted_precision_min": 0.75,
        "mcnemar_p_max": 0.01,
        "mcnemar_must_favor_on": True,
        "each_relation_supported_accept_min": 3,
        "each_relation_hard_negative_accept_max": 2,
        "each_wrong_source_mode_accept_max": 2,
    }:
        raise BenchmarkEvidenceError("EAD-2/3 capability gates drift")
    if value.get("regression_gates") != {
        "on_supported_accept_below": 18,
        "on_balanced_decision_accuracy_below": 0.45,
        "on_hard_negative_accept_exceeds_off": True,
    }:
        raise BenchmarkEvidenceError("EAD-2/3 regression gates drift")
    if value.get("integrity_gates") != {
        "complete_item_census_required": True,
        "exactly_one_off_and_one_on_per_item": True,
        "counterbalance_30_30_required": True,
        "worker_error_count_max": 0,
        "treatment_isolation_exact_required": True,
        "all_rows_reach_verified_live_producer_required": True,
        "candidate_same_before_after_required": True,
        "runtime_assets_same_before_after_required": True,
        "dataset_same_before_after_required": True,
        "evaluator_source_same_before_after_required": True,
    }:
        raise BenchmarkEvidenceError("EAD-2/3 integrity gates drift")
    if value.get("outcome_rule") != [
        "NO_GO if any integrity gate or diagnostic floor fails.",
        "REGRESSION if any regression gate fires after integrity and diagnostic floors pass.",
        "CAPABILITY_LIFT_CONFIRMED only if every capability lift gate passes and no regression gate fires.",
        "NO_LIFT otherwise; thresholds are not reinterpreted after observation.",
    ]:
        raise BenchmarkEvidenceError("EAD-2/3 outcome rule drift")
    if value.get("rerun_policy") != {
        "result_run_limit": 1,
        "mechanical_retry_limit": 0,
        "post_result_tuning_prohibited": True,
        "new_preregistration_required_after_any_change": True,
    }:
        raise BenchmarkEvidenceError("EAD-2/3 rerun policy drift")
    try:
        relative = path.resolve(strict=True).relative_to(REPO.resolve(strict=True)).as_posix()
    except (OSError, ValueError) as exc:
        raise BenchmarkEvidenceError("EAD-2/3 preregistration escapes repository") from exc
    return value, relative


def load_dataset(
    preregistration: Mapping[str, Any],
    path: Path = DATASET,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    descriptor = preregistration["sealed_dataset"]
    if (
        descriptor.get("path")
        != "data/eval/evidence_answer_discrimination_ead23_dataset_v1.json"
        or _raw_sha256(path) != descriptor.get("raw_sha256")
    ):
        raise BenchmarkEvidenceError("EAD-2/3 dataset raw binding mismatch")
    value = _load(path.resolve(strict=True), "EAD-2/3 dataset")
    if frozenset(value) != {
        "schema_version",
        "dataset_id",
        "frozen_at",
        "exposure",
        "case_content_sha256",
        "case_order_sha256",
        "census",
        "design",
        "cases",
    }:
        raise BenchmarkEvidenceError("EAD-2/3 dataset fields mismatch")
    if (
        value.get("schema_version") != DATASET_SCHEMA
        or value.get("dataset_id") != "ead23-fresh-adversarial-evidence-v1-20260726"
        or value.get("exposure") != "fresh_result_blind_synthetic"
        or value.get("census") != descriptor.get("census")
    ):
        raise BenchmarkEvidenceError("EAD-2/3 dataset identity/census mismatch")
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != 60:
        raise BenchmarkEvidenceError("EAD-2/3 requires exactly 60 cases")
    if (
        _sha(cases) != descriptor.get("case_content_sha256")
        or value.get("case_content_sha256") != descriptor.get("case_content_sha256")
        or _sha([row.get("item_key") for row in cases])
        != descriptor.get("case_order_sha256")
        or value.get("case_order_sha256") != descriptor.get("case_order_sha256")
    ):
        raise BenchmarkEvidenceError("EAD-2/3 dataset case digest mismatch")
    seen: set[str] = set()
    counts = {"POS": 0, "WRONG_SOURCE": 0, "UNKNOWN": 0}
    relations: dict[str, dict[str, int]] = {}
    positive_pairs: set[tuple[str, str]] = set()
    for index, row in enumerate(cases):
        if not isinstance(row, dict) or frozenset(row) != _ITEM_FIELDS:
            raise BenchmarkEvidenceError(f"EAD-2/3 case {index} fields mismatch")
        key, kind = row.get("item_key"), row.get("kind")
        if not _text(key, 32) or key in seen or kind not in counts:
            raise BenchmarkEvidenceError(f"EAD-2/3 case {index} identity invalid")
        seen.add(key)
        counts[kind] += 1
        relation = row.get("relation_id")
        if not _text(relation, 64):
            raise BenchmarkEvidenceError(f"EAD-2/3 case {index} relation invalid")
        relations.setdefault(relation, {name: 0 for name in counts})[kind] += 1
        for field in ("question", "evidence", "proposed_answer", "source_id"):
            if not _text(row.get(field)):
                raise BenchmarkEvidenceError(f"EAD-2/3 case {index} {field} invalid")
        evidence = row["evidence"].casefold()
        answer = row["proposed_answer"].casefold()
        if evidence.count(answer) != 1:
            raise BenchmarkEvidenceError(
                f"EAD-2/3 case {index} answer must be one exact evidence span"
            )
        if kind == "POS":
            if (
                row.get("gold_answer") != row.get("proposed_answer")
                or row.get("negative_mode") is not None
            ):
                raise BenchmarkEvidenceError("EAD-2/3 positive contract mismatch")
            positive_pairs.add((row["evidence"], row["proposed_answer"]))
        elif kind == "WRONG_SOURCE":
            if row.get("negative_mode") not in {
                "same_entity_sibling_relation",
                "same_relation_sibling_entity",
            } or not _text(row.get("gold_answer")):
                raise BenchmarkEvidenceError("EAD-2/3 wrong-source contract mismatch")
        elif (
            row.get("negative_mode") != "same_relation_unknown_entity"
            or row.get("gold_answer") is not None
        ):
            raise BenchmarkEvidenceError("EAD-2/3 unknown contract mismatch")
    if counts != {"POS": 24, "WRONG_SOURCE": 24, "UNKNOWN": 12}:
        raise BenchmarkEvidenceError("EAD-2/3 case census mismatch")
    if len(relations) != 6 or any(
        value != {"POS": 4, "WRONG_SOURCE": 4, "UNKNOWN": 2}
        for value in relations.values()
    ):
        raise BenchmarkEvidenceError("EAD-2/3 relation-family census mismatch")
    if any(
        (row["evidence"], row["proposed_answer"]) not in positive_pairs
        for row in cases
        if row["kind"] != "POS"
    ):
        raise BenchmarkEvidenceError("EAD-2/3 negative vocabulary control mismatch")
    relative = path.resolve(strict=True).relative_to(REPO.resolve(strict=True)).as_posix()
    return value, cases, relative


def counterbalance(cases: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    ordered = sorted(
        (str(row["item_key"]) for row in cases),
        key=lambda key: (hashlib.sha256(key.encode()).hexdigest(), key),
    )
    assignment = [
        {
            "item_key": key,
            "condition_order": ["OFF", "ON"] if index < 30 else ["ON", "OFF"],
        }
        for index, key in enumerate(ordered)
    ]
    if _sha(assignment) != (
        "6e567aada46d2fa97fc2e83a996ac2205f0588270ce561e075fd63f959c9787d"
    ):
        raise BenchmarkEvidenceError("EAD-2/3 counterbalance digest mismatch")
    return {"A": ordered[:30], "B": ordered[30:]}


def build_worker_requests(
    preregistration: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_key = {row["item_key"]: row for row in cases}
    opaque_keys = {_opaque_item_key(key) for key in by_key}
    opaque_sources = {_opaque_source_id(key) for key in by_key}
    if len(opaque_keys) != len(by_key) or len(opaque_sources) != len(by_key):
        raise BenchmarkEvidenceError("EAD-2/3 opaque identifier collision")
    strata = counterbalance(cases)
    requests = []
    for block_id, stratum, condition, order in _BLOCKS:
        keys = list(strata[stratum])
        if order == "reverse":
            keys.reverse()
        items = [
            {
                "index": index,
                "item_key": _opaque_item_key(key),
                "question": by_key[key]["question"],
                "evidence": by_key[key]["evidence"],
                "proposed_answer": by_key[key]["proposed_answer"],
                "source_id": _opaque_source_id(key),
            }
            for index, key in enumerate(keys)
        ]
        requests.append(
            {
                "schema_version": WORKER_REQUEST_SCHEMA,
                "preregistration_id": preregistration["preregistration_id"],
                "block_id": block_id,
                "condition": condition,
                "device_policy": "cpu_only",
                "python_hash_seed": "0",
                "candidate_content_sha256": preregistration["candidate"][
                    "content_sha256"
                ],
                "answerability_checkpoint": "ace_hotpot.pt",
                "support_checkpoint": "ace_support.pt",
                "answerability_threshold": 0.90,
                "support_net_threshold": 0.90,
                "items": items,
            }
        )
    return requests


def _run_worker(request: Mapping[str, Any], timeout: int = 3600) -> dict[str, Any]:
    env = dict(os.environ)
    env.update(
        {
            "CUDA_VISIBLE_DEVICES": "-1",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
    )
    completed = subprocess.run(
        [sys.executable, str(WORKER)],
        cwd=REPO,
        env=env,
        input=canonical_json_bytes(request),
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        tail = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise BenchmarkEvidenceError(
            f"EAD-3 worker {request['block_id']} failed: {tail}"
        )
    return strict_json_bytes(
        completed.stdout, label=f"EAD-3 worker {request['block_id']} result"
    )


def validate_worker_result(
    value: dict[str, Any],
    request: Mapping[str, Any],
) -> dict[str, Any]:
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
        raise BenchmarkEvidenceError("EAD-3 worker result fields mismatch")
    if (
        value.get("schema_version") != WORKER_RESULT_SCHEMA
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
    ):
        raise BenchmarkEvidenceError("EAD-3 worker result identity/isolation mismatch")
    if not isinstance(value.get("versions"), dict):
        raise BenchmarkEvidenceError("EAD-3 worker versions invalid")
    rows = value.get("items")
    if not isinstance(rows, list) or len(rows) != len(request["items"]):
        raise BenchmarkEvidenceError("EAD-3 worker result census mismatch")
    for expected, (row, asked) in enumerate(zip(rows, request["items"])):
        if not isinstance(row, dict) or frozenset(row) != _RESULT_ITEM_FIELDS:
            raise BenchmarkEvidenceError(f"EAD-3 worker row {expected} fields mismatch")
        if (
            row.get("index") != expected
            or row.get("item_key") != asked["item_key"]
            or row.get("condition") != request["condition"]
            or row.get("answer") != asked["proposed_answer"]
            or type(row.get("grounded")) is not bool
            or type(row.get("used_live")) is not bool
            or not isinstance(row.get("support"), list)
            or not isinstance(row.get("evidence"), list)
            or row.get("type") != "span"
            or row.get("selected_source_id") != asked["source_id"]
            or row.get("selected_fact_sha256")
            != hashlib.sha256(asked["evidence"].encode()).hexdigest()
            or not isinstance(row.get("grounding_signals"), dict)
            or (
                row.get("error") is not None
                and not _text(row.get("error"), maximum=1000)
            )
        ):
            raise BenchmarkEvidenceError(f"EAD-3 worker row {expected} identity invalid")
        confidence, latency = row.get("confidence"), row.get("latency_ms")
        if (
            type(confidence) not in (int, float)
            or not math.isfinite(float(confidence))
            or not 0.0 <= float(confidence) <= 1.0
            or type(latency) not in (int, float)
            or not math.isfinite(float(latency))
            or float(latency) < 0.0
        ):
            raise BenchmarkEvidenceError(f"EAD-3 worker row {expected} numeric invalid")
        canonical_json_bytes(row["grounding_signals"])
    return value


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 12)


def _mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(Fraction(math.comb(n, k), 2**n) for k in range(min(b, c) + 1))
    return round(float(min(Fraction(1), 2 * tail)), 12)


def _condition_correct(case: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    return bool(row["grounded"]) if case["kind"] == "POS" else not bool(row["grounded"])


def score_results(
    preregistration: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
    arms: Sequence[Mapping[str, Any]],
    *,
    closure_integrity: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    if len(arms) != 4:
        raise BenchmarkEvidenceError("EAD-3 requires exactly four counterbalanced blocks")
    by_key = {_opaque_item_key(row["item_key"]): row for row in cases}
    condition_rows: dict[str, dict[str, Mapping[str, Any]]] = {
        "OFF": {},
        "ON": {},
    }
    for arm in arms:
        condition = arm["condition"]
        for row in arm["result"]["items"]:
            key = row["item_key"]
            if key in condition_rows[condition]:
                raise BenchmarkEvidenceError("EAD-3 duplicate item/condition")
            condition_rows[condition][key] = row
    expected = set(by_key)
    complete_census = all(set(rows) == expected for rows in condition_rows.values())
    if not complete_census:
        raise BenchmarkEvidenceError("EAD-3 incomplete paired census")

    treatment_exact = True
    reached_verified = True
    worker_errors = 0
    raw_rows = []
    parity_fields = (
        "answer",
        "used_live",
        "support",
        "evidence",
        "type",
        "selected_source_id",
        "selected_fact_sha256",
    )
    for case in cases:
        key = _opaque_item_key(case["item_key"])
        off, on = condition_rows["OFF"][key], condition_rows["ON"][key]
        treatment_exact &= all(off[field] == on[field] for field in parity_fields)
        expected_evidence = [
            {
                "origin": "live",
                "title": f"live:{_opaque_source_id(case['item_key'])}",
                "verified": True,
                "candidate_index": 0,
            }
        ]
        for row in (off, on):
            reached_verified &= (
                row["used_live"] is True
                and row["evidence"] == expected_evidence
                and row["selected_source_id"] == _opaque_source_id(case["item_key"])
                and row["selected_fact_sha256"]
                == hashlib.sha256(case["evidence"].encode()).hexdigest()
            )
            worker_errors += int(row["error"] is not None)
        raw_rows.append(
            {
                "item_key": key,
                "kind": case["kind"],
                "relation_id": case["relation_id"],
                "negative_mode": case["negative_mode"],
                "question_sha256": hashlib.sha256(case["question"].encode()).hexdigest(),
                "evidence_sha256": hashlib.sha256(case["evidence"].encode()).hexdigest(),
                "proposed_answer_sha256": hashlib.sha256(
                    case["proposed_answer"].encode()
                ).hexdigest(),
                "off": {
                    "grounded": off["grounded"],
                    "confidence": off["confidence"],
                    "reason": off["grounding_reason"],
                    "signals": off["grounding_signals"],
                },
                "on": {
                    "grounded": on["grounded"],
                    "confidence": on["confidence"],
                    "reason": on["grounding_reason"],
                    "signals": on["grounding_signals"],
                },
            }
        )

    def accepted(condition: str, kind: str | None = None) -> int:
        return sum(
            bool(
                condition_rows[condition][_opaque_item_key(case["item_key"])][
                    "grounded"
                ]
            )
            for case in cases
            if kind is None or case["kind"] == kind
        )

    summary: dict[str, Any] = {}
    for condition in ("OFF", "ON"):
        pos = accepted(condition, "POS")
        wrong = accepted(condition, "WRONG_SOURCE")
        unknown = accepted(condition, "UNKNOWN")
        hard = wrong + unknown
        total = pos + hard
        decision_correct = pos + (36 - hard)
        ba = round(
            0.5 * (_ratio(pos, 24) + 1.0 - _ratio(hard, 36)),
            12,
        )
        summary[condition.lower()] = {
            "supported_accept": pos,
            "supported_total": 24,
            "wrong_source_accept": wrong,
            "wrong_source_total": 24,
            "unknown_accept": unknown,
            "unknown_total": 12,
            "aggregate_hard_negative_accept": hard,
            "aggregate_hard_negative_total": 36,
            "total_accept": total,
            "decision_correct": decision_correct,
            "decision_total": 60,
            "supported_accept_rate": _ratio(pos, 24),
            "wrong_source_adoption_rate": _ratio(wrong, 24),
            "unknown_false_grounding_rate": _ratio(unknown, 12),
            "aggregate_false_grounding_rate": _ratio(hard, 36),
            "decision_accuracy": _ratio(decision_correct, 60),
            "balanced_decision_accuracy": ba,
            "accepted_precision": _ratio(pos, total) if total else 0.0,
        }
    off_summary, on_summary = summary["off"], summary["on"]
    correctness = {
        condition: {
            _opaque_item_key(case["item_key"]): _condition_correct(
                case, condition_rows[condition][_opaque_item_key(case["item_key"])]
            )
            for case in cases
        }
        for condition in ("OFF", "ON")
    }
    b = sum(
        correctness["OFF"][key] and not correctness["ON"][key] for key in expected
    )
    c = sum(
        not correctness["OFF"][key] and correctness["ON"][key] for key in expected
    )
    mcnemar_p = _mcnemar_exact(b, c)
    relations = sorted({case["relation_id"] for case in cases})
    relation_metrics = {}
    for relation in relations:
        rows = [case for case in cases if case["relation_id"] == relation]
        relation_metrics[relation] = {
            "on_supported_accept": sum(
                condition_rows["ON"][_opaque_item_key(case["item_key"])][
                    "grounded"
                ]
                for case in rows
                if case["kind"] == "POS"
            ),
            "on_hard_negative_accept": sum(
                condition_rows["ON"][_opaque_item_key(case["item_key"])][
                    "grounded"
                ]
                for case in rows
                if case["kind"] != "POS"
            ),
        }
    modes = (
        "same_entity_sibling_relation",
        "same_relation_sibling_entity",
    )
    wrong_source_modes = {
        mode: {
            "on_accept": sum(
                condition_rows["ON"][_opaque_item_key(case["item_key"])][
                    "grounded"
                ]
                for case in cases
                if case["negative_mode"] == mode
            ),
            "total": 12,
        }
        for mode in modes
    }

    closures = dict(
        closure_integrity
        or {
            "candidate_same_before_after": True,
            "runtime_assets_same_before_after": True,
            "dataset_same_before_after": True,
            "evaluator_source_same_before_after": True,
        }
    )
    block_identity = [
        (
            arm.get("block_id"),
            arm.get("stratum"),
            arm.get("condition"),
            arm.get("order"),
        )
        for arm in arms
    ] == list(_BLOCKS)
    integrity_results = {
        "complete_item_census": complete_census,
        "exactly_one_off_and_one_on_per_item": complete_census,
        "counterbalance_30_30": block_identity
        and all(len(arm["result"]["items"]) == 30 for arm in arms),
        "worker_errors": worker_errors == 0,
        "treatment_isolation_exact": treatment_exact,
        "all_rows_reach_verified_live_producer": reached_verified,
        **closures,
    }
    diagnostic_results = {
        "off_supported_accept": off_summary["supported_accept"] == 24,
        "off_wrong_source_accept": off_summary["wrong_source_accept"] == 24,
        "off_unknown_accept": off_summary["unknown_accept"] == 12,
        "off_total_accept": off_summary["total_accept"] == 60,
    }
    gates = preregistration["capability_lift_gates"]
    ba_lift = round(
        on_summary["balanced_decision_accuracy"]
        - off_summary["balanced_decision_accuracy"],
        12,
    )
    capability_gate_results = {
        "on_supported_accept": on_summary["supported_accept"]
        >= gates["on_supported_accept_min"],
        "on_wrong_source_accept": on_summary["wrong_source_accept"]
        <= gates["on_wrong_source_accept_max"],
        "on_unknown_accept": on_summary["unknown_accept"]
        <= gates["on_unknown_accept_max"],
        "on_aggregate_hard_negative_accept": on_summary[
            "aggregate_hard_negative_accept"
        ]
        <= gates["on_aggregate_hard_negative_accept_max"],
        "on_balanced_decision_accuracy": on_summary["balanced_decision_accuracy"]
        >= gates["on_balanced_decision_accuracy_min"],
        "balanced_decision_accuracy_lift": ba_lift
        >= gates["balanced_decision_accuracy_lift_min"],
        "on_accepted_precision": on_summary["accepted_precision"]
        >= gates["on_accepted_precision_min"],
        "mcnemar_p": mcnemar_p <= gates["mcnemar_p_max"],
        "mcnemar_favors_on": c > b,
        "each_relation_supported_accept": all(
            row["on_supported_accept"] >= gates["each_relation_supported_accept_min"]
            for row in relation_metrics.values()
        ),
        "each_relation_hard_negative_accept": all(
            row["on_hard_negative_accept"]
            <= gates["each_relation_hard_negative_accept_max"]
            for row in relation_metrics.values()
        ),
        "each_wrong_source_mode_accept": all(
            row["on_accept"] <= gates["each_wrong_source_mode_accept_max"]
            for row in wrong_source_modes.values()
        ),
    }
    regression = preregistration["regression_gates"]
    regression_gate_results = {
        "supported_accept_regression": on_summary["supported_accept"]
        < regression["on_supported_accept_below"],
        "balanced_accuracy_regression": on_summary["balanced_decision_accuracy"]
        < regression["on_balanced_decision_accuracy_below"],
        "hard_negative_regression": on_summary["aggregate_hard_negative_accept"]
        > off_summary["aggregate_hard_negative_accept"],
    }
    measurement_valid = all(integrity_results.values()) and all(
        diagnostic_results.values()
    )
    if not measurement_valid:
        outcome = "NO_GO"
    elif any(regression_gate_results.values()):
        outcome = "REGRESSION"
    elif all(capability_gate_results.values()):
        outcome = "CAPABILITY_LIFT_CONFIRMED"
    else:
        outcome = "NO_LIFT"
    return {
        "summary": summary,
        "balanced_decision_accuracy_lift": ba_lift,
        "mcnemar": {"off_only_correct_b": b, "on_only_correct_c": c, "p_two_sided": mcnemar_p},
        "relation_metrics": relation_metrics,
        "wrong_source_mode_metrics": wrong_source_modes,
        "integrity_gate_results": integrity_results,
        "diagnostic_floor_results": diagnostic_results,
        "capability_lift_gate_results": capability_gate_results,
        "regression_gate_results": regression_gate_results,
        "measurement_valid": measurement_valid,
        "capability_lift_confirmed": outcome == "CAPABILITY_LIFT_CONFIRMED",
        "outcome": outcome,
        "worker_error_count": worker_errors,
        "raw_rows": raw_rows,
        "claim_boundary": (
            "fresh_local_synthetic_single_hop_discrimination_only_"
            "no_answer_generation_or_general_reasoning_claim"
        ),
    }


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise BenchmarkEvidenceError(f"EAD-3 write-once path exists: {path}") from exc


def _checksum(value: Mapping[str, Any]) -> str:
    detached = dict(value)
    detached.pop("checksum_sha256", None)
    return hashlib.sha256(canonical_json_bytes(detached)).hexdigest()


def run(preregistration_path: Path = PREREG) -> tuple[dict[str, Any], Path]:
    preregistration, prereg_relative = load_preregistration(preregistration_path)
    _dataset, cases, dataset_relative = load_dataset(preregistration)
    if any(path.exists() for path in (REPORT, ATTEMPT, FAILURE)):
        raise BenchmarkEvidenceError("EAD-3 report/attempt/failure exists; retry forbidden")
    source_before = bind_files(REPO, preregistration["evaluator_source_paths"])
    candidate_before = bind_files(REPO, preregistration["candidate"]["paths"])
    runtime_before = bind_files(REPO, preregistration["runtime_assets"]["paths"])
    dataset_before = bind_files(REPO, [prereg_relative, dataset_relative])
    if candidate_before["content_sha256"] != preregistration["candidate"]["content_sha256"]:
        raise BenchmarkEvidenceError("EAD-3 candidate differs from EAD-1")
    if runtime_before["content_sha256"] != preregistration["runtime_assets"]["content_sha256"]:
        raise BenchmarkEvidenceError("EAD-3 runtime assets differ from preregistration")
    requests = build_worker_requests(preregistration, cases)
    started_at = utc_now()
    _write_exclusive(
        ATTEMPT,
        {
            "schema_version": ATTEMPT_SCHEMA,
            "preregistration_id": preregistration["preregistration_id"],
            "started_at": started_at,
            "source_content_sha256": source_before["content_sha256"],
            "candidate_content_sha256": candidate_before["content_sha256"],
            "runtime_assets_content_sha256": runtime_before["content_sha256"],
            "dataset_content_sha256": dataset_before["content_sha256"],
            "request_count": 4,
            "request_sha256": [_sha(request) for request in requests],
        },
    )
    arms = []
    try:
        for spec, request in zip(_BLOCKS, requests):
            result = validate_worker_result(_run_worker(request), request)
            arms.append(
                {
                    "block_id": spec[0],
                    "stratum": spec[1],
                    "condition": spec[2],
                    "order": spec[3],
                    "request_sha256": _sha(request),
                    "result": result,
                }
            )
        source_after = bind_files(REPO, preregistration["evaluator_source_paths"])
        candidate_after = bind_files(REPO, preregistration["candidate"]["paths"])
        runtime_after = bind_files(REPO, preregistration["runtime_assets"]["paths"])
        dataset_after = bind_files(REPO, [prereg_relative, dataset_relative])
        closure_integrity = {
            "candidate_same_before_after": candidate_before == candidate_after,
            "runtime_assets_same_before_after": runtime_before == runtime_after,
            "dataset_same_before_after": dataset_before == dataset_after,
            "evaluator_source_same_before_after": source_before == source_after,
        }
        if not all(closure_integrity.values()):
            raise BenchmarkEvidenceError("EAD-3 bound bytes changed during run")
        derived = score_results(
            preregistration,
            cases,
            arms,
            closure_integrity=closure_integrity,
        )
        report = {
            "schema_version": REPORT_SCHEMA,
            "preregistration_id": preregistration["preregistration_id"],
            "started_at": started_at,
            "completed_at": utc_now(),
            "source": source_before,
            "candidate": candidate_before,
            "runtime_assets": runtime_before,
            "dataset": dataset_before,
            "environment": environment_record(),
            "arms": arms,
            "derived": derived,
            "integrity": {
                **closure_integrity,
                "write_once_attempt_present": True,
                "production_source_mutated": False,
                "production_activation_authorized": False,
                "authenticity_established": False,
                "limitations": preregistration["claim_boundary"]["limitations"],
            },
        }
        report["checksum_sha256"] = _checksum(report)
        _write_exclusive(REPORT, report)
        return report, REPORT
    except Exception as exc:
        try:
            _write_exclusive(
                FAILURE,
                {
                    "schema_version": FAILURE_SCHEMA,
                    "preregistration_id": preregistration["preregistration_id"],
                    "started_at": started_at,
                    "failed_at": utc_now(),
                    "completed_block_count": len(arms),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[-2000:],
                },
            )
        except Exception as failure_error:
            if hasattr(exc, "add_note"):
                exc.add_note(
                    f"EAD-3 failure receipt write also failed: {failure_error}"
                )
        raise


def verify(path: Path = REPORT) -> dict[str, Any]:
    findings: list[str] = []
    outcome = None
    try:
        report = _load(path.resolve(strict=True), "EAD-3 report")
        if frozenset(report) != {
            "schema_version",
            "preregistration_id",
            "started_at",
            "completed_at",
            "source",
            "candidate",
            "runtime_assets",
            "dataset",
            "environment",
            "arms",
            "derived",
            "integrity",
            "checksum_sha256",
        }:
            raise BenchmarkEvidenceError("EAD-3 report fields mismatch")
        if path.resolve(strict=True) != REPORT.resolve(strict=True):
            raise BenchmarkEvidenceError("EAD-3 report path identity mismatch")
        if (
            report.get("schema_version") != REPORT_SCHEMA
            or report.get("checksum_sha256") != _checksum(report)
        ):
            raise BenchmarkEvidenceError("EAD-3 report identity/checksum mismatch")
        preregistration, prereg_relative = load_preregistration(PREREG)
        _dataset, cases, dataset_relative = load_dataset(preregistration)
        if report.get("preregistration_id") != preregistration["preregistration_id"]:
            raise BenchmarkEvidenceError("EAD-3 report preregistration mismatch")
        if report.get("source") != bind_files(
            REPO, preregistration["evaluator_source_paths"]
        ):
            raise BenchmarkEvidenceError("EAD-3 source binding not current")
        if report.get("candidate") != bind_files(
            REPO, preregistration["candidate"]["paths"]
        ):
            raise BenchmarkEvidenceError("EAD-3 candidate binding not current")
        if report.get("runtime_assets") != bind_files(
            REPO, preregistration["runtime_assets"]["paths"]
        ):
            raise BenchmarkEvidenceError("EAD-3 runtime binding not current")
        if report.get("dataset") != bind_files(
            REPO, [prereg_relative, dataset_relative]
        ):
            raise BenchmarkEvidenceError("EAD-3 dataset binding not current")
        requests = build_worker_requests(preregistration, cases)
        arms = report.get("arms")
        if not isinstance(arms, list) or len(arms) != 4:
            raise BenchmarkEvidenceError("EAD-3 report arm census mismatch")
        for arm, spec, request in zip(arms, _BLOCKS, requests):
            if (
                frozenset(arm)
                != {
                    "block_id",
                    "stratum",
                    "condition",
                    "order",
                    "request_sha256",
                    "result",
                }
                or
                (
                    arm.get("block_id"),
                    arm.get("stratum"),
                    arm.get("condition"),
                    arm.get("order"),
                )
                != spec
                or arm.get("request_sha256") != _sha(request)
            ):
                raise BenchmarkEvidenceError("EAD-3 report arm identity mismatch")
            validate_worker_result(arm.get("result"), request)
        closures = {
            "candidate_same_before_after": True,
            "runtime_assets_same_before_after": True,
            "dataset_same_before_after": True,
            "evaluator_source_same_before_after": True,
        }
        recomputed = score_results(
            preregistration, cases, arms, closure_integrity=closures
        )
        if report.get("derived") != recomputed:
            raise BenchmarkEvidenceError("EAD-3 report derivation mismatch")
        integrity = report.get("integrity")
        if integrity != {
            **closures,
            "write_once_attempt_present": True,
            "production_source_mutated": False,
            "production_activation_authorized": False,
            "authenticity_established": False,
            "limitations": preregistration["claim_boundary"]["limitations"],
        }:
            raise BenchmarkEvidenceError("EAD-3 report closure integrity mismatch")
        attempt = _load(ATTEMPT, "EAD-3 attempt")
        if (
            frozenset(attempt)
            != {
                "schema_version",
                "preregistration_id",
                "started_at",
                "source_content_sha256",
                "candidate_content_sha256",
                "runtime_assets_content_sha256",
                "dataset_content_sha256",
                "request_count",
                "request_sha256",
            }
            or attempt.get("schema_version") != ATTEMPT_SCHEMA
            or attempt.get("preregistration_id")
            != preregistration["preregistration_id"]
            or attempt.get("started_at") != report.get("started_at")
            or attempt.get("source_content_sha256")
            != report["source"]["content_sha256"]
            or attempt.get("candidate_content_sha256")
            != report["candidate"]["content_sha256"]
            or attempt.get("runtime_assets_content_sha256")
            != report["runtime_assets"]["content_sha256"]
            or attempt.get("dataset_content_sha256")
            != report["dataset"]["content_sha256"]
            or attempt.get("request_count") != 4
            or attempt.get("request_sha256") != [_sha(request) for request in requests]
            or FAILURE.exists()
        ):
            raise BenchmarkEvidenceError("EAD-3 attempt/failure receipt mismatch")
        outcome = recomputed["outcome"]
    except (BenchmarkEvidenceError, OSError, KeyError, TypeError, ValueError) as exc:
        findings.append(str(exc))
    return {
        "valid": not findings,
        "measurement_outcome": outcome,
        "capability_lift_established": not findings
        and outcome == "CAPABILITY_LIFT_CONFIRMED",
        "production_activation_authorized": False,
        "authenticity_established": False,
        "findings": findings,
    }


def dry_run_record(
    preregistration: Mapping[str, Any],
    prereg_relative: str,
    cases: Sequence[Mapping[str, Any]],
    dataset_relative: str,
) -> dict[str, Any]:
    requests = build_worker_requests(preregistration, cases)
    return {
        "valid": True,
        "preregistration_id": preregistration["preregistration_id"],
        "source_paths_declared": preregistration["evaluator_source_paths"],
        "candidate": bind_files(REPO, preregistration["candidate"]["paths"]),
        "runtime_assets": bind_files(REPO, preregistration["runtime_assets"]["paths"]),
        "dataset": bind_files(REPO, [prereg_relative, dataset_relative]),
        "case_counts": {
            kind: sum(row["kind"] == kind for row in cases)
            for kind in ("POS", "WRONG_SOURCE", "UNKNOWN")
        },
        "block_counts": {
            request["block_id"]: len(request["items"]) for request in requests
        },
        "worker_visible_fields": sorted(_REQUEST_ITEM_FIELDS),
        "candidate_executed": False,
        "checkpoint_loaded": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "run", "verify"))
    parser.add_argument("path", nargs="?", type=Path)
    args = parser.parse_args(argv)
    if args.command == "validate":
        preregistration, prereg_relative = load_preregistration(args.path or PREREG)
        _dataset, cases, dataset_relative = load_dataset(preregistration)
        print(
            json.dumps(
                dry_run_record(
                    preregistration, prereg_relative, cases, dataset_relative
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "run":
        report, destination = run(args.path or PREREG)
        print(
            json.dumps(
                {
                    "report": str(destination),
                    "outcome": report["derived"]["outcome"],
                }
            )
        )
        return 0 if report["derived"]["measurement_valid"] else 2
    result = verify(args.path or REPORT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        raise SystemExit(2)
