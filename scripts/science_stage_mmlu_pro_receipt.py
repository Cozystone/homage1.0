"""Paired A-track measurement on the exposed local MMLU-Pro slice.

This is a development-only measurement receipt, not E5 evidence.  It fixes the
40-item ``slice_5`` bytes, keeps gold evaluator-side, runs stage-absent OFF and
validated-stage ON in a 20/20 counterbalanced order, and repeats each item in
reverse order.  ``sealed`` means only that the named local bytes stayed stable,
the paired semantic replay agreed, the base stayed immutable, and the checksum
and current-tree replay verify.  It does not mean hidden, independent, signed,
or externally authenticated evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from packages.eval_evidence.receipt import (  # noqa: E402
    BenchmarkEvidenceError,
    bind_files,
    canonical_json_bytes,
    ensure_safe_report_output,
    strict_json_bytes,
    write_manifest_exclusive,
)
from packages.reasoning_vm.science_exam import outcome_digest  # noqa: E402
from packages.reasoning_vm.science_staging import (  # noqa: E402
    ScienceStageSnapshot,
    load_science_stage,
)
from scripts import deliberator_benchmark_receipt as bench  # noqa: E402
from scripts import science_stage_e4_receipt as e4  # noqa: E402


SCHEMA_VERSION = "atanor.science-stage-mmlu-pro-paired-dev-receipt.v1"
EVIDENCE_KIND = "strict_self_measured_exposed_mmlu_pro_development_receipt"
DATASET_PATH = "data/benchmarks/mmlu_pro/slice_5.jsonl"
EXPECTED_DATASET_SHA256 = (
    "a1325092eabfb8dc394ef37f64fe63d79c002678b9d9d3b580605d41690e8b36"
)
EXPECTED_ITEMS = 40
EXPECTED_PER_CATEGORY = 5
CATEGORIES = tuple(sorted(bench._MMLU_CATEGORIES))
STAGE_ROOT = e4.STAGE_ROOT
STAGE_PATHS = e4.STAGE_PATHS

SOURCE_PATHS = (
    "packages/eval_evidence/__init__.py",
    "packages/eval_evidence/receipt.py",
    "scripts/deliberator_benchmark_receipt.py",
    "scripts/science_stage_e4_receipt.py",
    "scripts/science_stage_mmlu_pro_receipt.py",
)
CANDIDATE_PATHS = e4.CANDIDATE_PATHS
DATASET_PATHS = (DATASET_PATH,)
_MAX_RECEIPT_BYTES = 16 * 1024 * 1024
_SHA256 = e4._SHA256

_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_kind",
        "protocol",
        "claims",
        "seal",
        "source",
        "candidate",
        "dataset",
        "stage",
        "e4_prerequisite_contract",
        "stage_snapshot",
        "selection",
        "metrics",
        "items",
        "integrity",
        "manifest_checksum_sha256",
    }
)
_ITEM_FIELDS = frozenset(
    {
        "item_id",
        "ordinal",
        "category",
        "evaluator_eligible",
        "input_digest_sha256",
        "choices_digest_sha256",
        "primary_execution_order",
        "replay_execution_order",
        "conditions",
        "off_to_on",
        "replay",
        "gold_absent_from_candidate_arguments",
    }
)
_CONDITION_WRAPPER_FIELDS = frozenset({"result"})
_CLAIM_FIELDS = frozenset(
    {
        "classification",
        "development_only",
        "e4_contract_bound",
        "paired_measurement_gate_passed",
        "e5_claimed",
        "independent",
        "externally_signed",
        "external_authenticity_established",
        "benchmark_capability_claimed",
        "process_resource_curve_claimed",
    }
)
_SEAL_FIELDS = frozenset(
    {
        "sealed",
        "scope",
        "git_clean_required",
        "hidden_holdout_claimed",
        "independent_evaluation_claimed",
        "external_authenticity_established",
        "e5_equivalent",
    }
)
_SELECTION_FIELDS = frozenset(
    {
        "evaluator_owned_fixed_denominator",
        "dataset_path",
        "expected_dataset_sha256",
        "actual_dataset_sha256",
        "expected_item_count",
        "category_counts",
        "item_ids",
        "item_ids_sha256",
        "input_choice_pairs_sha256",
    }
)
_INTEGRITY_FIELDS = frozenset(
    {
        "source_same_before_after",
        "candidate_same_before_after",
        "dataset_same_before_after",
        "stage_same_before_after",
        "dataset_matches_pinned_hash",
        "same_items_choices_off_on",
        "gold_absent_from_candidate_arguments_all",
        "semantic_replay_all",
        "base_state_immutable",
        "off_snapshot_structurally_absent",
        "on_validated_snapshot_bound",
        "network_isolation_enforced",
        "shipped_graph_write_authority",
        "production_authority",
        "process_resource_telemetry_omitted",
    }
)
_SEAL_SCOPE = (
    "exact source/candidate/dataset/stage bytes stable before-after "
    "+ pinned dataset hash + counterbalanced reverse semantic replay "
    "+ immutable base + deterministic semantic records + recomputable checksum"
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        raise BenchmarkEvidenceError("metric denominator must be positive")
    return round(numerator / denominator, 12)


def _checksum(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_checksum_sha256", None)
    return _sha256(canonical_json_bytes(unsigned))


def _base_digest(base: Mapping[str, Any]) -> str:
    return _sha256(canonical_json_bytes(base))


def _protocol() -> dict[str, Any]:
    return {
        "benchmark": "MMLU-Pro",
        "slice": "slice_5",
        "classification": "exposed_local_development_slice_not_e5",
        "fixed_denominator": 40,
        "category_census": "8 categories x 5 items",
        "candidate_payload": "opaque item_id + question + choices; evaluator owns gold",
        "conditions": {
            "off": "no ScienceStageSnapshot reaches candidate or reasoner",
            "on": "one fail-closed validated read-only ScienceStageSnapshot",
        },
        "counterbalance": (
            "even ordinals OFF-then-ON; odd ordinals ON-then-OFF "
            "(20 items in each primary order)"
        ),
        "replay": "repeat both conditions in reverse primary order",
        "strict_scoring": "errors and abstentions are incorrect on all 40 items",
        "statistics": (
            "overall and per-category reach/accuracy/firing; exact paired "
            "McNemar and exact two-sided binomial intervals"
        ),
        "limitations": [
            "the local slice has prior project exposure",
            "the evaluator is not independent",
            "the receipt is unsigned",
            "declared source coordinates do not establish external authenticity",
            "zero compiler reach makes zero wrong-fire vacuous",
            "runtime identity, timestamps, and process resource telemetry are "
            "omitted because this unsigned in-process evaluator cannot attest them",
        ],
    }


def _scope_record(scope: Mapping[str, Any], path: str) -> Mapping[str, Any]:
    for row in scope.get("files", []):
        if isinstance(row, Mapping) and row.get("path") == path:
            return row
    raise BenchmarkEvidenceError(f"bound scope does not contain {path}")


def _e4_contract(source_scope: Mapping[str, Any]) -> dict[str, Any]:
    core = {
        "source_path": "scripts/science_stage_e4_receipt.py",
        "source_sha256": _scope_record(
            source_scope, "scripts/science_stage_e4_receipt.py"
        )["sha256"],
        "schema_version": e4.SCHEMA_VERSION,
        "evidence_kind": e4.EVIDENCE_KIND,
        "required_gate_path": "metrics.e4_development_gate_passed",
        "required_gate_value": True,
        "generated_external_receipt_required": False,
        "attestation": "contract_bound_only_not_reexecuted_as_a_prerequisite",
    }
    return {
        **core,
        "contract_digest_sha256": _sha256(canonical_json_bytes(core)),
    }


def _current_scopes(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "source": bind_files(repo_root, SOURCE_PATHS),
        "candidate": bind_files(repo_root, CANDIDATE_PATHS),
        "dataset": bind_files(repo_root, DATASET_PATHS),
        "stage": bind_files(repo_root, STAGE_PATHS),
    }


def _load_dataset(repo_root: Path) -> tuple[list[dict[str, Any]], bytes]:
    try:
        payload = (repo_root / DATASET_PATH).read_bytes()
    except OSError as exc:
        raise BenchmarkEvidenceError(
            f"fixed MMLU-Pro slice unavailable: {type(exc).__name__}"
        ) from exc
    if _sha256(payload) != EXPECTED_DATASET_SHA256:
        raise BenchmarkEvidenceError(
            "fixed MMLU-Pro slice_5 bytes do not match the pinned hash"
        )
    rows = bench._load_mmlu_pro_bytes(payload, slice_size=5)
    if len(rows) != EXPECTED_ITEMS:
        raise BenchmarkEvidenceError("MMLU-Pro denominator is not exactly 40")
    return rows, payload


def _item_identity(row: Mapping[str, Any], ordinal: int) -> str:
    return _sha256(
        canonical_json_bytes(
            {
                "benchmark": "mmlu-pro",
                "slice": 5,
                "ordinal": ordinal,
                "question": row["q"],
                "choices": row["choices"],
                "category": row["category"],
            }
        )
    )


def _candidate_payload(row: Mapping[str, Any], ordinal: int) -> dict[str, Any]:
    identity = _item_identity(row, ordinal)
    return e4._candidate_payload(
        {
            "id": identity,
            "question": row["q"],
            "choices": row["choices"],
        }
    )


def _execute_pair(
    safe_item: Mapping[str, Any],
    *,
    stage: ScienceStageSnapshot,
    primary_order: Sequence[str],
    gold: str,
    base_facts: Any,
    base_state_digest: Any,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if list(primary_order) not in (["off", "on"], ["on", "off"]):
        raise BenchmarkEvidenceError("paired execution order is invalid")
    replay_order = list(reversed(primary_order))
    primary: dict[str, dict[str, Any]] = {}
    repeated: dict[str, dict[str, Any]] = {}
    for condition in primary_order:
        primary[condition] = e4._run_condition(
            safe_item,
            stage=stage,
            enabled=condition == "on",
            base_facts=base_facts,
            base_state_digest=base_state_digest,
        )
    for condition in replay_order:
        repeated[condition] = e4._run_condition(
            safe_item,
            stage=stage,
            enabled=condition == "on",
            base_facts=base_facts,
            base_state_digest=base_state_digest,
        )
    for outcome in (*primary.values(), *repeated.values()):
        integrity = outcome.get("integrity")
        if (
            not isinstance(integrity, Mapping)
            or integrity.get("gold_in_candidate_payload") is not False
            or integrity.get("shipped_graph_write_authority") is not False
        ):
            raise BenchmarkEvidenceError(
                "candidate arguments contain gold or write authority"
            )

    records: dict[str, dict[str, Any]] = {}
    for condition in ("off", "on"):
        record = e4._condition_record(primary[condition], gold=gold)
        # Process RSS is intentionally outside this deterministic receipt.  A
        # local recomputable checksum cannot attest noisy process telemetry.
        record["rss_delta_bytes"] = None
        records[condition] = record
    compiler_records = [
        outcome["compiler"]
        for outcome in (
            primary["off"],
            primary["on"],
            repeated["off"],
            repeated["on"],
        )
    ]
    fingerprints = {
        record.get("input_fingerprint") for record in compiler_records
    }
    goal_digests = {
        record.get("goal_digest_sha256") for record in compiler_records
    }
    all_rejected = all(
        record.get("compiled") is not True for record in compiler_records
    )
    replay = {
        "input_fingerprint_same": (
            len(fingerprints) == 1 and None not in fingerprints
        ),
        "goal_digest_same": (
            len(goal_digests) == 1
            and (None not in goal_digests or all_rejected)
        ),
        "off_semantic_outcome_same": (
            records["off"]["semantic_outcome_digest_sha256"]
            == outcome_digest(repeated["off"])
        ),
        "on_semantic_outcome_same": (
            records["on"]["semantic_outcome_digest_sha256"]
            == outcome_digest(repeated["on"])
        ),
        "off_replay_digest_sha256": outcome_digest(repeated["off"]),
        "on_replay_digest_sha256": outcome_digest(repeated["on"]),
    }
    return (
        {
            condition: {"result": records[condition]}
            for condition in ("off", "on")
        },
        replay,
    )


def _binomial_cdf(k: int, n: int, p: float) -> float:
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return sum(
        math.comb(n, index)
        * (p**index)
        * ((1.0 - p) ** (n - index))
        for index in range(k + 1)
    )


def _exact_binomial_ci95(k: int, n: int) -> list[float]:
    if type(k) is not int or type(n) is not int or not 0 <= k <= n or n <= 0:
        raise BenchmarkEvidenceError("binomial interval inputs are invalid")

    def solve(cdf_k: int, target: float) -> float:
        low, high = 0.0, 1.0
        for _ in range(96):
            mid = (low + high) / 2.0
            if _binomial_cdf(cdf_k, n, mid) > target:
                low = mid
            else:
                high = mid
        return (low + high) / 2.0

    lower = 0.0 if k == 0 else solve(k - 1, 0.975)
    upper = 1.0 if k == n else solve(k, 0.025)
    return [round(lower, 12), round(upper, 12)]


def _exact_mcnemar_p(off_only: int, on_only: int) -> float:
    discordant = off_only + on_only
    if discordant == 0:
        return 1.0
    tail = sum(
        math.comb(discordant, index)
        for index in range(min(off_only, on_only) + 1)
    ) / (2**discordant)
    return round(min(1.0, 2.0 * tail), 12)


def _condition_metrics(
    items: Sequence[Mapping[str, Any]], condition: str
) -> dict[str, Any]:
    rows = [row["conditions"][condition]["result"] for row in items]
    n = len(rows)
    counts = {
        "input_valid": sum(
            int(row["compiler"]["input_valid"] is True) for row in rows
        ),
        "compiler_reach": sum(
            int(row["compiler"]["compiled"] is True) for row in rows
        ),
        "raw_fired": sum(int(row["raw_fired"] is True) for row in rows),
        "fired": sum(int(row["engine_fired"] is True) for row in rows),
        "grounded": sum(int(row["grounded"] is True) for row in rows),
        "correct": sum(int(row["correct"] is True) for row in rows),
        "wrong_fire": sum(int(row["wrong_fire"] is True) for row in rows),
        "abstain": sum(int(row["status"] == "abstain") for row in rows),
        "error": sum(int(row["status"] == "error") for row in rows),
    }
    return {
        "n": n,
        **counts,
        "input_valid_rate": _ratio(counts["input_valid"], n),
        "compiler_reach_rate": _ratio(counts["compiler_reach"], n),
        "engine_firing_rate": _ratio(counts["fired"], n),
        "grounded_coverage": _ratio(counts["grounded"], n),
        "strict_accuracy": _ratio(counts["correct"], n),
        "strict_accuracy_exact_binomial_95_ci": _exact_binomial_ci95(
            counts["correct"], n
        ),
        "wrong_fire_rate": _ratio(counts["wrong_fire"], n),
        "abstention_rate": _ratio(counts["abstain"], n),
        "answered_accuracy": (
            None
            if counts["fired"] == 0
            else _ratio(counts["correct"], counts["fired"])
        ),
    }


def _paired_metrics(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    off_only = sum(
        int(
            row["conditions"]["off"]["result"]["correct"] is True
            and row["conditions"]["on"]["result"]["correct"] is not True
        )
        for row in items
    )
    on_only = sum(
        int(
            row["conditions"]["off"]["result"]["correct"] is not True
            and row["conditions"]["on"]["result"]["correct"] is True
        )
        for row in items
    )
    transitions = Counter(row["off_to_on"]["label"] for row in items)
    return {
        "strict_accuracy_delta": round(
            _condition_metrics(items, "on")["strict_accuracy"]
            - _condition_metrics(items, "off")["strict_accuracy"],
            12,
        ),
        "transition_counts": dict(sorted(transitions.items())),
        "off_correct_on_incorrect": off_only,
        "off_incorrect_on_correct": on_only,
        "discordant_pairs": off_only + on_only,
        "exact_two_sided_mcnemar_p": _exact_mcnemar_p(off_only, on_only),
    }


def _derive_metrics(
    items: Sequence[Mapping[str, Any]],
    stage_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    by_category = {
        category: [row for row in items if row["category"] == category]
        for category in CATEGORIES
    }
    order_counts = Counter(
        "off_then_on"
        if row["primary_execution_order"] == ["off", "on"]
        else "on_then_off"
        for row in items
    )
    replay_all = all(
        all(
            row["replay"].get(field) is True
            for field in (
                "input_fingerprint_same",
                "goal_digest_same",
                "off_semantic_outcome_same",
                "on_semantic_outcome_same",
            )
        )
        for row in items
    )
    base_immutable = all(
        row["conditions"][condition]["result"]["base_state_unchanged"] is True
        for row in items
        for condition in ("off", "on")
    )
    off_absent = all(
        row["conditions"]["off"]["result"]["stage_digest_sha256"] is None
        and row["conditions"]["off"]["result"]["stage_snapshot_bound_bytes"] == 0
        and row["conditions"]["off"]["result"]["stage_hit_count"] == 0
        and row["conditions"]["off"]["result"]["evidence_ids"] == []
        for row in items
    )
    on_bound = all(
        row["conditions"]["on"]["result"]["stage_digest_sha256"]
        == stage_snapshot["stage_digest_sha256"]
        and row["conditions"]["on"]["result"]["stage_snapshot_bound_bytes"]
        == stage_snapshot["bound_bytes"]
        and row["conditions"]["on"]["result"]["stage_bytes_read"] == 0
        for row in items
    )
    category_census = {
        category: len(rows) for category, rows in by_category.items()
    }
    overall = {
        "off": _condition_metrics(items, "off"),
        "on": _condition_metrics(items, "on"),
        "paired": _paired_metrics(items),
    }
    categories = {
        category: {
            "n": len(rows),
            "off": _condition_metrics(rows, "off"),
            "on": _condition_metrics(rows, "on"),
            "paired": _paired_metrics(rows),
        }
        for category, rows in by_category.items()
    }
    measurement_gate = (
        len(items) == EXPECTED_ITEMS
        and category_census
        == {category: EXPECTED_PER_CATEGORY for category in CATEGORIES}
        and dict(order_counts)
        == {"off_then_on": 20, "on_then_off": 20}
        and replay_all
        and base_immutable
        and off_absent
        and on_bound
        and all(
            row["gold_absent_from_candidate_arguments"] is True
            for row in items
        )
        and overall["off"]["error"] == 0
        and overall["on"]["error"] == 0
    )
    return {
        "denominator": len(items),
        "category_census": category_census,
        "primary_order_counts": dict(sorted(order_counts.items())),
        "overall": overall,
        "categories": categories,
        "semantic_replay_all": replay_all,
        "base_state_immutable_all": base_immutable,
        "off_snapshot_structurally_absent_all": off_absent,
        "on_validated_snapshot_bound_all": on_bound,
        "paired_development_measurement_gate_passed": measurement_gate,
    }


def _selection(
    rows: Sequence[Mapping[str, Any]], dataset_bytes: bytes
) -> dict[str, Any]:
    ids = [
        _item_identity(row, ordinal) for ordinal, row in enumerate(rows)
    ]
    input_pairs = [
        {
            "item_id": ids[ordinal],
            "question": row["q"],
            "choices": row["choices"],
            "category": row["category"],
        }
        for ordinal, row in enumerate(rows)
    ]
    return {
        "evaluator_owned_fixed_denominator": True,
        "dataset_path": DATASET_PATH,
        "expected_dataset_sha256": EXPECTED_DATASET_SHA256,
        "actual_dataset_sha256": _sha256(dataset_bytes),
        "expected_item_count": EXPECTED_ITEMS,
        "category_counts": {
            category: sum(int(row["category"] == category) for row in rows)
            for category in CATEGORIES
        },
        "item_ids": ids,
        "item_ids_sha256": _sha256(canonical_json_bytes(ids)),
        "input_choice_pairs_sha256": _sha256(canonical_json_bytes(input_pairs)),
    }


def _stage_record(snapshot: ScienceStageSnapshot) -> dict[str, Any]:
    return {
        "stage_id": snapshot.stage_id,
        "stage_digest_sha256": snapshot.stage_digest_sha256,
        "manifest_checksum_sha256": snapshot.manifest_checksum_sha256,
        "bound_bytes": snapshot.bound_bytes,
        "row_count": len(snapshot.facts),
    }


def _validate_scope(
    value: Any, expected_paths: Sequence[str], label: str, findings: list[str]
) -> None:
    if not isinstance(value, Mapping) or frozenset(value) != {
        "files",
        "content_sha256",
    }:
        findings.append(f"{label} scope fields mismatch")
        return
    files = value.get("files")
    if not isinstance(files, list):
        findings.append(f"{label}.files must be a list")
        return
    if [row.get("path") for row in files if isinstance(row, Mapping)] != sorted(
        expected_paths
    ):
        findings.append(f"{label} bound paths mismatch")
    for index, row in enumerate(files):
        if (
            not isinstance(row, Mapping)
            or frozenset(row) != {"path", "bytes", "sha256"}
            or type(row.get("bytes")) is not int
            or row.get("bytes") < 0
            or not isinstance(row.get("sha256"), str)
            or _SHA256.fullmatch(row["sha256"]) is None
        ):
            findings.append(f"{label}.files[{index}] invalid")
    if value.get("content_sha256") != _sha256(canonical_json_bytes(files)):
        findings.append(f"{label}.content_sha256 is not derived")


def _validate_item(
    value: Any,
    index: int,
    stage_snapshot: Mapping[str, Any],
    findings: list[str],
) -> None:
    label = f"items[{index}]"
    if not isinstance(value, Mapping) or frozenset(value) != _ITEM_FIELDS:
        findings.append(f"{label} fields mismatch")
        return
    if value.get("ordinal") != index:
        findings.append(f"{label}.ordinal mismatch")
    if value.get("category") not in CATEGORIES:
        findings.append(f"{label}.category invalid")
    if (
        not isinstance(value.get("item_id"), str)
        or _SHA256.fullmatch(value["item_id"]) is None
    ):
        findings.append(f"{label}.item_id invalid")
    for field in ("input_digest_sha256", "choices_digest_sha256"):
        if (
            not isinstance(value.get(field), str)
            or _SHA256.fullmatch(value[field]) is None
        ):
            findings.append(f"{label}.{field} invalid")
    expected_order = ["off", "on"] if index % 2 == 0 else ["on", "off"]
    if value.get("primary_execution_order") != expected_order:
        findings.append(f"{label}.primary_execution_order mismatch")
    if value.get("replay_execution_order") != list(reversed(expected_order)):
        findings.append(f"{label}.replay_execution_order mismatch")
    if value.get("evaluator_eligible") is not True:
        findings.append(f"{label}.evaluator_eligible must be true")
    if value.get("gold_absent_from_candidate_arguments") is not True:
        findings.append(f"{label}.candidate arguments do not exclude gold")
    conditions = value.get("conditions")
    if not isinstance(conditions, Mapping) or frozenset(conditions) != {
        "off",
        "on",
    }:
        findings.append(f"{label}.conditions fields mismatch")
        return
    for condition in ("off", "on"):
        wrapper = conditions.get(condition)
        condition_label = f"{label}.conditions.{condition}"
        if (
            not isinstance(wrapper, Mapping)
            or frozenset(wrapper) != _CONDITION_WRAPPER_FIELDS
        ):
            findings.append(f"{condition_label} fields mismatch")
            continue
        e4._validate_condition(
            wrapper.get("result"),
            label=f"{condition_label}.result",
            findings=findings,
        )
        result = wrapper.get("result")
        if (
            isinstance(result, Mapping)
            and result.get("rss_delta_bytes") is not None
        ):
            findings.append(
                f"{condition_label} process resource telemetry must be omitted"
            )
    off = conditions["off"].get("result", {})
    on = conditions["on"].get("result", {})
    if (
        off.get("stage_digest_sha256") is not None
        or off.get("stage_snapshot_bound_bytes") != 0
        or off.get("stage_hit_count") != 0
        or off.get("evidence_ids") != []
    ):
        findings.append(f"{label}.OFF retained stage authority")
    if (
        on.get("stage_digest_sha256")
        != stage_snapshot.get("stage_digest_sha256")
        or on.get("stage_snapshot_bound_bytes")
        != stage_snapshot.get("bound_bytes")
        or on.get("stage_bytes_read") != 0
    ):
        findings.append(f"{label}.ON stage binding mismatch")
    if value.get("off_to_on") != e4._transition(off, on):
        findings.append(f"{label}.off_to_on is not derived")
    replay = value.get("replay")
    if not isinstance(replay, Mapping) or frozenset(replay) != e4._REPLAY_FIELDS:
        findings.append(f"{label}.replay fields mismatch")
    else:
        for field in (
            "input_fingerprint_same",
            "goal_digest_same",
            "off_semantic_outcome_same",
            "on_semantic_outcome_same",
        ):
            if replay.get(field) is not True:
                findings.append(f"{label}.replay.{field} must be true")
        if replay.get("off_replay_digest_sha256") != off.get(
            "semantic_outcome_digest_sha256"
        ):
            findings.append(f"{label}.replay OFF digest mismatch")
        if replay.get("on_replay_digest_sha256") != on.get(
            "semantic_outcome_digest_sha256"
        ):
            findings.append(f"{label}.replay ON digest mismatch")


def _compare_current_item(
    declared: Mapping[str, Any],
    row: Mapping[str, Any],
    ordinal: int,
    *,
    stage: ScienceStageSnapshot,
    base_facts: Any,
    base_state_digest: Any,
    findings: list[str],
) -> None:
    label = f"items[{ordinal}]"
    safe = _candidate_payload(row, ordinal)
    if (
        declared.get("item_id") != _item_identity(row, ordinal)
        or declared.get("category") != row["category"]
        or declared.get("input_digest_sha256")
        != _sha256(canonical_json_bytes(safe))
        or declared.get("choices_digest_sha256")
        != _sha256(canonical_json_bytes(safe["choices"]))
    ):
        findings.append(f"{label} input binding differs from current dataset")
        return
    conditions, replay = _execute_pair(
        safe,
        stage=stage,
        primary_order=declared["primary_execution_order"],
        gold=row["gold"],
        base_facts=base_facts,
        base_state_digest=base_state_digest,
    )
    for condition in ("off", "on"):
        actual = e4._condition_semantics(conditions[condition]["result"])
        expected = e4._condition_semantics(
            declared["conditions"][condition]["result"]
        )
        if actual != expected:
            findings.append(
                f"{label}.conditions.{condition} does not reproduce "
                "from the current candidate"
            )
    if declared.get("replay") != replay:
        findings.append(f"{label}.replay does not reproduce from current candidate")


def validate_receipt(
    manifest: Any,
    *,
    repo_root: Path = REPO,
    require_current: bool = False,
) -> list[str]:
    findings: list[str] = []
    try:
        if not isinstance(manifest, Mapping):
            return ["receipt root must be an object"]
        if frozenset(manifest) != _ROOT_FIELDS:
            findings.append("receipt root fields mismatch")
        if manifest.get("schema_version") != SCHEMA_VERSION:
            findings.append("schema_version mismatch")
        if manifest.get("evidence_kind") != EVIDENCE_KIND:
            findings.append("evidence_kind mismatch")
        if manifest.get("manifest_checksum_sha256") != _checksum(manifest):
            findings.append("manifest checksum mismatch")
        if manifest.get("protocol") != _protocol():
            findings.append("protocol mismatch")
        for label, paths in (
            ("source", SOURCE_PATHS),
            ("candidate", CANDIDATE_PATHS),
            ("dataset", DATASET_PATHS),
            ("stage", STAGE_PATHS),
        ):
            _validate_scope(manifest.get(label), paths, label, findings)

        contract = manifest.get("e4_prerequisite_contract")
        try:
            expected_contract = _e4_contract(manifest.get("source", {}))
        except (BenchmarkEvidenceError, KeyError, TypeError):
            expected_contract = None
        if contract != expected_contract:
            findings.append("E4 prerequisite source/schema/gate contract mismatch")

        stage_snapshot = manifest.get("stage_snapshot")
        if (
            not isinstance(stage_snapshot, Mapping)
            or frozenset(stage_snapshot) != {
                "stage_id",
                "stage_digest_sha256",
                "manifest_checksum_sha256",
                "bound_bytes",
                "row_count",
            }
            or type(stage_snapshot.get("bound_bytes")) is not int
            or stage_snapshot.get("bound_bytes") <= 0
            or type(stage_snapshot.get("row_count")) is not int
            or stage_snapshot.get("row_count") <= 0
        ):
            findings.append("stage_snapshot invalid")
            stage_snapshot = {}
        else:
            for field in (
                "stage_digest_sha256",
                "manifest_checksum_sha256",
            ):
                if (
                    not isinstance(stage_snapshot.get(field), str)
                    or _SHA256.fullmatch(stage_snapshot[field]) is None
                ):
                    findings.append(f"stage_snapshot.{field} invalid")

        items = manifest.get("items")
        if not isinstance(items, list) or len(items) != EXPECTED_ITEMS:
            findings.append("items must contain exactly 40 rows")
            items = []
        for index, item in enumerate(items):
            _validate_item(item, index, stage_snapshot, findings)

        if items:
            expected_metrics = _derive_metrics(items, stage_snapshot)
            if manifest.get("metrics") != expected_metrics:
                findings.append("metrics are not derived from item records")
            ids = [row.get("item_id") for row in items]
            selection = manifest.get("selection")
            if (
                not isinstance(selection, Mapping)
                or frozenset(selection) != _SELECTION_FIELDS
                or selection.get("evaluator_owned_fixed_denominator") is not True
                or selection.get("dataset_path") != DATASET_PATH
                or selection.get("expected_dataset_sha256")
                != EXPECTED_DATASET_SHA256
                or selection.get("actual_dataset_sha256")
                != EXPECTED_DATASET_SHA256
                or selection.get("expected_item_count") != EXPECTED_ITEMS
                or selection.get("category_counts")
                != {
                    category: EXPECTED_PER_CATEGORY for category in CATEGORIES
                }
                or selection.get("item_ids") != ids
                or selection.get("item_ids_sha256")
                != _sha256(canonical_json_bytes(ids))
                or not isinstance(
                    selection.get("input_choice_pairs_sha256"), str
                )
                or _SHA256.fullmatch(
                    selection.get("input_choice_pairs_sha256", "")
                )
                is None
            ):
                findings.append("selection binding mismatch")
        else:
            expected_metrics = {}

        claims = manifest.get("claims")
        if (
            not isinstance(claims, Mapping)
            or frozenset(claims) != _CLAIM_FIELDS
            or claims.get("classification")
            != "exposed_mmlu_pro_slice5_development_only"
            or claims.get("development_only") is not True
            or claims.get("e4_contract_bound") is not True
            or claims.get("paired_measurement_gate_passed")
            is not expected_metrics.get(
                "paired_development_measurement_gate_passed"
            )
            or claims.get("e5_claimed") is not False
            or claims.get("independent") is not False
            or claims.get("externally_signed") is not False
            or claims.get("external_authenticity_established") is not False
            or claims.get("benchmark_capability_claimed") is not False
            or claims.get("process_resource_curve_claimed") is not False
        ):
            findings.append("claims mismatch")
        seal = manifest.get("seal")
        if (
            not isinstance(seal, Mapping)
            or frozenset(seal) != _SEAL_FIELDS
            or seal.get("sealed") is not True
            or seal.get("scope") != _SEAL_SCOPE
            or seal.get("hidden_holdout_claimed") is not False
            or seal.get("independent_evaluation_claimed") is not False
            or seal.get("external_authenticity_established") is not False
            or seal.get("e5_equivalent") is not False
            or seal.get("git_clean_required") is not False
        ):
            findings.append("seal authority flags mismatch")
        integrity = manifest.get("integrity")
        if (
            not isinstance(integrity, Mapping)
            or frozenset(integrity) != _INTEGRITY_FIELDS
            or any(
                integrity.get(field) is not True
                for field in (
                    "source_same_before_after",
                    "candidate_same_before_after",
                    "dataset_same_before_after",
                    "stage_same_before_after",
                    "dataset_matches_pinned_hash",
                    "same_items_choices_off_on",
                    "gold_absent_from_candidate_arguments_all",
                    "semantic_replay_all",
                    "base_state_immutable",
                    "off_snapshot_structurally_absent",
                    "on_validated_snapshot_bound",
                    "process_resource_telemetry_omitted",
                )
            )
            or integrity.get("network_isolation_enforced") is not False
            or integrity.get("shipped_graph_write_authority") is not False
            or integrity.get("production_authority") is not False
        ):
            findings.append("integrity claims mismatch")

        if require_current:
            try:
                scopes_before_replay = _current_scopes(repo_root)
                for name in ("source", "candidate", "dataset", "stage"):
                    if manifest.get(name) != scopes_before_replay[name]:
                        findings.append(f"{name} scope differs from current bytes")
                rows, dataset_bytes = _load_dataset(repo_root)
                if manifest.get("selection") != _selection(rows, dataset_bytes):
                    findings.append("selection differs from current fixed dataset")
                current_stage = load_science_stage(repo_root / STAGE_ROOT)
                if stage_snapshot != _stage_record(current_stage):
                    findings.append(
                        "stage snapshot differs from current validated stage"
                    )
                base: dict[str, list[tuple[str, str, str]]] = {}

                def base_facts(subject: str) -> list[tuple[str, str, str]]:
                    return list(base.get(subject, ()))

                def base_state_digest() -> str:
                    return _base_digest(base)

                before = base_state_digest()
                for ordinal, row in enumerate(rows):
                    if ordinal >= len(items):
                        break
                    _compare_current_item(
                        items[ordinal],
                        row,
                        ordinal,
                        stage=current_stage,
                        base_facts=base_facts,
                        base_state_digest=base_state_digest,
                        findings=findings,
                    )
                if before != base_state_digest():
                    findings.append("current semantic replay mutated base state")
                scopes_after_replay = _current_scopes(repo_root)
                if scopes_before_replay != scopes_after_replay:
                    findings.append(
                        "bound bytes changed during current semantic replay"
                    )
                for name in ("source", "candidate", "dataset", "stage"):
                    if manifest.get(name) != scopes_after_replay[name]:
                        findings.append(
                            f"{name} scope differs after current semantic replay"
                        )
            except Exception as exc:
                findings.append(
                    "current verification failed closed: "
                    f"{type(exc).__name__}: {exc}"
                )
    except Exception as exc:
        findings.append(
            f"receipt validation failed closed: {type(exc).__name__}: {exc}"
        )
    return findings


def _finalize(
    payload: Mapping[str, Any], *, repo_root: Path = REPO
) -> dict[str, Any]:
    manifest = json.loads(canonical_json_bytes(payload))
    if "manifest_checksum_sha256" in manifest:
        raise BenchmarkEvidenceError("checksum must not be supplied by caller")
    manifest["manifest_checksum_sha256"] = _checksum(manifest)
    findings = validate_receipt(
        manifest, repo_root=repo_root, require_current=False
    )
    if findings:
        raise BenchmarkEvidenceError("; ".join(findings))
    return manifest


def build_receipt(
    *,
    repo_root: Path = REPO,
) -> dict[str, Any]:
    rows, dataset_bytes = _load_dataset(repo_root)
    stage = load_science_stage(repo_root / STAGE_ROOT)
    stage_snapshot = _stage_record(stage)
    scopes_before = _current_scopes(repo_root)
    base: dict[str, list[tuple[str, str, str]]] = {}

    def base_facts(subject: str) -> list[tuple[str, str, str]]:
        return list(base.get(subject, ()))

    def base_state_digest() -> str:
        return _base_digest(base)

    base_before = base_state_digest()
    items: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows):
        safe = _candidate_payload(row, ordinal)
        primary_order = ["off", "on"] if ordinal % 2 == 0 else ["on", "off"]
        conditions, replay = _execute_pair(
            safe,
            stage=stage,
            primary_order=primary_order,
            gold=row["gold"],
            base_facts=base_facts,
            base_state_digest=base_state_digest,
        )
        off = conditions["off"]["result"]
        on = conditions["on"]["result"]
        items.append(
            {
                "item_id": _item_identity(row, ordinal),
                "ordinal": ordinal,
                "category": row["category"],
                "evaluator_eligible": True,
                "input_digest_sha256": _sha256(canonical_json_bytes(safe)),
                "choices_digest_sha256": _sha256(
                    canonical_json_bytes(safe["choices"])
                ),
                "primary_execution_order": primary_order,
                "replay_execution_order": list(reversed(primary_order)),
                "conditions": conditions,
                "off_to_on": e4._transition(off, on),
                "replay": replay,
                "gold_absent_from_candidate_arguments": True,
            }
        )
    base_after = base_state_digest()
    scopes_after = _current_scopes(repo_root)
    changed = [
        name
        for name in scopes_before
        if scopes_before[name] != scopes_after[name]
    ]
    if changed:
        raise BenchmarkEvidenceError(
            "bound bytes changed during run: " + ", ".join(changed)
        )
    if base_before != base_after:
        raise BenchmarkEvidenceError("base state changed during paired run")

    metrics = _derive_metrics(items, stage_snapshot)
    if not metrics["paired_development_measurement_gate_passed"]:
        raise BenchmarkEvidenceError("paired development measurement gate failed")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "protocol": _protocol(),
        "claims": {
            "classification": "exposed_mmlu_pro_slice5_development_only",
            "development_only": True,
            "e4_contract_bound": True,
            "paired_measurement_gate_passed": True,
            "e5_claimed": False,
            "independent": False,
            "externally_signed": False,
            "external_authenticity_established": False,
            "benchmark_capability_claimed": False,
            "process_resource_curve_claimed": False,
        },
        "seal": {
            "sealed": True,
            "scope": _SEAL_SCOPE,
            "git_clean_required": False,
            "hidden_holdout_claimed": False,
            "independent_evaluation_claimed": False,
            "external_authenticity_established": False,
            "e5_equivalent": False,
        },
        **scopes_before,
        "e4_prerequisite_contract": _e4_contract(scopes_before["source"]),
        "stage_snapshot": stage_snapshot,
        "selection": _selection(rows, dataset_bytes),
        "metrics": metrics,
        "items": items,
        "integrity": {
            "source_same_before_after": True,
            "candidate_same_before_after": True,
            "dataset_same_before_after": True,
            "stage_same_before_after": True,
            "dataset_matches_pinned_hash": True,
            "same_items_choices_off_on": True,
            "gold_absent_from_candidate_arguments_all": True,
            "semantic_replay_all": metrics["semantic_replay_all"],
            "base_state_immutable": (
                base_before == base_after
                and metrics["base_state_immutable_all"]
            ),
            "off_snapshot_structurally_absent": metrics[
                "off_snapshot_structurally_absent_all"
            ],
            "on_validated_snapshot_bound": metrics[
                "on_validated_snapshot_bound_all"
            ],
            "process_resource_telemetry_omitted": True,
            "network_isolation_enforced": False,
            "shipped_graph_write_authority": False,
            "production_authority": False,
        },
    }
    manifest = _finalize(payload, repo_root=repo_root)
    current_findings = validate_receipt(
        manifest, repo_root=repo_root, require_current=True
    )
    if current_findings:
        raise BenchmarkEvidenceError("; ".join(current_findings))
    return manifest


def read_receipt(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise BenchmarkEvidenceError(
            f"receipt unreadable: {type(exc).__name__}"
        ) from exc
    if len(payload) > _MAX_RECEIPT_BYTES:
        raise BenchmarkEvidenceError("receipt exceeds bounded size")
    manifest = strict_json_bytes(payload, label="science-stage MMLU-Pro receipt")
    if payload != canonical_json_bytes(manifest) + b"\n":
        raise BenchmarkEvidenceError(
            "receipt is not canonical JSON with one trailing newline"
        )
    return manifest


def verify_receipt(
    path: Path,
    *,
    repo_root: Path = REPO,
    require_current: bool = True,
) -> dict[str, Any]:
    try:
        manifest = read_receipt(path)
    except BenchmarkEvidenceError as exc:
        return {
            "valid": False,
            "structure_valid": False,
            "matches_current": False if require_current else None,
            "declared_sealed": False,
            "verified_sealed": False,
            "sealed": False,
            "e5_claimed": False,
            "independent": False,
            "external_authenticity_established": False,
            "checksum_sha256": None,
            "findings": [str(exc)],
        }
    structural = validate_receipt(
        manifest, repo_root=repo_root, require_current=False
    )
    current = (
        validate_receipt(manifest, repo_root=repo_root, require_current=True)
        if require_current
        else structural
    )
    declared = manifest.get("seal", {}).get("sealed") is True
    verified = require_current and declared and not current
    return {
        "valid": not current,
        "structure_valid": not structural,
        "matches_current": (not current if require_current else None),
        "declared_sealed": declared,
        "verified_sealed": verified,
        "sealed": verified,
        "e5_claimed": False,
        "independent": False,
        "external_authenticity_established": False,
        "checksum_sha256": manifest.get("manifest_checksum_sha256"),
        "findings": current,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--output", type=Path)
    mode.add_argument("--verify", type=Path)
    parser.add_argument("--allow-historical", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.verify is not None:
            report = verify_receipt(
                args.verify,
                require_current=not args.allow_historical,
            )
            print(canonical_json_bytes(report).decode("utf-8"))
            return 0 if report["valid"] else 1
        manifest = build_receipt()
        if args.output is None:
            sys.stdout.buffer.write(canonical_json_bytes(manifest) + b"\n")
            return 0
        destination = ensure_safe_report_output(REPO, args.output)
        write_manifest_exclusive(destination, manifest)
        report = verify_receipt(destination)
        print(canonical_json_bytes(report).decode("utf-8"))
        return 0 if report["valid"] else 1
    except BenchmarkEvidenceError as exc:
        print(f"MMLU-Pro paired receipt failed closed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
