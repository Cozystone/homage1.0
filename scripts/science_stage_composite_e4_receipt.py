"""Sealed E4 receipt for the routed atomic/scalar science composition."""
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
from packages.reasoning_vm.science_quantity_staging import (
    load_science_quantity_stage,
)
from packages.reasoning_vm.science_staging import load_science_stage
from scripts import science_stage_e4_receipt as atomic_e4
from scripts import science_stage_scalar_e4_receipt as scalar_e4


REPO = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = (
    "atanor.science-stage-composite-preservation-e4-receipt.v1"
)
EVIDENCE_KIND = (
    "strict_self_measured_science_composite_preservation_e4_receipt"
)
FROZEN_FIXTURE_SHA256 = (
    "61cd361e66582574dc62e2a8f4cb575b5e1f9de38785f85cce165d740a6f402a"
)
MAX_RECEIPT_BYTES = 32 * 1024 * 1024

FIXTURE_PATH = (
    "packages/reasoning_vm/tests/fixtures/"
    "science_composite_controls_e4_v1.json"
)
ATOMIC_FIXTURE_PATH = atomic_e4.FIXTURE_PATH
SCALAR_FIXTURE_PATH = scalar_e4.FIXTURE_PATH
ATOMIC_PREREQUISITE_PATH = "scripts/science_stage_e4_receipt.py"
SCALAR_PREREQUISITE_PATH = "scripts/science_stage_scalar_e4_receipt.py"

