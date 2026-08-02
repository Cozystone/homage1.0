"""Paired scalar A-track measurement on the exposed local MMLU-Pro slice.

This receipt fixes the public 40-item development slice, keeps all evaluator
metadata (especially gold and the post-hoc target marker) outside candidate
arguments, and compares a structurally absent scalar stage with the same
validated read-only stage present.  It records the full compiler-to-proof
firing curve and repeats every pair in reverse order.

The seal is deliberately narrow.  It means that current local bytes, a fresh
process replay, the scalar E4 prerequisite, partial-inconsistency controls,
and the deterministic checksum agree.  It is not hidden, independent,
externally authenticated, resource evidence, unbiased generalization
evidence, or E5 evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
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
from packages.reasoning_vm.science_quantity_staging import (  # noqa: E402
    NEUTRALIZATION_FORMULA_ID,
    load_science_quantity_stage,
)
from scripts import deliberator_benchmark_receipt as bench  # noqa: E402
from scripts import science_stage_scalar_e4_receipt as scalar_e4  # noqa: E402


SCHEMA_VERSION = (
    "atanor.science-stage-scalar-mmlu-pro-paired-dev-receipt.v1"
)
EVIDENCE_KIND = (
    "strict_self_measured_exposed_scalar_mmlu_pro_development_receipt"
)
DATASET_PATH = "data/benchmarks/mmlu_pro/slice_5.jsonl"
EXPECTED_DATASET_SHA256 = (
    "a1325092eabfb8dc394ef37f64fe63d79c002678b9d9d3b580605d41690e8b36"
)
EXPECTED_ITEMS = 40
EXPECTED_PER_CATEGORY = 5
CATEGORIES = tuple(sorted(bench._MMLU_CATEGORIES))
TARGET_ORDINAL = 7
TARGET_CATEGORY = "chemistry"
TARGET_EVIDENCE_IDS = (
    "quantity-evidence-005",
    "quantity-evidence-006",
    "quantity-evidence-008",
)

STAGE_ROOT = scalar_e4.STAGE_ROOT
STAGE_PATHS = scalar_e4.STAGE_PATHS
CONTROL_FIXTURE_PATH = scalar_e4.FIXTURE_PATH
CONTROL_FIXTURE_PATHS = (CONTROL_FIXTURE_PATH,)
SOURCE_PATHS = (
    "packages/eval_evidence/__init__.py",
    "packages/eval_evidence/receipt.py",
    "scripts/deliberator_benchmark_receipt.py",
    "scripts/science_stage_scalar_e4_receipt.py",
    "scripts/science_stage_scalar_mmlu_pro_receipt.py",
)
CANDIDATE_PATHS = scalar_e4.CANDIDATE_PATHS
DATASET_PATHS = (DATASET_PATH,)
MAX_RECEIPT_BYTES = 16 * 1024 * 1024

if len(CANDIDATE_PATHS) != 19:
    raise RuntimeError("scalar candidate closure must contain exactly 19 files")

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SCOPE_FIELDS = frozenset({"files", "content_sha256"})
_FILE_FIELDS = frozenset({"path", "bytes", "sha256"})
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
        "control_fixture",
        "stage",
        "candidate_closure_contract",
        "e4_prerequisite_contract",
        "adaptation_disclosure",
        "stage_snapshot",
        "selection",
        "metrics",
        "items",
        "targeted_stage_control",
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
        "post_hoc_targeted_item",
        "input_digest_sha256",
        "choices_digest_sha256",
        "primary_execution_order",
        "replay_execution_order",
        "conditions",
        "off_to_on",
        "replay",
        "gold_absent_from_candidate_arguments",
        "evaluator_metadata_absent_from_candidate_arguments",
    }
)
_TARGET_CONTROL_FIELDS = frozenset(
    {
        "control_id",
        "control_type",
        "target_row_id",
        "target_evidence_id",
        "mutation_recipe_id",
        "original_equivalents_per_mole",
        "mutated_equivalents_per_mole",
        "mutated_stage_content_sha256",
        "loader_accepted",
        "snapshot_returned",
        "expected_rejection_observed",
        "semantic_replay_same",
        "contract_passed",
        "reason",
        "error_kind",
        "observed_loader_error_sha256",
        "control_scope",
        "coordinated_stage_rewrite_resistance_claimed",
    }
)
_SEAL_SCOPE = (
    "current source/candidate/dataset/control-fixture/stage bytes stable "
    "before-after + pinned public dataset + 20/20 counterbalanced reverse "
    "semantic replay + fresh-process full rebuild + current scalar E4 "
    "prerequisite replay + partial-inconsistency target control + stable "
    "receipt-owned evaluator sentinel + deterministic payload + "
    "recomputable checksum"
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        raise BenchmarkEvidenceError("metric denominator must be positive")
    return round(numerator / denominator, 12)


def _sentinel_digest(sentinel: Mapping[str, Any]) -> str:
    return _sha256(canonical_json_bytes(sentinel))


def _checksum(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_checksum_sha256", None)
    return _sha256(canonical_json_bytes(unsigned))


def _scope_paths(scope: Any) -> list[str] | None:
    if not isinstance(scope, Mapping) or frozenset(scope) != _SCOPE_FIELDS:
        return None
    files = scope.get("files")
    if not isinstance(files, list) or not files:
        return None
    paths = []
    for row in files:
        if (
            not isinstance(row, Mapping)
            or frozenset(row) != _FILE_FIELDS
            or not isinstance(row.get("path"), str)
            or type(row.get("bytes")) is not int
            or row["bytes"] < 0
            or not isinstance(row.get("sha256"), str)
            or _SHA256.fullmatch(row["sha256"]) is None
        ):
            return None
        paths.append(row["path"])
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        return None
    if scope.get("content_sha256") != _sha256(canonical_json_bytes(files)):
        return None
    return paths


def _scope_matches_current(scope: Any, repo_root: Path) -> bool:
    paths = _scope_paths(scope)
    if paths is None:
        return False
    try:
        return bind_files(repo_root, paths) == scope
    except (BenchmarkEvidenceError, OSError, ValueError):
        return False


def _scope_record(scope: Mapping[str, Any], path: str) -> Mapping[str, Any]:
    for row in scope.get("files", []):
        if isinstance(row, Mapping) and row.get("path") == path:
            return row
    raise BenchmarkEvidenceError(f"bound scope does not contain {path}")


def _current_scopes(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "source": bind_files(repo_root, SOURCE_PATHS),
        "candidate": bind_files(repo_root, CANDIDATE_PATHS),
        "dataset": bind_files(repo_root, DATASET_PATHS),
        "control_fixture": bind_files(repo_root, CONTROL_FIXTURE_PATHS),
        "stage": bind_files(repo_root, STAGE_PATHS),
    }


def _protocol() -> dict[str, Any]:
    return {
        "benchmark": "MMLU-Pro",
        "slice": "slice_5",
        "classification": (
            "exposed_post_hoc_targeted_scalar_development_measurement_not_e5"
        ),
        "fixed_denominator": EXPECTED_ITEMS,
        "category_census": "8 categories x 5 items",
        "candidate_payload": (
            "question + choices only; item ID, ordinal, category, gold, "
            "target marker, and expected outcomes remain evaluator-side"
        ),
        "conditions": {
            "off": (
                "same scalar compiler with ScienceQuantityStageSnapshot "
                "structurally absent; no fallback or guessing"
            ),
            "on": (
                "same scalar compiler and inputs with one fail-closed "
                "validated read-only ScienceQuantityStageSnapshot"
            ),
        },
        "counterbalance": (
            "even ordinals OFF-then-ON; odd ordinals ON-then-OFF "
            "(20 items in each primary order)"
        ),
        "replay": "repeat both conditions in reverse primary order",
        "strict_scoring": "errors and abstentions are incorrect on all 40 items",
        "statistics": (
            "overall and per-category compiler/raw/formula/resolver/proof/"
            "accepted/grounded firing and strict accuracy; exact paired "
            "McNemar and exact two-sided binomial intervals"
        ),
        "measurement_protocol_gate_meaning": (
            "complete fixed-denominator paired execution, reverse replay, "
            "scope binding, and disclosed target-proof observation only; "
            "there is no minimum accuracy or lift threshold and no capability "
            "promotion"
        ),
        "prerequisite": (
            "reexecute the complete current scalar E4 receipt in its fresh "
            "process, bind its exact checksum/scopes/gates, and retain its "
            "declared limits"
        ),
        "current_verification": (
            "start a fresh Python process, rebuild the complete deterministic "
            "public payload and all semantic replays, compare exactly, then "
            "rebind scopes after replay"
        ),
        "fresh_process_current_replay_enforced": True,
        "staging_control_limit": (
            "stage controls rechecksum a modified data file and manifest "
            "while leaving an evidence, dimension, or policy corroborator "
            "inconsistent; only partial-inconsistency rejection is tested, "
            "not resistance to a coordinated stage rewrite"
        ),
        "evaluator_sentinel_limit": (
            "the integrity callback observes only a receipt-owned empty "
            "sentinel that the candidate cannot access; shipped graph "
            "immutability is not observed"
        ),
        "limitations": [
            "the public development slice was exposed before profile freeze",
            "the scalar profile and stage target were selected after item inspection",
            "the observed target is a post-selection confirmation, not an "
            "unbiased generalization estimate",
            "the evaluator is local, unsigned, and not independent",
            "declared source coordinates do not establish external authenticity",
            "zero wrong-fire at low firing count is weak and potentially vacuous",
            "process resource telemetry is omitted and no resource curve is claimed",
            "hidden holdout, coordinated stage rewrite resistance, benchmark-wide "
            "capability, and E5 are not claimed",
        ],
        "separate_process_isolation_enforced": False,
        "network_isolation_enforced": False,
        "process_resource_telemetry_omitted": True,
    }


def _adaptation_disclosure() -> dict[str, Any]:
    core = {
        "classification": "post_hoc_exposed_development_target",
        "public_slice_exposed_before_profile_freeze": True,
        "profile_and_stage_selected_after_public_item_inspection": True,
        "targeted_item_zero_based_ordinal": TARGET_ORDINAL,
        "targeted_category": TARGET_CATEGORY,
        "targeted_stage_rows": [
            {
                "kind": "species",
                "alias": "H3PO4",
                "row_id": "quantity-species-row-005",
                "evidence_id": "quantity-evidence-005",
            },
            {
                "kind": "species",
                "alias": "KOH",
                "row_id": "quantity-species-row-006",
                "evidence_id": "quantity-evidence-006",
            },
            {
                "kind": "formula",
                "rule_id": NEUTRALIZATION_FORMULA_ID,
                "evidence_id": "quantity-evidence-008",
            },
        ],
        "pre_targeting_scalar_public_receipt_exists": False,
        "selection_chronology_basis": (
            "declared project chronology, not independently authenticated"
        ),
        "git_row_addition_timing_treated_as_preregistration": False,
        "measurement_role": (
            "post_selection_confirmation_not_unbiased_generalization"
        ),
        "hiddenness_claimed": False,
        "independent_evaluation_claimed": False,
        "external_authenticity_established": False,
        "unbiased_generalization_claimed": False,
        "e5_claimed": False,
    }
    return {
        **core,
        "disclosure_digest_sha256": _sha256(canonical_json_bytes(core)),
    }


def _claims(
    *,
    measurement_protocol_gate: bool,
    prerequisite_gate: bool,
    targeted_control_gate: bool,
) -> dict[str, Any]:
    return {
        "classification": (
            "post_hoc_exposed_scalar_mmlu_pro_development_confirmation"
        ),
        "development_only": True,
        "e4_prerequisite_reexecuted": True,
        "e4_prerequisite_gate_passed": prerequisite_gate,
        "paired_measurement_protocol_gate_passed": (
            measurement_protocol_gate
        ),
        "post_hoc_targeting_disclosed": True,
        "targeted_partial_inconsistency_control_passed": (
            targeted_control_gate
        ),
        "e5_claimed": False,
        "independent": False,
        "externally_signed": False,
        "hidden_holdout_claimed": False,
        "external_authenticity_established": False,
        "unbiased_generalization_claimed": False,
        "coordinated_stage_rewrite_resistance_claimed": False,
        "shipped_graph_immutability_claimed": False,
        "benchmark_capability_claimed": False,
        "process_resource_curve_claimed": False,
    }


def _seal() -> dict[str, Any]:
    return {
        "sealed": True,
        "scope": _SEAL_SCOPE,
        "git_clean_required": False,
        "hidden_holdout_claimed": False,
        "independent_evaluation_claimed": False,
        "authenticity_established": False,
        "unbiased_generalization_established": False,
        "coordinated_stage_rewrite_resistance_claimed": False,
        "shipped_graph_immutability_claimed": False,
        "resource_curve_established": False,
        "e5_equivalent": False,
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


def _candidate_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return scalar_e4._candidate_payload(
        {
            "question": row["q"],
            "choices": row["choices"],
        }
    )


def _selection(
    rows: Sequence[Mapping[str, Any]], dataset_bytes: bytes
) -> dict[str, Any]:
    item_ids = [
        _item_identity(row, ordinal) for ordinal, row in enumerate(rows)
    ]
    input_pairs = [
        {
            "item_id": item_ids[ordinal],
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
        "item_ids": item_ids,
        "item_ids_sha256": _sha256(canonical_json_bytes(item_ids)),
        "input_choice_pairs_sha256": _sha256(
            canonical_json_bytes(input_pairs)
        ),
        "targeted_item_zero_based_ordinal": TARGET_ORDINAL,
        "targeted_item_id": item_ids[TARGET_ORDINAL],
        "targeted_category": TARGET_CATEGORY,
        "gold_positions_evaluator_side_only": dict(
            sorted(Counter(row["gold"] for row in rows).items())
        ),
    }


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
    rows = [row["conditions"][condition] for row in items]
    n = len(rows)
    if n <= 0:
        raise BenchmarkEvidenceError("empty scalar public denominator")
    counts = {
        "input_valid": sum(
            int(row["compiler"]["input_valid"] is True) for row in rows
        ),
        "compiler_reach": sum(
            int(row["compiler"]["compiled"] is True) for row in rows
        ),
        "raw_fired": sum(int(row["raw_fired"] is True) for row in rows),
        "formula_fired": sum(
            int(row["formula_fired"] is True) for row in rows
        ),
        "resolver_grounded": sum(
            int(row["resolver_grounded"] is True) for row in rows
        ),
        "proof_replayed": sum(
            int(row["proof_replayed"] is True) for row in rows
        ),
        "accepted_fired": sum(
            int(row["accepted_fire"] is True) for row in rows
        ),
        "grounded": sum(int(row["grounded"] is True) for row in rows),
        "correct": sum(int(row["correct"] is True) for row in rows),
        "wrong_fire": sum(int(row["wrong_fire"] is True) for row in rows),
        "abstain": sum(int(row["status"] == "abstain") for row in rows),
        "error": sum(int(row["status"] == "error") for row in rows),
        "provenance_bound_fires": sum(
            int(row["provenance_bound"] is True) for row in rows
        ),
        "grounded_leaf_count_total": sum(
            int(row["grounded_leaf_count"]) for row in rows
        ),
        "grounded_stage_leaf_count_total": sum(
            int(row["grounded_stage_leaf_count"]) for row in rows
        ),
        "evidence_id_count_total": sum(
            len(row["evidence_ids"]) for row in rows
        ),
    }
    return {
        "n": n,
        **counts,
        "input_valid_rate": _ratio(counts["input_valid"], n),
        "compiler_reach_rate": _ratio(counts["compiler_reach"], n),
        "raw_firing_rate": _ratio(counts["raw_fired"], n),
        "formula_firing_rate": _ratio(counts["formula_fired"], n),
        "resolver_grounding_rate": _ratio(counts["resolver_grounded"], n),
        "proof_replay_rate": _ratio(counts["proof_replayed"], n),
        "accepted_firing_rate": _ratio(counts["accepted_fired"], n),
        "grounded_coverage": _ratio(counts["grounded"], n),
        "strict_accuracy": _ratio(counts["correct"], n),
        "strict_accuracy_exact_binomial_95_ci": _exact_binomial_ci95(
            counts["correct"], n
        ),
        "wrong_fire_rate": _ratio(counts["wrong_fire"], n),
        "abstention_rate": _ratio(counts["abstain"], n),
        "answered_accuracy": (
            None
            if counts["accepted_fired"] == 0
            else _ratio(counts["correct"], counts["accepted_fired"])
        ),
    }


def _paired_metrics(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    off = _condition_metrics(items, "off")
    on = _condition_metrics(items, "on")
    off_only = sum(
        int(
            row["conditions"]["off"]["correct"] is True
            and row["conditions"]["on"]["correct"] is not True
        )
        for row in items
    )
    on_only = sum(
        int(
            row["conditions"]["off"]["correct"] is not True
            and row["conditions"]["on"]["correct"] is True
        )
        for row in items
    )
    transitions = Counter(row["off_to_on"]["label"] for row in items)
    return {
        "strict_accuracy_delta": round(
            on["strict_accuracy"] - off["strict_accuracy"], 12
        ),
        "compiler_reach_rate_delta": round(
            on["compiler_reach_rate"] - off["compiler_reach_rate"], 12
        ),
        "raw_firing_rate_delta": round(
            on["raw_firing_rate"] - off["raw_firing_rate"], 12
        ),
        "formula_firing_rate_delta": round(
            on["formula_firing_rate"] - off["formula_firing_rate"], 12
        ),
        "resolver_grounding_rate_delta": round(
            on["resolver_grounding_rate"] - off["resolver_grounding_rate"],
            12,
        ),
        "proof_replay_rate_delta": round(
            on["proof_replay_rate"] - off["proof_replay_rate"], 12
        ),
        "accepted_firing_rate_delta": round(
            on["accepted_firing_rate"] - off["accepted_firing_rate"], 12
        ),
        "grounded_coverage_delta": round(
            on["grounded_coverage"] - off["grounded_coverage"], 12
        ),
        "wrong_fire_rate_delta": round(
            on["wrong_fire_rate"] - off["wrong_fire_rate"], 12
        ),
        "transition_counts": dict(sorted(transitions.items())),
        "off_correct_on_incorrect": off_only,
        "off_incorrect_on_correct": on_only,
        "discordant_pairs": off_only + on_only,
        "exact_two_sided_mcnemar_p": _exact_mcnemar_p(
            off_only, on_only
        ),
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
        row["replay"].get("input_fingerprint_same") is True
        and row["replay"].get("goal_digest_same") is True
        and row["replay"].get("off_semantic_outcome_same") is True
        and row["replay"].get("on_semantic_outcome_same") is True
        for row in items
    )
    sentinel_unchanged = all(
        row["conditions"][condition]["evaluator_sentinel_unchanged"] is True
        for row in items
        for condition in ("off", "on")
    )
    off_absent = all(
        row["conditions"]["off"]["stage_structurally_absent"] is True
        and row["conditions"]["off"]["stage_digest_sha256"] is None
        and row["conditions"]["off"]["stage_snapshot_bound_bytes"] == 0
        and row["conditions"]["off"]["stage_hit_count"] == 0
        and row["conditions"]["off"]["evidence_ids"] == []
        for row in items
    )
    on_bound = all(
        row["conditions"]["on"]["stage_structurally_absent"] is False
        and row["conditions"]["on"]["stage_digest_sha256"]
        == stage_snapshot["stage_digest_sha256"]
        and row["conditions"]["on"]["stage_snapshot_bound_bytes"]
        == stage_snapshot["bound_bytes"]
        and row["conditions"]["on"]["stage_bytes_read"] == 0
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
    target = items[TARGET_ORDINAL]
    target_proof_matches = (
        target["post_hoc_targeted_item"] is True
        and target["category"] == TARGET_CATEGORY
        and tuple(target["conditions"]["on"]["evidence_ids"])
        == TARGET_EVIDENCE_IDS
        and target["conditions"]["on"]["grounded_stage_leaf_count"] == 3
        and target["conditions"]["on"]["proof_replayed"] is True
        and target["conditions"]["on"]["accepted_fire"] is True
    )
    measurement_protocol_gate = (
        len(items) == EXPECTED_ITEMS
        and category_census
        == {category: EXPECTED_PER_CATEGORY for category in CATEGORIES}
        and dict(order_counts)
        == {"off_then_on": 20, "on_then_off": 20}
        and replay_all
        and sentinel_unchanged
        and off_absent
        and on_bound
        and all(
            row["gold_absent_from_candidate_arguments"] is True
            and row["evaluator_metadata_absent_from_candidate_arguments"]
            is True
            for row in items
        )
        and sum(int(row["post_hoc_targeted_item"]) for row in items) == 1
        and target_proof_matches
        and overall["off"]["error"] == 0
        and overall["on"]["error"] == 0
    )
    return {
        "denominator": len(items),
        "category_census": category_census,
        "primary_order_counts": dict(sorted(order_counts.items())),
        "overall": overall,
        "categories": categories,
        "targeted_public_observation": {
            "zero_based_ordinal": TARGET_ORDINAL,
            "category": TARGET_CATEGORY,
            "off_status": target["conditions"]["off"]["status"],
            "on_status": target["conditions"]["on"]["status"],
            "on_evidence_ids": list(
                target["conditions"]["on"]["evidence_ids"]
            ),
            "proof_matches_disclosed_stage_rows": target_proof_matches,
            "post_hoc_targeted": True,
            "unbiased_generalization_observation": False,
        },
        "semantic_replay_all": replay_all,
        "evaluator_sentinel_unchanged_all": sentinel_unchanged,
        "off_snapshot_structurally_absent_all": off_absent,
        "on_validated_snapshot_bound_all": on_bound,
        "paired_development_measurement_protocol_gate_passed": (
            measurement_protocol_gate
        ),
    }


def _stage_record(snapshot: Any) -> dict[str, Any]:
    formula = snapshot.formula_for(NEUTRALIZATION_FORMULA_ID)
    if formula is None:
        raise BenchmarkEvidenceError("validated scalar formula missing")
    return {
        "stage_id": snapshot.stage_id,
        "stage_digest_sha256": snapshot.stage_digest_sha256,
        "manifest_checksum_sha256": snapshot.manifest_checksum_sha256,
        "bound_bytes": snapshot.bound_bytes,
        "species_count": len(snapshot.species),
        "formula_count": len(snapshot.formulas),
        "formula_expression_digest_sha256": (
            formula.expression_digest_sha256
        ),
        "external_authenticity_established": False,
    }


def _candidate_closure_contract(
    candidate_scope: Mapping[str, Any],
    e4_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    if e4_receipt.get("candidate") != candidate_scope:
        raise BenchmarkEvidenceError(
            "public candidate scope differs from fresh scalar prerequisite"
        )
    core = {
        "observation_method": (
            "exact project-local Python closure bound by the current scalar "
            "E4 fresh-process worker"
        ),
        "fresh_process_prerequisite_replayed": True,
        "expected_path_count": 19,
        "actual_path_count": len(CANDIDATE_PATHS),
        "paths": list(CANDIDATE_PATHS),
        "paths_sha256": _sha256(
            canonical_json_bytes(list(CANDIDATE_PATHS))
        ),
        "candidate_content_sha256": candidate_scope["content_sha256"],
        "exact_closure_bound": True,
    }
    return {
        **core,
        "contract_digest_sha256": _sha256(canonical_json_bytes(core)),
    }


def _e4_prerequisite_contract(
    *,
    source_scope: Mapping[str, Any],
    candidate_scope: Mapping[str, Any],
    control_fixture_scope: Mapping[str, Any],
    stage_scope: Mapping[str, Any],
    e4_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    findings = scalar_e4.validate_receipt(e4_receipt)
    if findings:
        raise BenchmarkEvidenceError(
            "current scalar E4 prerequisite invalid: " + "; ".join(findings)
        )
    metrics = e4_receipt.get("metrics")
    claims = e4_receipt.get("claims")
    seal = e4_receipt.get("seal")
    integrity = e4_receipt.get("integrity")
    if not all(
        isinstance(value, Mapping)
        for value in (metrics, claims, seal, integrity)
    ):
        raise BenchmarkEvidenceError("scalar E4 prerequisite fields missing")
    assert isinstance(metrics, Mapping)
    assert isinstance(claims, Mapping)
    assert isinstance(seal, Mapping)
    assert isinstance(integrity, Mapping)
    controls = metrics.get("controls")
    if not isinstance(controls, Mapping):
        raise BenchmarkEvidenceError("scalar E4 prerequisite controls missing")
    required = (
        metrics.get("e4_development_gate_passed") is True
        and controls.get("candidate_control_count")
        == scalar_e4.EXPECTED_CONTROLS
        and controls.get("candidate_contract_passed")
        == scalar_e4.EXPECTED_CONTROLS
        and controls.get("candidate_controls_all_passed") is True
        and controls.get("staging_control_count")
        == scalar_e4.EXPECTED_STAGING_CONTROLS
        and controls.get("staging_rejections_observed")
        == scalar_e4.EXPECTED_STAGING_CONTROLS
        and controls.get("staging_controls_all_passed") is True
        and claims.get("coordinated_stage_rewrite_resistance_claimed")
        is False
        and claims.get("shipped_graph_immutability_claimed") is False
        and seal.get("coordinated_stage_rewrite_resistance_claimed")
        is False
        and seal.get("shipped_graph_immutability_claimed") is False
        and integrity.get("coordinated_stage_rewrite_resistance_claimed")
        is False
        and integrity.get("shipped_graph_immutability_observed") is False
        and integrity.get("fresh_process_current_replay_enforced") is True
        and e4_receipt.get("candidate") == candidate_scope
        and e4_receipt.get("dataset") == control_fixture_scope
        and e4_receipt.get("stage") == stage_scope
    )
    if not required:
        raise BenchmarkEvidenceError(
            "scalar E4 prerequisite gate or scope mismatch"
        )
    core = {
        "source_path": "scripts/science_stage_scalar_e4_receipt.py",
        "source_sha256": _scope_record(
            source_scope, "scripts/science_stage_scalar_e4_receipt.py"
        )["sha256"],
        "schema_version": scalar_e4.SCHEMA_VERSION,
        "evidence_kind": scalar_e4.EVIDENCE_KIND,
        "current_receipt_checksum_sha256": e4_receipt[
            "manifest_checksum_sha256"
        ],
        "current_reexecuted": True,
        "fresh_process_current_replay_enforced": True,
        "e4_development_gate_passed": True,
        "candidate_control_count": scalar_e4.EXPECTED_CONTROLS,
        "candidate_controls_passed": scalar_e4.EXPECTED_CONTROLS,
        "staging_control_count": scalar_e4.EXPECTED_STAGING_CONTROLS,
        "staging_controls_passed": scalar_e4.EXPECTED_STAGING_CONTROLS,
        "candidate_content_sha256": candidate_scope["content_sha256"],
        "control_fixture_content_sha256": control_fixture_scope[
            "content_sha256"
        ],
        "stage_content_sha256": stage_scope["content_sha256"],
        "stage_controls_scope": (
            "manifest-rechecksummed partial-inconsistency rejection only"
        ),
        "coordinated_stage_rewrite_resistance_claimed": False,
        "shipped_graph_immutability_claimed": False,
        "hidden_holdout_claimed": False,
        "independent_evaluation_claimed": False,
        "external_authenticity_established": False,
        "resource_curve_established": False,
        "e5_claimed": False,
    }
    return {
        **core,
        "contract_digest_sha256": _sha256(canonical_json_bytes(core)),
    }


def _stage_tree_digest(stage_root: Path) -> str:
    rows = []
    for name in (
        "evidence.jsonl",
        "formulas.jsonl",
        "manifest.json",
        "species.jsonl",
    ):
        payload = (stage_root / name).read_bytes()
        rows.append(
            {"path": name, "bytes": len(payload), "sha256": _sha256(payload)}
        )
    return _sha256(canonical_json_bytes(rows))


def _run_targeted_stage_control(repo_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="atanor-scalar-public-target-control-"
    ) as temporary:
        stage_root = Path(temporary) / "stage"
        shutil.copytree(repo_root / STAGE_ROOT, stage_root)
        species_path = stage_root / "species.jsonl"
        rows = [
            strict_json_bytes(
                line.encode("utf-8"),
                label=f"targeted species row {index}",
            )
            for index, line in enumerate(
                species_path.read_text(encoding="utf-8").splitlines()
            )
        ]
        targets = [
            row
            for row in rows
            if row.get("row_id") == "quantity-species-row-005"
        ]
        if len(targets) != 1:
            raise BenchmarkEvidenceError("targeted H3PO4 row missing")
        original = targets[0].get("equivalents_per_mole")
        if original != 3 or targets[0].get("evidence_id") != (
            "quantity-evidence-005"
        ):
            raise BenchmarkEvidenceError("targeted H3PO4 row contract changed")
        targets[0]["equivalents_per_mole"] = 2
        species_path.write_bytes(scalar_e4._canonical_jsonl(rows))
        scalar_e4._refresh_stage_manifest(stage_root, species_path.name)
        content_digest = _stage_tree_digest(stage_root)
        primary = scalar_e4._observe_stage_load(stage_root)
        replay = scalar_e4._observe_stage_load(stage_root)
    replay_same = primary == replay
    expected_rejection = (
        primary["loader_accepted"] is False
        and primary["snapshot_returned"] is False
        and primary["error_kind"] == "ScienceQuantityStageError"
    )
    return {
        "control_id": "scalar-public-target-h3po4-claim-control",
        "control_type": "targeted_species_claim",
        "target_row_id": "quantity-species-row-005",
        "target_evidence_id": "quantity-evidence-005",
        "mutation_recipe_id": (
            "manifest_rechecksummed_h3po4_equivalents_without_evidence_rebind_v1"
        ),
        "original_equivalents_per_mole": original,
        "mutated_equivalents_per_mole": 2,
        "mutated_stage_content_sha256": content_digest,
        **primary,
        "expected_rejection_observed": expected_rejection,
        "semantic_replay_same": replay_same,
        "contract_passed": expected_rejection and replay_same,
        "control_scope": (
            "partial-inconsistency only: species and manifest changed while "
            "evidence claim remained unchanged"
        ),
        "coordinated_stage_rewrite_resistance_claimed": False,
    }


def _validate_item_shapes(items: Any, findings: list[str]) -> None:
    if not isinstance(items, list) or len(items) != EXPECTED_ITEMS:
        findings.append("item denominator mismatch")
        return
    for index, row in enumerate(items):
        if not isinstance(row, Mapping) or frozenset(row) != _ITEM_FIELDS:
            findings.append(f"items[{index}] fields mismatch")
            continue
        if (
            row.get("ordinal") != index
            or row.get("category") not in CATEGORIES
            or row.get("evaluator_eligible") is not True
            or row.get("post_hoc_targeted_item")
            is not (index == TARGET_ORDINAL)
            or row.get("primary_execution_order")
            != (["off", "on"] if index % 2 == 0 else ["on", "off"])
            or row.get("replay_execution_order")
            != list(reversed(row.get("primary_execution_order", [])))
            or row.get("gold_absent_from_candidate_arguments") is not True
            or row.get("evaluator_metadata_absent_from_candidate_arguments")
            is not True
        ):
            findings.append(f"items[{index}] evaluator contract mismatch")
        for digest_field in (
            "item_id",
            "input_digest_sha256",
            "choices_digest_sha256",
        ):
            digest = row.get(digest_field)
            if (
                not isinstance(digest, str)
                or _SHA256.fullmatch(digest) is None
            ):
                findings.append(
                    f"items[{index}].{digest_field} is not sha256"
                )
        conditions = row.get("conditions")
        if (
            not isinstance(conditions, Mapping)
            or frozenset(conditions) != {"off", "on"}
        ):
            findings.append(f"items[{index}] conditions mismatch")
            continue
        for condition in ("off", "on"):
            record = conditions.get(condition)
            if (
                not isinstance(record, Mapping)
                or frozenset(record) != scalar_e4._CONDITION_FIELDS
            ):
                findings.append(
                    f"items[{index}].conditions.{condition} fields mismatch"
                )
                continue
            compiler = record.get("compiler")
            if (
                not isinstance(compiler, Mapping)
                or frozenset(compiler) != scalar_e4._COMPILER_FIELDS
            ):
                findings.append(
                    f"items[{index}].conditions.{condition}.compiler "
                    "fields mismatch"
                )
        off_to_on = row.get("off_to_on")
        if (
            isinstance(conditions.get("off"), Mapping)
            and isinstance(conditions.get("on"), Mapping)
            and (
                not isinstance(off_to_on, Mapping)
                or frozenset(off_to_on) != scalar_e4._TRANSITION_FIELDS
                or off_to_on
                != scalar_e4._transition(
                    conditions["off"], conditions["on"]
                )
            )
        ):
            findings.append(f"items[{index}] transition does not derive")
        replay = row.get("replay")
        if (
            not isinstance(replay, Mapping)
            or frozenset(replay) != scalar_e4._REPLAY_FIELDS
        ):
            findings.append(f"items[{index}] replay fields mismatch")
        elif isinstance(conditions.get("off"), Mapping) and isinstance(
            conditions.get("on"), Mapping
        ):
            for field in (
                "input_fingerprint_same",
                "goal_digest_same",
                "off_semantic_outcome_same",
                "on_semantic_outcome_same",
            ):
                if replay.get(field) is not True:
                    findings.append(
                        f"items[{index}].replay.{field} must be true"
                    )
            if (
                replay.get("off_replay_digest_sha256")
                != conditions["off"].get(
                    "semantic_outcome_digest_sha256"
                )
                or replay.get("on_replay_digest_sha256")
                != conditions["on"].get(
                    "semantic_outcome_digest_sha256"
                )
            ):
                findings.append(
                    f"items[{index}] replay digests do not derive"
                )


def _validate_candidate_closure_contract(
    value: Any,
    candidate_scope: Any,
    findings: list[str],
) -> None:
    if not isinstance(value, Mapping) or not isinstance(
        candidate_scope, Mapping
    ):
        findings.append("candidate closure contract missing")
        return
    core = dict(value)
    digest = core.pop("contract_digest_sha256", None)
    required = (
        core.get("fresh_process_prerequisite_replayed") is True
        and core.get("expected_path_count") == 19
        and core.get("actual_path_count") == 19
        and core.get("paths") == list(CANDIDATE_PATHS)
        and core.get("paths_sha256")
        == _sha256(canonical_json_bytes(list(CANDIDATE_PATHS)))
        and core.get("candidate_content_sha256")
        == candidate_scope.get("content_sha256")
        and core.get("exact_closure_bound") is True
        and digest == _sha256(canonical_json_bytes(core))
    )
    if not required:
        findings.append("candidate closure contract invalid")


def _validate_e4_contract(
    value: Any,
    *,
    source_scope: Any,
    candidate_scope: Any,
    control_fixture_scope: Any,
    stage_scope: Any,
    findings: list[str],
) -> None:
    if not all(
        isinstance(row, Mapping)
        for row in (
            value,
            source_scope,
            candidate_scope,
            control_fixture_scope,
            stage_scope,
        )
    ):
        findings.append("E4 prerequisite contract or scope missing")
        return
    assert isinstance(value, Mapping)
    core = dict(value)
    digest = core.pop("contract_digest_sha256", None)
    try:
        source_sha = _scope_record(
            source_scope, "scripts/science_stage_scalar_e4_receipt.py"
        )["sha256"]
    except (BenchmarkEvidenceError, KeyError, TypeError):
        source_sha = None
    required_false = (
        "coordinated_stage_rewrite_resistance_claimed",
        "shipped_graph_immutability_claimed",
        "hidden_holdout_claimed",
        "independent_evaluation_claimed",
        "external_authenticity_established",
        "resource_curve_established",
        "e5_claimed",
    )
    required = (
        core.get("source_path")
        == "scripts/science_stage_scalar_e4_receipt.py"
        and core.get("source_sha256") == source_sha
        and core.get("schema_version") == scalar_e4.SCHEMA_VERSION
        and core.get("evidence_kind") == scalar_e4.EVIDENCE_KIND
        and isinstance(core.get("current_receipt_checksum_sha256"), str)
        and _SHA256.fullmatch(
            core.get("current_receipt_checksum_sha256", "")
        )
        is not None
        and core.get("current_reexecuted") is True
        and core.get("fresh_process_current_replay_enforced") is True
        and core.get("e4_development_gate_passed") is True
        and core.get("candidate_control_count")
        == scalar_e4.EXPECTED_CONTROLS
        and core.get("candidate_controls_passed")
        == scalar_e4.EXPECTED_CONTROLS
        and core.get("staging_control_count")
        == scalar_e4.EXPECTED_STAGING_CONTROLS
        and core.get("staging_controls_passed")
        == scalar_e4.EXPECTED_STAGING_CONTROLS
        and core.get("candidate_content_sha256")
        == candidate_scope.get("content_sha256")
        and core.get("control_fixture_content_sha256")
        == control_fixture_scope.get("content_sha256")
        and core.get("stage_content_sha256")
        == stage_scope.get("content_sha256")
        and core.get("stage_controls_scope")
        == "manifest-rechecksummed partial-inconsistency rejection only"
        and all(core.get(field) is False for field in required_false)
        and digest == _sha256(canonical_json_bytes(core))
    )
    if not required:
        findings.append("E4 prerequisite contract invalid or overstated")


def validate_receipt(manifest: Mapping[str, Any]) -> list[str]:
    """Validate exact structure and every result derivable in-receipt."""

    findings: list[str] = []
    try:
        if not isinstance(manifest, Mapping) or frozenset(manifest) != (
            _ROOT_FIELDS
        ):
            return ["receipt fields mismatch"]
        if manifest.get("schema_version") != SCHEMA_VERSION:
            findings.append("schema_version mismatch")
        if manifest.get("evidence_kind") != EVIDENCE_KIND:
            findings.append("evidence_kind mismatch")
        if manifest.get("protocol") != _protocol():
            findings.append("protocol mismatch")
        if manifest.get("adaptation_disclosure") != _adaptation_disclosure():
            findings.append("adaptation disclosure mismatch")
        for name, expected_paths in (
            ("source", SOURCE_PATHS),
            ("candidate", CANDIDATE_PATHS),
            ("dataset", DATASET_PATHS),
            ("control_fixture", CONTROL_FIXTURE_PATHS),
            ("stage", STAGE_PATHS),
        ):
            if _scope_paths(manifest.get(name)) != sorted(expected_paths):
                findings.append(f"{name} scope paths mismatch")
        _validate_candidate_closure_contract(
            manifest.get("candidate_closure_contract"),
            manifest.get("candidate"),
            findings,
        )
        _validate_e4_contract(
            manifest.get("e4_prerequisite_contract"),
            source_scope=manifest.get("source"),
            candidate_scope=manifest.get("candidate"),
            control_fixture_scope=manifest.get("control_fixture"),
            stage_scope=manifest.get("stage"),
            findings=findings,
        )
        items = manifest.get("items")
        _validate_item_shapes(items, findings)
        stage_snapshot = manifest.get("stage_snapshot")
        if (
            not isinstance(stage_snapshot, Mapping)
            or stage_snapshot.get("species_count") != 7
            or stage_snapshot.get("formula_count") != 1
            or stage_snapshot.get("external_authenticity_established")
            is not False
        ):
            findings.append("stage snapshot descriptor invalid")
        selection = manifest.get("selection")
        if not isinstance(selection, Mapping) or not isinstance(items, list):
            findings.append("selection missing")
        else:
            item_ids = [row.get("item_id") for row in items]
            category_counts = dict(
                sorted(Counter(row.get("category") for row in items).items())
            )
            if (
                selection.get("evaluator_owned_fixed_denominator") is not True
                or selection.get("dataset_path") != DATASET_PATH
                or selection.get("expected_dataset_sha256")
                != EXPECTED_DATASET_SHA256
                or selection.get("actual_dataset_sha256")
                != EXPECTED_DATASET_SHA256
                or selection.get("expected_item_count") != EXPECTED_ITEMS
                or selection.get("category_counts") != category_counts
                or selection.get("item_ids") != item_ids
                or selection.get("item_ids_sha256")
                != _sha256(canonical_json_bytes(item_ids))
                or selection.get("targeted_item_zero_based_ordinal")
                != TARGET_ORDINAL
                or selection.get("targeted_item_id")
                != item_ids[TARGET_ORDINAL]
                or selection.get("targeted_category") != TARGET_CATEGORY
            ):
                findings.append("selection does not derive")
        metrics = manifest.get("metrics")
        if (
            not findings
            and isinstance(items, list)
            and isinstance(stage_snapshot, Mapping)
        ):
            expected_metrics = _derive_metrics(items, stage_snapshot)
            if metrics != expected_metrics:
                findings.append("metrics do not derive from outcomes")
        measurement_protocol_gate = (
            metrics.get(
                "paired_development_measurement_protocol_gate_passed"
            )
            if isinstance(metrics, Mapping)
            else False
        )
        e4_contract = manifest.get("e4_prerequisite_contract")
        prerequisite_gate = (
            isinstance(e4_contract, Mapping)
            and e4_contract.get("current_reexecuted") is True
            and e4_contract.get("e4_development_gate_passed") is True
        )
        target_control = manifest.get("targeted_stage_control")
        if (
            not isinstance(target_control, Mapping)
            or frozenset(target_control) != _TARGET_CONTROL_FIELDS
            or target_control.get("control_id")
            != "scalar-public-target-h3po4-claim-control"
            or target_control.get("target_row_id")
            != "quantity-species-row-005"
            or target_control.get("target_evidence_id")
            != "quantity-evidence-005"
            or target_control.get("original_equivalents_per_mole") != 3
            or target_control.get("mutated_equivalents_per_mole") != 2
            or target_control.get("loader_accepted") is not False
            or target_control.get("snapshot_returned") is not False
            or target_control.get("expected_rejection_observed") is not True
            or target_control.get("semantic_replay_same") is not True
            or target_control.get("contract_passed") is not True
            or target_control.get("control_scope")
            != (
                "partial-inconsistency only: species and manifest changed "
                "while evidence claim remained unchanged"
            )
            or target_control.get(
                "coordinated_stage_rewrite_resistance_claimed"
            )
            is not False
        ):
            findings.append("targeted stage control invalid or overstated")
        targeted_control_gate = (
            isinstance(target_control, Mapping)
            and target_control.get("contract_passed") is True
        )
        if manifest.get("claims") != _claims(
            measurement_protocol_gate=measurement_protocol_gate is True,
            prerequisite_gate=prerequisite_gate,
            targeted_control_gate=targeted_control_gate,
        ):
            findings.append("claims invalid or overstate authority")
        if manifest.get("seal") != _seal():
            findings.append("seal meaning invalid")
        integrity = manifest.get("integrity")
        required_true = {
            "source_same_before_after",
            "candidate_same_before_after",
            "dataset_same_before_after",
            "control_fixture_same_before_after",
            "stage_same_before_after",
            "dataset_matches_pinned_hash",
            "same_items_choices_off_on",
            "gold_absent_from_candidate_arguments_all",
            "evaluator_metadata_absent_from_candidate_arguments_all",
            "semantic_replay_all",
            "evaluator_sentinel_unchanged",
            "off_snapshot_structurally_absent_all",
            "on_validated_snapshot_bound_all",
            "fresh_process_current_replay_enforced",
            "e4_prerequisite_current_reexecuted",
            "e4_prerequisite_gate_passed",
            "candidate_closure_exact_19_files",
            "post_hoc_targeting_disclosed",
            "target_proof_matches_disclosed_stage_rows",
            "targeted_partial_inconsistency_control_passed",
            "process_resource_telemetry_omitted",
        }
        required_false = {
            "network_isolation_enforced",
            "shipped_graph_write_authority",
            "production_authority",
            "hidden_holdout_claimed",
            "independent_evaluation_claimed",
            "external_authenticity_established",
            "unbiased_generalization_established",
            "coordinated_stage_rewrite_resistance_claimed",
            "shipped_graph_immutability_claimed",
            "resource_curve_established",
            "e5_equivalent",
        }
        if not isinstance(integrity, Mapping):
            findings.append("integrity missing")
        else:
            for field in required_true:
                if integrity.get(field) is not True:
                    findings.append(f"integrity.{field} must be true")
            for field in required_false:
                if integrity.get(field) is not False:
                    findings.append(f"integrity.{field} must be false")
            if integrity.get("evaluator_sentinel_digest_before") != (
                integrity.get("evaluator_sentinel_digest_after")
            ):
                findings.append("evaluator sentinel digest mismatch")
        checksum = manifest.get("manifest_checksum_sha256")
        if (
            not isinstance(checksum, str)
            or _SHA256.fullmatch(checksum) is None
            or checksum != _checksum(manifest)
        ):
            findings.append("manifest checksum mismatch")
    except (
        AttributeError,
        BenchmarkEvidenceError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        ZeroDivisionError,
        RecursionError,
    ) as exc:
        findings.append(
            f"receipt validation failed closed: {type(exc).__name__}"
        )
    return findings


def _finalize(payload: Mapping[str, Any]) -> dict[str, Any]:
    detached = json.loads(canonical_json_bytes(payload))
    if "manifest_checksum_sha256" in detached:
        raise BenchmarkEvidenceError("payload already carries checksum")
    detached["manifest_checksum_sha256"] = _checksum(detached)
    findings = validate_receipt(detached)
    if findings:
        raise BenchmarkEvidenceError("; ".join(findings))
    return detached


def _build_receipt_in_process(
    *,
    repo_root: Path = REPO,
) -> dict[str, Any]:
    scopes_before = _current_scopes(repo_root)
    rows, dataset_bytes = _load_dataset(repo_root)
    stage = load_science_quantity_stage(repo_root / STAGE_ROOT)
    stage_snapshot = _stage_record(stage)
    e4_receipt = scalar_e4.build_receipt(repo_root=repo_root)
    candidate_closure = _candidate_closure_contract(
        scopes_before["candidate"], e4_receipt
    )
    e4_contract = _e4_prerequisite_contract(
        source_scope=scopes_before["source"],
        candidate_scope=scopes_before["candidate"],
        control_fixture_scope=scopes_before["control_fixture"],
        stage_scope=scopes_before["stage"],
        e4_receipt=e4_receipt,
    )
    evaluator_sentinel: dict[str, Any] = {}

    def base_state_digest() -> str:
        return _sentinel_digest(evaluator_sentinel)

    sentinel_before = base_state_digest()
    items = []
    for ordinal, row in enumerate(rows):
        safe_item = _candidate_payload(row)
        primary_order = (
            ["off", "on"] if ordinal % 2 == 0 else ["on", "off"]
        )
        records, replay = scalar_e4._execute_pair(
            safe_item,
            stage=stage,
            primary_order=primary_order,
            gold=row["gold"],
            base_state_digest=base_state_digest,
        )
        items.append(
            {
                "item_id": _item_identity(row, ordinal),
                "ordinal": ordinal,
                "category": row["category"],
                "evaluator_eligible": True,
                "post_hoc_targeted_item": ordinal == TARGET_ORDINAL,
                "input_digest_sha256": _sha256(
                    canonical_json_bytes(safe_item)
                ),
                "choices_digest_sha256": _sha256(
                    canonical_json_bytes(safe_item["choices"])
                ),
                "primary_execution_order": primary_order,
                "replay_execution_order": list(reversed(primary_order)),
                "conditions": records,
                "off_to_on": scalar_e4._transition(
                    records["off"], records["on"]
                ),
                "replay": replay,
                "gold_absent_from_candidate_arguments": True,
                "evaluator_metadata_absent_from_candidate_arguments": True,
            }
        )
    target_control = _run_targeted_stage_control(repo_root)
    sentinel_after = base_state_digest()
    scopes_after = _current_scopes(repo_root)
    changed = [
        name
        for name in scopes_before
        if scopes_before[name] != scopes_after[name]
    ]
    if changed:
        raise BenchmarkEvidenceError(
            "bound bytes changed during scalar public run: "
            + ", ".join(changed)
        )
    if sentinel_before != sentinel_after:
        raise BenchmarkEvidenceError(
            "evaluator sentinel changed during scalar public run"
        )
    selection = _selection(rows, dataset_bytes)
    metrics = _derive_metrics(items, stage_snapshot)
    if (
        metrics["targeted_public_observation"][
            "proof_matches_disclosed_stage_rows"
        ]
        is not True
    ):
        raise BenchmarkEvidenceError(
            "public target proof does not match disclosed stage rows"
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "protocol": _protocol(),
        "claims": _claims(
            measurement_protocol_gate=metrics[
                "paired_development_measurement_protocol_gate_passed"
            ],
            prerequisite_gate=True,
            targeted_control_gate=target_control["contract_passed"],
        ),
        "seal": _seal(),
        **scopes_before,
        "candidate_closure_contract": candidate_closure,
        "e4_prerequisite_contract": e4_contract,
        "adaptation_disclosure": _adaptation_disclosure(),
        "stage_snapshot": stage_snapshot,
        "selection": selection,
        "metrics": metrics,
        "items": items,
        "targeted_stage_control": target_control,
        "integrity": {
            "source_same_before_after": True,
            "candidate_same_before_after": True,
            "dataset_same_before_after": True,
            "control_fixture_same_before_after": True,
            "stage_same_before_after": True,
            "dataset_matches_pinned_hash": True,
            "same_items_choices_off_on": True,
            "gold_absent_from_candidate_arguments_all": True,
            "evaluator_metadata_absent_from_candidate_arguments_all": True,
            "semantic_replay_all": metrics["semantic_replay_all"],
            "evaluator_sentinel_unchanged": (
                sentinel_before == sentinel_after
                and metrics["evaluator_sentinel_unchanged_all"] is True
            ),
            "off_snapshot_structurally_absent_all": metrics[
                "off_snapshot_structurally_absent_all"
            ],
            "on_validated_snapshot_bound_all": metrics[
                "on_validated_snapshot_bound_all"
            ],
            "fresh_process_current_replay_enforced": True,
            "e4_prerequisite_current_reexecuted": True,
            "e4_prerequisite_gate_passed": True,
            "candidate_closure_exact_19_files": True,
            "post_hoc_targeting_disclosed": True,
            "target_proof_matches_disclosed_stage_rows": metrics[
                "targeted_public_observation"
            ]["proof_matches_disclosed_stage_rows"],
            "targeted_partial_inconsistency_control_passed": target_control[
                "contract_passed"
            ],
            "process_resource_telemetry_omitted": True,
            "evaluator_sentinel_digest_before": sentinel_before,
            "evaluator_sentinel_digest_after": sentinel_after,
            "network_isolation_enforced": False,
            "shipped_graph_write_authority": False,
            "production_authority": False,
            "hidden_holdout_claimed": False,
            "independent_evaluation_claimed": False,
            "external_authenticity_established": False,
            "unbiased_generalization_established": False,
            "coordinated_stage_rewrite_resistance_claimed": False,
            "shipped_graph_immutability_claimed": False,
            "resource_curve_established": False,
            "e5_equivalent": False,
        },
    }
    return _finalize(payload)


def build_receipt(
    *,
    repo_root: Path = REPO,
) -> dict[str, Any]:
    """Build through a fresh process so executed code follows bound bytes."""

    script_path = repo_root / "scripts/science_stage_scalar_mmlu_pro_receipt.py"
    scopes_before = _current_scopes(repo_root)
    try:
        completed = subprocess.run(
            [sys.executable, str(script_path), "--internal-build-worker"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BenchmarkEvidenceError(
            f"fresh scalar public worker failed: {type(exc).__name__}"
        ) from exc
    if completed.returncode != 0:
        raise BenchmarkEvidenceError(
            "fresh scalar public worker exited nonzero"
        )
    payload = completed.stdout
    if not payload or len(payload) > MAX_RECEIPT_BYTES:
        raise BenchmarkEvidenceError("fresh scalar public worker size invalid")
    manifest = strict_json_bytes(
        payload, label="fresh scalar public receipt worker"
    )
    if payload != canonical_json_bytes(manifest) + b"\n":
        raise BenchmarkEvidenceError(
            "fresh scalar public worker output is not canonical JSON"
        )
    findings = validate_receipt(manifest)
    if findings:
        raise BenchmarkEvidenceError("; ".join(findings))
    scopes_after = _current_scopes(repo_root)
    changed = [
        name
        for name in scopes_before
        if (
            scopes_before[name] != scopes_after[name]
            or manifest.get(name) != scopes_after[name]
        )
    ]
    if changed:
        raise BenchmarkEvidenceError(
            "bound bytes changed across fresh scalar public worker: "
            + ", ".join(changed)
        )
    return manifest


def read_receipt(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise BenchmarkEvidenceError(
            f"scalar public receipt unreadable: {type(exc).__name__}"
        ) from exc
    if not payload or len(payload) > MAX_RECEIPT_BYTES:
        raise BenchmarkEvidenceError("scalar public receipt size invalid")
    manifest = strict_json_bytes(payload, label="scalar public receipt")
    if payload != canonical_json_bytes(manifest) + b"\n":
        raise BenchmarkEvidenceError(
            "scalar public receipt is not canonical JSON with one newline"
        )
    return manifest


def write_receipt_exclusive(
    path: Path,
    manifest: Mapping[str, Any],
    *,
    repo_root: Path = REPO,
) -> None:
    findings = validate_receipt(manifest)
    if findings:
        raise BenchmarkEvidenceError("; ".join(findings))
    safe_path = ensure_safe_report_output(repo_root, path)
    write_manifest_exclusive(safe_path, manifest)


def verify_receipt(
    path: Path,
    *,
    repo_root: Path = REPO,
    require_current: bool = True,
) -> dict[str, Any]:
    """Verify structure and, by default, replay the complete current receipt."""

    scope_names = (
        "source",
        "candidate",
        "dataset",
        "control_fixture",
        "stage",
    )
    try:
        manifest = read_receipt(path)
    except BenchmarkEvidenceError as exc:
        return {
            "valid": False,
            "structure_valid": False,
            "matches_current": False,
            "declared_sealed": False,
            "verified_sealed": False,
            "sealed": False,
            "e5_claimed": False,
            "authenticity_established": False,
            "unbiased_generalization_established": False,
            "resource_curve_established": False,
            "checksum_sha256": None,
            **{f"{name}_matches_current": False for name in scope_names},
            "findings": [str(exc)],
        }
    findings = validate_receipt(manifest)
    structure_valid = not findings
    current_scopes = {
        name: _scope_matches_current(manifest.get(name), repo_root)
        for name in scope_names
    }
    matches_current = all(current_scopes.values())
    if require_current:
        try:
            expected = build_receipt(repo_root=repo_root)
        except Exception as exc:
            findings.append(
                "current scalar public replay failed closed: "
                f"{type(exc).__name__}"
            )
            matches_current = False
        else:
            mismatched = [
                field
                for field in sorted(_ROOT_FIELDS)
                if manifest.get(field) != expected.get(field)
            ]
            if mismatched:
                findings.append(
                    "current deterministic payload mismatch: "
                    + ", ".join(mismatched)
                )
                matches_current = False
            for name in scope_names:
                current_scopes[name] = _scope_matches_current(
                    manifest.get(name), repo_root
                )
                if not current_scopes[name]:
                    findings.append(
                        f"{name} scope differs after current semantic replay"
                    )
                    matches_current = False
    seal_value = manifest.get("seal")
    declared_sealed = (
        isinstance(seal_value, Mapping)
        and seal_value.get("sealed") is True
    )
    verified = (
        declared_sealed
        and not findings
        and require_current
        and matches_current
    )
    return {
        "valid": not findings,
        "structure_valid": structure_valid,
        "matches_current": matches_current,
        "declared_sealed": declared_sealed,
        "verified_sealed": verified,
        "sealed": verified,
        "e5_claimed": False,
        "authenticity_established": False,
        "unbiased_generalization_established": False,
        "resource_curve_established": False,
        "checksum_sha256": manifest.get("manifest_checksum_sha256"),
        **{
            f"{name}_matches_current": current_scopes[name]
            for name in scope_names
        },
        "findings": findings,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or verify the exposed scalar MMLU-Pro receipt."
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--build", type=Path)
    actions.add_argument("--verify", type=Path)
    parser.add_argument(
        "--internal-build-worker",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.internal_build_worker:
        if args.build is not None or args.verify is not None:
            raise SystemExit("internal build worker cannot combine actions")
        manifest = _build_receipt_in_process(repo_root=REPO)
        sys.stdout.buffer.write(canonical_json_bytes(manifest) + b"\n")
        return 0
    if args.build is not None:
        manifest = build_receipt(repo_root=REPO)
        write_receipt_exclusive(args.build, manifest, repo_root=REPO)
        return 0
    if args.verify is not None:
        result = verify_receipt(args.verify, repo_root=REPO)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["verified_sealed"] else 1
    _parser().print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
