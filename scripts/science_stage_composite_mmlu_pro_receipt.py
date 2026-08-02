"""Exposed MMLU-Pro development receipt for the routed science composite."""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from packages.eval_evidence.receipt import (
    BenchmarkEvidenceError,
    bind_files,
    canonical_json_bytes,
    ensure_safe_report_output,
    strict_json_bytes,
    write_manifest_exclusive,
)
from packages.reasoning_vm.science_candidate import (
    ScienceStageBundle,
    answer_prepared_science_candidate,
    prepare_science_input,
)
from scripts import science_stage_composite_e4_receipt as composite_e4
from scripts import science_stage_mmlu_pro_receipt as atomic_public
from scripts import science_stage_scalar_mmlu_pro_receipt as scalar_public


REPO = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = (
    "atanor.science-stage-composite-mmlu-pro-exposed-receipt.v1"
)
EVIDENCE_KIND = (
    "strict_self_measured_exposed_science_composite_development_receipt"
)

CONDITION_IDS = ("O", "A", "S", "B")
CONDITION_BUNDLE_LABELS = {
    "O": "off",
    "A": "atomic_only",
    "S": "scalar_only",
    "B": "both",
}
WILLIAMS_SEQUENCES = (
    ("O", "A", "B", "S"),
    ("A", "S", "O", "B"),
    ("S", "B", "A", "O"),
    ("B", "O", "S", "A"),
)
EXPECTED_ITEMS = 40
EXPECTED_PER_CATEGORY = 5
DATASET_PATH = scalar_public.DATASET_PATH
EXPECTED_DATASET_SHA256 = scalar_public.EXPECTED_DATASET_SHA256
CATEGORIES = scalar_public.CATEGORIES
TARGET_ORDINAL = scalar_public.TARGET_ORDINAL
TARGET_CATEGORY = scalar_public.TARGET_CATEGORY
TARGET_EVIDENCE_IDS = scalar_public.TARGET_EVIDENCE_IDS
CONTROL_FIXTURE_PATH = scalar_public.CONTROL_FIXTURE_PATH
MAX_RECEIPT_BYTES = 32 * 1024 * 1024

SOURCE_PATHS = tuple(
    sorted(
        {
            *atomic_public.SOURCE_PATHS,
            *scalar_public.SOURCE_PATHS,
            "scripts/science_stage_composite_e4_receipt.py",
            "scripts/science_stage_composite_mmlu_pro_receipt.py",
        }
    )
)
CANDIDATE_PATHS = composite_e4.CANDIDATE_PATHS
DATASET_PATHS = (DATASET_PATH,)
PREREQUISITE_FIXTURE_PATHS = composite_e4.DATASET_PATHS
STAGE_PATHS = composite_e4.STAGE_PATHS
PREREQUISITE_PATHS = (
    "scripts/science_stage_composite_e4_receipt.py",
    "scripts/science_stage_mmlu_pro_receipt.py",
    "scripts/science_stage_scalar_mmlu_pro_receipt.py",
)