SOURCE_PATHS = tuple(
    sorted(
        {
            "packages/eval_evidence/__init__.py",
            "packages/eval_evidence/receipt.py",
            "scripts/science_stage_composite_e4_receipt.py",
            *atomic_e4.SOURCE_PATHS,
            *scalar_e4.SOURCE_PATHS,
        }
    )
)
CANDIDATE_PATHS = tuple(
    sorted(
        {
            *atomic_e4.CANDIDATE_PATHS,
            *scalar_e4.CANDIDATE_PATHS,
            "packages/reasoning_vm/science_candidate.py",
            "packages/reasoning_vm/science_route.py",
        }
    )
)
DATASET_PATHS = tuple(
    sorted({FIXTURE_PATH, ATOMIC_FIXTURE_PATH, SCALAR_FIXTURE_PATH})
)
STAGE_PATHS = tuple(
    sorted({*atomic_e4.STAGE_PATHS, *scalar_e4.STAGE_PATHS})
)
PREREQUISITE_PATHS = (
    ATOMIC_PREREQUISITE_PATH,
    SCALAR_PREREQUISITE_PATH,
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

EXPECTED_ITEMS = 27
EXPECTED_CONTROLS = 9
EXPECTED_RECLASSIFICATIONS = 3
EXPECTED_NATIVE_CONTROL_COMPARISONS = 24
EXPECTED_STAGE_CONTROLS = 5
EXPECTED_ITEM_IDS_SHA256 = (
    "379484e243dc47598122522b94d1bafe6e8dd55816cecf3777e87738ac510a5a"
)
EXPECTED_CONTROL_IDS_SHA256 = (
    "f371b092b8f85e698afc14415bae67959a8e8d4066a0d8b01ffa917e7f89bcb5"
)
RECLASSIFICATION_CONTROLS = frozenset(
    {
        ("atomic", "science-e4-negative-unsupported-001"),
        ("scalar", "scalar-control-pH"),
        ("scalar", "scalar-control-partial"),
    }
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
        "stage",
        "prerequisites",
        "fixture",
        "stage_snapshots",
        "selection",
        "metrics",
        "items",
        "controls",
        "integrity",
        "manifest_checksum_sha256",
    }
)
_SCOPE_FIELDS = frozenset({"files", "content_sha256"})
_FILE_FIELDS = frozenset({"path", "bytes", "sha256"})
_FAMILY_LEGACY_CONDITIONS = {
    "atomic": {"O": "off", "A": "on", "S": "off", "B": "on"},
    "scalar": {"O": "off", "A": "off", "S": "on", "B": "on"},
}
_ITEM_FIELDS = frozenset(
    {
        "item_id",
        "family",
        "global_ordinal",
        "family_ordinal",
        "surface_id",
        "semantic_group_id",
        "evaluator_eligible",
        "input_digest_sha256",
        "choices_digest_sha256",
        "original_mapping_read_count",
        "williams_sequence_id",
        "primary_execution_order",
        "replay_execution_order",
        "conditions",
        "legacy",
        "replay",
        "gold_absent_from_candidate_arguments",
    }
)
_CONTROL_FIELDS = frozenset(
    {
        "control_id",
        "family",
        "control_type",
        "global_ordinal",
        "family_ordinal",
        "expectation_kind",
        "evaluator_eligible",
        "input_digest_sha256",
        "choices_digest_sha256",
        "original_mapping_read_count",
        "williams_sequence_id",
        "primary_execution_order",
        "replay_execution_order",
        "conditions",
        "legacy",
        "replay",
        "contract_passed",
        "gold_absent_from_candidate_arguments",
    }
)
_CONDITION_FIELDS = frozenset(
    {
        "condition_id",
        "global_bundle_condition",
        "status",
        "choice_key",
        "correct",
        "wrong_fire",
        "compiled",
        "raw_fired",
        "accepted_fire",
        "grounded",
        "route_status",
        "route_lane",
        "route_revalidated",
        "lane_entered",
        "selected_stage_passed",
        "unselected_stage_passed",
        "fallback_attempted",
        "original_mapping_read_count",
        "native_semantic_outcome_digest_sha256",
        "routed_semantic_outcome_digest_sha256",
        "expected_legacy_condition",
        "expected_legacy_semantic_outcome_digest_sha256",
        "legacy_semantic_outcome_same",
        "proof_digest_sha256",
        "provenance_digest_sha256",
        "stage_digest_sha256",
        "reason",
        "error_kind",
    }
)
_LEGACY_FIELDS = frozenset(
    {
        "off_semantic_outcome_digest_sha256",
        "on_semantic_outcome_digest_sha256",
    }
)
_REPLAY_FIELDS = frozenset({"all_conditions_same", "conditions"})
_REPLAY_CONDITION_FIELDS = frozenset(
    {
        "semantic_outcome_same",
        "native_semantic_outcome_same",
        "replay_digest_sha256",
    }
)
_PREREQUISITE_FIELDS = frozenset(
    {
        "receipt_path",
        "schema_version",
        "manifest_checksum_sha256",
        "verified_current",
        "verified_sealed",
        "fixture_sha256",
        "stage_digest_sha256",
        "selection_digest_sha256",
        "item_semantics_digest_sha256",
        "control_semantics_digest_sha256",
        "staging_controls_digest_sha256",
        "item_count",
        "control_count",
        "e4_development_gate_passed",
        "control_probe_gate_passed",
        "candidate_controls_passed",
        "candidate_controls_all_passed",
        "staging_control_count",
        "staging_controls_passed",
        "staging_controls_all_passed",
        "benchmark_capability_claimed",
        "e5_claimed",
        "independent",
        "external_authenticity_established",
        "resource_curve_established",
    }
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _checksum(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_checksum_sha256", None)
    return _sha256(canonical_json_bytes(unsigned))


def _detached(value: Any) -> Any:
    return json.loads(canonical_json_bytes(value))


def _fixture(repo_root: Path) -> tuple[dict[str, Any], bytes]:
    path = repo_root / FIXTURE_PATH
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise BenchmarkEvidenceError(
            f"composite fixture unreadable: {type(exc).__name__}"
        ) from exc
    if _sha256(payload) != FROZEN_FIXTURE_SHA256:
        raise BenchmarkEvidenceError("composite fixture hash mismatch")
    value = strict_json_bytes(payload, label="composite control fixture")
    if payload != canonical_json_bytes(value) + b"\n":
        raise BenchmarkEvidenceError(
            "composite fixture must be canonical JSON with one newline"
        )
    if set(value) != {
        "schema_version",
        "profile_id",
        "classification",
        "source_fixture_sha256",
        "router_reclassifications",
    }:
        raise BenchmarkEvidenceError("composite fixture root fields mismatch")
    if (
        value["schema_version"] != "atanor.science-composite-controls.v1"
        or value["profile_id"] != "science-composite-preservation-e4-v1"
        or value["classification"]
        != "authored_composite_development_controls_only"
        or value["source_fixture_sha256"]
        != {
            "atomic": atomic_e4.FROZEN_FIXTURE_SHA256,
            "scalar": scalar_e4.FROZEN_FIXTURE_SHA256,
        }
    ):
        raise BenchmarkEvidenceError("composite fixture contract mismatch")
    rows = value["router_reclassifications"]
    if (
        not isinstance(rows, list)
        or len(rows) != EXPECTED_RECLASSIFICATIONS
        or len({row.get("control_id") for row in rows})
        != EXPECTED_RECLASSIFICATIONS
    ):
        raise BenchmarkEvidenceError(
            "composite reclassification denominator mismatch"
        )
    expected_fields = {
        "control_id",
        "family",
        "expected_route_status",
        "expected_lane",
        "expected_mode",
        "expected_reason",
    }
    for index, row in enumerate(rows):
        if (
            not isinstance(row, Mapping)
            or set(row) != expected_fields
            or row.get("family") not in {"atomic", "scalar"}
            or row.get("expected_route_status") != "unsupported"
            or row.get("expected_lane") is not None
            or row.get("expected_mode") != "abstain"
            or row.get("expected_reason") != "unsupported_science_profile"
        ):
            raise BenchmarkEvidenceError(
                f"composite reclassification[{index}] invalid"
            )
    if {
        (row["family"], row["control_id"]) for row in rows
    } != RECLASSIFICATION_CONTROLS:
        raise BenchmarkEvidenceError(
            "composite reclassification identities mismatch"
        )
    return value, payload


def _bind_scopes(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "source": bind_files(repo_root, SOURCE_PATHS),
        "candidate": bind_files(repo_root, CANDIDATE_PATHS),
        "dataset": bind_files(repo_root, DATASET_PATHS),
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


def _native_semantics_digest(
    rows: Sequence[Mapping[str, Any]],
) -> str:
    records = []
    for row in rows:
        conditions = row["conditions"]
        records.append(
            {
                "item_id": row["item_id"],
                "off": conditions["off"][
                    "semantic_outcome_digest_sha256"
                ],
                "on": conditions["on"][
                    "semantic_outcome_digest_sha256"
                ],
            }
        )
    return _sha256(canonical_json_bytes(records))


def _prerequisite_summary(
    family: str,
    manifest: Mapping[str, Any],
    *,
    receipt_path: str,
    repo_root: Path,
) -> dict[str, Any]:
    items = manifest["items"]
    controls = manifest["controls"]
    staging_controls = manifest["staging_controls"]
    if family == "atomic":
        leaf_e4_gate = manifest["metrics"][
            "e4_development_gate_passed"
        ]
        leaf_control_metrics = manifest["metrics"]["control_probes"]
        leaf_control_gate = leaf_control_metrics[
            "control_probe_gate_passed"
        ]
        candidate_all = (
            leaf_control_gate
            and leaf_control_metrics["candidate"]["n"] == len(controls)
        )
        staging_all = (
            leaf_control_gate
            and leaf_control_metrics["staging"]["n"]
            == len(staging_controls)
        )
    else:
        leaf_e4_gate = manifest["metrics"][
            "e4_development_gate_passed"
        ]
        leaf_control_metrics = manifest["metrics"]["controls"]
        leaf_control_gate = leaf_control_metrics[
            "control_probe_gate_passed"
        ]
        candidate_all = leaf_control_metrics[
            "candidate_controls_all_passed"
        ]
        staging_all = leaf_control_metrics[
            "staging_controls_all_passed"
        ]
    scopes_current = all(
        (
            atomic_e4._scope_matches_current
            if family == "atomic"
            else scalar_e4._scope_matches_current
        )(manifest[name], repo_root)
        for name in ("source", "candidate", "dataset", "stage")
    )
    limitations_hold = (
        manifest["claims"]["benchmark_capability_claimed"] is False
        and manifest["claims"]["e5_claimed"] is False
        and manifest["claims"]["independent"] is False
        and manifest["seal"]["authenticity_established"] is False
        and manifest["claims"]["process_resource_curve_claimed"] is False
    )
    verified_sealed = (
        scopes_current
        and manifest["seal"]["sealed"] is True
        and leaf_e4_gate is True
        and leaf_control_gate is True
        and candidate_all is True
        and staging_all is True
        and limitations_hold
    )
    return {
        "receipt_path": receipt_path,
        "schema_version": manifest["schema_version"],
        "manifest_checksum_sha256": manifest[
            "manifest_checksum_sha256"
        ],
        "verified_current": scopes_current,
        "verified_sealed": verified_sealed,
        "fixture_sha256": manifest["fixture"]["actual_sha256"],
        "stage_digest_sha256": manifest["stage_snapshot"][
            "stage_digest_sha256"
        ],
        "selection_digest_sha256": _sha256(
            canonical_json_bytes(manifest["selection"])
        ),
        "item_semantics_digest_sha256": _native_semantics_digest(items),
        "control_semantics_digest_sha256": _native_semantics_digest(
            controls
        ),
        "staging_controls_digest_sha256": _sha256(
            canonical_json_bytes(staging_controls)
        ),
        "item_count": len(items),
        "control_count": len(controls),
        "e4_development_gate_passed": leaf_e4_gate is True,
        "control_probe_gate_passed": leaf_control_gate is True,
        "candidate_controls_passed": (
            len(controls) if candidate_all is True else 0
        ),
        "candidate_controls_all_passed": candidate_all is True,
        "staging_control_count": len(staging_controls),
        "staging_controls_passed": (
            len(staging_controls) if staging_all is True else 0
        ),
        "staging_controls_all_passed": staging_all is True,
        "benchmark_capability_claimed": False,
        "e5_claimed": False,
        "independent": False,
        "external_authenticity_established": False,
        "resource_curve_established": False,
    }


def _fresh_prerequisites(
    repo_root: Path,
) -> tuple[
    dict[str, Any],
    dict[str, Mapping[str, Any]],
]:
    atomic = atomic_e4.build_receipt(repo_root=repo_root)
    atomic_findings = atomic_e4.validate_receipt(
        atomic,
        repo_root=repo_root,
        require_current=True,
    )
    if atomic_findings:
        raise BenchmarkEvidenceError(
            "atomic prerequisite invalid: " + "; ".join(atomic_findings)
        )
    scalar = scalar_e4.build_receipt(repo_root=repo_root)
    scalar_findings = scalar_e4.validate_receipt(scalar)
    if scalar_findings:
        raise BenchmarkEvidenceError(
            "scalar prerequisite invalid: " + "; ".join(scalar_findings)
        )
    summaries = {
        "scope": (
            "fresh current prerequisite receipts rebuilt and validated "
            "inside the composite worker; no report file is trusted"
        ),
        "atomic": _prerequisite_summary(
            "atomic",
            atomic,
            receipt_path=ATOMIC_PREREQUISITE_PATH,
            repo_root=repo_root,
        ),
        "scalar": _prerequisite_summary(
            "scalar",
            scalar,
            receipt_path=SCALAR_PREREQUISITE_PATH,
            repo_root=repo_root,
        ),
    }
    if not all(
        summaries[name]["verified_current"]
        and summaries[name]["verified_sealed"]
        for name in ("atomic", "scalar")
    ):
        raise BenchmarkEvidenceError("prerequisite seal/current gate failed")
    return summaries, {"atomic": atomic, "scalar": scalar}


def _legacy_index(
    manifests: Mapping[str, Mapping[str, Any]],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    index: dict[tuple[str, str], Mapping[str, Any]] = {}
    for family in ("atomic", "scalar"):
        manifest = manifests[family]
        for row in (*manifest["items"], *manifest["controls"]):
            key = (family, row["item_id"])
            if key in index:
                raise BenchmarkEvidenceError(
                    "duplicate prerequisite semantic identity"
                )
            index[key] = row
    return index


def _stage_bundles(
    repo_root: Path,
) -> tuple[dict[str, ScienceStageBundle], dict[str, Any]]:
    atomic = load_science_stage(repo_root / atomic_e4.STAGE_ROOT)
    scalar = load_science_quantity_stage(repo_root / scalar_e4.STAGE_ROOT)
    return (
        {
            "O": ScienceStageBundle(),
            "A": ScienceStageBundle(atomic_stage=atomic),
            "S": ScienceStageBundle(scalar_stage=scalar),
            "B": ScienceStageBundle(
                atomic_stage=atomic,
                scalar_stage=scalar,
            ),
        },
        {
            "atomic": {
                "stage_id": atomic.stage_id,
                "stage_digest_sha256": atomic.stage_digest_sha256,
                "manifest_checksum_sha256": (
                    atomic.manifest_checksum_sha256
                ),
                "bound_bytes": atomic.bound_bytes,
                "row_count": len(atomic.facts),
            },
            "scalar": {
                "stage_id": scalar.stage_id,
                "stage_digest_sha256": scalar.stage_digest_sha256,
                "manifest_checksum_sha256": (
                    scalar.manifest_checksum_sha256
                ),
                "bound_bytes": scalar.bound_bytes,
                "species_count": len(scalar.species),
                "formula_count": len(scalar.formulas),
                "external_authenticity_established": False,
            },
        },
    )


def _routed_semantics(outcome: Mapping[str, Any]) -> dict[str, Any]:
    route = outcome.get("route")
    condition = outcome.get("condition")
    lane = outcome.get("lane")
    integrity = outcome.get("integrity")
    return {
        "schema_version": outcome.get("schema_version"),
        "input_digest_sha256": outcome.get("input_digest_sha256"),
        "choices_digest_sha256": outcome.get("choices_digest_sha256"),
        "original_mapping_read_count": outcome.get(
            "original_mapping_read_count"
        ),
        "choice_key": outcome.get("choice_key"),
        "mode": outcome.get("mode"),
        "reason": outcome.get("reason"),
        "error_kind": outcome.get("error_kind"),
        "route": {
            "decision": (
                route.get("decision")
                if isinstance(route, Mapping)
                else None
            ),
            "revalidated": (
                route.get("revalidated")
                if isinstance(route, Mapping)
                else False
            ),
        },
        "condition": {
            "global_bundle_condition": (
                condition.get("global_bundle_condition")
                if isinstance(condition, Mapping)
                else None
            ),
            "selected_lane_overlay_enabled": (
                condition.get("selected_lane_overlay_enabled")
                if isinstance(condition, Mapping)
                else False
            ),
        },
        "lane": {
            key: lane.get(key) if isinstance(lane, Mapping) else None
            for key in (
                "selected",
                "entered",
                "atomic_invoked",
                "scalar_invoked",
                "selected_stage_passed",
                "unselected_stage_passed",
                "fallback_attempted",
                "semantic_outcome_digest_sha256",
            )
        },
        "integrity": {
            key: (
                integrity.get(key)
                if isinstance(integrity, Mapping)
                else None
            )
            for key in (
                "prepared_input_exact_type",
                "choice_snapshot_immutable",
                "route_revalidated",
                "choices_digest_bound",
                "original_mapping_read_count",
                "gold_in_candidate_payload",
                "benchmark_metadata_in_candidate_payload",
                "selected_lane_only",
                "unselected_stage_passed",
                "fallback_attempted",
            )
        },
    }


def _run_condition(
    prepared: Any,
    condition_id: str,
    bundles: Mapping[str, ScienceStageBundle],
) -> dict[str, Any]:
    empty_base_digest = atomic_e4._base_digest({})
    return answer_prepared_science_candidate(
        prepared,
        bundles[condition_id],
        base_facts=lambda _subject: [],
        base_state_digest=lambda: empty_base_digest,
    )


def _condition_record(
    outcome: Mapping[str, Any],
    *,
    family: str,
    condition_id: str,
    gold: str | None,
    expected_legacy_digest: str,
) -> dict[str, Any]:
    route = outcome.get("route", {})
    decision = route.get("decision")
    condition = outcome.get("condition", {})
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
    elif gold is not None and choice_key == gold:
        status = "correct"
    else:
        status = "wrong"
    native_digest = lane.get("semantic_outcome_digest_sha256")
    return {
        "condition_id": condition_id,
        "global_bundle_condition": CONDITION_BUNDLE_LABELS[condition_id],
        "status": status,
        "choice_key": choice_key,
        "correct": status == "correct",
        "wrong_fire": status == "wrong",
        "compiled": compiler.get("compiled") is True,
        "raw_fired": engine.get("raw_fired") is True,
        "accepted_fire": engine.get("accepted_fire") is True,
        "grounded": engine.get("grounded") is True,
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
            canonical_json_bytes(_routed_semantics(outcome))
        ),
        "expected_legacy_condition": (
            _FAMILY_LEGACY_CONDITIONS[family][condition_id]
        ),
        "expected_legacy_semantic_outcome_digest_sha256": (
            expected_legacy_digest
        ),
        "legacy_semantic_outcome_same": (
            native_digest == expected_legacy_digest
        ),
        "proof_digest_sha256": engine.get("proof_digest_sha256"),
        "provenance_digest_sha256": staging.get(
            "provenance_digest_sha256"
        ),
        "stage_digest_sha256": staging.get("stage_digest_sha256"),
        "reason": outcome.get("reason"),
        "error_kind": error_kind,
    }


def _condition_behavior_digest(record: Mapping[str, Any]) -> str:
    return _sha256(
        canonical_json_bytes(
            {
                key: record.get(key)
                for key in (
                    "status",
                    "choice_key",
                    "correct",
                    "wrong_fire",
                    "compiled",
                    "raw_fired",
                    "accepted_fire",
                    "grounded",
                    "route_status",
                    "route_lane",
                    "route_revalidated",
                    "lane_entered",
                    "selected_stage_passed",
                    "unselected_stage_passed",
                    "fallback_attempted",
                    "original_mapping_read_count",
                    "native_semantic_outcome_digest_sha256",
                    "proof_digest_sha256",
                    "provenance_digest_sha256",
                    "stage_digest_sha256",
                    "error_kind",
                )
            }
        )
    )


def _execute_row(
    row: Mapping[str, Any],
    *,
    family: str,
    family_ordinal: int,
    global_ordinal: int,
    legacy_row: Mapping[str, Any],
    bundles: Mapping[str, ScienceStageBundle],
    control_type: str | None = None,
    reclassification: Mapping[str, Any] | None = None,
    order_ordinal: int | None = None,
) -> dict[str, Any]:
    prepared = prepare_science_input(row["question"], row["choices"])
    sequence_index = (
        family_ordinal if order_ordinal is None else order_ordinal
    ) % len(WILLIAMS_SEQUENCES)
    primary_order = list(WILLIAMS_SEQUENCES[sequence_index])
    replay_order = list(reversed(primary_order))
    primary_outcomes = {
        condition_id: _run_condition(prepared, condition_id, bundles)
        for condition_id in primary_order
    }
    replay_outcomes = {
        condition_id: _run_condition(prepared, condition_id, bundles)
        for condition_id in replay_order
    }
    gold = row.get("gold") if control_type is None else None
    conditions: dict[str, dict[str, Any]] = {}
    replay_records: dict[str, dict[str, Any]] = {}
    for condition_id in CONDITION_IDS:
        legacy_condition = _FAMILY_LEGACY_CONDITIONS[family][condition_id]
        legacy_digest = legacy_row["conditions"][legacy_condition][
            "semantic_outcome_digest_sha256"
        ]
        conditions[condition_id] = _condition_record(
            primary_outcomes[condition_id],
            family=family,
            condition_id=condition_id,
            gold=gold,
            expected_legacy_digest=legacy_digest,
        )
        replay_record = _condition_record(
            replay_outcomes[condition_id],
            family=family,
            condition_id=condition_id,
            gold=gold,
            expected_legacy_digest=legacy_digest,
        )
        replay_records[condition_id] = {
            "semantic_outcome_same": (
                replay_record[
                    "routed_semantic_outcome_digest_sha256"
                ]
                == conditions[condition_id][
                    "routed_semantic_outcome_digest_sha256"
                ]
            ),
            "native_semantic_outcome_same": (
                replay_record[
                    "native_semantic_outcome_digest_sha256"
                ]
                == conditions[condition_id][
                    "native_semantic_outcome_digest_sha256"
                ]
            ),
            "replay_digest_sha256": replay_record[
                "routed_semantic_outcome_digest_sha256"
            ],
        }
    base = {
        "family": family,
        "global_ordinal": global_ordinal,
        "family_ordinal": family_ordinal,
        "evaluator_eligible": control_type is None,
        "input_digest_sha256": prepared.input_digest_sha256,
        "choices_digest_sha256": prepared.choices_digest_sha256,
        "original_mapping_read_count": (
            prepared.original_mapping_read_count
        ),
        "williams_sequence_id": f"W{sequence_index}",
        "primary_execution_order": primary_order,
        "replay_execution_order": replay_order,
        "conditions": conditions,
        "legacy": {
            "off_semantic_outcome_digest_sha256": legacy_row[
                "conditions"
            ]["off"]["semantic_outcome_digest_sha256"],
            "on_semantic_outcome_digest_sha256": legacy_row["conditions"][
                "on"
            ]["semantic_outcome_digest_sha256"],
        },
        "replay": {
            "all_conditions_same": all(
                record["semantic_outcome_same"]
                and record["native_semantic_outcome_same"]
                for record in replay_records.values()
            ),
            "conditions": replay_records,
        },
        "gold_absent_from_candidate_arguments": True,
    }
    if control_type is None:
        return {
            "item_id": row["id"],
            **base,
            "surface_id": row["surface_id"],
            "semantic_group_id": row.get("semantic_group_id"),
        }
    expectation_kind = (
        "router_reclassification"
        if reclassification is not None
        else "legacy_native"
    )
    if reclassification is None:
        contract_passed = (
            all(
                record["legacy_semantic_outcome_same"]
                for record in conditions.values()
            )
            and base["replay"]["all_conditions_same"]
        )
    else:
        contract_passed = (
            all(
                record["route_status"]
                == reclassification["expected_route_status"]
                and record["route_lane"]
                == reclassification["expected_lane"]
                and record["status"] == reclassification["expected_mode"]
                and record["reason"]
                == reclassification["expected_reason"]
                and record["error_kind"] is None
                and record["choice_key"] is None
                and record["compiled"] is False
                and record["raw_fired"] is False
                and record["accepted_fire"] is False
                and record["grounded"] is False
                and record["lane_entered"] is False
                and record["selected_stage_passed"] is False
                and record["fallback_attempted"] is False
                for record in conditions.values()
            )
            and base["replay"]["all_conditions_same"]
        )
    return {
        "control_id": row["id"],
        **base,
        "control_type": control_type,
        "expectation_kind": expectation_kind,
        "contract_passed": contract_passed,
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 12)


def _condition_metrics(
    rows: Sequence[Mapping[str, Any]],
    condition_id: str,
) -> dict[str, Any]:
    records = [row["conditions"][condition_id] for row in rows]
    counts = Counter(record["status"] for record in records)
    n = len(records)
    return {
        "n": n,
        "correct": counts["correct"],
        "wrong": counts["wrong"],
        "abstain": counts["abstain"],
        "error": counts["error"],
        "compiled": sum(record["compiled"] is True for record in records),
        "raw_fired": sum(
            record["raw_fired"] is True for record in records
        ),
        "accepted_fired": sum(
            record["accepted_fire"] is True for record in records
        ),
        "grounded": sum(
            record["grounded"] is True for record in records
        ),
        "strict_accuracy": _ratio(counts["correct"], n),
        "wrong_fire_rate": _ratio(counts["wrong"], n),
        "raw_firing_rate": _ratio(
            sum(record["raw_fired"] is True for record in records),
            n,
        ),
        "accepted_firing_rate": _ratio(
            sum(record["accepted_fire"] is True for record in records),
            n,
        ),
        "grounded_coverage": _ratio(
            sum(record["grounded"] is True for record in records),
            n,
        ),
    }


def _order_balance(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    assignments = Counter(row["williams_sequence_id"] for row in rows)
    positions = {
        condition_id: [0, 0, 0, 0] for condition_id in CONDITION_IDS
    }
    directed_carryover: Counter[tuple[str, str]] = Counter()
    reverse_exact = True
    for row in rows:
        order = row["primary_execution_order"]
        reverse_exact = reverse_exact and (
            row["replay_execution_order"] == list(reversed(order))
        )
        for position, condition_id in enumerate(order):
            positions[condition_id][position] += 1
        directed_carryover.update(zip(order, order[1:]))
        replay_order = row["replay_execution_order"]
        directed_carryover.update(zip(replay_order, replay_order[1:]))
    position_spread = max(
        max(counts) - min(counts) for counts in positions.values()
    )
    directed_counts = {
        f"{left}->{right}": directed_carryover[(left, right)]
        for left in CONDITION_IDS
        for right in CONDITION_IDS
        if left != right
    }
    directed_spread = max(directed_counts.values()) - min(
        directed_counts.values()
    )
    return {
        "row_count": len(rows),
        "williams_sequence_counts": {
            key: assignments[key] for key in ("W0", "W1", "W2", "W3")
        },
        "condition_position_counts": positions,
        "maximum_position_imbalance": position_spread,
        "directed_carryover_counts_primary_plus_reverse": directed_counts,
        "maximum_directed_carryover_imbalance": directed_spread,
        "reverse_replay_exact_all": reverse_exact,
        "counterbalance_gate_passed": (
            reverse_exact
            and max(assignments.values()) - min(assignments.values()) <= 1
            and position_spread <= 1
            and directed_spread <= 1
        ),
    }


def _derive_metrics(
    items: Sequence[Mapping[str, Any]],
    controls: Sequence[Mapping[str, Any]],
    prerequisites: Mapping[str, Any],
) -> dict[str, Any]:
    by_family = {
        family: [row for row in items if row["family"] == family]
        for family in ("atomic", "scalar")
    }
    capability = {
        "all_items": {
            condition_id: _condition_metrics(items, condition_id)
            for condition_id in CONDITION_IDS
        },
        "by_family": {
            family: {
                condition_id: _condition_metrics(rows, condition_id)
                for condition_id in CONDITION_IDS
            }
            for family, rows in by_family.items()
        },
    }
    all_item_conditions = [
        record
        for row in items
        for record in row["conditions"].values()
    ]
    all_control_conditions = [
        record
        for row in controls
        for record in row["conditions"].values()
    ]
    all_primary_conditions = [
        *all_item_conditions,
        *all_control_conditions,
    ]
    replay_comparisons = [
        replay
        for row in (*items, *controls)
        for replay in row["replay"]["conditions"].values()
    ]
    mechanism = {
        "primary_item_condition_executions": len(all_item_conditions),
        "replay_item_condition_executions": len(items) * 4,
        "primary_control_condition_executions": len(controls) * 4,
        "replay_control_condition_executions": len(controls) * 4,
        "compiled": sum(row["compiled"] for row in all_item_conditions),
        "raw_fired": sum(row["raw_fired"] for row in all_item_conditions),
        "accepted_fired": sum(
            row["accepted_fire"] for row in all_item_conditions
        ),
        "item_primary_routes_revalidated": sum(
            row["route_revalidated"] for row in all_item_conditions
        ),
        "control_primary_routes_revalidated": sum(
            row["route_revalidated"] for row in all_control_conditions
        ),
        "primary_routes_revalidated": sum(
            row["route_revalidated"] for row in all_primary_conditions
        ),
        "main_source_mapping_reads": sum(
            row["original_mapping_read_count"] for row in items
        ),
        "main_prepared_condition_executions": len(items) * 8,
        "control_source_mapping_reads": sum(
            row["original_mapping_read_count"] for row in controls
        ),
        "control_prepared_condition_executions": len(controls) * 8,
        "source_mapping_read_once_per_row_all": all(
            row["original_mapping_read_count"] == 1
            for row in (*items, *controls)
        ),
        "semantic_replay_comparisons": len(replay_comparisons),
        "semantic_replay_matches": sum(
            row["semantic_outcome_same"]
            and row["native_semantic_outcome_same"]
            for row in replay_comparisons
        ),
    }
    mechanism["mechanism_gate_passed"] = (
        mechanism["main_source_mapping_reads"] == EXPECTED_ITEMS
        and mechanism["control_source_mapping_reads"] == EXPECTED_CONTROLS
        and mechanism["main_prepared_condition_executions"]
        == EXPECTED_ITEMS * 8
        and mechanism["control_prepared_condition_executions"]
        == EXPECTED_CONTROLS * 8
        and mechanism["primary_item_condition_executions"]
        == EXPECTED_ITEMS * 4
        and mechanism["replay_item_condition_executions"]
        == EXPECTED_ITEMS * 4
        and mechanism["primary_control_condition_executions"]
        == EXPECTED_CONTROLS * 4
        and mechanism["replay_control_condition_executions"]
        == EXPECTED_CONTROLS * 4
        and mechanism["primary_routes_revalidated"]
        == (EXPECTED_ITEMS + EXPECTED_CONTROLS) * 4
        and mechanism["source_mapping_read_once_per_row_all"]
    )
    item_legacy = [
        record["legacy_semantic_outcome_same"]
        for row in items
        for record in row["conditions"].values()
    ]
    native_controls = [
        row
        for row in controls
        if row["expectation_kind"] == "legacy_native"
    ]
    native_control_legacy = [
        record["legacy_semantic_outcome_same"]
        for row in native_controls
        for record in row["conditions"].values()
    ]
    preservation = {
        "item_legacy_comparisons": len(item_legacy),
        "item_legacy_semantics_same": sum(item_legacy),
        "native_control_comparisons": len(native_control_legacy),
        "native_control_semantics_same": sum(native_control_legacy),
        "preservation_gate_passed": (
            len(item_legacy) == EXPECTED_ITEMS * 4
            and all(item_legacy)
            and len(native_control_legacy)
            == EXPECTED_NATIVE_CONTROL_COMPARISONS
            and all(native_control_legacy)
        ),
    }
    irrelevant_pairs = {
        "atomic": (("O", "S"), ("A", "B")),
        "scalar": (("O", "A"), ("S", "B")),
    }
    interaction_results = []
    factorial_correct_interactions = []
    for row in items:
        for left, right in irrelevant_pairs[row["family"]]:
            interaction_results.append(
                _condition_behavior_digest(row["conditions"][left])
                == _condition_behavior_digest(row["conditions"][right])
            )
        factorial_correct_interactions.append(
            int(row["conditions"]["B"]["correct"])
            - int(row["conditions"]["A"]["correct"])
            - int(row["conditions"]["S"]["correct"])
            + int(row["conditions"]["O"]["correct"])
        )
    interaction = {
        "irrelevant_stage_comparisons": len(interaction_results),
        "irrelevant_stage_semantics_same": sum(interaction_results),
        "cross_lane_interference_observed": (
            len(interaction_results) - sum(interaction_results)
        ),
        "factorial_correct_interaction_zero_count": sum(
            value == 0 for value in factorial_correct_interactions
        ),
        "factorial_correct_interaction_values": (
            factorial_correct_interactions
        ),
        "both_matches_legacy_on_count": sum(
            row["conditions"]["B"]["legacy_semantic_outcome_same"]
            for row in items
        ),
        "unselected_stage_passed_count": sum(
            record["unselected_stage_passed"]
            for row in (*items, *controls)
            for record in row["conditions"].values()
        ),
        "fallback_attempted_count": sum(
            record["fallback_attempted"]
            for row in (*items, *controls)
            for record in row["conditions"].values()
        ),
        "interaction_gate_passed": (
            len(interaction_results) == EXPECTED_ITEMS * 2
            and all(interaction_results)
            and all(value == 0 for value in factorial_correct_interactions)
            and all(
                row["conditions"]["B"]["legacy_semantic_outcome_same"]
                for row in items
            )
            and all(
                not record["unselected_stage_passed"]
                and not record["fallback_attempted"]
                for row in (*items, *controls)
                for record in row["conditions"].values()
            )
        ),
    }
    reclassified = [
        row
        for row in controls
        if row["expectation_kind"] == "router_reclassification"
    ]
    stage_control_count = sum(
        prerequisites[family]["staging_control_count"]
        for family in ("atomic", "scalar")
    )
    control_metrics = {
        "candidate_control_count": len(controls),
        "legacy_native_control_count": len(native_controls),
        "router_reclassification_control_count": len(reclassified),
        "router_reclassification_condition_comparisons": (
            len(reclassified) * 4
        ),
        "candidate_controls_passed": sum(
            row["contract_passed"] for row in controls
        ),
        "staging_control_count": stage_control_count,
        "prerequisite_staging_controls_digest_bound": all(
            _SHA256.fullmatch(
                prerequisites[family][
                    "staging_controls_digest_sha256"
                ]
            )
            is not None
            for family in ("atomic", "scalar")
        ),
        "control_probe_gate_passed": (
            len(controls) == EXPECTED_CONTROLS
            and len(native_controls)
            == EXPECTED_CONTROLS - EXPECTED_RECLASSIFICATIONS
            and len(reclassified) == EXPECTED_RECLASSIFICATIONS
            and all(row["contract_passed"] for row in controls)
            and stage_control_count == EXPECTED_STAGE_CONTROLS
        ),
    }
    item_order = _order_balance(items)
    control_order = _order_balance(controls)
    order_balance = {
        "items": item_order,
        "controls": control_order,
        "order_gate_passed": (
            item_order["counterbalance_gate_passed"]
            and control_order["counterbalance_gate_passed"]
        ),
    }
    prerequisite_gate = all(
        prerequisites[family]["verified_current"]
        and prerequisites[family]["verified_sealed"]
        and prerequisites[family]["e4_development_gate_passed"]
        and prerequisites[family]["control_probe_gate_passed"]
        and prerequisites[family]["candidate_controls_all_passed"]
        and prerequisites[family]["staging_controls_all_passed"]
        and prerequisites[family]["candidate_controls_passed"]
        == prerequisites[family]["control_count"]
        and prerequisites[family]["staging_controls_passed"]
        == prerequisites[family]["staging_control_count"]
        and prerequisites[family]["benchmark_capability_claimed"] is False
        and prerequisites[family]["e5_claimed"] is False
        and prerequisites[family]["independent"] is False
        and prerequisites[family]["external_authenticity_established"]
        is False
        and prerequisites[family]["resource_curve_established"] is False
        for family in ("atomic", "scalar")
    )
    replay_gate = (
        mechanism["semantic_replay_comparisons"]
        == (EXPECTED_ITEMS + EXPECTED_CONTROLS) * 4
        and mechanism["semantic_replay_matches"]
        == mechanism["semantic_replay_comparisons"]
    )
    gates = {
        "prerequisite_gate_passed": prerequisite_gate,
        "mechanism_gate_passed": mechanism["mechanism_gate_passed"],
        "replay_gate_passed": replay_gate,
        "preservation_gate_passed": preservation[
            "preservation_gate_passed"
        ],
        "interaction_gate_passed": interaction[
            "interaction_gate_passed"
        ],
        "control_probe_gate_passed": control_metrics[
            "control_probe_gate_passed"
        ],
        "order_gate_passed": order_balance["order_gate_passed"],
        "composite_e4_development_gate_passed": all(
            (
                prerequisite_gate,
                mechanism["mechanism_gate_passed"],
                replay_gate,
                preservation["preservation_gate_passed"],
                interaction["interaction_gate_passed"],
                control_metrics["control_probe_gate_passed"],
                order_balance["order_gate_passed"],
            )
        ),
        "public_capability_gate_passed": False,
        "public_capability_gate_evaluated": False,
    }
    return {
        "capability": capability,
        "mechanism": mechanism,
        "preservation": preservation,
        "interaction": interaction,
        "controls": control_metrics,
        "order_balance": order_balance,
        "gates": gates,
        "inference": {
            "development_preservation_interaction_only": True,
            "independent_evaluation": False,
            "hidden_holdout": False,
            "external_authenticity": False,
            "public_capability_inference": False,
            "e5_inference": False,
            "resource_curve_inference": False,
        },
    }


def _selection(
    items: Sequence[Mapping[str, Any]],
    controls: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    item_ids = [row["item_id"] for row in items]
    control_ids = [row["control_id"] for row in controls]
    assignments = [
        {
            "id": row.get("item_id", row.get("control_id")),
            "sequence_id": row["williams_sequence_id"],
            "primary_execution_order": row["primary_execution_order"],
        }
        for row in (*items, *controls)
    ]
    return {
        "scope": (
            "fixed union of the 15 atomic and 12 scalar E4 prerequisite "
            "items plus all nine native controls"
        ),
        "evaluator_owned_fixed_denominator": True,
        "expected_item_count": EXPECTED_ITEMS,
        "actual_item_count": len(items),
        "family_counts": {
            family: sum(row["family"] == family for row in items)
            for family in ("atomic", "scalar")
        },
        "item_ids": item_ids,
        "item_ids_sha256": _sha256(canonical_json_bytes(item_ids)),
        "expected_control_count": EXPECTED_CONTROLS,
        "actual_control_count": len(controls),
        "control_ids": control_ids,
        "control_ids_sha256": _sha256(
            canonical_json_bytes(control_ids)
        ),
        "condition_ids": list(CONDITION_IDS),
        "condition_bundle_labels": dict(CONDITION_BUNDLE_LABELS),
        "williams_sequences": [list(row) for row in WILLIAMS_SEQUENCES],
        "order_assignment_sha256": _sha256(
            canonical_json_bytes(assignments)
        ),
        "inferential_independence_claimed": False,
    }


def _fresh_candidate_closure(repo_root: Path) -> dict[str, Any]:
    code = r"""
import json
import sys
from pathlib import Path
from packages.reasoning_vm.science_candidate import (
    ScienceStageBundle,
    answer_prepared_science_candidate,
    prepare_science_input,
)
from packages.reasoning_vm.science_staging import load_science_stage
from packages.reasoning_vm.science_quantity_staging import (
    load_science_quantity_stage,
)
root = Path.cwd().resolve()
atomic = load_science_stage(
    root / "packages/reasoning_vm/tests/fixtures/science_stage_atomic_number_v1"
)
scalar = load_science_quantity_stage(
    root / "packages/reasoning_vm/tests/fixtures/science_stage_scalar_quantity_v1"
)
examples = (
    (
        "What is the atomic number of hydrogen?",
        {"A": "1", "B": "2"},
    ),
    (
        "What volume of 0.30 M NaOH is required to completely neutralize "
        "25.0 mL of 0.18 M HCl?",
        {"A": "12 mL", "B": "15 mL"},
    ),
)
for stem, choices in examples:
    prepared = prepare_science_input(stem, choices)
    answer_prepared_science_candidate(
        prepared,
        ScienceStageBundle(atomic_stage=atomic, scalar_stage=scalar),
        base_facts=lambda _subject: [],
        base_state_digest=lambda: (
            "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
        ),
    )
paths = set()
for module in tuple(sys.modules.values()):
    value = getattr(module, "__file__", None)
    if not value:
        continue
    try:
        relative = Path(value).resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        continue
    if relative.endswith(".py"):
        paths.add(relative)
sys.stdout.buffer.write(
    json.dumps(sorted(paths), separators=(",", ":")).encode("utf-8")
    + b"\n"
)
"""
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo_root,
            check=False,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BenchmarkEvidenceError(
            f"candidate closure worker failed: {type(exc).__name__}"
        ) from exc
    if completed.returncode != 0:
        raise BenchmarkEvidenceError(
            "candidate closure worker exited nonzero"
        )
    try:
        paths = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BenchmarkEvidenceError(
            "candidate closure worker output invalid"
        ) from exc
    expected = list(CANDIDATE_PATHS)
    if (
        not isinstance(paths, list)
        or not all(isinstance(path, str) for path in paths)
        or paths != sorted(set(paths))
        or completed.stdout
        != canonical_json_bytes(paths) + b"\n"
    ):
        raise BenchmarkEvidenceError(
            "candidate closure worker output not canonical"
        )
    return {
        "fresh_process_candidate_closure_expected_path_count": len(
            expected
        ),
        "fresh_process_candidate_closure_actual_path_count": len(paths),
        "fresh_process_candidate_closure_paths_sha256": _sha256(
            canonical_json_bytes(paths)
        ),
        "fresh_process_candidate_closure_exact": paths == expected,
    }


def _protocol() -> dict[str, Any]:
    return {
        "name": "science_composite_preservation_factorial_e4_v1",
        "development_only": True,
        "fresh_process_build_enforced": True,
        "fresh_prerequisite_rebuild_enforced": True,
        "report_file_prerequisites_trusted": False,
        "candidate_prepare_once_per_row": True,
        "prepared_input_reused_across_conditions_and_replay": True,
        "condition_ids": list(CONDITION_IDS),
        "condition_bundle_labels": dict(CONDITION_BUNDLE_LABELS),
        "williams_sequences": [list(row) for row in WILLIAMS_SEQUENCES],
        "sequence_assignment": (
            "main_family_ordinal_mod_4; controls_global_control_ordinal_mod_4"
        ),
        "reverse_replay_enforced": True,
        "selected_lane_only": True,
        "cross_lane_fallback_allowed": False,
        "gold_passed_to_candidate": False,
        "process_resource_telemetry_recorded": False,
        "public_capability_gate_evaluated": False,
        "e5_claimed": False,
    }


def _claims(metrics: Mapping[str, Any]) -> dict[str, Any]:
    gates = metrics["gates"]
    return {
        "classification": (
            "bounded_routed_atomic_scalar_preservation_interaction_"
            "e4_development_only"
        ),
        "development_only": True,
        "e4_development_evidence": True,
        "e4_development_gate_passed": gates[
            "composite_e4_development_gate_passed"
        ],
        "mechanism_evidence": True,
        "mechanism_gate_passed": gates["mechanism_gate_passed"],
        "preservation_evidence": True,
        "preservation_gate_passed": gates[
            "preservation_gate_passed"
        ],
        "interaction_evidence": True,
        "interaction_gate_passed": gates["interaction_gate_passed"],
        "control_probe_evidence": True,
        "control_probe_gate_passed": gates[
            "control_probe_gate_passed"
        ],
        "public_capability_gate_evaluated": False,
        "public_capability_gate_passed": False,
        "public_capability_evidence": False,
        "e5_claimed": False,
        "e5_equivalent": False,
        "independent": False,
        "independent_evaluation_claimed": False,
        "externally_signed": False,
        "hidden_holdout_claimed": False,
        "external_authenticity_established": False,
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
            "exact current composite evaluator/candidate/dataset/stage "
            "bytes + fresh validated atomic/scalar prerequisite receipts + "
            "prepare-once four-condition Williams/reverse semantic replay + "
            "legacy preservation, lane interaction, and control gates + "
            "recomputable checksum"
        ),
        "git_clean_required": False,
        "hidden_holdout_claimed": False,
        "independent_evaluation_claimed": False,
        "authenticity_established": False,
        "public_capability_established": False,
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
    gates = metrics["gates"]
    mechanism = metrics["mechanism"]
    return {
        "source_same_before_after": True,
        "candidate_same_before_after": True,
        "dataset_same_before_after": True,
        "stage_same_before_after": True,
        "fixture_matches_frozen_hash": True,
        "source_fixtures_match_prerequisites": True,
        "prerequisites_fresh_current_and_sealed": gates[
            "prerequisite_gate_passed"
        ],
        "atomic_prerequisite_checksum_sha256": prerequisites["atomic"][
            "manifest_checksum_sha256"
        ],
        "scalar_prerequisite_checksum_sha256": prerequisites["scalar"][
            "manifest_checksum_sha256"
        ],
        "candidate_prepared_once_per_row": mechanism[
            "source_mapping_read_once_per_row_all"
        ],
        "main_source_mapping_reads": mechanism[
            "main_source_mapping_reads"
        ],
        "main_prepared_condition_executions": mechanism[
            "main_prepared_condition_executions"
        ],
        "control_source_mapping_reads": mechanism[
            "control_source_mapping_reads"
        ],
        "control_prepared_condition_executions": mechanism[
            "control_prepared_condition_executions"
        ],
        "gold_absent_from_candidate_arguments_all": all(
            gates[name]
            for name in (
                "replay_gate_passed",
                "preservation_gate_passed",
                "interaction_gate_passed",
            )
        ),
        "selected_lane_only_all": metrics["interaction"][
            "unselected_stage_passed_count"
        ]
        == 0,
        "fallback_attempted_count": metrics["interaction"][
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
        "e5_claimed": False,
    }


def _valid_digest(value: Any, *, allow_none: bool = False) -> bool:
    return (
        allow_none
        and value is None
        or isinstance(value, str)
        and _SHA256.fullmatch(value) is not None
    )


def _validate_row(
    row: Any,
    *,
    index: int,
    control: bool,
    findings: list[str],
) -> None:
    label = f"{'controls' if control else 'items'}[{index}]"
    expected_fields = _CONTROL_FIELDS if control else _ITEM_FIELDS
    if not isinstance(row, Mapping) or frozenset(row) != expected_fields:
        findings.append(f"{label} fields mismatch")
        return
    family = row.get("family")
    expected_family = (
        "atomic"
        if index < (
            atomic_e4.EXPECTED_NEGATIVE_CONTROLS
            if control
            else atomic_e4.EXPECTED_ITEMS
        )
        else "scalar"
    )
    family_offset = (
        atomic_e4.EXPECTED_NEGATIVE_CONTROLS
        if control
        else atomic_e4.EXPECTED_ITEMS
    )
    expected_family_ordinal = (
        index if expected_family == "atomic" else index - family_offset
    )
    if (
        family != expected_family
        or row.get("global_ordinal") != index
        or row.get("family_ordinal") != expected_family_ordinal
    ):
        findings.append(f"{label} family/order identity mismatch")
    identifier = row.get("control_id" if control else "item_id")
    if not isinstance(identifier, str) or not identifier:
        findings.append(f"{label} identifier invalid")
    expected_eligibility = not control
    if row.get("evaluator_eligible") is not expected_eligibility:
        findings.append(f"{label} evaluator eligibility mismatch")
    if (
        row.get("gold_absent_from_candidate_arguments") is not True
        or row.get("original_mapping_read_count") != 1
        or not _valid_digest(row.get("input_digest_sha256"))
        or not _valid_digest(row.get("choices_digest_sha256"))
    ):
        findings.append(f"{label} candidate boundary invalid")
    order_ordinal = index if control else expected_family_ordinal
    sequence_index = order_ordinal % 4
    expected_order = list(WILLIAMS_SEQUENCES[sequence_index])
    if (
        row.get("williams_sequence_id") != f"W{sequence_index}"
        or row.get("primary_execution_order") != expected_order
        or row.get("replay_execution_order")
        != list(reversed(expected_order))
    ):
        findings.append(f"{label} Williams/reverse order mismatch")
    legacy = row.get("legacy")
    if not isinstance(legacy, Mapping) or frozenset(legacy) != _LEGACY_FIELDS:
        findings.append(f"{label} legacy mapping invalid")
        return
    if not all(_valid_digest(value) for value in legacy.values()):
        findings.append(f"{label} legacy digests invalid")
    conditions = row.get("conditions")
    if (
        not isinstance(conditions, Mapping)
        or set(conditions) != set(CONDITION_IDS)
    ):
        findings.append(f"{label} condition set mismatch")
        return
    expectation_kind = (
        row.get("expectation_kind") if control else "legacy_native"
    )
    expected_expectation_kind = (
        "router_reclassification"
        if control and (family, identifier) in RECLASSIFICATION_CONTROLS
        else "legacy_native"
    )
    if control and expectation_kind not in {
        "legacy_native",
        "router_reclassification",
    }:
        findings.append(f"{label} expectation kind invalid")
    if control and expectation_kind != expected_expectation_kind:
        findings.append(
            f"{label} expectation kind differs from frozen fixture"
        )
    for condition_id in CONDITION_IDS:
        record = conditions[condition_id]
        condition_label = f"{label}.conditions.{condition_id}"
        if (
            not isinstance(record, Mapping)
            or frozenset(record) != _CONDITION_FIELDS
        ):
            findings.append(f"{condition_label} fields mismatch")
            continue
        expected_legacy = _FAMILY_LEGACY_CONDITIONS[family][
            condition_id
        ]
        expected_digest = legacy[
            f"{expected_legacy}_semantic_outcome_digest_sha256"
        ]
        boolean_fields = (
            "correct",
            "wrong_fire",
            "compiled",
            "raw_fired",
            "accepted_fire",
            "grounded",
            "route_revalidated",
            "lane_entered",
            "selected_stage_passed",
            "unselected_stage_passed",
            "fallback_attempted",
            "legacy_semantic_outcome_same",
        )
        if any(type(record.get(field)) is not bool for field in boolean_fields):
            findings.append(f"{condition_label} booleans invalid")
        if (
            record.get("condition_id") != condition_id
            or record.get("global_bundle_condition")
            != CONDITION_BUNDLE_LABELS[condition_id]
            or record.get("expected_legacy_condition")
            != expected_legacy
            or record.get(
                "expected_legacy_semantic_outcome_digest_sha256"
            )
            != expected_digest
            or record.get("original_mapping_read_count") != 1
            or not _valid_digest(
                record.get("routed_semantic_outcome_digest_sha256")
            )
            or not _valid_digest(
                record.get("proof_digest_sha256"),
                allow_none=True,
            )
            or not _valid_digest(
                record.get("provenance_digest_sha256"),
                allow_none=True,
            )
            or not _valid_digest(
                record.get("stage_digest_sha256"),
                allow_none=True,
            )
        ):
            findings.append(f"{condition_label} binding invalid")
        if (
            record.get("status")
            not in {"correct", "wrong", "abstain", "error"}
            or record.get("correct")
            is not (record.get("status") == "correct")
            or record.get("wrong_fire")
            is not (record.get("status") == "wrong")
            or record.get("route_revalidated") is not True
            or record.get("unselected_stage_passed") is not False
            or record.get("fallback_attempted") is not False
            or record.get("error_kind") is not None
        ):
            findings.append(f"{condition_label} outcome contract invalid")
        reclassified = expectation_kind == "router_reclassification"
        if reclassified:
            if (
                record.get("route_status") != "unsupported"
                or record.get("route_lane") is not None
                or record.get("lane_entered") is not False
                or record.get("selected_stage_passed") is not False
                or record.get("native_semantic_outcome_digest_sha256")
                is not None
                or record.get("legacy_semantic_outcome_same") is not False
                or record.get("status") != "abstain"
                or record.get("choice_key") is not None
                or record.get("compiled") is not False
                or record.get("raw_fired") is not False
                or record.get("accepted_fire") is not False
                or record.get("grounded") is not False
                or record.get("reason") != "unsupported_science_profile"
            ):
                findings.append(
                    f"{condition_label} reclassification contract invalid"
                )
        else:
            expected_stage = expected_legacy == "on"
            if (
                record.get("route_status") != "selected"
                or record.get("route_lane") != family
                or record.get("lane_entered") is not True
                or record.get("selected_stage_passed") is not expected_stage
                or not _valid_digest(
                    record.get("native_semantic_outcome_digest_sha256")
                )
                or record.get("native_semantic_outcome_digest_sha256")
                != expected_digest
                or record.get("legacy_semantic_outcome_same") is not True
            ):
                findings.append(
                    f"{condition_label} native preservation invalid"
                )
            if control:
                if (
                    record.get("status") != "abstain"
                    or record.get("choice_key") is not None
                    or record.get("raw_fired") is not False
                    or record.get("accepted_fire") is not False
                    or record.get("grounded") is not False
                ):
                    findings.append(
                        f"{condition_label} native control fired"
                    )
            else:
                if (
                    record.get("compiled") is not True
                    or record.get("status")
                    != ("correct" if expected_stage else "abstain")
                    or record.get("raw_fired") is not expected_stage
                    or record.get("accepted_fire") is not expected_stage
                    or record.get("grounded") is not expected_stage
                    or (
                        expected_stage
                        and not isinstance(record.get("choice_key"), str)
                    )
                    or (
                        not expected_stage
                        and record.get("choice_key") is not None
                    )
                ):
                    findings.append(
                        f"{condition_label} item capability curve invalid"
                    )
    replay = row.get("replay")
    if (
        not isinstance(replay, Mapping)
        or frozenset(replay) != _REPLAY_FIELDS
        or replay.get("all_conditions_same") is not True
        or not isinstance(replay.get("conditions"), Mapping)
        or set(replay["conditions"]) != set(CONDITION_IDS)
    ):
        findings.append(f"{label} replay contract invalid")
    else:
        for condition_id in CONDITION_IDS:
            record = replay["conditions"][condition_id]
            if (
                not isinstance(record, Mapping)
                or frozenset(record) != _REPLAY_CONDITION_FIELDS
                or record.get("semantic_outcome_same") is not True
                or record.get("native_semantic_outcome_same") is not True
                or record.get("replay_digest_sha256")
                != conditions[condition_id][
                    "routed_semantic_outcome_digest_sha256"
                ]
            ):
                findings.append(
                    f"{label}.replay.{condition_id} mismatch"
                )
    if control and row.get("contract_passed") is not True:
        findings.append(f"{label} control contract failed")


def _validate_prerequisites(
    prerequisites: Any,
    stage_snapshots: Any,
    integrity: Any,
    findings: list[str],
) -> None:
    if (
        not isinstance(prerequisites, Mapping)
        or set(prerequisites) != {"scope", "atomic", "scalar"}
        or not isinstance(prerequisites.get("scope"), str)
    ):
        findings.append("prerequisites root mismatch")
        return
    expected = {
        "atomic": {
            "receipt_path": ATOMIC_PREREQUISITE_PATH,
            "schema_version": atomic_e4.SCHEMA_VERSION,
            "fixture_sha256": atomic_e4.FROZEN_FIXTURE_SHA256,
            "item_count": atomic_e4.EXPECTED_ITEMS,
            "control_count": atomic_e4.EXPECTED_NEGATIVE_CONTROLS,
            "e4_development_gate_passed": True,
            "control_probe_gate_passed": True,
            "candidate_controls_passed": (
                atomic_e4.EXPECTED_NEGATIVE_CONTROLS
            ),
            "candidate_controls_all_passed": True,
            "staging_control_count": atomic_e4.EXPECTED_STAGING_CONTROLS,
            "staging_controls_passed": (
                atomic_e4.EXPECTED_STAGING_CONTROLS
            ),
            "staging_controls_all_passed": True,
            "benchmark_capability_claimed": False,
            "e5_claimed": False,
            "independent": False,
            "external_authenticity_established": False,
            "resource_curve_established": False,
        },
        "scalar": {
            "receipt_path": SCALAR_PREREQUISITE_PATH,
            "schema_version": scalar_e4.SCHEMA_VERSION,
            "fixture_sha256": scalar_e4.FROZEN_FIXTURE_SHA256,
            "item_count": scalar_e4.EXPECTED_ITEMS,
            "control_count": scalar_e4.EXPECTED_CONTROLS,
            "e4_development_gate_passed": True,
            "control_probe_gate_passed": True,
            "candidate_controls_passed": scalar_e4.EXPECTED_CONTROLS,
            "candidate_controls_all_passed": True,
            "staging_control_count": scalar_e4.EXPECTED_STAGING_CONTROLS,
            "staging_controls_passed": (
                scalar_e4.EXPECTED_STAGING_CONTROLS
            ),
            "staging_controls_all_passed": True,
            "benchmark_capability_claimed": False,
            "e5_claimed": False,
            "independent": False,
            "external_authenticity_established": False,
            "resource_curve_established": False,
        },
    }
    for family in ("atomic", "scalar"):
        value = prerequisites.get(family)
        if (
            not isinstance(value, Mapping)
            or frozenset(value) != _PREREQUISITE_FIELDS
        ):
            findings.append(f"{family} prerequisite fields mismatch")
            continue
        for field, expected_value in expected[family].items():
            if value.get(field) != expected_value:
                findings.append(
                    f"{family} prerequisite {field} mismatch"
                )
        for field in (
            "manifest_checksum_sha256",
            "fixture_sha256",
            "stage_digest_sha256",
            "selection_digest_sha256",
            "item_semantics_digest_sha256",
            "control_semantics_digest_sha256",
            "staging_controls_digest_sha256",
        ):
            if not _valid_digest(value.get(field)):
                findings.append(
                    f"{family} prerequisite {field} invalid"
                )
        if (
            value.get("verified_current") is not True
            or value.get("verified_sealed") is not True
        ):
            findings.append(f"{family} prerequisite is not verified")
        if (
            isinstance(stage_snapshots, Mapping)
            and isinstance(stage_snapshots.get(family), Mapping)
            and stage_snapshots[family].get("stage_digest_sha256")
            != value.get("stage_digest_sha256")
        ):
            findings.append(
                f"{family} prerequisite stage digest mismatch"
            )
        if (
            isinstance(integrity, Mapping)
            and integrity.get(
                f"{family}_prerequisite_checksum_sha256"
            )
            != value.get("manifest_checksum_sha256")
        ):
            findings.append(
                f"{family} prerequisite integrity checksum mismatch"
            )


def validate_receipt(
    manifest: Mapping[str, Any],
    *,
    repo_root: Path = REPO,
    require_current: bool = False,
) -> list[str]:
    """Validate exact structure and optionally replay current semantics."""

    findings: list[str] = []
    try:
        if (
            not isinstance(manifest, Mapping)
            or frozenset(manifest) != _ROOT_FIELDS
        ):
            return ["receipt root fields mismatch"]
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
            ("stage", STAGE_PATHS),
        ):
            if _scope_paths(manifest.get(name)) != list(expected_paths):
                findings.append(f"{name} scope mismatch")
        fixture = manifest.get("fixture")
        expected_fixture = {
            "path": FIXTURE_PATH,
            "frozen_expected_sha256": FROZEN_FIXTURE_SHA256,
            "actual_sha256": FROZEN_FIXTURE_SHA256,
            "schema_version": "atanor.science-composite-controls.v1",
            "profile_id": "science-composite-preservation-e4-v1",
            "classification": (
                "authored_composite_development_controls_only"
            ),
            "source_fixture_sha256": {
                "atomic": atomic_e4.FROZEN_FIXTURE_SHA256,
                "scalar": scalar_e4.FROZEN_FIXTURE_SHA256,
            },
            "item_count": EXPECTED_ITEMS,
            "control_count": EXPECTED_CONTROLS,
            "router_reclassification_count": (
                EXPECTED_RECLASSIFICATIONS
            ),
        }
        if fixture != expected_fixture:
            findings.append("fixture contract mismatch")
        items = manifest.get("items")
        controls = manifest.get("controls")
        if (
            not isinstance(items, list)
            or len(items) != EXPECTED_ITEMS
        ):
            findings.append("item denominator mismatch")
            items = []
        if (
            not isinstance(controls, list)
            or len(controls) != EXPECTED_CONTROLS
        ):
            findings.append("control denominator mismatch")
            controls = []
        for index, row in enumerate(items):
            _validate_row(
                row,
                index=index,
                control=False,
                findings=findings,
            )
        for index, row in enumerate(controls):
            _validate_row(
                row,
                index=index,
                control=True,
                findings=findings,
            )
        item_ids = [
            row.get("item_id")
            for row in items
            if isinstance(row, Mapping)
        ]
        control_ids = [
            row.get("control_id")
            for row in controls
            if isinstance(row, Mapping)
        ]
        if (
            len(set(item_ids)) != EXPECTED_ITEMS
            or len(set(control_ids)) != EXPECTED_CONTROLS
            or set(item_ids) & set(control_ids)
        ):
            findings.append("row identifiers are not unique")
        if (
            _sha256(canonical_json_bytes(item_ids))
            != EXPECTED_ITEM_IDS_SHA256
            or _sha256(canonical_json_bytes(control_ids))
            != EXPECTED_CONTROL_IDS_SHA256
        ):
            findings.append(
                "row identifiers differ from frozen source fixtures"
            )
        stage_snapshots = manifest.get("stage_snapshots")
        if (
            not isinstance(stage_snapshots, Mapping)
            or set(stage_snapshots) != {"atomic", "scalar"}
            or not isinstance(stage_snapshots.get("atomic"), Mapping)
            or set(stage_snapshots["atomic"])
            != {
                "stage_id",
                "stage_digest_sha256",
                "manifest_checksum_sha256",
                "bound_bytes",
                "row_count",
            }
            or not isinstance(stage_snapshots.get("scalar"), Mapping)
            or set(stage_snapshots["scalar"])
            != {
                "stage_id",
                "stage_digest_sha256",
                "manifest_checksum_sha256",
                "bound_bytes",
                "species_count",
                "formula_count",
                "external_authenticity_established",
            }
        ):
            findings.append("stage snapshot fields mismatch")
        else:
            for family in ("atomic", "scalar"):
                snapshot = stage_snapshots[family]
                if (
                    not _valid_digest(
                        snapshot.get("stage_digest_sha256")
                    )
                    or not _valid_digest(
                        snapshot.get("manifest_checksum_sha256")
                    )
                    or type(snapshot.get("bound_bytes")) is not int
                    or snapshot["bound_bytes"] <= 0
                ):
                    findings.append(
                        f"{family} stage snapshot invalid"
                    )
            if (
                stage_snapshots["scalar"][
                    "external_authenticity_established"
                ]
                is not False
            ):
                findings.append("scalar stage authenticity overclaimed")
        integrity = manifest.get("integrity")
        _validate_prerequisites(
            manifest.get("prerequisites"),
            stage_snapshots,
            integrity,
            findings,
        )
        if items and controls:
            expected_selection = _selection(items, controls)
            if manifest.get("selection") != expected_selection:
                findings.append("selection does not derive from rows")
            expected_metrics = _derive_metrics(
                items,
                controls,
                manifest["prerequisites"],
            )
            if manifest.get("metrics") != expected_metrics:
                findings.append("metrics do not derive from rows")
            if manifest.get("claims") != _claims(expected_metrics):
                findings.append("claims do not derive from gates")
            closure = {
                "fresh_process_candidate_closure_expected_path_count": len(
                    CANDIDATE_PATHS
                ),
                "fresh_process_candidate_closure_actual_path_count": len(
                    CANDIDATE_PATHS
                ),
                "fresh_process_candidate_closure_paths_sha256": _sha256(
                    canonical_json_bytes(list(CANDIDATE_PATHS))
                ),
                "fresh_process_candidate_closure_exact": True,
            }
            expected_integrity = _integrity(
                expected_metrics,
                manifest["prerequisites"],
                closure,
            )
            if integrity != expected_integrity:
                findings.append("integrity does not derive")
            if expected_metrics["gates"][
                "composite_e4_development_gate_passed"
            ] is not True:
                findings.append("composite development gate did not pass")
        if manifest.get("seal") != _seal():
            findings.append("seal meaning is invalid")
        checksum = manifest.get("manifest_checksum_sha256")
        if (
            not _valid_digest(checksum)
            or checksum != _checksum(manifest)
        ):
            findings.append("manifest checksum mismatch")
        if require_current:
            initial_scopes = {
                name: _scope_matches_current(
                    manifest.get(name),
                    repo_root,
                )
                for name in ("source", "candidate", "dataset", "stage")
            }
            for name, matches in initial_scopes.items():
                if not matches:
                    findings.append(f"{name} scope differs from current")
            try:
                expected_current = build_receipt(repo_root=repo_root)
            except Exception as exc:
                findings.append(
                    "current semantic replay failed closed: "
                    + type(exc).__name__
                )
            else:
                mismatched = [
                    field
                    for field in sorted(_ROOT_FIELDS)
                    if manifest.get(field) != expected_current.get(field)
                ]
                if mismatched:
                    findings.append(
                        "current deterministic payload mismatch: "
                        + ", ".join(mismatched)
                    )
            for name in ("source", "candidate", "dataset", "stage"):
                if not _scope_matches_current(
                    manifest.get(name),
                    repo_root,
                ):
                    findings.append(
                        f"{name} scope differs after current semantic replay"
                    )
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        RecursionError,
        BenchmarkEvidenceError,
    ) as exc:
        findings.append(
            f"receipt validation failed closed: {type(exc).__name__}"
        )
    return findings


def _finalize(payload: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _detached(payload)
    if "manifest_checksum_sha256" in manifest:
        raise BenchmarkEvidenceError(
            "composite payload already carries checksum"
        )
    try:
        gate = manifest["metrics"]["gates"][
            "composite_e4_development_gate_passed"
        ]
    except (KeyError, TypeError) as exc:
        raise BenchmarkEvidenceError(
            "composite development gate is missing"
        ) from exc
    if gate is not True:
        raise BenchmarkEvidenceError(
            "composite development gate did not pass"
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
    fixture, fixture_bytes = _fixture(repo_root)
    prerequisites, prerequisite_manifests = _fresh_prerequisites(repo_root)
    atomic_fixture, _ = atomic_e4._fixture(repo_root)
    scalar_fixture, _ = scalar_e4._fixture(repo_root)
    if fixture["source_fixture_sha256"] != {
        "atomic": prerequisites["atomic"]["fixture_sha256"],
        "scalar": prerequisites["scalar"]["fixture_sha256"],
    }:
        raise BenchmarkEvidenceError(
            "source fixture hashes differ from fresh prerequisites"
        )

    bundles, stage_snapshots = _stage_bundles(repo_root)
    for family in ("atomic", "scalar"):
        if (
            stage_snapshots[family]["stage_digest_sha256"]
            != prerequisites[family]["stage_digest_sha256"]
        ):
            raise BenchmarkEvidenceError(
                f"{family} stage differs from fresh prerequisite"
            )
    legacy = _legacy_index(prerequisite_manifests)
    item_receipts: list[dict[str, Any]] = []
    family_fixtures = {
        "atomic": atomic_fixture,
        "scalar": scalar_fixture,
    }
    for family in ("atomic", "scalar"):
        for family_ordinal, row in enumerate(
            family_fixtures[family]["paired_items"]
        ):
            item_receipts.append(
                _execute_row(
                    row,
                    family=family,
                    family_ordinal=family_ordinal,
                    global_ordinal=len(item_receipts),
                    legacy_row=legacy[(family, row["id"])],
                    bundles=bundles,
                )
            )
    if (
        len(item_receipts) != EXPECTED_ITEMS
        or Counter(row["family"] for row in item_receipts)
        != {"atomic": atomic_e4.EXPECTED_ITEMS, "scalar": scalar_e4.EXPECTED_ITEMS}
    ):
        raise BenchmarkEvidenceError("composite item denominator mismatch")

    reclassifications = {
        row["control_id"]: row
        for row in fixture["router_reclassifications"]
    }
    control_receipts: list[dict[str, Any]] = []
    observed_reclassifications: set[str] = set()
    for family in ("atomic", "scalar"):
        for family_ordinal, row in enumerate(
            family_fixtures[family]["negative_controls"]
        ):
            reclassification = reclassifications.get(row["id"])
            if reclassification is not None:
                if reclassification["family"] != family:
                    raise BenchmarkEvidenceError(
                        "reclassification family mismatch"
                    )
                observed_reclassifications.add(row["id"])
            control_receipts.append(
                _execute_row(
                    row,
                    family=family,
                    family_ordinal=family_ordinal,
                    global_ordinal=len(control_receipts),
                    legacy_row=legacy[(family, row["id"])],
                    bundles=bundles,
                    control_type=row["control_type"],
                    reclassification=reclassification,
                    order_ordinal=len(control_receipts),
                )
            )
    if (
        len(control_receipts) != EXPECTED_CONTROLS
        or observed_reclassifications != set(reclassifications)
    ):
        raise BenchmarkEvidenceError("composite control denominator mismatch")

    selection = _selection(item_receipts, control_receipts)
    metrics = _derive_metrics(
        item_receipts,
        control_receipts,
        prerequisites,
    )
    closure = _fresh_candidate_closure(repo_root)
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
            "bound bytes changed during composite run: "
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
        "fixture": {
            "path": FIXTURE_PATH,
            "frozen_expected_sha256": FROZEN_FIXTURE_SHA256,
            "actual_sha256": _sha256(fixture_bytes),
            "schema_version": fixture["schema_version"],
            "profile_id": fixture["profile_id"],
            "classification": fixture["classification"],
            "source_fixture_sha256": fixture[
                "source_fixture_sha256"
            ],
            "item_count": EXPECTED_ITEMS,
            "control_count": EXPECTED_CONTROLS,
            "router_reclassification_count": (
                EXPECTED_RECLASSIFICATIONS
            ),
        },
        "stage_snapshots": stage_snapshots,
        "selection": selection,
        "metrics": metrics,
        "items": item_receipts,
        "controls": control_receipts,
        "integrity": _integrity(metrics, prerequisites, closure),
    }
    return _finalize(payload)


def build_receipt(*, repo_root: Path = REPO) -> dict[str, Any]:
    """Build through a fresh worker and bind the bytes visible outside it."""

    outer_scopes_before = _bind_scopes(repo_root)
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.science_stage_composite_e4_receipt",
                "--internal-build-worker",
            ],
            cwd=repo_root,
            check=False,
            capture_output=True,
            timeout=240,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BenchmarkEvidenceError(
            f"fresh composite worker failed: {type(exc).__name__}"
        ) from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise BenchmarkEvidenceError(
            "fresh composite worker exited nonzero"
            + (f": {detail}" if detail else "")
        )
    payload = completed.stdout
    if not payload or len(payload) > MAX_RECEIPT_BYTES:
        raise BenchmarkEvidenceError(
            "fresh composite worker output size invalid"
        )
    manifest = strict_json_bytes(
        payload,
        label="fresh composite receipt worker",
    )
    if payload != canonical_json_bytes(manifest) + b"\n":
        raise BenchmarkEvidenceError(
            "fresh composite worker output is not canonical JSON"
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
            "bound bytes changed across fresh composite worker: "
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
            f"composite receipt unreadable: {type(exc).__name__}"
        ) from exc
    if not payload or len(payload) > MAX_RECEIPT_BYTES:
        raise BenchmarkEvidenceError("composite receipt size invalid")
    manifest = strict_json_bytes(payload, label="composite receipt")
    if payload != canonical_json_bytes(manifest) + b"\n":
        raise BenchmarkEvidenceError(
            "composite receipt is not canonical JSON with one newline"
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
        "e5_claimed": False,
        "public_capability_gate_passed": False,
        "checksum_sha256": None,
        "source_matches_current": False,
        "candidate_matches_current": False,
        "dataset_matches_current": False,
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
    """Verify structure and, by default, a fresh deterministic rebuild."""

    try:
        manifest = read_receipt(path)
    except BenchmarkEvidenceError as exc:
        return _failed_verify_report(str(exc))
    findings = validate_receipt(manifest, repo_root=repo_root)
    structure_valid = not findings
    if require_current:
        current_scopes: dict[str, bool | None] = {
            name: _scope_matches_current(manifest.get(name), repo_root)
            for name in ("source", "candidate", "dataset", "stage")
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
                "current composite replay failed closed: "
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
            for name in ("source", "candidate", "dataset", "stage"):
                current_scopes[name] = _scope_matches_current(
                    manifest.get(name),
                    repo_root,
                )
                if not current_scopes[name]:
                    findings.append(
                        f"{name} scope differs after current semantic replay"
                    )
        matches_current: bool | None = (
            initial_scopes_match
            and all(value is True for value in current_scopes.values())
            and prerequisite_matches_current is True
            and not any(
                finding.startswith(
                    "current deterministic payload mismatch"
                )
                or finding.startswith("current composite replay failed")
                for finding in findings
            )
        )
    else:
        current_scopes = {
            name: None
            for name in ("source", "candidate", "dataset", "stage")
        }
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
        "e5_claimed": (
            isinstance(claims, Mapping)
            and claims.get("e5_claimed") is True
        ),
        "public_capability_gate_passed": (
            isinstance(claims, Mapping)
            and claims.get("public_capability_gate_passed") is True
        ),
        "checksum_sha256": manifest.get("manifest_checksum_sha256"),
        "source_matches_current": current_scopes["source"],
        "candidate_matches_current": current_scopes["candidate"],
        "dataset_matches_current": current_scopes["dataset"],
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