EXPECTED_ROUTE_DISTRIBUTION = {
    "selected_atomic": 0,
    "selected_scalar": 1,
    "unsupported": 39,
    "invalid": 0,
    "ambiguous": 0,
}
EXPECTED_ITEM_IDS_SHA256 = (
    "17877ef5a55e93046e0c2e2902927c5df48a9e1fdc749ef866f0138f83433842"
)
EXPECTED_TARGET_ITEM_ID = (
    "7c5246e10e0cee6129580888cc2dd1a85f605833d2341a9a6acbb06018fdde90"
)
EXPECTED_TARGET_OFF_NATIVE_DIGEST = (
    "1b7e99576efb8ac317a0aae98b0e862647b0dfdff40453167a3e4e2c7e4118cd"
)
EXPECTED_TARGET_ON_NATIVE_DIGEST = (
    "37de4650a6df994f71dc38a3cbca16b01dc2a64dbf41d7ca984bfac2cd180a38"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
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
        "prerequisite_fixtures",
        "stage",
        "prerequisites",
        "adaptation_disclosure",
        "stage_snapshots",
        "selection",
        "metrics",
        "items",
        "integrity",
        "manifest_checksum_sha256",
    }
)
_SCOPE_FIELDS = frozenset({"files", "content_sha256"})
_FILE_FIELDS = frozenset({"path", "bytes", "sha256"})


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _checksum(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_checksum_sha256", None)
    return _sha256(canonical_json_bytes(unsigned))


def _detached(value: Any) -> Any:
    return json.loads(canonical_json_bytes(value))


def _bind_scopes(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "source": bind_files(repo_root, SOURCE_PATHS),
        "candidate": bind_files(repo_root, CANDIDATE_PATHS),
        "dataset": bind_files(repo_root, DATASET_PATHS),
        "prerequisite_fixtures": bind_files(
            repo_root,
            PREREQUISITE_FIXTURE_PATHS,
        ),
        "stage": bind_files(repo_root, STAGE_PATHS),
    }


def _scope_paths(scope: Any) -> list[str] | None:
    if not isinstance(scope, Mapping) or set(scope) != _SCOPE_FIELDS:
        return None
    files = scope.get("files")
    digest = scope.get("content_sha256")
    if (
        not isinstance(files, list)
        or not files
        or not isinstance(digest, str)
        or _SHA256.fullmatch(digest) is None
    ):
        return None
    paths: list[str] = []
    for row in files:
        if (
            not isinstance(row, Mapping)
            or set(row) != _FILE_FIELDS
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
    if digest != _sha256(canonical_json_bytes(files)):
        return None
    return paths


def _scope_matches_current(scope: Any, repo_root: Path) -> bool:
    paths = _scope_paths(scope)
    if paths is None:
        return False
    try:
        return scope == bind_files(repo_root, paths)
    except BenchmarkEvidenceError:
        return False


def _load_dataset(
    repo_root: Path,
) -> tuple[list[dict[str, Any]], bytes]:
    rows, payload = scalar_public._load_dataset(repo_root)
    if (
        len(rows) != EXPECTED_ITEMS
        or _sha256(payload) != EXPECTED_DATASET_SHA256
        or Counter(row["category"] for row in rows)
        != {category: EXPECTED_PER_CATEGORY for category in CATEGORIES}
    ):
        raise BenchmarkEvidenceError(
            "exposed MMLU-Pro slice contract mismatch"
        )
    return rows, payload


def _public_item_semantics_digest(
    manifest: Mapping[str, Any],
    *,
    scalar: bool,
) -> str:
    records = []
    for row in manifest["items"]:
        if scalar:
            off = row["conditions"]["off"]
            on = row["conditions"]["on"]
        else:
            off = row["conditions"]["off"]["result"]
            on = row["conditions"]["on"]["result"]
        records.append(
            {
                "item_id": row["item_id"],
                "off": off["semantic_outcome_digest_sha256"],
                "on": on["semantic_outcome_digest_sha256"],
            }
        )
    return _sha256(canonical_json_bytes(records))


def _summary_with_digest(core: Mapping[str, Any]) -> dict[str, Any]:
    detached = _detached(core)
    detached["summary_digest_sha256"] = _sha256(
        canonical_json_bytes(detached)
    )
    return detached


def _fresh_prerequisites(
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Mapping[str, Any]]]:
    composite = composite_e4.build_receipt(repo_root=repo_root)
    composite_findings = composite_e4.validate_receipt(
        composite,
        repo_root=repo_root,
    )
    if composite_findings:
        raise BenchmarkEvidenceError(
            "composite E4 prerequisite invalid: "
            + "; ".join(composite_findings)
        )
    atomic = atomic_public.build_receipt(repo_root=repo_root)
    atomic_findings = atomic_public.validate_receipt(
        atomic,
        repo_root=repo_root,
        require_current=True,
    )
    if atomic_findings:
        raise BenchmarkEvidenceError(
            "atomic public prerequisite invalid: "
            + "; ".join(atomic_findings)
        )
    scalar = scalar_public.build_receipt(repo_root=repo_root)
    scalar_findings = scalar_public.validate_receipt(scalar)
    if scalar_findings:
        raise BenchmarkEvidenceError(
            "scalar public prerequisite invalid: "
            + "; ".join(scalar_findings)
        )
    if (
        atomic["dataset"] != scalar["dataset"]
        or atomic["selection"]["item_ids"]
        != scalar["selection"]["item_ids"]
        or atomic["selection"]["input_choice_pairs_sha256"]
        != scalar["selection"]["input_choice_pairs_sha256"]
    ):
        raise BenchmarkEvidenceError(
            "public prerequisite selections differ"
        )
    composite_current = all(
        _scope_matches_current(composite[name], repo_root)
        for name in ("source", "candidate", "dataset", "stage")
    )
    atomic_current = all(
        _scope_matches_current(atomic[name], repo_root)
        for name in ("source", "candidate", "dataset", "stage")
    )
    scalar_current = all(
        _scope_matches_current(scalar[name], repo_root)
        for name in (
            "source",
            "candidate",
            "dataset",
            "control_fixture",
            "stage",
        )
    )
    composite_gate = composite["metrics"]["gates"][
        "composite_e4_development_gate_passed"
    ]
    atomic_gate = atomic["metrics"][
        "paired_development_measurement_gate_passed"
    ]
    scalar_gate = scalar["metrics"][
        "paired_development_measurement_protocol_gate_passed"
    ]
    composite_limits_ok = (
        composite["claims"]["public_capability_gate_evaluated"] is False
        and composite["claims"]["public_capability_gate_passed"] is False
        and composite["claims"]["e5_claimed"] is False
        and composite["claims"]["independent"] is False
        and composite["claims"][
            "external_authenticity_established"
        ]
        is False
        and composite["claims"]["resource_curve_established"] is False
        and composite["claims"]["process_resource_curve_claimed"]
        is False
    )
    atomic_limits_ok = (
        atomic["claims"]["benchmark_capability_claimed"] is False
        and atomic["claims"]["e5_claimed"] is False
        and atomic["claims"]["independent"] is False
        and atomic["claims"]["external_authenticity_established"]
        is False
        and atomic["claims"]["process_resource_curve_claimed"] is False
        and atomic["seal"].get("resource_curve_established", False)
        is False
    )
    scalar_limits_ok = (
        scalar["claims"]["benchmark_capability_claimed"] is False
        and scalar["claims"]["unbiased_generalization_claimed"] is False
        and scalar["claims"]["e5_claimed"] is False
        and scalar["claims"]["independent"] is False
        and scalar["claims"]["external_authenticity_established"]
        is False
        and scalar["claims"]["process_resource_curve_claimed"] is False
        and scalar["seal"]["resource_curve_established"] is False
    )
    scalar_selected = scalar["items"][TARGET_ORDINAL]
    scalar_off = scalar_selected["conditions"]["off"]
    scalar_on = scalar_selected["conditions"]["on"]
    selected_contract = {
        "zero_based_ordinal": TARGET_ORDINAL,
        "item_id": scalar_selected["item_id"],
        "category": scalar_selected["category"],
        "post_hoc_targeted_item": scalar_selected[
            "post_hoc_targeted_item"
        ],
        "off_semantic_outcome_digest_sha256": scalar_off[
            "semantic_outcome_digest_sha256"
        ],
        "on_semantic_outcome_digest_sha256": scalar_on[
            "semantic_outcome_digest_sha256"
        ],
        "off_status": scalar_off["status"],
        "on_status": scalar_on["status"],
        "off_choice_key": scalar_off["choice_key"],
        "on_choice_key": scalar_on["choice_key"],
        "off_compiled": scalar_off["compiler"]["compiled"],
        "on_compiled": scalar_on["compiler"]["compiled"],
        "off_reason": scalar_off["reason"],
        "on_reason": scalar_on["reason"],
        "on_evidence_ids": scalar_on["evidence_ids"],
        "on_proof_digest_sha256": scalar_on["proof_digest_sha256"],
        "on_provenance_digest_sha256": scalar_on[
            "provenance_digest_sha256"
        ],
        "on_stage_digest_sha256": scalar_on["stage_digest_sha256"],
        "on_grounded_leaf_count": scalar_on["grounded_leaf_count"],
        "on_grounded_stage_leaf_count": scalar_on[
            "grounded_stage_leaf_count"
        ],
    }
    composite_core = {
        "receipt_path": (
            "scripts/science_stage_composite_e4_receipt.py"
        ),
        "schema_version": composite_e4.SCHEMA_VERSION,
        "evidence_kind": composite_e4.EVIDENCE_KIND,
        "manifest_checksum_sha256": composite[
            "manifest_checksum_sha256"
        ],
        "verified_current": composite_current,
        "verified_sealed": (
            composite_current
            and composite["seal"]["sealed"] is True
            and composite_gate is True
            and composite_limits_ok
        ),
        "development_gate_passed": composite_gate is True,
        "candidate_closure_path_count": len(
            composite_e4.CANDIDATE_PATHS
        ),
        "candidate_closure_exact": composite["integrity"][
            "fresh_process_candidate_closure_exact"
        ],
        "stage_snapshots_digest_sha256": _sha256(
            canonical_json_bytes(composite["stage_snapshots"])
        ),
        "public_capability_gate_evaluated": composite["claims"][
            "public_capability_gate_evaluated"
        ],
        "public_capability_gate_passed": composite["claims"][
            "public_capability_gate_passed"
        ],
        "e5_claimed": composite["claims"]["e5_claimed"],
        "independent": composite["claims"]["independent"],
        "external_authenticity_established": composite["claims"][
            "external_authenticity_established"
        ],
        "resource_curve_established": composite["claims"][
            "resource_curve_established"
        ],
        "process_resource_curve_claimed": composite["claims"][
            "process_resource_curve_claimed"
        ],
    }
    atomic_core = {
        "receipt_path": "scripts/science_stage_mmlu_pro_receipt.py",
        "schema_version": atomic_public.SCHEMA_VERSION,
        "evidence_kind": atomic_public.EVIDENCE_KIND,
        "manifest_checksum_sha256": atomic[
            "manifest_checksum_sha256"
        ],
        "verified_current": atomic_current,
        "verified_sealed": (
            atomic_current
            and atomic["seal"]["sealed"] is True
            and atomic_gate is True
            and atomic_limits_ok
        ),
        "dataset_sha256": atomic["selection"][
            "actual_dataset_sha256"
        ],
        "item_count": len(atomic["items"]),
        "selection_digest_sha256": _sha256(
            canonical_json_bytes(atomic["selection"])
        ),
        "item_semantics_digest_sha256": (
            _public_item_semantics_digest(atomic, scalar=False)
        ),
        "stage_snapshot_digest_sha256": _sha256(
            canonical_json_bytes(atomic["stage_snapshot"])
        ),
        "stage_digest_sha256": atomic["stage_snapshot"][
            "stage_digest_sha256"
        ],
        "off_correct": atomic["metrics"]["overall"]["off"]["correct"],
        "on_correct": atomic["metrics"]["overall"]["on"]["correct"],
        "off_wrong_fire": atomic["metrics"]["overall"]["off"][
            "wrong_fire"
        ],
        "on_wrong_fire": atomic["metrics"]["overall"]["on"][
            "wrong_fire"
        ],
        "measurement_gate_passed": atomic_gate is True,
        "exposed_slice": True,
        "post_hoc_targeting_disclosed": False,
        "benchmark_capability_claimed": atomic["claims"][
            "benchmark_capability_claimed"
        ],
        "e5_claimed": atomic["claims"]["e5_claimed"],
        "independent": atomic["claims"]["independent"],
        "external_authenticity_established": atomic["claims"][
            "external_authenticity_established"
        ],
        "resource_curve_established": atomic["seal"].get(
            "resource_curve_established",
            False,
        ),
        "resource_curve_established_source_field_present": (
            "resource_curve_established" in atomic["seal"]
        ),
        "process_resource_curve_claimed": atomic["claims"][
            "process_resource_curve_claimed"
        ],
    }
    scalar_core = {
        "receipt_path": (
            "scripts/science_stage_scalar_mmlu_pro_receipt.py"
        ),
        "schema_version": scalar_public.SCHEMA_VERSION,
        "evidence_kind": scalar_public.EVIDENCE_KIND,
        "manifest_checksum_sha256": scalar[
            "manifest_checksum_sha256"
        ],
        "verified_current": scalar_current,
        "verified_sealed": (
            scalar_current
            and scalar["seal"]["sealed"] is True
            and scalar_gate is True
            and scalar["claims"][
                "targeted_partial_inconsistency_control_passed"
            ]
            is True
            and scalar_limits_ok
        ),
        "dataset_sha256": scalar["selection"][
            "actual_dataset_sha256"
        ],
        "item_count": len(scalar["items"]),
        "selection_digest_sha256": _sha256(
            canonical_json_bytes(scalar["selection"])
        ),
        "item_semantics_digest_sha256": (
            _public_item_semantics_digest(scalar, scalar=True)
        ),
        "stage_snapshot_digest_sha256": _sha256(
            canonical_json_bytes(scalar["stage_snapshot"])
        ),
        "stage_digest_sha256": scalar["stage_snapshot"][
            "stage_digest_sha256"
        ],
        "off_correct": scalar["metrics"]["overall"]["off"]["correct"],
        "on_correct": scalar["metrics"]["overall"]["on"]["correct"],
        "off_wrong_fire": scalar["metrics"]["overall"]["off"][
            "wrong_fire"
        ],
        "on_wrong_fire": scalar["metrics"]["overall"]["on"][
            "wrong_fire"
        ],
        "measurement_gate_passed": scalar_gate is True,
        "exposed_slice": True,
        "post_hoc_targeting_disclosed": scalar["claims"][
            "post_hoc_targeting_disclosed"
        ],
        "adaptation_disclosure_digest_sha256": scalar[
            "adaptation_disclosure"
        ]["disclosure_digest_sha256"],
        "targeted_partial_inconsistency_control_passed": scalar[
            "targeted_stage_control"
        ]["contract_passed"],
        "selected_item": selected_contract,
        "benchmark_capability_claimed": scalar["claims"][
            "benchmark_capability_claimed"
        ],
        "unbiased_generalization_claimed": scalar["claims"][
            "unbiased_generalization_claimed"
        ],
        "e5_claimed": scalar["claims"]["e5_claimed"],
        "independent": scalar["claims"]["independent"],
        "external_authenticity_established": scalar["claims"][
            "external_authenticity_established"
        ],
        "resource_curve_established": scalar["seal"][
            "resource_curve_established"
        ],
        "resource_curve_established_source_field_present": True,
        "process_resource_curve_claimed": scalar["claims"][
            "process_resource_curve_claimed"
        ],
    }
    summaries = {
        "scope": (
            "fresh current composite E4 and exposed atomic/scalar public "
            "receipts rebuilt inside this worker; no report file is trusted"
        ),
        "composite_e4": _summary_with_digest(composite_core),
        "atomic_public": _summary_with_digest(atomic_core),
        "scalar_public": _summary_with_digest(scalar_core),
    }
    if not all(
        summaries[name]["verified_current"]
        and summaries[name]["verified_sealed"]
        for name in ("composite_e4", "atomic_public", "scalar_public")
    ):
        raise BenchmarkEvidenceError(
            "fresh public prerequisite gate failed"
        )
    return summaries, {
        "composite_e4": composite,
        "atomic_public": atomic,
        "scalar_public": scalar,
    }


def _run_condition(
    prepared: Any,
    condition_id: str,
    bundles: Mapping[str, ScienceStageBundle],
) -> dict[str, Any]:
    empty_state_digest = atomic_public._base_digest({})
    return answer_prepared_science_candidate(
        prepared,
        bundles[condition_id],
        base_facts=lambda _subject: [],
        base_state_digest=lambda: empty_state_digest,
    )


def _condition_record(
    outcome: Mapping[str, Any],
    *,
    condition_id: str,
    gold: str,
    expected_native_condition: str | None,
    expected_native_digest: str | None,
) -> dict[str, Any]:
    route = outcome.get("route", {})
    decision = route.get("decision")
    lane = outcome.get("lane", {})
    lane_outcome = outcome.get("lane_outcome")
    compiler = (
        lane_outcome.get("compiler", {})
        if isinstance(lane_outcome, Mapping)
        else {}
    )
    engine = (
        lane_outcome.get("engine", {})
        if isinstance(lane_outcome, Mapping)
        else {}
    )
    staging = (
        lane_outcome.get("staging", {})
        if isinstance(lane_outcome, Mapping)
        else {}
    )
    choice_key = outcome.get("choice_key")
    error_kind = outcome.get("error_kind")
    if error_kind is not None:
        status = "error"
    elif choice_key is None:
        status = "abstain"
    elif choice_key == gold:
        status = "correct"
    else:
        status = "wrong"
    native_digest = lane.get("semantic_outcome_digest_sha256")
    evidence_ids = staging.get("evidence_ids", [])
    if not isinstance(evidence_ids, list):
        evidence_ids = []
    proof_digest = engine.get("proof_digest_sha256")
    provenance_digest = staging.get("provenance_digest_sha256")
    return {
        "condition_id": condition_id,
        "global_bundle_condition": CONDITION_BUNDLE_LABELS[condition_id],
        "status": status,
        "choice_key": choice_key,
        "correct": status == "correct",
        "wrong_fire": status == "wrong",
        "compiled": compiler.get("compiled") is True,
        "raw_fired": engine.get("raw_fired") is True,
        "formula_fired": engine.get("formula_fired") is True,
        "resolver_grounded": (
            engine.get("resolver_grounded") is True
        ),
        "proof_replayed": engine.get("proof_replayed") is True,
        "accepted_fire": engine.get("accepted_fire") is True,
        "grounded": engine.get("grounded") is True,
        "provenance_bound": (
            proof_digest is not None and provenance_digest is not None
        ),
        "route_status": (
            decision.get("status")
            if isinstance(decision, Mapping)
            else None
        ),
        "route_lane": (
            decision.get("lane")
            if isinstance(decision, Mapping)
            else None
        ),
        "route_reason": (
            decision.get("reason")
            if isinstance(decision, Mapping)
            else None
        ),
        "route_revalidated": route.get("revalidated") is True,
        "lane_entered": lane.get("entered") is True,
        "selected_stage_passed": (
            lane.get("selected_stage_passed") is True
        ),
        "unselected_stage_passed": (
            lane.get("unselected_stage_passed") is True
        ),
        "fallback_attempted": lane.get("fallback_attempted") is True,
        "original_mapping_read_count": outcome.get(
            "original_mapping_read_count"
        ),
        "native_semantic_outcome_digest_sha256": native_digest,
        "routed_semantic_outcome_digest_sha256": _sha256(
            canonical_json_bytes(composite_e4._routed_semantics(outcome))
        ),
        "expected_native_condition": expected_native_condition,
        "expected_native_semantic_outcome_digest_sha256": (
            expected_native_digest
        ),
        "native_semantic_preservation_same": (
            None
            if expected_native_digest is None
            else native_digest == expected_native_digest
        ),
        "proof_digest_sha256": proof_digest,
        "provenance_digest_sha256": provenance_digest,
        "stage_digest_sha256": staging.get("stage_digest_sha256"),
        "evidence_ids": evidence_ids,
        "grounded_leaf_count": int(
            staging.get("grounded_leaf_count", 0)
        ),
        "grounded_stage_leaf_count": int(
            staging.get("grounded_stage_leaf_count", 0)
        ),
        "reason": outcome.get("reason"),
        "error_kind": error_kind,
    }


def _execute_item(
    row: Mapping[str, Any],
    *,
    ordinal: int,
    bundles: Mapping[str, ScienceStageBundle],
    scalar_native: Mapping[str, Any],
) -> dict[str, Any]:
    prepared = prepare_science_input(row["q"], row["choices"])
    route = prepared.route
    expected_selected = ordinal == TARGET_ORDINAL
    if expected_selected:
        if route.status != "selected" or route.lane != "scalar":
            raise BenchmarkEvidenceError(
                "targeted public item did not select scalar lane"
            )
    elif route.status != "unsupported" or route.lane is not None:
        raise BenchmarkEvidenceError(
            "non-target public item route distribution changed"
        )
    sequence_index = ordinal % len(WILLIAMS_SEQUENCES)
    primary_order = list(WILLIAMS_SEQUENCES[sequence_index])
    replay_order = list(reversed(primary_order))
    primary = {
        condition_id: _run_condition(
            prepared,
            condition_id,
            bundles,
        )
        for condition_id in primary_order
    }
    repeated = {
        condition_id: _run_condition(
            prepared,
            condition_id,
            bundles,
        )
        for condition_id in replay_order
    }
    conditions: dict[str, dict[str, Any]] = {}
    replay_conditions: dict[str, dict[str, Any]] = {}
    for condition_id in CONDITION_IDS:
        if expected_selected:
            native_condition = (
                "on" if condition_id in {"S", "B"} else "off"
            )
            native_digest = scalar_native[
                f"{native_condition}_semantic_outcome_digest_sha256"
            ]
        else:
            native_condition = None
            native_digest = None
        record = _condition_record(
            primary[condition_id],
            condition_id=condition_id,
            gold=row["gold"],
            expected_native_condition=native_condition,
            expected_native_digest=native_digest,
        )
        replay_record = _condition_record(
            repeated[condition_id],
            condition_id=condition_id,
            gold=row["gold"],
            expected_native_condition=native_condition,
            expected_native_digest=native_digest,
        )
        conditions[condition_id] = record
        replay_conditions[condition_id] = {
            "semantic_outcome_same": (
                replay_record[
                    "routed_semantic_outcome_digest_sha256"
                ]
                == record["routed_semantic_outcome_digest_sha256"]
            ),
            "native_semantic_outcome_same": (
                replay_record[
                    "native_semantic_outcome_digest_sha256"
                ]
                == record["native_semantic_outcome_digest_sha256"]
            ),
            "replay_digest_sha256": replay_record[
                "routed_semantic_outcome_digest_sha256"
            ],
        }
    return {
        "item_id": scalar_public._item_identity(row, ordinal),
        "ordinal": ordinal,
        "category": row["category"],
        "evaluator_eligible": True,
        "post_hoc_targeted_item": expected_selected,
        "route_status": route.status,
        "route_lane": route.lane,
        "route_reason": route.reason,
        "input_digest_sha256": prepared.input_digest_sha256,
        "choices_digest_sha256": prepared.choices_digest_sha256,
        "original_mapping_read_count": (
            prepared.original_mapping_read_count
        ),
        "williams_sequence_id": f"W{sequence_index}",
        "primary_execution_order": primary_order,
        "replay_execution_order": replay_order,
        "conditions": conditions,
        "replay": {
            "all_conditions_same": all(
                value["semantic_outcome_same"]
                and value["native_semantic_outcome_same"]
                for value in replay_conditions.values()
            ),
            "conditions": replay_conditions,
        },
        "gold_absent_from_candidate_arguments": True,
        "evaluator_metadata_absent_from_candidate_arguments": True,
    }


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        raise BenchmarkEvidenceError(
            "public metric denominator must be positive"
        )
    return round(numerator / denominator, 12)


def _condition_metrics(
    items: Sequence[Mapping[str, Any]],
    condition_id: str,
) -> dict[str, Any]:
    records = [row["conditions"][condition_id] for row in items]
    n = len(records)
    if n <= 0:
        raise BenchmarkEvidenceError("empty public condition denominator")
    counts = {
        "selected_routes": sum(
            record["route_status"] == "selected" for record in records
        ),
        "unsupported_routes": sum(
            record["route_status"] == "unsupported"
            for record in records
        ),
        "compiled": sum(record["compiled"] for record in records),
        "raw_fired": sum(record["raw_fired"] for record in records),
        "formula_fired": sum(
            record["formula_fired"] for record in records
        ),
        "resolver_grounded": sum(
            record["resolver_grounded"] for record in records
        ),
        "proof_replayed": sum(
            record["proof_replayed"] for record in records
        ),
        "accepted_fired": sum(
            record["accepted_fire"] for record in records
        ),
        "grounded": sum(record["grounded"] for record in records),
        "correct": sum(record["correct"] for record in records),
        "wrong_fire": sum(record["wrong_fire"] for record in records),
        "abstain": sum(
            record["status"] == "abstain" for record in records
        ),
        "error": sum(record["status"] == "error" for record in records),
        "provenance_bound_fires": sum(
            record["provenance_bound"] for record in records
        ),
    }
    return {
        "n": n,
        **counts,
        "route_selection_rate": _ratio(counts["selected_routes"], n),
        "compiler_reach_rate": _ratio(counts["compiled"], n),
        "raw_firing_rate": _ratio(counts["raw_fired"], n),
        "formula_firing_rate": _ratio(counts["formula_fired"], n),
        "resolver_grounding_rate": _ratio(
            counts["resolver_grounded"], n
        ),
        "proof_replay_rate": _ratio(counts["proof_replayed"], n),
        "accepted_firing_rate": _ratio(counts["accepted_fired"], n),
        "grounded_coverage": _ratio(counts["grounded"], n),
        "strict_accuracy": _ratio(counts["correct"], n),
        "strict_accuracy_exact_binomial_95_ci": (
            scalar_public._exact_binomial_ci95(counts["correct"], n)
        ),
        "wrong_fire_rate": _ratio(counts["wrong_fire"], n),
        "abstention_rate": _ratio(counts["abstain"], n),
        "answered_accuracy": (
            None
            if counts["accepted_fired"] == 0
            else _ratio(counts["correct"], counts["accepted_fired"])
        ),
    }


def _contrast(
    items: Sequence[Mapping[str, Any]],
    left: str,
    right: str,
) -> dict[str, Any]:
    left_metrics = _condition_metrics(items, left)
    right_metrics = _condition_metrics(items, right)
    left_only = sum(
        row["conditions"][left]["correct"]
        and not row["conditions"][right]["correct"]
        for row in items
    )
    right_only = sum(
        not row["conditions"][left]["correct"]
        and row["conditions"][right]["correct"]
        for row in items
    )
    transitions = Counter(
        f"{row['conditions'][left]['status']}_to_"
        f"{row['conditions'][right]['status']}"
        for row in items
    )
    return {
        "left_condition": left,
        "right_condition": right,
        "strict_accuracy_delta": round(
            right_metrics["strict_accuracy"]
            - left_metrics["strict_accuracy"],
            12,
        ),
        "compiler_reach_rate_delta": round(
            right_metrics["compiler_reach_rate"]
            - left_metrics["compiler_reach_rate"],
            12,
        ),
        "raw_firing_rate_delta": round(
            right_metrics["raw_firing_rate"]
            - left_metrics["raw_firing_rate"],
            12,
        ),
        "accepted_firing_rate_delta": round(
            right_metrics["accepted_firing_rate"]
            - left_metrics["accepted_firing_rate"],
            12,
        ),
        "wrong_fire_rate_delta": round(
            right_metrics["wrong_fire_rate"]
            - left_metrics["wrong_fire_rate"],
            12,
        ),
        "transition_counts": dict(sorted(transitions.items())),
        "left_correct_right_incorrect": left_only,
        "left_incorrect_right_correct": right_only,
        "discordant_pairs": left_only + right_only,
        "exact_two_sided_mcnemar_p": scalar_public._exact_mcnemar_p(
            left_only,
            right_only,
        ),
    }


def _route_distribution(
    items: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    return {
        "selected_atomic": sum(
            row["route_status"] == "selected"
            and row["route_lane"] == "atomic"
            for row in items
        ),
        "selected_scalar": sum(
            row["route_status"] == "selected"
            and row["route_lane"] == "scalar"
            for row in items
        ),
        "unsupported": sum(
            row["route_status"] == "unsupported" for row in items
        ),
        "invalid": sum(row["route_status"] == "invalid" for row in items),
        "ambiguous": sum(
            row["route_status"] == "ambiguous" for row in items
        ),
    }


def _prerequisite_gate(prerequisites: Mapping[str, Any]) -> bool:
    return (
        all(
            prerequisites[name]["verified_current"] is True
            and prerequisites[name]["verified_sealed"] is True
            for name in (
                "composite_e4",
                "atomic_public",
                "scalar_public",
            )
        )
        and prerequisites["composite_e4"][
            "development_gate_passed"
        ]
        is True
        and prerequisites["composite_e4"][
            "public_capability_gate_evaluated"
        ]
        is False
        and prerequisites["composite_e4"][
            "public_capability_gate_passed"
        ]
        is False
        and prerequisites["atomic_public"][
            "measurement_gate_passed"
        ]
        is True
        and prerequisites["scalar_public"][
            "measurement_gate_passed"
        ]
        is True
        and prerequisites["scalar_public"][
            "targeted_partial_inconsistency_control_passed"
        ]
        is True
        and all(
            prerequisites[name][field] is False
            for name in (
                "composite_e4",
                "atomic_public",
                "scalar_public",
            )
            for field in (
                (
                    "public_capability_gate_passed"
                    if name == "composite_e4"
                    else "benchmark_capability_claimed"
                ),
                "e5_claimed",
                "independent",
                "external_authenticity_established",
                "resource_curve_established",
            )
        )
        and prerequisites["scalar_public"][
            "unbiased_generalization_claimed"
        ]
        is False
        and all(
            prerequisites[name]["process_resource_curve_claimed"]
            is False
            for name in (
                "composite_e4",
                "atomic_public",
                "scalar_public",
            )
        )
    )


def _derive_metrics(
    items: Sequence[Mapping[str, Any]],
    prerequisites: Mapping[str, Any],
) -> dict[str, Any]:
    conditions = {
        condition_id: _condition_metrics(items, condition_id)
        for condition_id in CONDITION_IDS
    }
    by_category = {
        category: [row for row in items if row["category"] == category]
        for category in CATEGORIES
    }
    capability = {
        "overall": conditions,
        "categories": {
            category: {
                condition_id: _condition_metrics(rows, condition_id)
                for condition_id in CONDITION_IDS
            }
            for category, rows in by_category.items()
        },
        "contrasts": {
            "O_to_A": _contrast(items, "O", "A"),
            "O_to_S": _contrast(items, "O", "S"),
            "O_to_B": _contrast(items, "O", "B"),
            "A_to_B": _contrast(items, "A", "B"),
            "S_to_B": _contrast(items, "S", "B"),
        },
        "targeted_public_observation": {
            "zero_based_ordinal": TARGET_ORDINAL,
            "item_id": items[TARGET_ORDINAL]["item_id"],
            "category": items[TARGET_ORDINAL]["category"],
            "route_lane": items[TARGET_ORDINAL]["route_lane"],
            "post_hoc_targeted": True,
            "O_status": items[TARGET_ORDINAL]["conditions"]["O"][
                "status"
            ],
            "A_status": items[TARGET_ORDINAL]["conditions"]["A"][
                "status"
            ],
            "S_status": items[TARGET_ORDINAL]["conditions"]["S"][
                "status"
            ],
            "B_status": items[TARGET_ORDINAL]["conditions"]["B"][
                "status"
            ],
            "S_evidence_ids": items[TARGET_ORDINAL]["conditions"]["S"][
                "evidence_ids"
            ],
            "B_evidence_ids": items[TARGET_ORDINAL]["conditions"]["B"][
                "evidence_ids"
            ],
            "unbiased_generalization_observation": False,
        },
    }
    replay_records = [
        record
        for row in items
        for record in row["replay"]["conditions"].values()
    ]
    primary_records = [
        record for row in items for record in row["conditions"].values()
    ]
    route_distribution = _route_distribution(items)
    mechanism = {
        "prepared_row_count": len(items),
        "source_mapping_reads": sum(
            row["original_mapping_read_count"] for row in items
        ),
        "source_mapping_read_once_per_row_all": all(
            row["original_mapping_read_count"] == 1 for row in items
        ),
        "prepared_condition_executions": len(items) * 8,
        "primary_condition_executions": len(primary_records),
        "replay_condition_executions": len(items) * 4,
        "primary_routes_revalidated": sum(
            record["route_revalidated"] for record in primary_records
        ),
        "condition_routes_match_prepared_all": all(
            record["route_status"] == row["route_status"]
            and record["route_lane"] == row["route_lane"]
            and record["route_reason"] == row["route_reason"]
            for row in items
            for record in row["conditions"].values()
        ),
        "semantic_replay_comparisons": len(replay_records),
        "semantic_replay_matches": sum(
            record["semantic_outcome_same"]
            and record["native_semantic_outcome_same"]
            for record in replay_records
        ),
        "route_distribution": route_distribution,
        "strict_route_distribution_passed": (
            route_distribution == EXPECTED_ROUTE_DISTRIBUTION
        ),
        "selected_item_count": route_distribution["selected_scalar"],
        "selected_primary_condition_executions": sum(
            record["route_status"] == "selected"
            for record in primary_records
        ),
        "compiled_primary_condition_executions": sum(
            record["compiled"] for record in primary_records
        ),
        "raw_fired_primary_condition_executions": sum(
            record["raw_fired"] for record in primary_records
        ),
        "accepted_primary_condition_executions": sum(
            record["accepted_fire"] for record in primary_records
        ),
        "wrong_fire_primary_condition_executions": sum(
            record["wrong_fire"] for record in primary_records
        ),
        "error_primary_condition_executions": sum(
            record["status"] == "error" for record in primary_records
        ),
        "gold_absent_from_candidate_arguments_all": all(
            row["gold_absent_from_candidate_arguments"] is True
            for row in items
        ),
        "evaluator_metadata_absent_from_candidate_arguments_all": all(
            row[
                "evaluator_metadata_absent_from_candidate_arguments"
            ]
            is True
            for row in items
        ),
    }
    mechanism["mechanism_gate_passed"] = (
        mechanism["prepared_row_count"] == EXPECTED_ITEMS
        and mechanism["source_mapping_reads"] == EXPECTED_ITEMS
        and mechanism["source_mapping_read_once_per_row_all"]
        and mechanism["prepared_condition_executions"]
        == EXPECTED_ITEMS * 8
        and mechanism["primary_condition_executions"]
        == EXPECTED_ITEMS * 4
        and mechanism["replay_condition_executions"]
        == EXPECTED_ITEMS * 4
        and mechanism["primary_routes_revalidated"]
        == EXPECTED_ITEMS * 4
        and mechanism["condition_routes_match_prepared_all"]
        and mechanism["semantic_replay_comparisons"]
        == EXPECTED_ITEMS * 4
        and mechanism["semantic_replay_matches"]
        == EXPECTED_ITEMS * 4
        and mechanism["strict_route_distribution_passed"]
        and mechanism["selected_primary_condition_executions"] == 4
        and mechanism["compiled_primary_condition_executions"] == 4
        and mechanism["raw_fired_primary_condition_executions"] == 2
        and mechanism["accepted_primary_condition_executions"] == 2
        and mechanism["wrong_fire_primary_condition_executions"] == 0
        and mechanism["error_primary_condition_executions"] == 0
        and mechanism["gold_absent_from_candidate_arguments_all"]
        and mechanism[
            "evaluator_metadata_absent_from_candidate_arguments_all"
        ]
    )
    target = items[TARGET_ORDINAL]
    scalar_preservation_results = [
        target["conditions"][condition_id][
            "native_semantic_preservation_same"
        ]
        for condition_id in CONDITION_IDS
    ]
    preservation = {
        "atomic_native_mapping_evaluated": False,
        "atomic_native_mapping_denominator": 0,
        "scalar_selected_item_count": 1,
        "scalar_native_comparisons": len(
            scalar_preservation_results
        ),
        "scalar_native_semantics_same": sum(
            value is True for value in scalar_preservation_results
        ),
        "scalar_O_A_map_to_leaf_off": (
            target["conditions"]["O"]["expected_native_condition"]
            == target["conditions"]["A"]["expected_native_condition"]
            == "off"
        ),
        "scalar_S_B_map_to_leaf_on": (
            target["conditions"]["S"]["expected_native_condition"]
            == target["conditions"]["B"]["expected_native_condition"]
            == "on"
        ),
        "preservation_gate_passed": (
            len(scalar_preservation_results) == 4
            and all(value is True for value in scalar_preservation_results)
        ),
    }
    atomic_irrelevance = []
    unsupported_invariance = []
    factorial_correct = []
    for row in items:
        conditions_for_row = row["conditions"]
        for left, right in (("O", "A"), ("S", "B")):
            atomic_irrelevance.append(
                composite_e4._condition_behavior_digest(
                    conditions_for_row[left]
                )
                == composite_e4._condition_behavior_digest(
                    conditions_for_row[right]
                )
            )
        if row["route_status"] == "unsupported":
            for other in ("A", "S", "B"):
                unsupported_invariance.append(
                    composite_e4._condition_behavior_digest(
                        conditions_for_row["O"]
                    )
                    == composite_e4._condition_behavior_digest(
                        conditions_for_row[other]
                    )
                )
        factorial_correct.append(
            int(conditions_for_row["B"]["correct"])
            - int(conditions_for_row["A"]["correct"])
            - int(conditions_for_row["S"]["correct"])
            + int(conditions_for_row["O"]["correct"])
        )
    interaction = {
        "atomic_stage_irrelevance_comparisons": len(atomic_irrelevance),
        "atomic_stage_irrelevance_matches": sum(atomic_irrelevance),
        "unsupported_all_stage_invariance_comparisons": len(
            unsupported_invariance
        ),
        "unsupported_all_stage_invariance_matches": sum(
            unsupported_invariance
        ),
        "factorial_correct_interaction_values": factorial_correct,
        "factorial_correct_interaction_zero_count": sum(
            value == 0 for value in factorial_correct
        ),
        "unselected_stage_passed_count": sum(
            record["unselected_stage_passed"]
            for record in primary_records
        ),
        "fallback_attempted_count": sum(
            record["fallback_attempted"] for record in primary_records
        ),
        "noninterference_gate_passed": (
            len(atomic_irrelevance) == EXPECTED_ITEMS * 2
            and all(atomic_irrelevance)
            and len(unsupported_invariance) == 39 * 3
            and all(unsupported_invariance)
            and all(value == 0 for value in factorial_correct)
            and all(
                not record["unselected_stage_passed"]
                and not record["fallback_attempted"]
                for record in primary_records
            )
        ),
    }
    order = composite_e4._order_balance(items)
    prerequisite_gate = _prerequisite_gate(prerequisites)
    zero_wrong_fire = all(
        record["wrong_fire"] is False for record in primary_records
    )
    target_gate = (
        target["post_hoc_targeted_item"] is True
        and target["route_lane"] == "scalar"
        and target["conditions"]["O"]["status"] == "abstain"
        and target["conditions"]["A"]["status"] == "abstain"
        and target["conditions"]["S"]["status"] == "correct"
        and target["conditions"]["B"]["status"] == "correct"
        and tuple(target["conditions"]["S"]["evidence_ids"])
        == TARGET_EVIDENCE_IDS
        and tuple(target["conditions"]["B"]["evidence_ids"])
        == TARGET_EVIDENCE_IDS
    )
    gates = {
        "prerequisite_gate_passed": prerequisite_gate,
        "route_distribution_gate_passed": mechanism[
            "strict_route_distribution_passed"
        ],
        "mechanism_gate_passed": mechanism["mechanism_gate_passed"],
        "replay_gate_passed": (
            mechanism["semantic_replay_matches"]
            == mechanism["semantic_replay_comparisons"]
        ),
        "preservation_gate_passed": preservation[
            "preservation_gate_passed"
        ],
        "noninterference_gate_passed": interaction[
            "noninterference_gate_passed"
        ],
        "zero_wrong_fire_gate_passed": zero_wrong_fire,
        "zero_condition_error_gate_passed": (
            mechanism["error_primary_condition_executions"] == 0
        ),
        "candidate_boundary_gate_passed": (
            mechanism["source_mapping_read_once_per_row_all"]
            and mechanism["condition_routes_match_prepared_all"]
            and mechanism["gold_absent_from_candidate_arguments_all"]
            and mechanism[
                "evaluator_metadata_absent_from_candidate_arguments_all"
            ]
        ),
        "targeted_observation_gate_passed": target_gate,
        "order_gate_passed": order["counterbalance_gate_passed"],
        "composite_public_development_measurement_protocol_gate_passed": (
            all(
                (
                    prerequisite_gate,
                    mechanism["strict_route_distribution_passed"],
                    mechanism["mechanism_gate_passed"],
                    preservation["preservation_gate_passed"],
                    interaction["noninterference_gate_passed"],
                    zero_wrong_fire,
                    mechanism["error_primary_condition_executions"] == 0,
                    mechanism["source_mapping_read_once_per_row_all"],
                    mechanism["condition_routes_match_prepared_all"],
                    mechanism[
                        "gold_absent_from_candidate_arguments_all"
                    ],
                    mechanism[
                        "evaluator_metadata_absent_from_candidate_arguments_all"
                    ],
                    target_gate,
                    order["counterbalance_gate_passed"],
                )
            )
        ),
        "public_capability_gate_evaluated": False,
        "public_capability_gate_passed": False,
        "e5_gate_evaluated": False,
        "e5_gate_passed": False,
    }
    return {
        "capability": capability,
        "mechanism": mechanism,
        "preservation": preservation,
        "interaction": interaction,
        "order_balance": order,
        "gates": gates,
        "inference": {
            "exposed_post_hoc_development_measurement_only": True,
            "atomic_public_mapping_inference": False,
            "public_capability_inference": False,
            "unbiased_generalization_inference": False,
            "independent_evaluation_inference": False,
            "external_authenticity_inference": False,
            "resource_curve_inference": False,
            "e5_inference": False,
            "synergy_inference": False,
            "firing_only_progress_inference": False,
        },
    }


def _selection(
    rows: Sequence[Mapping[str, Any]],
    dataset_bytes: bytes,
    items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    base = scalar_public._selection(rows, dataset_bytes)
    route_assignments = [
        {
            "item_id": row["item_id"],
            "route_status": row["route_status"],
            "route_lane": row["route_lane"],
            "route_reason": row["route_reason"],
        }
        for row in items
    ]
    orders = [
        {
            "item_id": row["item_id"],
            "williams_sequence_id": row["williams_sequence_id"],
            "primary_execution_order": row["primary_execution_order"],
        }
        for row in items
    ]
    return {
        **base,
        "classification": (
            "exposed_post_hoc_composite_development_measurement"
        ),
        "route_distribution": _route_distribution(items),
        "route_assignments_sha256": _sha256(
            canonical_json_bytes(route_assignments)
        ),
        "condition_ids": list(CONDITION_IDS),
        "condition_bundle_labels": dict(CONDITION_BUNDLE_LABELS),
        "williams_sequences": [list(row) for row in WILLIAMS_SEQUENCES],
        "order_assignment_sha256": _sha256(
            canonical_json_bytes(orders)
        ),
        "public_capability_gate_evaluated": False,
        "inferential_independence_claimed": False,
    }


def _protocol() -> dict[str, Any]:
    return {
        "name": "science_composite_mmlu_pro_exposed_development_v1",
        "benchmark": "MMLU-Pro",
        "slice": "slice_5",
        "classification": (
            "exposed_post_hoc_routed_composite_development_measurement"
        ),
        "fixed_denominator": EXPECTED_ITEMS,
        "category_census": "8 categories x 5 items",
        "public_slice_exposed_before_profile_freeze": True,
        "post_hoc_targeting_disclosed": True,
        "fresh_process_build_enforced": True,
        "fresh_prerequisite_rebuild_enforced": True,
        "report_file_prerequisites_trusted": False,
        "prerequisite_receipt_paths": list(PREREQUISITE_PATHS),
        "prerequisite_fixture_union_paths": sorted(
            PREREQUISITE_FIXTURE_PATHS
        ),
        "candidate_payload": (
            "question + choices only; item ID, ordinal, category, gold, "
            "target marker, and evaluator metadata remain evaluator-side"
        ),
        "candidate_prepare_once_per_row": True,
        "prepared_input_reused_across_conditions_and_replay": True,
        "condition_ids": list(CONDITION_IDS),
        "condition_bundle_labels": dict(CONDITION_BUNDLE_LABELS),
        "williams_sequences": [list(row) for row in WILLIAMS_SEQUENCES],
        "sequence_assignment": "dataset_zero_based_ordinal_mod_4",
        "reverse_replay_enforced": True,
        "strict_router_distribution": dict(EXPECTED_ROUTE_DISTRIBUTION),
        "selected_lane_only": True,
        "cross_lane_fallback_allowed": False,
        "strict_scoring": (
            "errors and abstentions are incorrect on all 40 items"
        ),
        "measurement_protocol_gate_meaning": (
            "complete fixed-denominator exposed development execution, "
            "prepare-once Williams/reverse replay, exact router census, "
            "scalar selected-item leaf semantic preservation, zero wrong "
            "fire, prerequisite and scope binding; no capability threshold"
        ),
        "atomic_public_mapping_evaluated": False,
        "public_capability_gate_evaluated": False,
        "e5_gate_evaluated": False,
        "process_resource_telemetry_recorded": False,
        "current_verification": (
            "fresh deterministic rebuild, exact root comparison, then "
            "post-replay scope rebind"
        ),
        "limitations": [
            "the public development slice was exposed before profile freeze",
            "the scalar profile and stage target were selected after item inspection",
            "the observed scalar item is post-selection confirmation",
            "there is no routed atomic public item in this fixed slice",
            "the evaluator is local, unsigned, and not independent",
            "process resource telemetry and a resource curve are absent",
            "benchmark capability, unbiased generalization, hidden holdout, "
            "external authenticity, and E5 are not claimed",
        ],
    }


def _claims(metrics: Mapping[str, Any]) -> dict[str, Any]:
    gates = metrics["gates"]
    return {
        "classification": (
            "exposed_post_hoc_routed_composite_development_measurement"
        ),
        "development_only": True,
        "exposed_slice": True,
        "post_hoc_targeting_disclosed": True,
        "prerequisites_fresh_current_and_sealed": gates[
            "prerequisite_gate_passed"
        ],
        "exposed_development_capability_curve_measured": True,
        "mechanism_curve_measured": True,
        "composite_public_development_measurement_protocol_gate_passed": (
            gates[
                "composite_public_development_measurement_protocol_gate_passed"
            ]
        ),
        "route_distribution_gate_passed": gates[
            "route_distribution_gate_passed"
        ],
        "mechanism_gate_passed": gates["mechanism_gate_passed"],
        "preservation_gate_passed": gates[
            "preservation_gate_passed"
        ],
        "noninterference_gate_passed": gates[
            "noninterference_gate_passed"
        ],
        "zero_wrong_fire_gate_passed": gates[
            "zero_wrong_fire_gate_passed"
        ],
        "zero_condition_error_gate_passed": gates[
            "zero_condition_error_gate_passed"
        ],
        "candidate_boundary_gate_passed": gates[
            "candidate_boundary_gate_passed"
        ],
        "atomic_native_mapping_evaluated": False,
        "public_capability_gate_evaluated": False,
        "public_capability_gate_passed": False,
        "public_capability_evidence": False,
        "e5_gate_evaluated": False,
        "e5_gate_passed": False,
        "e5_claimed": False,
        "e5_equivalent": False,
        "independent": False,
        "independent_evaluation_claimed": False,
        "externally_signed": False,
        "hidden_holdout_claimed": False,
        "external_authenticity_established": False,
        "unbiased_generalization_claimed": False,
        "benchmark_capability_claimed": False,
        "process_resource_curve_claimed": False,
        "resource_curve_established": False,
        "synergy_claimed": False,
        "generalization_claimed": False,
        "firing_only_progress_claimed": False,
        "coordinated_stage_rewrite_resistance_claimed": False,
        "shipped_graph_immutability_claimed": False,
        "shipped_graph_write_authority": False,
        "production_authority": False,
    }


def _seal() -> dict[str, Any]:
    return {
        "sealed": True,
        "scope": (
            "exact current evaluator/candidate/public-dataset/full-E4-fixture-"
            "union/stage bytes + three freshly rebuilt current sealed "
            "prerequisites + exact 40-row routed O/A/S/B Williams/reverse "
            "development outcomes + scalar selected-item native OFF/ON "
            "semantic preservation + fresh 27-file candidate closure + "
            "recomputable checksum"
        ),
        "git_clean_required": False,
        "hidden_holdout_claimed": False,
        "independent_evaluation_claimed": False,
        "authenticity_established": False,
        "unbiased_generalization_established": False,
        "public_capability_established": False,
        "benchmark_capability_established": False,
        "coordinated_stage_rewrite_resistance_claimed": False,
        "shipped_graph_immutability_claimed": False,
        "resource_curve_established": False,
        "e5_equivalent": False,
    }


def _integrity(
    metrics: Mapping[str, Any],
    prerequisites: Mapping[str, Any],
    closure: Mapping[str, Any],
) -> dict[str, Any]:
    mechanism = metrics["mechanism"]
    preservation = metrics["preservation"]
    interaction = metrics["interaction"]
    gates = metrics["gates"]
    return {
        "source_same_before_after": True,
        "candidate_same_before_after": True,
        "dataset_same_before_after": True,
        "prerequisite_fixtures_same_before_after": True,
        "stage_same_before_after": True,
        "dataset_matches_pinned_hash": True,
        "prerequisite_fixture_union_exact": True,
        "prerequisites_fresh_current_and_sealed": gates[
            "prerequisite_gate_passed"
        ],
        "composite_e4_prerequisite_checksum_sha256": prerequisites[
            "composite_e4"
        ]["manifest_checksum_sha256"],
        "atomic_public_prerequisite_checksum_sha256": prerequisites[
            "atomic_public"
        ]["manifest_checksum_sha256"],
        "scalar_public_prerequisite_checksum_sha256": prerequisites[
            "scalar_public"
        ]["manifest_checksum_sha256"],
        "candidate_prepared_once_per_row": mechanism[
            "source_mapping_read_once_per_row_all"
        ],
        "prepared_row_count": mechanism["prepared_row_count"],
        "source_mapping_reads": mechanism["source_mapping_reads"],
        "prepared_condition_executions": mechanism[
            "prepared_condition_executions"
        ],
        "primary_condition_executions": mechanism[
            "primary_condition_executions"
        ],
        "replay_condition_executions": mechanism[
            "replay_condition_executions"
        ],
        "condition_routes_match_prepared_all": mechanism[
            "condition_routes_match_prepared_all"
        ],
        "gold_absent_from_candidate_arguments_all": mechanism[
            "gold_absent_from_candidate_arguments_all"
        ],
        "evaluator_metadata_absent_from_candidate_arguments_all": (
            mechanism[
                "evaluator_metadata_absent_from_candidate_arguments_all"
            ]
        ),
        "zero_primary_condition_errors": (
            mechanism["error_primary_condition_executions"] == 0
        ),
        "semantic_replay_all": (
            mechanism["semantic_replay_matches"]
            == mechanism["semantic_replay_comparisons"]
        ),
        "strict_route_distribution_exact": mechanism[
            "strict_route_distribution_passed"
        ],
        "scalar_native_semantic_preservation_all": preservation[
            "preservation_gate_passed"
        ],
        "atomic_native_mapping_evaluated": preservation[
            "atomic_native_mapping_evaluated"
        ],
        "atomic_native_mapping_denominator": preservation[
            "atomic_native_mapping_denominator"
        ],
        "selected_lane_only_all": (
            interaction["unselected_stage_passed_count"] == 0
        ),
        "fallback_attempted_count": interaction[
            "fallback_attempted_count"
        ],
        "process_resource_telemetry_omitted": True,
        **closure,
        "network_isolation_enforced": False,
        "shipped_graph_write_authority": False,
        "shipped_graph_immutability_observed": False,
        "production_authority": False,
        "hidden_holdout_claimed": False,
        "independent_evaluation_claimed": False,
        "external_authenticity_established": False,
        "resource_curve_established": False,
        "public_capability_gate_evaluated": False,
        "e5_gate_evaluated": False,
        "e5_claimed": False,
    }


def _valid_digest(value: Any, *, allow_none: bool = False) -> bool:
    return (
        allow_none
        and value is None
        or isinstance(value, str)
        and _SHA256.fullmatch(value) is not None
    )


def _summary_digest_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    core = dict(value)
    digest = core.pop("summary_digest_sha256", None)
    return (
        _valid_digest(digest)
        and digest == _sha256(canonical_json_bytes(core))
    )


def _validate_item(
    item: Any,
    *,
    index: int,
    row: Mapping[str, Any],
    scalar_contract: Mapping[str, Any],
    findings: list[str],
) -> None:
    label = f"items[{index}]"
    item_fields = {
        "item_id",
        "ordinal",
        "category",
        "evaluator_eligible",
        "post_hoc_targeted_item",
        "route_status",
        "route_lane",
        "route_reason",
        "input_digest_sha256",
        "choices_digest_sha256",
        "original_mapping_read_count",
        "williams_sequence_id",
        "primary_execution_order",
        "replay_execution_order",
        "conditions",
        "replay",
        "gold_absent_from_candidate_arguments",
        "evaluator_metadata_absent_from_candidate_arguments",
    }
    condition_fields = {
        "condition_id",
        "global_bundle_condition",
        "status",
        "choice_key",
        "correct",
        "wrong_fire",
        "compiled",
        "raw_fired",
        "formula_fired",
        "resolver_grounded",
        "proof_replayed",
        "accepted_fire",
        "grounded",
        "provenance_bound",
        "route_status",
        "route_lane",
        "route_reason",
        "route_revalidated",
        "lane_entered",
        "selected_stage_passed",
        "unselected_stage_passed",
        "fallback_attempted",
        "original_mapping_read_count",
        "native_semantic_outcome_digest_sha256",
        "routed_semantic_outcome_digest_sha256",
        "expected_native_condition",
        "expected_native_semantic_outcome_digest_sha256",
        "native_semantic_preservation_same",
        "proof_digest_sha256",
        "provenance_digest_sha256",
        "stage_digest_sha256",
        "evidence_ids",
        "grounded_leaf_count",
        "grounded_stage_leaf_count",
        "reason",
        "error_kind",
    }
    if not isinstance(item, Mapping) or set(item) != item_fields:
        findings.append(f"{label} fields mismatch")
        return
    prepared = prepare_science_input(row["q"], row["choices"])
    expected_target = index == TARGET_ORDINAL
    if (
        item.get("item_id") != scalar_public._item_identity(row, index)
        or item.get("ordinal") != index
        or item.get("category") != row["category"]
        or item.get("evaluator_eligible") is not True
        or item.get("post_hoc_targeted_item") is not expected_target
        or item.get("route_status") != prepared.route.status
        or item.get("route_lane") != prepared.route.lane
        or item.get("route_reason") != prepared.route.reason
        or item.get("input_digest_sha256")
        != prepared.input_digest_sha256
        or item.get("choices_digest_sha256")
        != prepared.choices_digest_sha256
        or item.get("original_mapping_read_count") != 1
        or item.get("gold_absent_from_candidate_arguments") is not True
        or item.get(
            "evaluator_metadata_absent_from_candidate_arguments"
        )
        is not True
    ):
        findings.append(f"{label} identity/candidate boundary mismatch")
    sequence_index = index % 4
    expected_order = list(WILLIAMS_SEQUENCES[sequence_index])
    if (
        item.get("williams_sequence_id") != f"W{sequence_index}"
        or item.get("primary_execution_order") != expected_order
        or item.get("replay_execution_order")
        != list(reversed(expected_order))
    ):
        findings.append(f"{label} Williams/reverse order mismatch")
    conditions = item.get("conditions")
    if (
        not isinstance(conditions, Mapping)
        or set(conditions) != set(CONDITION_IDS)
    ):
        findings.append(f"{label}.conditions mismatch")
        return
    for condition_id in CONDITION_IDS:
        record = conditions[condition_id]
        condition_label = f"{label}.conditions.{condition_id}"
        if (
            not isinstance(record, Mapping)
            or set(record) != condition_fields
        ):
            findings.append(f"{condition_label} fields mismatch")
            continue
        status = record.get("status")
        choice_key = record.get("choice_key")
        error_kind = record.get("error_kind")
        valid_choice_keys = set(row["choices"])
        expected_status = (
            "error"
            if error_kind is not None
            else "abstain"
            if choice_key is None
            else "correct"
            if choice_key == row["gold"]
            else "wrong"
        )
        if (
            record.get("condition_id") != condition_id
            or record.get("global_bundle_condition")
            != CONDITION_BUNDLE_LABELS[condition_id]
            or status not in {"correct", "wrong", "abstain", "error"}
            or status != expected_status
            or record.get("correct") is not (status == "correct")
            or record.get("wrong_fire") is not (status == "wrong")
            or (
                status in {"abstain", "error"}
                and choice_key is not None
            )
            or (
                choice_key is not None
                and choice_key not in valid_choice_keys
            )
            or (status == "error") is not (error_kind is not None)
            or record.get("route_status") != item["route_status"]
            or record.get("route_lane") != item["route_lane"]
            or record.get("route_reason") != item["route_reason"]
            or record.get("route_revalidated") is not True
            or record.get("original_mapping_read_count") != 1
            or record.get("unselected_stage_passed") is not False
            or record.get("fallback_attempted") is not False
            or not _valid_digest(
                record.get("routed_semantic_outcome_digest_sha256")
            )
            or not _valid_digest(
                record.get("native_semantic_outcome_digest_sha256"),
                allow_none=True,
            )
            or not isinstance(record.get("evidence_ids"), list)
            or type(record.get("grounded_leaf_count")) is not int
            or type(record.get("grounded_stage_leaf_count")) is not int
        ):
            findings.append(f"{condition_label} semantic contract mismatch")
        if expected_target:
            native_condition = (
                "on" if condition_id in {"S", "B"} else "off"
            )
            expected_digest = scalar_contract.get(
                f"{native_condition}_semantic_outcome_digest_sha256"
            )
            target_expected_status = (
                "correct" if condition_id in {"S", "B"} else "abstain"
            )
            if (
                record.get("expected_native_condition")
                != native_condition
                or record.get(
                    "expected_native_semantic_outcome_digest_sha256"
                )
                != expected_digest
                or record.get(
                    "native_semantic_outcome_digest_sha256"
                )
                != expected_digest
                or record.get("native_semantic_preservation_same")
                is not True
                or status != target_expected_status
                or record.get("wrong_fire") is not False
                or record.get("error_kind") is not None
            ):
                findings.append(
                    f"{condition_label} scalar native mapping mismatch"
                )
            if condition_id in {"S", "B"}:
                if (
                    choice_key != scalar_contract.get("on_choice_key")
                    or choice_key != row["gold"]
                    or record.get("evidence_ids")
                    != scalar_contract.get("on_evidence_ids")
                    or record.get("compiled")
                    is not scalar_contract.get("on_compiled")
                    or record.get("raw_fired") is not True
                    or record.get("formula_fired") is not True
                    or record.get("resolver_grounded") is not True
                    or record.get("proof_replayed") is not True
                    or record.get("accepted_fire") is not True
                    or record.get("grounded") is not True
                    or record.get("provenance_bound") is not True
                    or record.get("lane_entered") is not True
                    or record.get("selected_stage_passed") is not True
                    or record.get("proof_digest_sha256")
                    != scalar_contract.get("on_proof_digest_sha256")
                    or record.get("provenance_digest_sha256")
                    != scalar_contract.get(
                        "on_provenance_digest_sha256"
                    )
                    or record.get("stage_digest_sha256")
                    != scalar_contract.get("on_stage_digest_sha256")
                    or record.get("grounded_leaf_count")
                    != scalar_contract.get("on_grounded_leaf_count")
                    or record.get("grounded_stage_leaf_count")
                    != scalar_contract.get(
                        "on_grounded_stage_leaf_count"
                    )
                    or record.get("reason")
                    != scalar_contract.get("on_reason")
                ):
                    findings.append(
                        f"{condition_label} targeted fire mismatch"
                    )
            elif (
                choice_key != scalar_contract.get("off_choice_key")
                or record.get("compiled")
                is not scalar_contract.get("off_compiled")
                or record.get("raw_fired") is not False
                or record.get("formula_fired") is not False
                or record.get("resolver_grounded") is not False
                or record.get("proof_replayed") is not False
                or record.get("accepted_fire") is not False
                or record.get("grounded") is not False
                or record.get("provenance_bound") is not False
                or record.get("lane_entered") is not True
                or record.get("selected_stage_passed") is not False
                or record.get("evidence_ids") != []
                or record.get("proof_digest_sha256") is not None
                or record.get("provenance_digest_sha256") is not None
                or record.get("stage_digest_sha256") is not None
                or record.get("grounded_leaf_count") != 0
                or record.get("grounded_stage_leaf_count") != 0
                or record.get("reason")
                != scalar_contract.get("off_reason")
            ):
                findings.append(
                    f"{condition_label} targeted OFF mismatch"
                )
        elif (
            item["route_status"] != "unsupported"
            or item["route_lane"] is not None
            or status != "abstain"
            or choice_key is not None
            or any(
                record.get(field) is not False
                for field in (
                    "compiled",
                    "raw_fired",
                    "formula_fired",
                    "resolver_grounded",
                    "proof_replayed",
                    "accepted_fire",
                    "grounded",
                    "provenance_bound",
                    "lane_entered",
                    "selected_stage_passed",
                )
            )
            or record.get("native_semantic_outcome_digest_sha256")
            is not None
            or record.get("expected_native_condition") is not None
            or record.get(
                "expected_native_semantic_outcome_digest_sha256"
            )
            is not None
            or record.get("native_semantic_preservation_same") is not None
            or record.get("proof_digest_sha256") is not None
            or record.get("provenance_digest_sha256") is not None
            or record.get("stage_digest_sha256") is not None
            or record.get("evidence_ids") != []
            or record.get("grounded_leaf_count") != 0
            or record.get("grounded_stage_leaf_count") != 0
            or record.get("reason") != "unsupported_science_profile"
            or record.get("error_kind") is not None
        ):
            findings.append(
                f"{condition_label} unsupported abstention mismatch"
            )
    replay = item.get("replay")
    if (
        not isinstance(replay, Mapping)
        or set(replay) != {"all_conditions_same", "conditions"}
        or replay.get("all_conditions_same") is not True
        or not isinstance(replay.get("conditions"), Mapping)
        or set(replay["conditions"]) != set(CONDITION_IDS)
    ):
        findings.append(f"{label}.replay mismatch")
        return
    for condition_id in CONDITION_IDS:
        replay_record = replay["conditions"][condition_id]
        if (
            not isinstance(replay_record, Mapping)
            or set(replay_record)
            != {
                "semantic_outcome_same",
                "native_semantic_outcome_same",
                "replay_digest_sha256",
            }
            or replay_record.get("semantic_outcome_same") is not True
            or replay_record.get("native_semantic_outcome_same") is not True
            or replay_record.get("replay_digest_sha256")
            != conditions[condition_id].get(
                "routed_semantic_outcome_digest_sha256"
            )
        ):
            findings.append(
                f"{label}.replay.conditions.{condition_id} mismatch"
            )


def _validate_receipt_impl(
    manifest: Mapping[str, Any],
    *,
    repo_root: Path = REPO,
    require_current: bool = False,
) -> list[str]:
    findings: list[str] = []
    if not isinstance(manifest, Mapping):
        return ["receipt root is not an object"]
    if set(manifest) != _ROOT_FIELDS:
        findings.append("root fields mismatch")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        findings.append("schema_version mismatch")
    if manifest.get("evidence_kind") != EVIDENCE_KIND:
        findings.append("evidence_kind mismatch")
    if manifest.get("protocol") != _protocol():
        findings.append("protocol mismatch")
    for name, expected_paths in (
        ("source", SOURCE_PATHS),
        ("candidate", CANDIDATE_PATHS),
        ("dataset", DATASET_PATHS),
        ("prerequisite_fixtures", PREREQUISITE_FIXTURE_PATHS),
        ("stage", STAGE_PATHS),
    ):
        if _scope_paths(manifest.get(name)) != sorted(expected_paths):
            findings.append(f"{name} scope paths mismatch")

    prerequisites = manifest.get("prerequisites")
    if (
        not isinstance(prerequisites, Mapping)
        or set(prerequisites)
        != {"scope", "composite_e4", "atomic_public", "scalar_public"}
    ):
        findings.append("prerequisites structure mismatch")
        prerequisites = {}
    else:
        if prerequisites.get("scope") != (
            "fresh current composite E4 and exposed atomic/scalar public "
            "receipts rebuilt inside this worker; no report file is trusted"
        ):
            findings.append("prerequisite scope statement mismatch")
        for name in ("composite_e4", "atomic_public", "scalar_public"):
            if not _summary_digest_valid(prerequisites.get(name)):
                findings.append(f"{name} prerequisite summary digest invalid")
        composite = prerequisites.get("composite_e4", {})
        atomic = prerequisites.get("atomic_public", {})
        scalar = prerequisites.get("scalar_public", {})
        if (
            not isinstance(composite, Mapping)
            or composite.get("receipt_path") != PREREQUISITE_PATHS[0]
            or composite.get("schema_version")
            != composite_e4.SCHEMA_VERSION
            or composite.get("evidence_kind") != composite_e4.EVIDENCE_KIND
            or composite.get("candidate_closure_path_count")
            != len(CANDIDATE_PATHS)
            or composite.get("candidate_closure_exact") is not True
        ):
            findings.append("composite E4 prerequisite contract mismatch")
        if (
            not isinstance(atomic, Mapping)
            or atomic.get("receipt_path") != PREREQUISITE_PATHS[1]
            or atomic.get("schema_version") != atomic_public.SCHEMA_VERSION
            or atomic.get("evidence_kind") != atomic_public.EVIDENCE_KIND
            or atomic.get("dataset_sha256") != EXPECTED_DATASET_SHA256
            or atomic.get("item_count") != EXPECTED_ITEMS
            or atomic.get("off_correct") != 0
            or atomic.get("on_correct") != 0
            or atomic.get("off_wrong_fire") != 0
            or atomic.get("on_wrong_fire") != 0
            or atomic.get("post_hoc_targeting_disclosed") is not False
        ):
            findings.append("atomic public prerequisite contract mismatch")
        scalar_contract = (
            scalar.get("selected_item", {})
            if isinstance(scalar, Mapping)
            else {}
        )
        if (
            not isinstance(scalar, Mapping)
            or scalar.get("receipt_path") != PREREQUISITE_PATHS[2]
            or scalar.get("schema_version") != scalar_public.SCHEMA_VERSION
            or scalar.get("evidence_kind") != scalar_public.EVIDENCE_KIND
            or scalar.get("dataset_sha256") != EXPECTED_DATASET_SHA256
            or scalar.get("item_count") != EXPECTED_ITEMS
            or scalar.get("off_correct") != 0
            or scalar.get("on_correct") != 1
            or scalar.get("off_wrong_fire") != 0
            or scalar.get("on_wrong_fire") != 0
            or scalar.get("post_hoc_targeting_disclosed") is not True
            or scalar.get(
                "targeted_partial_inconsistency_control_passed"
            )
            is not True
            or not isinstance(scalar_contract, Mapping)
            or scalar_contract.get("zero_based_ordinal") != TARGET_ORDINAL
            or scalar_contract.get("item_id") != EXPECTED_TARGET_ITEM_ID
            or scalar_contract.get("category") != TARGET_CATEGORY
            or scalar_contract.get("post_hoc_targeted_item") is not True
            or scalar_contract.get("off_status") != "abstain"
            or scalar_contract.get("on_status") != "correct"
            or scalar_contract.get("off_choice_key") is not None
            or scalar_contract.get("on_choice_key") != "B"
            or scalar_contract.get("off_compiled") is not True
            or scalar_contract.get("on_compiled") is not True
            or scalar_contract.get("off_reason")
            != "required_evidence_unavailable"
            or scalar_contract.get("on_reason")
            != "grounded_stage_formula_derivation"
            or scalar_contract.get("on_evidence_ids")
            != list(TARGET_EVIDENCE_IDS)
            or scalar_contract.get(
                "off_semantic_outcome_digest_sha256"
            )
            != EXPECTED_TARGET_OFF_NATIVE_DIGEST
            or scalar_contract.get(
                "on_semantic_outcome_digest_sha256"
            )
            != EXPECTED_TARGET_ON_NATIVE_DIGEST
            or not _valid_digest(
                scalar_contract.get("on_proof_digest_sha256")
            )
            or not _valid_digest(
                scalar_contract.get("on_provenance_digest_sha256")
            )
            or not _valid_digest(
                scalar_contract.get("on_stage_digest_sha256")
            )
            or scalar_contract.get("on_grounded_leaf_count") != 3
            or scalar_contract.get("on_grounded_stage_leaf_count") != 3
        ):
            findings.append("scalar public prerequisite contract mismatch")
        if prerequisites and not _prerequisite_gate(prerequisites):
            findings.append("fresh prerequisite gate mismatch")
        for name in ("composite_e4", "atomic_public", "scalar_public"):
            summary = prerequisites.get(name, {})
            if (
                not isinstance(summary, Mapping)
                or summary.get("verified_current") is not True
                or summary.get("verified_sealed") is not True
                or summary.get("e5_claimed") is not False
                or summary.get("independent") is not False
                or summary.get("external_authenticity_established")
                is not False
                or summary.get("resource_curve_established") is not False
                or summary.get("process_resource_curve_claimed")
                is not False
            ):
                findings.append(f"{name} declared limits mismatch")
        if (
            atomic.get(
                "resource_curve_established_source_field_present"
            )
            is not False
            or scalar.get(
                "resource_curve_established_source_field_present"
            )
            is not True
        ):
            findings.append(
                "public resource establishment source-field binding mismatch"
            )

    if manifest.get("adaptation_disclosure") != (
        scalar_public._adaptation_disclosure()
    ):
        findings.append("adaptation disclosure mismatch")
    elif isinstance(prerequisites, Mapping):
        scalar = prerequisites.get("scalar_public", {})
        if (
            not isinstance(scalar, Mapping)
            or scalar.get("adaptation_disclosure_digest_sha256")
            != manifest["adaptation_disclosure"].get(
                "disclosure_digest_sha256"
            )
        ):
            findings.append(
                "adaptation disclosure prerequisite binding mismatch"
            )

    stage_snapshots = manifest.get("stage_snapshots")
    if (
        not isinstance(stage_snapshots, Mapping)
        or set(stage_snapshots) != {"atomic", "scalar"}
    ):
        findings.append("stage snapshots structure mismatch")
        stage_snapshots = {}
    else:
        for name in ("atomic", "scalar"):
            snapshot = stage_snapshots[name]
            if (
                not isinstance(snapshot, Mapping)
                or not _valid_digest(snapshot.get("stage_digest_sha256"))
                or not _valid_digest(
                    snapshot.get("manifest_checksum_sha256")
                )
                or type(snapshot.get("bound_bytes")) is not int
                or snapshot["bound_bytes"] <= 0
            ):
                findings.append(f"{name} stage snapshot invalid")
        if isinstance(prerequisites, Mapping):
            composite = prerequisites.get("composite_e4", {})
            atomic = prerequisites.get("atomic_public", {})
            scalar = prerequisites.get("scalar_public", {})
            if (
                not isinstance(composite, Mapping)
                or composite.get("stage_snapshots_digest_sha256")
                != _sha256(canonical_json_bytes(stage_snapshots))
            ):
                findings.append("composite stage snapshot binding mismatch")
            if (
                not isinstance(atomic, Mapping)
                or atomic.get("stage_digest_sha256")
                != stage_snapshots["atomic"].get("stage_digest_sha256")
            ):
                findings.append("atomic stage snapshot binding mismatch")
            if (
                not isinstance(scalar, Mapping)
                or scalar.get("stage_digest_sha256")
                != stage_snapshots["scalar"].get("stage_digest_sha256")
                or not isinstance(
                    scalar.get("selected_item"),
                    Mapping,
                )
                or scalar["selected_item"].get(
                    "on_stage_digest_sha256"
                )
                != stage_snapshots["scalar"].get("stage_digest_sha256")
            ):
                findings.append("scalar stage snapshot binding mismatch")

    try:
        rows, dataset_bytes = _load_dataset(repo_root)
    except BenchmarkEvidenceError as exc:
        findings.append(str(exc))
        rows = []
        dataset_bytes = b""
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != EXPECTED_ITEMS:
        findings.append("item denominator mismatch")
        items = []
    scalar_contract = (
        prerequisites.get("scalar_public", {}).get("selected_item", {})
        if isinstance(prerequisites, Mapping)
        else {}
    )
    if len(rows) == EXPECTED_ITEMS and len(items) == EXPECTED_ITEMS:
        for index, (item, row) in enumerate(zip(items, rows, strict=True)):
            _validate_item(
                item,
                index=index,
                row=row,
                scalar_contract=scalar_contract,
                findings=findings,
            )
        if _sha256(
            canonical_json_bytes([item.get("item_id") for item in items])
        ) != EXPECTED_ITEM_IDS_SHA256:
            findings.append("item identity census hash mismatch")
        try:
            expected_selection = _selection(rows, dataset_bytes, items)
        except (BenchmarkEvidenceError, KeyError, TypeError, ValueError):
            findings.append("selection derivation failed")
        else:
            if manifest.get("selection") != expected_selection:
                findings.append("selection mismatch")

    if len(items) == EXPECTED_ITEMS and isinstance(prerequisites, Mapping):
        try:
            expected_metrics = _derive_metrics(items, prerequisites)
        except (BenchmarkEvidenceError, KeyError, TypeError, ValueError):
            findings.append("metric derivation failed")
            expected_metrics = None
        if (
            expected_metrics is not None
            and manifest.get("metrics") != expected_metrics
        ):
            findings.append("metrics mismatch")
    else:
        expected_metrics = None
    metrics = manifest.get("metrics")
    if isinstance(metrics, Mapping):
        gates = metrics.get("gates", {})
        if (
            not isinstance(gates, Mapping)
            or gates.get(
                "composite_public_development_measurement_protocol_gate_passed"
            )
            is not True
            or gates.get("public_capability_gate_evaluated") is not False
            or gates.get("public_capability_gate_passed") is not False
            or gates.get("e5_gate_evaluated") is not False
            or gates.get("e5_gate_passed") is not False
        ):
            findings.append("measurement/capability gate contract mismatch")
        if manifest.get("claims") != _claims(metrics):
            findings.append("claims mismatch")
    else:
        findings.append("metrics missing")
    if manifest.get("seal") != _seal():
        findings.append("seal mismatch")

    integrity = manifest.get("integrity")
    if (
        isinstance(metrics, Mapping)
        and isinstance(prerequisites, Mapping)
        and isinstance(integrity, Mapping)
    ):
        closure = {
            field: integrity.get(field)
            for field in (
                "fresh_process_candidate_closure_expected_path_count",
                "fresh_process_candidate_closure_actual_path_count",
                "fresh_process_candidate_closure_paths_sha256",
                "fresh_process_candidate_closure_exact",
            )
        }
        expected_closure = {
            "fresh_process_candidate_closure_expected_path_count": len(
                CANDIDATE_PATHS
            ),
            "fresh_process_candidate_closure_actual_path_count": len(
                CANDIDATE_PATHS
            ),
            "fresh_process_candidate_closure_paths_sha256": _sha256(
                canonical_json_bytes(sorted(CANDIDATE_PATHS))
            ),
            "fresh_process_candidate_closure_exact": True,
        }
        if closure != expected_closure:
            findings.append("candidate closure contract mismatch")
        if integrity != _integrity(
            metrics,
            prerequisites,
            expected_closure,
        ):
            findings.append("integrity mismatch")
    else:
        findings.append("integrity missing")

    checksum = manifest.get("manifest_checksum_sha256")
    if not _valid_digest(checksum) or checksum != _checksum(manifest):
        findings.append("manifest checksum mismatch")

    if require_current and not findings:
        for name in (
            "source",
            "candidate",
            "dataset",
            "prerequisite_fixtures",
            "stage",
        ):
            if not _scope_matches_current(manifest.get(name), repo_root):
                findings.append(f"{name} scope differs from current")
        if not findings:
            try:
                current = build_receipt(repo_root=repo_root)
            except Exception as exc:
                findings.append(
                    "current deterministic replay failed closed: "
                    + type(exc).__name__
                )
            else:
                mismatched = [
                    field
                    for field in sorted(_ROOT_FIELDS)
                    if manifest.get(field) != current.get(field)
                ]
                if mismatched:
                    findings.append(
                        "current deterministic payload mismatch: "
                        + ", ".join(mismatched)
                    )
                for name in (
                    "source",
                    "candidate",
                    "dataset",
                    "prerequisite_fixtures",
                    "stage",
                ):
                    if not _scope_matches_current(
                        manifest.get(name),
                        repo_root,
                    ):
                        findings.append(
                            f"{name} scope differs after current replay"
                        )
    return findings


def validate_receipt(
    manifest: Mapping[str, Any],
    *,
    repo_root: Path = REPO,
    require_current: bool = False,
) -> list[str]:
    """Validate fail-closed, including adversarially malformed objects."""

    try:
        return _validate_receipt_impl(
            manifest,
            repo_root=repo_root,
            require_current=require_current,
        )
    except Exception as exc:
        return [
            "malformed composite public receipt rejected: "
            + type(exc).__name__
        ]


def _finalize(payload: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _detached(payload)
    if "manifest_checksum_sha256" in manifest:
        raise BenchmarkEvidenceError(
            "composite public payload already carries checksum"
        )
    try:
        gate = manifest["metrics"]["gates"][
            "composite_public_development_measurement_protocol_gate_passed"
        ]
    except (KeyError, TypeError) as exc:
        raise BenchmarkEvidenceError(
            "composite public measurement gate is missing"
        ) from exc
    if gate is not True:
        raise BenchmarkEvidenceError(
            "composite public measurement gate did not pass"
        )
    claims = manifest.get("claims", {})
    if (
        claims.get("public_capability_gate_evaluated") is not False
        or claims.get("public_capability_gate_passed") is not False
        or claims.get("benchmark_capability_claimed") is not False
        or claims.get("e5_gate_evaluated") is not False
        or claims.get("e5_gate_passed") is not False
        or claims.get("e5_claimed") is not False
    ):
        raise BenchmarkEvidenceError(
            "composite public capability/E5 limit changed"
        )
    manifest["manifest_checksum_sha256"] = _checksum(manifest)
    findings = validate_receipt(manifest)
    if findings:
        raise BenchmarkEvidenceError("; ".join(findings))
    return manifest


def _build_receipt_in_process(
    *,
    repo_root: Path = REPO,
) -> dict[str, Any]:
    scopes_before = _bind_scopes(repo_root)
    rows, dataset_bytes = _load_dataset(repo_root)
    prerequisites, prerequisite_manifests = _fresh_prerequisites(
        repo_root
    )
    if (
        prerequisite_manifests["atomic_public"]["dataset"]
        != scopes_before["dataset"]
        or prerequisite_manifests["scalar_public"]["dataset"]
        != scopes_before["dataset"]
        or prerequisite_manifests["composite_e4"]["dataset"]
        != scopes_before["prerequisite_fixtures"]
    ):
        raise BenchmarkEvidenceError(
            "fresh prerequisite scopes differ from bound dataset fixtures"
        )
    bundles, stage_snapshots = composite_e4._stage_bundles(repo_root)
    composite_stage_snapshots = prerequisite_manifests["composite_e4"][
        "stage_snapshots"
    ]
    if stage_snapshots != composite_stage_snapshots:
        raise BenchmarkEvidenceError(
            "current stage snapshots differ from composite E4 prerequisite"
        )
    atomic_snapshot = prerequisite_manifests["atomic_public"][
        "stage_snapshot"
    ]
    if atomic_snapshot != stage_snapshots["atomic"]:
        raise BenchmarkEvidenceError(
            "atomic public stage differs from composite stage"
        )
    scalar_snapshot = prerequisite_manifests["scalar_public"][
        "stage_snapshot"
    ]
    for field in stage_snapshots["scalar"]:
        if scalar_snapshot.get(field) != stage_snapshots["scalar"][field]:
            raise BenchmarkEvidenceError(
                "scalar public stage differs from composite stage"
            )
    adaptation_disclosure = _detached(
        prerequisite_manifests["scalar_public"][
            "adaptation_disclosure"
        ]
    )
    if (
        adaptation_disclosure
        != scalar_public._adaptation_disclosure()
        or adaptation_disclosure["disclosure_digest_sha256"]
        != prerequisites["scalar_public"][
            "adaptation_disclosure_digest_sha256"
        ]
    ):
        raise BenchmarkEvidenceError(
            "scalar adaptation disclosure binding mismatch"
        )
    scalar_native = prerequisites["scalar_public"]["selected_item"]
    items = [
        _execute_item(
            row,
            ordinal=ordinal,
            bundles=bundles,
            scalar_native=scalar_native,
        )
        for ordinal, row in enumerate(rows)
    ]
    if (
        len(items) != EXPECTED_ITEMS
        or _route_distribution(items) != EXPECTED_ROUTE_DISTRIBUTION
    ):
        raise BenchmarkEvidenceError(
            "composite public routed denominator mismatch"
        )
    selection = _selection(rows, dataset_bytes, items)
    metrics = _derive_metrics(items, prerequisites)
    closure = composite_e4._fresh_candidate_closure(repo_root)
    if closure["fresh_process_candidate_closure_exact"] is not True:
        raise BenchmarkEvidenceError(
            "fresh process candidate closure mismatch"
        )
    scopes_after = _bind_scopes(repo_root)
    changed = [
        name
        for name in scopes_before
        if scopes_before[name] != scopes_after[name]
    ]
    if changed:
        raise BenchmarkEvidenceError(
            "bound bytes changed during composite public run: "
            + ", ".join(changed)
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "protocol": _protocol(),
        "claims": _claims(metrics),
        "seal": _seal(),
        **scopes_before,
        "prerequisites": prerequisites,
        "adaptation_disclosure": adaptation_disclosure,
        "stage_snapshots": stage_snapshots,
        "selection": selection,
        "metrics": metrics,
        "items": items,
        "integrity": _integrity(metrics, prerequisites, closure),
    }
    return _finalize(payload)


def build_receipt(*, repo_root: Path = REPO) -> dict[str, Any]:
    """Build through a fresh worker and bind bytes visible outside it."""

    outer_scopes_before = _bind_scopes(repo_root)
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.science_stage_composite_mmlu_pro_receipt",
                "--internal-build-worker",
            ],
            cwd=repo_root,
            check=False,
            capture_output=True,
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BenchmarkEvidenceError(
            "fresh composite public worker failed: "
            + type(exc).__name__
        ) from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode(
            "utf-8",
            errors="replace",
        )[-3000:]
        raise BenchmarkEvidenceError(
            "fresh composite public worker exited nonzero"
            + (f": {detail}" if detail else "")
        )
    payload = completed.stdout
    if not payload or len(payload) > MAX_RECEIPT_BYTES:
        raise BenchmarkEvidenceError(
            "fresh composite public worker output size invalid"
        )
    manifest = strict_json_bytes(
        payload,
        label="fresh composite public receipt worker",
    )
    if payload != canonical_json_bytes(manifest) + b"\n":
        raise BenchmarkEvidenceError(
            "fresh composite public worker output is not canonical JSON"
        )
    outer_scopes_after = _bind_scopes(repo_root)
    changed = [
        name
        for name in outer_scopes_before
        if (
            outer_scopes_before[name] != outer_scopes_after[name]
            or manifest.get(name) != outer_scopes_before[name]
        )
    ]
    if changed:
        raise BenchmarkEvidenceError(
            "bound bytes changed across fresh composite public worker: "
            + ", ".join(changed)
        )
    findings = validate_receipt(manifest)
    if findings:
        raise BenchmarkEvidenceError("; ".join(findings))
    return manifest


def read_receipt(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise BenchmarkEvidenceError(
            "composite public receipt unreadable: "
            + type(exc).__name__
        ) from exc
    if not payload or len(payload) > MAX_RECEIPT_BYTES:
        raise BenchmarkEvidenceError(
            "composite public receipt size invalid"
        )
    manifest = strict_json_bytes(
        payload,
        label="composite public receipt",
    )
    if payload != canonical_json_bytes(manifest) + b"\n":
        raise BenchmarkEvidenceError(
            "composite public receipt is not canonical JSON with one newline"
        )
    return manifest


def write_receipt_exclusive(
    path: Path,
    manifest: Mapping[str, Any],
    *,
    repo_root: Path = REPO,
) -> None:
    findings = validate_receipt(manifest, repo_root=repo_root)
    if findings:
        raise BenchmarkEvidenceError("; ".join(findings))
    safe_path = ensure_safe_report_output(repo_root, path)
    write_manifest_exclusive(safe_path, manifest)


def _failed_verify_report(finding: str) -> dict[str, Any]:
    return {
        "valid": False,
        "structure_valid": False,
        "matches_current": False,
        "declared_sealed": False,
        "verified_sealed": False,
        "sealed": False,
        "e5_gate_passed": False,
        "public_capability_gate_passed": False,
        "checksum_sha256": None,
        "source_matches_current": False,
        "candidate_matches_current": False,
        "dataset_matches_current": False,
        "prerequisite_fixtures_matches_current": False,
        "stage_matches_current": False,
        "prerequisite_matches_current": False,
        "findings": [finding],
    }


def verify_receipt(
    path: Path,
    *,
    repo_root: Path = REPO,
    require_current: bool = True,
) -> dict[str, Any]:
    try:
        manifest = read_receipt(path)
    except BenchmarkEvidenceError as exc:
        return _failed_verify_report(str(exc))
    findings = validate_receipt(manifest, repo_root=repo_root)
    structure_valid = not findings
    scope_names = (
        "source",
        "candidate",
        "dataset",
        "prerequisite_fixtures",
        "stage",
    )
    if require_current:
        current_scopes: dict[str, bool | None] = {
            name: _scope_matches_current(manifest.get(name), repo_root)
            for name in scope_names
        }
        initial_scopes_match = all(
            value is True for value in current_scopes.values()
        )
        for name, matches in current_scopes.items():
            if not matches:
                findings.append(f"{name} scope differs from current")
        prerequisite_matches_current: bool | None = False
        try:
            expected = build_receipt(repo_root=repo_root)
        except Exception as exc:
            findings.append(
                "current composite public replay failed closed: "
                + type(exc).__name__
            )
        else:
            prerequisite_matches_current = (
                manifest.get("prerequisites")
                == expected.get("prerequisites")
            )
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
            for name in scope_names:
                current_scopes[name] = _scope_matches_current(
                    manifest.get(name),
                    repo_root,
                )
                if not current_scopes[name]:
                    findings.append(
                        f"{name} scope differs after current replay"
                    )
        matches_current: bool | None = (
            initial_scopes_match
            and all(value is True for value in current_scopes.values())
            and prerequisite_matches_current is True
            and not any(
                finding.startswith(
                    "current deterministic payload mismatch"
                )
                or finding.startswith(
                    "current composite public replay failed"
                )
                for finding in findings
            )
        )
    else:
        current_scopes = {name: None for name in scope_names}
        prerequisite_matches_current = None
        matches_current = None
    seal = manifest.get("seal")
    claims = manifest.get("claims")
    declared_sealed = (
        isinstance(seal, Mapping) and seal.get("sealed") is True
    )
    verified_sealed = (
        declared_sealed
        and require_current
        and matches_current is True
        and not findings
    )
    return {
        "valid": not findings,
        "structure_valid": structure_valid,
        "matches_current": matches_current,
        "declared_sealed": declared_sealed,
        "verified_sealed": verified_sealed,
        "sealed": verified_sealed,
        "e5_gate_passed": (
            isinstance(claims, Mapping)
            and claims.get("e5_gate_passed") is True
        ),
        "public_capability_gate_passed": (
            isinstance(claims, Mapping)
            and claims.get("public_capability_gate_passed") is True
        ),
        "checksum_sha256": manifest.get("manifest_checksum_sha256"),
        "source_matches_current": current_scopes["source"],
        "candidate_matches_current": current_scopes["candidate"],
        "dataset_matches_current": current_scopes["dataset"],
        "prerequisite_fixtures_matches_current": current_scopes[
            "prerequisite_fixtures"
        ],
        "stage_matches_current": current_scopes["stage"],
        "prerequisite_matches_current": prerequisite_matches_current,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--allow-historical", action="store_true")
    parser.add_argument(
        "--internal-build-worker",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    if args.internal_build_worker:
        if (
            args.output is not None
            or args.verify is not None
            or args.allow_historical
        ):
            raise BenchmarkEvidenceError(
                "internal worker cannot combine actions"
            )
        manifest = _build_receipt_in_process(repo_root=REPO)
        sys.stdout.buffer.write(canonical_json_bytes(manifest) + b"\n")
        return 0
    if args.verify is not None:
        if args.output is not None:
            raise BenchmarkEvidenceError(
                "--verify cannot be combined with --output"
            )
        report = verify_receipt(
            args.verify,
            repo_root=REPO,
            require_current=not args.allow_historical,
        )
        sys.stdout.buffer.write(canonical_json_bytes(report) + b"\n")
        return 0 if report["valid"] else 1
    if args.allow_historical:
        raise BenchmarkEvidenceError(
            "--allow-historical requires --verify"
        )
    manifest = build_receipt(repo_root=REPO)
    if args.output is not None:
        write_receipt_exclusive(
            args.output,
            manifest,
            repo_root=REPO,
        )
    else:
        sys.stdout.buffer.write(canonical_json_bytes(manifest) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
