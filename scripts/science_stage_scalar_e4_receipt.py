"""Sealed local development receipt for scalar science staging.

The receipt pairs the same frozen scalar-neutralization items with the stage
structurally absent or present, reverses the order for semantic replay, and
records strict accuracy separately from compiler, formula, raw, accepted, and
provenance-bound firing.  Its seal is deliberately local: exact current bytes,
deterministic replay, controls, and a checksum.  It is not a hidden-set,
independent, externally authenticated, resource, or benchmark-capability
claim.
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from packages.eval_evidence.receipt import (
    BenchmarkEvidenceError,
    bind_files,
    canonical_json_bytes,
    ensure_safe_report_output,
    strict_json_bytes,
    write_manifest_exclusive,
)
from packages.reasoning_vm.science_quantity_exam import (
    answer_scalar_science_mcq,
    scalar_outcome_digest,
)
from packages.reasoning_vm.science_quantity_staging import (
    NEUTRALIZATION_FORMULA_ID,
    ScienceQuantityStageError,
    ScienceQuantityStageSnapshot,
    load_science_quantity_stage,
)


REPO = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "atanor.science-stage-scalar-paired-e4-receipt.v1"
EVIDENCE_KIND = "strict_self_measured_scalar_e4_development_receipt"
FROZEN_FIXTURE_SHA256 = (
    "725c1073eac795c63113a5c63c1a3facf40c9e5739d7f7a1d99de31f53def34f"
)
EXPECTED_ITEMS = 12
EXPECTED_SEMANTIC_GROUPS = 6
EXPECTED_CONTROLS = 6
EXPECTED_STAGING_CONTROLS = 3
MAX_RECEIPT_BYTES = 16 * 1024 * 1024

FIXTURE_PATH = (
    "packages/reasoning_vm/tests/fixtures/"
    "science_scalar_neutralization_e4_v1.json"
)
STAGE_ROOT = (
    "packages/reasoning_vm/tests/fixtures/"
    "science_stage_scalar_quantity_v1"
)
STAGE_PATHS = (
    f"{STAGE_ROOT}/evidence.jsonl",
    f"{STAGE_ROOT}/formulas.jsonl",
    f"{STAGE_ROOT}/manifest.json",
    f"{STAGE_ROOT}/species.jsonl",
)
SOURCE_PATHS = (
    "packages/eval_evidence/__init__.py",
    "packages/eval_evidence/receipt.py",
    "scripts/science_stage_scalar_e4_receipt.py",
)
# This is the exact fresh-process project-local Python closure observed after
# loading the stage and running one ON candidate.  Package initializers are
# included because importing a child module executes them.
CANDIDATE_PATHS = (
    "packages/__init__.py",
    "packages/cognitive_core/__init__.py",
    "packages/cognitive_core/adapters.py",
    "packages/cognitive_core/canonical.py",
    "packages/cognitive_core/chat_shadow.py",
    "packages/cognitive_core/contracts.py",
    "packages/cognitive_core/cycle.py",
    "packages/cognitive_core/cycle_ledger.py",
    "packages/cognitive_core/replay.py",
    "packages/cognitive_core/shadow.py",
    "packages/evolution/rational_evolver.py",
    "packages/reasoning_vm/__init__.py",
    "packages/reasoning_vm/deliberator/__init__.py",
    "packages/reasoning_vm/deliberator/science_quantity_goal.py",
    "packages/reasoning_vm/deliberator/science_quantity_resolver.py",
    "packages/reasoning_vm/quantity.py",
    "packages/reasoning_vm/scalar_quantity.py",
    "packages/reasoning_vm/science_quantity_exam.py",
    "packages/reasoning_vm/science_quantity_staging.py",
)
DATASET_PATHS = (FIXTURE_PATH,)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_EVALUATOR_VOLUME_CHOICE = re.compile(
    r"(?P<value>(?:0|[1-9][0-9]*)(?:\.[0-9]+)?) "
    r"(?P<unit>mL|L)\Z"
)
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
        "fixture",
        "stage_snapshot",
        "selection",
        "metrics",
        "items",
        "controls",
        "staging_controls",
        "integrity",
        "manifest_checksum_sha256",
    }
)
_SCOPE_FIELDS = frozenset({"files", "content_sha256"})
_FILE_FIELDS = frozenset({"path", "bytes", "sha256"})
_ITEM_FIELDS = frozenset(
    {
        "item_id",
        "ordinal",
        "surface_id",
        "semantic_group_id",
        "evaluator_eligible",
        "expected_answer_liters",
        "on_output_matches_expected_answer",
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
_CONTROL_FIELDS = frozenset(
    (
        _ITEM_FIELDS
        - {
            "surface_id",
            "semantic_group_id",
            "expected_answer_liters",
            "on_output_matches_expected_answer",
        }
    )
    | {"control_type", "contract_passed"}
)
_COMPILER_FIELDS = frozenset(
    {
        "schema_version",
        "input_valid",
        "compiled",
        "status",
        "reason",
        "input_fingerprint",
        "goal_digest_sha256",
        "surface_family",
        "compiler_rule",
    }
)
_CONDITION_FIELDS = frozenset(
    {
        "status",
        "choice_key",
        "choice_digest_sha256",
        "output_value_liters",
        "correct",
        "wrong_fire",
        "compiler",
        "raw_fired",
        "formula_fired",
        "resolver_grounded",
        "proof_replayed",
        "accepted_fire",
        "grounded",
        "proof_digest_sha256",
        "provenance_digest_sha256",
        "provenance_bound",
        "evidence_ids",
        "grounded_leaf_count",
        "grounded_stage_leaf_count",
        "stage_hit_count",
        "stage_digest_sha256",
        "stage_snapshot_bound_bytes",
        "stage_bytes_read",
        "stage_structurally_absent",
        "external_authenticity_established",
        "reason",
        "error_kind",
        "semantic_outcome_digest_sha256",
        "evaluator_sentinel_unchanged",
    }
)
_TRANSITION_FIELDS = frozenset(
    {
        "label",
        "correct_delta",
        "raw_firing_delta",
        "formula_firing_delta",
        "resolver_grounding_delta",
        "proof_replay_delta",
        "accepted_firing_delta",
        "grounding_delta",
        "wrong_fire_delta",
    }
)
_REPLAY_FIELDS = frozenset(
    {
        "input_fingerprint_same",
        "goal_digest_same",
        "off_semantic_outcome_same",
        "on_semantic_outcome_same",
        "off_replay_digest_sha256",
        "on_replay_digest_sha256",
    }
)
_STAGING_CONTROL_FIELDS = frozenset(
    {
        "control_id",
        "control_type",
        "mutation_recipe_id",
        "mutated_stage_content_sha256",
        "loader_accepted",
        "snapshot_returned",
        "expected_rejection_observed",
        "semantic_replay_same",
        "contract_passed",
        "reason",
        "error_kind",
        "observed_loader_error_sha256",
    }
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        raise BenchmarkEvidenceError("metric denominator must be positive")
    return round(numerator / denominator, 12)


def _base_digest(base: Mapping[str, Any]) -> str:
    return _sha256(canonical_json_bytes(dict(base)))


def _evaluator_volume_liters(text: Any) -> Fraction:
    if type(text) is not str:
        raise BenchmarkEvidenceError("evaluator choice is not text")
    match = _EVALUATOR_VOLUME_CHOICE.fullmatch(text)
    if match is None:
        raise BenchmarkEvidenceError("evaluator choice is not an exact volume")
    try:
        value = Fraction(match.group("value"))
    except (ValueError, ZeroDivisionError) as exc:
        raise BenchmarkEvidenceError(
            "evaluator choice numeric value invalid"
        ) from exc
    if value <= 0:
        raise BenchmarkEvidenceError("evaluator choice volume nonpositive")
    return value / 1000 if match.group("unit") == "mL" else value


def _fixture(repo_root: Path) -> tuple[dict[str, Any], bytes]:
    try:
        payload = (repo_root / FIXTURE_PATH).read_bytes()
    except OSError as exc:
        raise BenchmarkEvidenceError(
            f"scalar fixture unreadable: {type(exc).__name__}"
        ) from exc
    if _sha256(payload) != FROZEN_FIXTURE_SHA256:
        raise BenchmarkEvidenceError("scalar fixture frozen hash mismatch")
    fixture = strict_json_bytes(payload, label="frozen scalar fixture")
    if (
        fixture.get("schema_version")
        != "atanor.scalar-neutralization-e4-fixture.v1"
        or fixture.get("profile_id")
        != (
            "scalar_quantity_resolve.acid_base_complete_neutralization."
            "base_volume.v1"
        )
        or fixture.get("classification")
        != "frozen_development_probe_not_e5"
        or fixture.get("authorship")
        != {
            "independently_written": True,
            "public_benchmark_question_copied": False,
            "public_benchmark_choices_copied": False,
            "external_authenticity_established": False,
        }
    ):
        raise BenchmarkEvidenceError("scalar fixture authority fields invalid")
    protocol = fixture.get("paired_protocol")
    items = fixture.get("paired_items")
    groups = fixture.get("semantic_groups")
    controls = fixture.get("negative_controls")
    if (
        not isinstance(protocol, Mapping)
        or protocol.get("fixed_denominator") != EXPECTED_ITEMS
        or protocol.get("semantic_group_count") != EXPECTED_SEMANTIC_GROUPS
        or not isinstance(items, list)
        or len(items) != EXPECTED_ITEMS
        or not isinstance(groups, list)
        or len(groups) != EXPECTED_SEMANTIC_GROUPS
        or not isinstance(controls, list)
        or len(controls) != EXPECTED_CONTROLS
    ):
        raise BenchmarkEvidenceError("scalar fixture denominator mismatch")
    identifiers: set[str] = set()
    for ordinal, row in enumerate(items):
        if not isinstance(row, Mapping):
            raise BenchmarkEvidenceError(f"fixture item {ordinal} is not an object")
        item_id = row.get("id")
        choices = row.get("choices")
        if (
            not isinstance(item_id, str)
            or not item_id
            or item_id in identifiers
            or not isinstance(row.get("question"), str)
            or not isinstance(row.get("surface_id"), str)
            or not isinstance(row.get("semantic_group_id"), str)
            or not isinstance(choices, Mapping)
            or len(choices) != 4
            or row.get("gold") not in choices
        ):
            raise BenchmarkEvidenceError(f"fixture item {ordinal} malformed")
        try:
            answer = Fraction(str(row["expected_answer_liters"]))
        except (KeyError, ValueError, ZeroDivisionError) as exc:
            raise BenchmarkEvidenceError(
                f"fixture item {ordinal} expected answer invalid"
            ) from exc
        if answer <= 0:
            raise BenchmarkEvidenceError(
                f"fixture item {ordinal} expected answer nonpositive"
            )
        try:
            choice_values = {
                key: _evaluator_volume_liters(text)
                for key, text in choices.items()
                if type(key) is str and key
            }
        except BenchmarkEvidenceError as exc:
            raise BenchmarkEvidenceError(
                f"fixture item {ordinal} evaluator choice invalid"
            ) from exc
        matching_keys = [
            key for key, value in choice_values.items() if value == answer
        ]
        if (
            len(choice_values) != len(choices)
            or len(set(choice_values.values())) != len(choice_values)
            or matching_keys != [row["gold"]]
        ):
            raise BenchmarkEvidenceError(
                f"fixture item {ordinal} gold is not the unique exact answer"
            )
        identifiers.add(item_id)
    if Counter(row["gold"] for row in items) != Counter(
        {"A": 3, "B": 3, "C": 3, "D": 3}
    ):
        raise BenchmarkEvidenceError("scalar gold positions are not balanced")
    group_ids = [row.get("group_id") for row in groups]
    if (
        len(set(group_ids)) != EXPECTED_SEMANTIC_GROUPS
        or any(
            not isinstance(row, Mapping)
            or not isinstance(row.get("relation"), str)
            or not isinstance(row.get("item_ids"), list)
            or len(row["item_ids"]) != 2
            or any(item_id not in identifiers for item_id in row["item_ids"])
            for row in groups
        )
    ):
        raise BenchmarkEvidenceError("scalar semantic groups malformed")
    control_ids: set[str] = set()
    for ordinal, row in enumerate(controls):
        if (
            not isinstance(row, Mapping)
            or not isinstance(row.get("id"), str)
            or not row["id"]
            or row["id"] in identifiers
            or row["id"] in control_ids
            or not isinstance(row.get("control_type"), str)
            or not isinstance(row.get("question"), str)
            or not isinstance(row.get("choices"), Mapping)
        ):
            raise BenchmarkEvidenceError(
                f"fixture control {ordinal} malformed"
            )
        control_ids.add(row["id"])
    return fixture, payload


def _candidate_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "question": row["question"],
        "choices": json.loads(canonical_json_bytes(row["choices"])),
    }


def run_candidate(
    item: Mapping[str, Any],
    *,
    stage: ScienceQuantityStageSnapshot | None,
    overlay_enabled: bool,
    base_state_digest: Callable[[], str],
) -> dict[str, Any]:
    """Execute the candidate with only question and choices crossing boundary."""

    if not isinstance(item, Mapping) or frozenset(item) != {
        "question",
        "choices",
    }:
        raise BenchmarkEvidenceError(
            "candidate item must contain only question and choices"
        )
    if not isinstance(item["question"], str) or not isinstance(
        item["choices"], Mapping
    ):
        raise BenchmarkEvidenceError("candidate question or choices invalid")
    return answer_scalar_science_mcq(
        item["question"],
        item["choices"],
        stage,
        overlay_enabled=overlay_enabled,
        base_state_digest=base_state_digest,
    )


def _run_condition(
    safe_item: Mapping[str, Any],
    *,
    stage: ScienceQuantityStageSnapshot,
    enabled: bool,
    base_state_digest: Callable[[], str],
) -> dict[str, Any]:
    detached = json.loads(canonical_json_bytes(safe_item))
    before = canonical_json_bytes(detached)
    outcome = run_candidate(
        detached,
        stage=stage if enabled else None,
        overlay_enabled=enabled,
        base_state_digest=base_state_digest,
    )
    if canonical_json_bytes(detached) != before:
        raise BenchmarkEvidenceError("candidate mutated its item or choices")
    return outcome


def _compiler_record(outcome: Mapping[str, Any]) -> dict[str, Any]:
    compiler = outcome.get("compiler")
    if not isinstance(compiler, Mapping):
        raise BenchmarkEvidenceError("scalar compiler telemetry missing")
    return {
        "schema_version": compiler.get("schema_version"),
        "input_valid": compiler.get("input_valid") is True,
        "compiled": compiler.get("compiled") is True,
        "status": compiler.get("status"),
        "reason": compiler.get("reason"),
        "input_fingerprint": compiler.get("input_fingerprint"),
        "goal_digest_sha256": compiler.get("goal_digest_sha256"),
        "surface_family": compiler.get("surface_family"),
        "compiler_rule": compiler.get("compiler_rule"),
    }


def _evaluator_output_value_liters(
    outcome: Mapping[str, Any],
    choices: Mapping[str, Any],
) -> str | None:
    choice_key = outcome.get("choice_key")
    if choice_key is None:
        return None
    if not isinstance(choice_key, str) or choice_key not in choices:
        raise BenchmarkEvidenceError(
            "candidate selected a choice outside evaluator choices"
        )
    return str(_evaluator_volume_liters(choices[choice_key]))


def _condition_record(
    outcome: Mapping[str, Any],
    *,
    gold: str | None,
    evaluator_choices: Mapping[str, Any],
) -> dict[str, Any]:
    engine = outcome.get("engine")
    staging = outcome.get("staging")
    integrity = outcome.get("integrity")
    if not all(isinstance(row, Mapping) for row in (engine, staging, integrity)):
        raise BenchmarkEvidenceError("scalar candidate telemetry incomplete")
    assert isinstance(engine, Mapping)
    assert isinstance(staging, Mapping)
    assert isinstance(integrity, Mapping)
    accepted = engine.get("accepted_fire") is True
    choice = outcome.get("choice_key")
    correct = gold is not None and choice == gold
    error_kind = outcome.get("error_kind")
    status = (
        "error"
        if error_kind is not None
        else "correct"
        if correct
        else "wrong"
        if accepted
        else "abstain"
    )
    grounded_leaf_count = staging.get("grounded_leaf_count")
    grounded_stage_leaf_count = staging.get("grounded_stage_leaf_count")
    evidence_ids = list(staging.get("evidence_ids") or [])
    proof_digest = engine.get("proof_digest_sha256")
    provenance_digest = staging.get("provenance_digest_sha256")
    provenance_bound = (
        accepted
        and grounded_leaf_count == 3
        and grounded_stage_leaf_count == 3
        and len(evidence_ids) == 3
        and isinstance(proof_digest, str)
        and _SHA256.fullmatch(proof_digest) is not None
        and isinstance(provenance_digest, str)
        and _SHA256.fullmatch(provenance_digest) is not None
        and staging.get("external_authenticity_established") is False
    )
    return {
        "status": status,
        "choice_key": choice,
        "choice_digest_sha256": outcome.get("choice_digest_sha256"),
        "output_value_liters": _evaluator_output_value_liters(
            outcome,
            evaluator_choices,
        ),
        "correct": correct,
        "wrong_fire": accepted and not correct,
        "compiler": _compiler_record(outcome),
        "raw_fired": engine.get("raw_fired") is True,
        "formula_fired": engine.get("formula_fired") is True,
        "resolver_grounded": engine.get("resolver_grounded") is True,
        "proof_replayed": engine.get("proof_replayed") is True,
        "accepted_fire": accepted,
        "grounded": engine.get("grounded") is True,
        "proof_digest_sha256": proof_digest,
        "provenance_digest_sha256": provenance_digest,
        "provenance_bound": provenance_bound,
        "evidence_ids": evidence_ids,
        "grounded_leaf_count": grounded_leaf_count,
        "grounded_stage_leaf_count": grounded_stage_leaf_count,
        "stage_hit_count": staging.get("staged_hit_count"),
        "stage_digest_sha256": staging.get("stage_digest_sha256"),
        "stage_snapshot_bound_bytes": staging.get(
            "stage_snapshot_bound_bytes"
        ),
        "stage_bytes_read": staging.get("stage_bytes_read"),
        "stage_structurally_absent": integrity.get(
            "stage_structurally_absent"
        )
        is True,
        "external_authenticity_established": staging.get(
            "external_authenticity_established"
        )
        is True,
        "reason": outcome.get("reason"),
        "error_kind": error_kind,
        "semantic_outcome_digest_sha256": scalar_outcome_digest(outcome),
        "evaluator_sentinel_unchanged": (
            integrity.get("base_state_unchanged") is True
        ),
    }


def _transition(
    off: Mapping[str, Any],
    on: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "label": f"{off['status']}_to_{on['status']}",
        "correct_delta": int(on["correct"]) - int(off["correct"]),
        "raw_firing_delta": int(on["raw_fired"]) - int(off["raw_fired"]),
        "formula_firing_delta": int(on["formula_fired"])
        - int(off["formula_fired"]),
        "resolver_grounding_delta": int(on["resolver_grounded"])
        - int(off["resolver_grounded"]),
        "proof_replay_delta": int(on["proof_replayed"])
        - int(off["proof_replayed"]),
        "accepted_firing_delta": int(on["accepted_fire"])
        - int(off["accepted_fire"]),
        "grounding_delta": int(on["grounded"]) - int(off["grounded"]),
        "wrong_fire_delta": int(on["wrong_fire"]) - int(off["wrong_fire"]),
    }


def _execute_pair(
    safe_item: Mapping[str, Any],
    *,
    stage: ScienceQuantityStageSnapshot,
    primary_order: Sequence[str],
    gold: str | None,
    base_state_digest: Callable[[], str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if list(primary_order) not in (["off", "on"], ["on", "off"]):
        raise BenchmarkEvidenceError("scalar primary order invalid")
    replay_order = list(reversed(primary_order))
    primary: dict[str, dict[str, Any]] = {}
    repeated: dict[str, dict[str, Any]] = {}
    for condition in primary_order:
        primary[condition] = _run_condition(
            safe_item,
            stage=stage,
            enabled=condition == "on",
            base_state_digest=base_state_digest,
        )
    for condition in replay_order:
        repeated[condition] = _run_condition(
            safe_item,
            stage=stage,
            enabled=condition == "on",
            base_state_digest=base_state_digest,
        )
    records = {
        condition: _condition_record(
            primary[condition],
            gold=gold,
            evaluator_choices=safe_item["choices"],
        )
        for condition in ("off", "on")
    }
    compiler_rows = [
        outcome["compiler"]
        for outcome in (
            primary["off"],
            primary["on"],
            repeated["off"],
            repeated["on"],
        )
    ]
    fingerprints = {
        row.get("input_fingerprint")
        for row in compiler_rows
        if isinstance(row, Mapping)
    }
    goal_digests = {
        row.get("goal_digest_sha256")
        for row in compiler_rows
        if isinstance(row, Mapping)
    }
    replay = {
        "input_fingerprint_same": (
            len(fingerprints) == 1 and None not in fingerprints
        ),
        "goal_digest_same": len(goal_digests) == 1,
        "off_semantic_outcome_same": (
            records["off"]["semantic_outcome_digest_sha256"]
            == scalar_outcome_digest(repeated["off"])
        ),
        "on_semantic_outcome_same": (
            records["on"]["semantic_outcome_digest_sha256"]
            == scalar_outcome_digest(repeated["on"])
        ),
        "off_replay_digest_sha256": scalar_outcome_digest(repeated["off"]),
        "on_replay_digest_sha256": scalar_outcome_digest(repeated["on"]),
    }
    return records, replay


def _canonical_jsonl(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(dict(row)) + b"\n" for row in rows)


def _refresh_stage_manifest(stage_root: Path, filename: str) -> None:
    manifest_path = stage_root / "manifest.json"
    manifest = strict_json_bytes(
        manifest_path.read_bytes(),
        label="mutated quantity stage manifest",
    )
    field = {
        "species.jsonl": "species_file",
        "formulas.jsonl": "formulas_file",
        "evidence.jsonl": "evidence_file",
    }[filename]
    payload = (stage_root / filename).read_bytes()
    manifest[field] = {
        "path": filename,
        "bytes": len(payload),
        "sha256": _sha256(payload),
    }
    manifest.pop("manifest_checksum_sha256", None)
    manifest["manifest_checksum_sha256"] = _sha256(
        canonical_json_bytes(manifest)
    )
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")


def _mutate_stage(stage_root: Path, control_type: str) -> None:
    if control_type == "species_claim":
        path = stage_root / "species.jsonl"
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        rows[0]["equivalents_per_mole"] = 7
        path.write_bytes(_canonical_jsonl(rows))
        _refresh_stage_manifest(stage_root, path.name)
        return
    if control_type == "formula_ast":
        path = stage_root / "formulas.jsonl"
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        rows[0]["expression"][1] = "+"
        path.write_bytes(_canonical_jsonl(rows))
        _refresh_stage_manifest(stage_root, path.name)
        return
    if control_type == "external_auth_flag":
        path = stage_root / "evidence.jsonl"
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        rows[0]["externally_authenticated"] = True
        path.write_bytes(_canonical_jsonl(rows))
        _refresh_stage_manifest(stage_root, path.name)
        return
    raise BenchmarkEvidenceError(f"unknown scalar stage control: {control_type}")


def _stage_tree_digest(stage_root: Path) -> str:
    rows = []
    for name in ("evidence.jsonl", "formulas.jsonl", "manifest.json", "species.jsonl"):
        payload = (stage_root / name).read_bytes()
        rows.append(
            {"path": name, "bytes": len(payload), "sha256": _sha256(payload)}
        )
    return _sha256(canonical_json_bytes(rows))


def _observe_stage_load(stage_root: Path) -> dict[str, Any]:
    try:
        snapshot = load_science_quantity_stage(stage_root)
    except ScienceQuantityStageError as exc:
        message = str(exc)
        return {
            "loader_accepted": False,
            "snapshot_returned": False,
            "reason": "loader_rejected_fail_closed",
            "error_kind": type(exc).__name__,
            "observed_loader_error_sha256": _sha256(
                message.encode("utf-8")
            ),
        }
    return {
        "loader_accepted": True,
        "snapshot_returned": snapshot is not None,
        "reason": "loader_accepted_mutated_stage",
        "error_kind": None,
        "observed_loader_error_sha256": None,
    }


def _run_staging_controls(
    repo_root: Path,
) -> list[dict[str, Any]]:
    recipes = (
        (
            "scalar-stage-species-claim-control",
            "species_claim",
            "manifest_rechecksummed_species_claim_without_evidence_rebind_v1",
        ),
        (
            "scalar-stage-formula-ast-control",
            "formula_ast",
            "manifest_rechecksummed_formula_ast_without_dimension_rebind_v1",
        ),
        (
            "scalar-stage-external-auth-control",
            "external_auth_flag",
            "manifest_rechecksummed_external_auth_flag_policy_violation_v1",
        ),
    )
    receipts = []
    for control_id, control_type, recipe_id in recipes:
        with tempfile.TemporaryDirectory(
            prefix="atanor-scalar-stage-control-"
        ) as temporary:
            stage_root = Path(temporary) / "stage"
            shutil.copytree(repo_root / STAGE_ROOT, stage_root)
            _mutate_stage(stage_root, control_type)
            content_digest = _stage_tree_digest(stage_root)
            primary = _observe_stage_load(stage_root)
            replay = _observe_stage_load(stage_root)
        replay_same = primary == replay
        expected_rejection = (
            primary["loader_accepted"] is False
            and primary["snapshot_returned"] is False
            and primary["error_kind"] == "ScienceQuantityStageError"
        )
        receipts.append(
            {
                "control_id": control_id,
                "control_type": control_type,
                "mutation_recipe_id": recipe_id,
                "mutated_stage_content_sha256": content_digest,
                **primary,
                "expected_rejection_observed": expected_rejection,
                "semantic_replay_same": replay_same,
                "contract_passed": expected_rejection and replay_same,
            }
        )
    return receipts


def _condition_metrics(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    n = len(rows)
    if n <= 0:
        raise BenchmarkEvidenceError("empty scalar condition denominator")
    input_valid = sum(
        int(row["compiler"]["input_valid"] is True) for row in rows
    )
    compiled = sum(int(row["compiler"]["compiled"] is True) for row in rows)
    raw_fired = sum(int(row["raw_fired"] is True) for row in rows)
    formula_fired = sum(int(row["formula_fired"] is True) for row in rows)
    resolver_grounded = sum(
        int(row["resolver_grounded"] is True) for row in rows
    )
    proof_replayed = sum(int(row["proof_replayed"] is True) for row in rows)
    accepted = sum(int(row["accepted_fire"] is True) for row in rows)
    grounded = sum(int(row["grounded"] is True) for row in rows)
    correct = sum(int(row["correct"] is True) for row in rows)
    wrong_fire = sum(int(row["wrong_fire"] is True) for row in rows)
    error = sum(int(row["status"] == "error") for row in rows)
    abstain = sum(int(row["status"] == "abstain") for row in rows)
    provenance_bound = sum(
        int(row["provenance_bound"] is True) for row in rows
    )
    grounded_leaf_total = sum(int(row["grounded_leaf_count"]) for row in rows)
    stage_leaf_total = sum(
        int(row["grounded_stage_leaf_count"]) for row in rows
    )
    evidence_id_total = sum(len(row["evidence_ids"]) for row in rows)
    return {
        "n": n,
        "input_valid": input_valid,
        "compiled": compiled,
        "raw_fired": raw_fired,
        "formula_fired": formula_fired,
        "resolver_grounded": resolver_grounded,
        "proof_replayed": proof_replayed,
        "accepted_fired": accepted,
        "grounded": grounded,
        "correct": correct,
        "wrong_fire": wrong_fire,
        "abstain": abstain,
        "error": error,
        "provenance_bound_fires": provenance_bound,
        "grounded_leaf_count_total": grounded_leaf_total,
        "grounded_stage_leaf_count_total": stage_leaf_total,
        "evidence_id_count_total": evidence_id_total,
        "input_valid_rate": _ratio(input_valid, n),
        "compiler_conformance_rate": _ratio(compiled, n),
        "raw_firing_rate": _ratio(raw_fired, n),
        "formula_firing_rate": _ratio(formula_fired, n),
        "resolver_grounding_rate": _ratio(resolver_grounded, n),
        "proof_replay_rate": _ratio(proof_replayed, n),
        "accepted_firing_rate": _ratio(accepted, n),
        "grounded_coverage": _ratio(grounded, n),
        "strict_accuracy": _ratio(correct, n),
        "wrong_fire_rate": _ratio(wrong_fire, n),
        "abstention_rate": _ratio(abstain, n),
    }


def _relation_holds(
    relation: str,
    left: Fraction,
    right: Fraction,
) -> bool:
    if relation in {
        "same_physical_quantity_after_milliliter_liter_conversion",
        "common_concentration_scale_invariant",
    }:
        return left == right
    if relation in {
        "acid_equivalents_times_two_implies_target_volume_times_two",
        "known_volume_times_two_implies_target_volume_times_two",
    }:
        return right == 2 * left
    if (
        relation
        == "base_equivalents_times_two_implies_target_volume_divided_by_two"
    ):
        return 2 * right == left
    raise BenchmarkEvidenceError(
        f"unknown scalar metamorphic relation: {relation}"
    )


def _derive_metamorphic(
    items: Sequence[Mapping[str, Any]],
    semantic_groups: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_id = {row["item_id"]: row for row in items}
    records = []
    for group in semantic_groups:
        item_ids = group["item_ids"]
        if len(item_ids) != 2 or any(item_id not in by_id for item_id in item_ids):
            raise BenchmarkEvidenceError("metamorphic group item mismatch")
        left_text = by_id[item_ids[0]]["conditions"]["on"][
            "output_value_liters"
        ]
        right_text = by_id[item_ids[1]]["conditions"]["on"][
            "output_value_liters"
        ]
        try:
            left = Fraction(left_text)
            right = Fraction(right_text)
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            raise BenchmarkEvidenceError(
                "metamorphic output is not an exact rational"
            ) from exc
        passed = _relation_holds(group["relation"], left, right)
        records.append(
            {
                "group_id": group["group_id"],
                "item_ids": list(item_ids),
                "relation": group["relation"],
                "left_value_liters": str(left),
                "right_value_liters": str(right),
                "passed": passed,
            }
        )
    return {
        "semantic_group_count": len(records),
        "passed": sum(int(row["passed"] is True) for row in records),
        "all_passed": all(row["passed"] is True for row in records),
        "groups": records,
        "inferential_independence_claimed": False,
    }


def _derive_metrics(
    items: Sequence[Mapping[str, Any]],
    controls: Sequence[Mapping[str, Any]],
    staging_controls: Sequence[Mapping[str, Any]],
    semantic_groups: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    off_rows = [row["conditions"]["off"] for row in items]
    on_rows = [row["conditions"]["on"] for row in items]
    off = _condition_metrics(off_rows)
    on = _condition_metrics(on_rows)
    transitions = Counter(row["off_to_on"]["label"] for row in items)
    regressions = sum(
        int(
            row["conditions"]["off"]["correct"] is True
            and row["conditions"]["on"]["correct"] is not True
        )
        for row in items
    )
    paired = {
        "strict_accuracy_delta": round(
            on["strict_accuracy"] - off["strict_accuracy"], 12
        ),
        "correct_delta": on["correct"] - off["correct"],
        "raw_firing_rate_delta": round(
            on["raw_firing_rate"] - off["raw_firing_rate"], 12
        ),
        "formula_firing_rate_delta": round(
            on["formula_firing_rate"] - off["formula_firing_rate"], 12
        ),
        "resolver_grounding_rate_delta": round(
            on["resolver_grounding_rate"]
            - off["resolver_grounding_rate"],
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
        "regressions": regressions,
        "transition_counts": dict(sorted(transitions.items())),
    }
    replay_all = all(
        row["replay"]["input_fingerprint_same"] is True
        and row["replay"]["goal_digest_same"] is True
        and row["replay"]["off_semantic_outcome_same"] is True
        and row["replay"]["on_semantic_outcome_same"] is True
        for row in (*items, *controls)
    )
    sentinel_all = all(
        condition["evaluator_sentinel_unchanged"] is True
        for row in (*items, *controls)
        for condition in row["conditions"].values()
    )
    off_structurally_absent = all(
        row["conditions"]["off"]["stage_structurally_absent"] is True
        and row["conditions"]["off"]["stage_digest_sha256"] is None
        and row["conditions"]["off"]["stage_snapshot_bound_bytes"] == 0
        for row in (*items, *controls)
    )
    candidate_controls_passed = all(
        row["contract_passed"] is True for row in controls
    )
    stage_controls_passed = all(
        row["contract_passed"] is True for row in staging_controls
    )
    metamorphic = _derive_metamorphic(items, semantic_groups)
    control_metrics = {
        "candidate_control_count": len(controls),
        "candidate_condition_executions": len(controls) * 2,
        "candidate_contract_passed": sum(
            int(row["contract_passed"] is True) for row in controls
        ),
        "candidate_controls_all_passed": candidate_controls_passed,
        "candidate_accepted_fires": sum(
            int(condition["accepted_fire"] is True)
            for row in controls
            for condition in row["conditions"].values()
        ),
        "candidate_raw_fires": sum(
            int(condition["raw_fired"] is True)
            for row in controls
            for condition in row["conditions"].values()
        ),
        "staging_control_count": len(staging_controls),
        "staging_rejections_observed": sum(
            int(row["expected_rejection_observed"] is True)
            for row in staging_controls
        ),
        "staging_controls_all_passed": stage_controls_passed,
        "control_probe_gate_passed": (
            len(controls) == EXPECTED_CONTROLS
            and len(staging_controls) == EXPECTED_STAGING_CONTROLS
            and candidate_controls_passed
            and stage_controls_passed
        ),
    }
    gate = (
        off["n"] == on["n"] == EXPECTED_ITEMS
        and off["input_valid"] == off["compiled"] == EXPECTED_ITEMS
        and off["raw_fired"]
        == off["formula_fired"]
        == off["resolver_grounded"]
        == off["proof_replayed"]
        == off["accepted_fired"]
        == off["grounded"]
        == off["correct"]
        == off["wrong_fire"]
        == off["error"]
        == 0
        and off["abstain"] == EXPECTED_ITEMS
        and on["input_valid"]
        == on["compiled"]
        == on["raw_fired"]
        == on["formula_fired"]
        == on["resolver_grounded"]
        == on["proof_replayed"]
        == on["accepted_fired"]
        == on["grounded"]
        == on["correct"]
        == on["provenance_bound_fires"]
        == EXPECTED_ITEMS
        and on["wrong_fire"] == on["abstain"] == on["error"] == 0
        and on["grounded_leaf_count_total"] == EXPECTED_ITEMS * 3
        and on["grounded_stage_leaf_count_total"] == EXPECTED_ITEMS * 3
        and on["evidence_id_count_total"] == EXPECTED_ITEMS * 3
        and paired["regressions"] == 0
        and paired["transition_counts"] == {"abstain_to_correct": EXPECTED_ITEMS}
        and all(
            row["on_output_matches_expected_answer"] is True for row in items
        )
        and metamorphic["semantic_group_count"] == EXPECTED_SEMANTIC_GROUPS
        and metamorphic["passed"] == EXPECTED_SEMANTIC_GROUPS
        and replay_all
        and sentinel_all
        and off_structurally_absent
        and control_metrics["control_probe_gate_passed"]
    )
    return {
        "off": off,
        "on": on,
        "off_to_on": paired,
        "metamorphic": metamorphic,
        "controls": control_metrics,
        "input_goal_replay_all": replay_all,
        "evaluator_sentinel_unchanged_all": sentinel_all,
        "off_stage_structurally_absent_all": off_structurally_absent,
        "on_output_matches_expected_answer_all": all(
            row["on_output_matches_expected_answer"] is True for row in items
        ),
        "e4_development_gate_passed": gate,
    }


def _control_contract_passed(
    fixture_row: Mapping[str, Any],
    records: Mapping[str, Mapping[str, Any]],
    replay: Mapping[str, Any],
) -> bool:
    off = records["off"]
    on = records["on"]
    expected_status = fixture_row.get("expected_status")
    common = (
        off["compiler"]["status"] == expected_status
        and on["compiler"]["status"] == expected_status
        and off["raw_fired"] is False
        and on["raw_fired"] is False
        and off["accepted_fire"] is False
        and on["accepted_fire"] is False
        and off["choice_key"] is None
        and on["choice_key"] is None
        and off["provenance_digest_sha256"] is None
        and on["provenance_digest_sha256"] is None
        and all(value is True for value in replay.values() if type(value) is bool)
    )
    if not common:
        return False
    if expected_status == "compiled":
        return (
            off["reason"] == fixture_row.get("expected_reason_off")
            and on["reason"] == fixture_row.get("expected_reason_on")
        )
    return (
        off["reason"] == fixture_row.get("expected_reason")
        and on["reason"] == fixture_row.get("expected_reason")
    )


def _selection(fixture: Mapping[str, Any]) -> dict[str, Any]:
    items = fixture["paired_items"]
    controls = fixture["negative_controls"]
    item_ids = [row["id"] for row in items]
    control_ids = [row["id"] for row in controls]
    safe_items = [_candidate_payload(row) for row in items]
    safe_controls = [_candidate_payload(row) for row in controls]
    semantic_groups = json.loads(
        canonical_json_bytes(fixture["semantic_groups"])
    )
    return {
        "evaluator_owned_fixed_denominator": True,
        "expected_item_count": EXPECTED_ITEMS,
        "expected_semantic_group_count": EXPECTED_SEMANTIC_GROUPS,
        "expected_control_count": EXPECTED_CONTROLS,
        "item_ids": item_ids,
        "item_ids_sha256": _sha256(canonical_json_bytes(item_ids)),
        "input_choice_pairs_sha256": _sha256(
            canonical_json_bytes(safe_items)
        ),
        "semantic_groups": semantic_groups,
        "semantic_groups_sha256": _sha256(
            canonical_json_bytes(semantic_groups)
        ),
        "control_ids": control_ids,
        "control_ids_sha256": _sha256(canonical_json_bytes(control_ids)),
        "control_input_choice_pairs_sha256": _sha256(
            canonical_json_bytes(safe_controls)
        ),
        "gold_positions": dict(
            sorted(Counter(row["gold"] for row in items).items())
        ),
    }


def _protocol() -> dict[str, Any]:
    return {
        "pair": (
            "same frozen scalar items and choices; only access to the "
            "validated quantity stage differs"
        ),
        "conditions": {
            "off": (
                "compiler enabled; stage snapshot structurally absent; "
                "no fallback or guessing"
            ),
            "on": (
                "same compiler, items, and choices; validated read-only "
                "quantity stage enabled"
            ),
        },
        "counterbalance": (
            "even ordinals OFF-then-ON, odd ordinals ON-then-OFF; "
            "semantic replay reverses primary order"
        ),
        "off_first_items": 6,
        "on_first_items": 6,
        "strict_denominator": EXPECTED_ITEMS,
        "correlated_semantic_group_denominator": EXPECTED_SEMANTIC_GROUPS,
        "candidate_control_denominator": EXPECTED_CONTROLS,
        "staging_control_denominator": EXPECTED_STAGING_CONTROLS,
        "denominator_owner": "frozen evaluator selection, never compiler",
        "candidate_arguments_exclude_gold": True,
        "candidate_worker_boundary": (
            "function arguments contain only question and choices; item IDs, "
            "gold, expected outcomes, and control labels stay evaluator-side"
        ),
        "metamorphic_inference_limit": (
            "twelve authored items form six correlated semantic groups; "
            "no independent-sample inference is claimed"
        ),
        "staging_control_limit": (
            "the three controls rechecksum a modified data file and manifest "
            "while leaving an evidence, dimension, or policy corroborator "
            "inconsistent; resistance to a fully coordinated stage rewrite "
            "is not established"
        ),
        "evaluator_sentinel_limit": (
            "the callback observes only a receipt-owned empty sentinel that "
            "the candidate cannot access; shipped graph immutability is not "
            "observed"
        ),
        "current_verification": (
            "start a fresh Python process, rebuild the complete deterministic "
            "payload with current bytes and semantic replay, then compare it "
            "exactly"
        ),
        "fresh_process_current_replay_enforced": True,
        "separate_process_isolation_enforced": False,
        "network_isolation_enforced": False,
        "process_resource_telemetry_omitted": True,
    }


def _claims(gate: bool, control_gate: bool) -> dict[str, Any]:
    return {
        "classification": (
            "bounded_scalar_neutralization_with_controls_development_only"
        ),
        "e4_development_evidence": True,
        "e4_development_gate_passed": gate,
        "control_probe_evidence": True,
        "control_probe_gate_passed": control_gate,
        "e5_claimed": False,
        "independent": False,
        "externally_signed": False,
        "hidden_holdout_claimed": False,
        "external_authenticity_established": False,
        "coordinated_stage_rewrite_resistance_claimed": False,
        "shipped_graph_immutability_claimed": False,
        "benchmark_capability_claimed": False,
        "process_resource_curve_claimed": False,
    }


def _seal() -> dict[str, Any]:
    return {
        "sealed": True,
        "scope": (
            "current local evaluator, candidate closure, fixture, and stage "
            "bytes stable before-after; exact paired reverse replay; stable "
            "receipt-owned evaluator sentinel; candidate and manifest-"
            "rechecksummed partial-inconsistency stage controls; deterministic "
            "payload; recomputable checksum"
        ),
        "git_clean_required": False,
        "hidden_holdout_claimed": False,
        "independent_evaluation_claimed": False,
        "authenticity_established": False,
        "coordinated_stage_rewrite_resistance_claimed": False,
        "shipped_graph_immutability_claimed": False,
        "resource_curve_established": False,
        "e5_equivalent": False,
    }


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


def _bind_receipt_scopes(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "source": bind_files(repo_root, SOURCE_PATHS),
        "candidate": bind_files(repo_root, CANDIDATE_PATHS),
        "dataset": bind_files(repo_root, DATASET_PATHS),
        "stage": bind_files(repo_root, STAGE_PATHS),
    }


def _validate_record_shapes(
    items: Any,
    controls: Any,
    staging_controls: Any,
    findings: list[str],
) -> None:
    if not isinstance(items, list) or len(items) != EXPECTED_ITEMS:
        findings.append("item denominator mismatch")
        return
    if not isinstance(controls, list) or len(controls) != EXPECTED_CONTROLS:
        findings.append("candidate-control denominator mismatch")
        return
    if (
        not isinstance(staging_controls, list)
        or len(staging_controls) != EXPECTED_STAGING_CONTROLS
    ):
        findings.append("staging-control denominator mismatch")
        return
    for label, rows, fields in (
        ("items", items, _ITEM_FIELDS),
        ("controls", controls, _CONTROL_FIELDS),
    ):
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping) or frozenset(row) != fields:
                findings.append(f"{label}[{index}] fields mismatch")
                continue
            if row.get("ordinal") != index:
                findings.append(f"{label}[{index}] ordinal mismatch")
            if label == "items":
                try:
                    expected_answer = str(
                        Fraction(str(row.get("expected_answer_liters")))
                    )
                except (ValueError, ZeroDivisionError):
                    findings.append(
                        f"{label}[{index}] expected answer invalid"
                    )
                else:
                    if (
                        row.get("expected_answer_liters") != expected_answer
                        or row.get("on_output_matches_expected_answer")
                        is not True
                    ):
                        findings.append(
                            f"{label}[{index}] expected answer mismatch"
                        )
            primary = row.get("primary_execution_order")
            replay_order = row.get("replay_execution_order")
            expected_primary = (
                ["off", "on"] if index % 2 == 0 else ["on", "off"]
            )
            if primary != expected_primary or replay_order != list(
                reversed(expected_primary)
            ):
                findings.append(f"{label}[{index}] execution order mismatch")
            conditions = row.get("conditions")
            if (
                not isinstance(conditions, Mapping)
                or frozenset(conditions) != {"off", "on"}
            ):
                findings.append(f"{label}[{index}] condition map mismatch")
                continue
            for condition_name, condition in conditions.items():
                if (
                    not isinstance(condition, Mapping)
                    or frozenset(condition) != _CONDITION_FIELDS
                ):
                    findings.append(
                        f"{label}[{index}].{condition_name} fields mismatch"
                    )
                    continue
                compiler = condition.get("compiler")
                if (
                    not isinstance(compiler, Mapping)
                    or frozenset(compiler) != _COMPILER_FIELDS
                ):
                    findings.append(
                        f"{label}[{index}].{condition_name}.compiler mismatch"
                    )
            transition = row.get("off_to_on")
            replay = row.get("replay")
            if (
                not isinstance(transition, Mapping)
                or frozenset(transition) != _TRANSITION_FIELDS
                or transition
                != _transition(conditions["off"], conditions["on"])
            ):
                findings.append(f"{label}[{index}] transition mismatch")
            if (
                not isinstance(replay, Mapping)
                or frozenset(replay) != _REPLAY_FIELDS
            ):
                findings.append(f"{label}[{index}] replay fields mismatch")
    for index, row in enumerate(staging_controls):
        if (
            not isinstance(row, Mapping)
            or frozenset(row) != _STAGING_CONTROL_FIELDS
        ):
            findings.append(f"staging_controls[{index}] fields mismatch")


def validate_receipt(manifest: Mapping[str, Any]) -> list[str]:
    """Validate deterministic structure and all metrics derivable in-receipt."""

    findings: list[str] = []
    try:
        if not isinstance(manifest, Mapping) or frozenset(manifest) != _ROOT_FIELDS:
            return ["receipt fields mismatch"]
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
            paths = _scope_paths(manifest.get(name))
            if paths != sorted(expected_paths):
                findings.append(f"{name} scope paths mismatch")
        items = manifest.get("items")
        controls = manifest.get("controls")
        staging_controls = manifest.get("staging_controls")
        _validate_record_shapes(items, controls, staging_controls, findings)
        selection = manifest.get("selection")
        if not isinstance(selection, Mapping):
            findings.append("selection missing")
            semantic_groups: list[Mapping[str, Any]] = []
        else:
            semantic_groups_value = selection.get("semantic_groups")
            semantic_groups = (
                semantic_groups_value
                if isinstance(semantic_groups_value, list)
                else []
            )
            item_ids = [row.get("item_id") for row in items]
            control_ids = [row.get("item_id") for row in controls]
            if (
                selection.get("expected_item_count") != EXPECTED_ITEMS
                or selection.get("expected_semantic_group_count")
                != EXPECTED_SEMANTIC_GROUPS
                or selection.get("expected_control_count") != EXPECTED_CONTROLS
                or selection.get("item_ids") != item_ids
                or selection.get("control_ids") != control_ids
                or selection.get("item_ids_sha256")
                != _sha256(canonical_json_bytes(item_ids))
                or selection.get("control_ids_sha256")
                != _sha256(canonical_json_bytes(control_ids))
                or selection.get("semantic_groups_sha256")
                != _sha256(canonical_json_bytes(semantic_groups))
            ):
                findings.append("selection does not derive")
        if not findings:
            expected_metrics = _derive_metrics(
                items,
                controls,
                staging_controls,
                semantic_groups,
            )
            if manifest.get("metrics") != expected_metrics:
                findings.append("metrics do not derive from outcomes")
        metrics = manifest.get("metrics")
        gate = (
            metrics.get("e4_development_gate_passed")
            if isinstance(metrics, Mapping)
            else False
        )
        control_gate = (
            metrics.get("controls", {}).get("control_probe_gate_passed")
            if isinstance(metrics, Mapping)
            and isinstance(metrics.get("controls"), Mapping)
            else False
        )
        if manifest.get("claims") != _claims(
            gate is True,
            control_gate is True,
        ):
            findings.append("claims invalid or overstate authority")
        if manifest.get("seal") != _seal():
            findings.append("seal meaning invalid")
        fixture = manifest.get("fixture")
        if (
            not isinstance(fixture, Mapping)
            or fixture.get("path") != FIXTURE_PATH
            or fixture.get("frozen_expected_sha256")
            != FROZEN_FIXTURE_SHA256
            or fixture.get("actual_sha256") != FROZEN_FIXTURE_SHA256
            or fixture.get("item_count") != EXPECTED_ITEMS
            or fixture.get("semantic_group_count") != EXPECTED_SEMANTIC_GROUPS
            or fixture.get("candidate_control_count") != EXPECTED_CONTROLS
            or fixture.get("staging_control_count")
            != EXPECTED_STAGING_CONTROLS
        ):
            findings.append("fixture binding invalid")
        stage_snapshot = manifest.get("stage_snapshot")
        if (
            not isinstance(stage_snapshot, Mapping)
            or stage_snapshot.get("species_count") != 7
            or stage_snapshot.get("formula_count") != 1
            or stage_snapshot.get("external_authenticity_established")
            is not False
        ):
            findings.append("stage snapshot descriptor invalid")
        integrity = manifest.get("integrity")
        required_true = {
            "source_same_before_after",
            "candidate_same_before_after",
            "dataset_same_before_after",
            "stage_same_before_after",
            "fixture_matches_frozen_hash",
            "same_items_choices_off_on",
            "gold_absent_from_candidate_arguments_all",
            "input_goal_replay_all",
            "evaluator_sentinel_unchanged",
            "off_stage_structurally_absent_all",
            "candidate_control_probes_passed",
            "staging_control_probes_passed",
            "fresh_process_current_replay_enforced",
            "process_resource_telemetry_omitted",
        }
        required_false = {
            "network_isolation_enforced",
            "shipped_graph_write_authority",
            "shipped_graph_immutability_observed",
            "production_authority",
            "hidden_holdout_claimed",
            "independent_evaluation_claimed",
            "external_authenticity_established",
            "coordinated_stage_rewrite_resistance_claimed",
            "resource_curve_established",
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
            if integrity.get("evaluator_sentinel_digest_before") != integrity.get(
                "evaluator_sentinel_digest_after"
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
    """Run the complete fixed pair, controls, and reverse replay."""

    scopes_before = _bind_receipt_scopes(repo_root)
    fixture, fixture_bytes = _fixture(repo_root)
    stage_snapshot = load_science_quantity_stage(repo_root / STAGE_ROOT)
    if (
        len(stage_snapshot.species) != 7
        or len(stage_snapshot.formulas) != 1
        or any(
            row.evidence.externally_authenticated is not False
            for row in (*stage_snapshot.species, *stage_snapshot.formulas)
        )
    ):
        raise BenchmarkEvidenceError("scalar stage snapshot contract mismatch")
    evaluator_sentinel: dict[str, Any] = {}

    def base_state_digest() -> str:
        return _base_digest(evaluator_sentinel)

    base_before = base_state_digest()
    item_receipts = []
    for ordinal, row in enumerate(fixture["paired_items"]):
        safe_item = _candidate_payload(row)
        expected_answer_liters = str(
            Fraction(str(row["expected_answer_liters"]))
        )
        primary_order = (
            ["off", "on"] if ordinal % 2 == 0 else ["on", "off"]
        )
        records, replay = _execute_pair(
            safe_item,
            stage=stage_snapshot,
            primary_order=primary_order,
            gold=row["gold"],
            base_state_digest=base_state_digest,
        )
        item_receipts.append(
            {
                "item_id": row["id"],
                "ordinal": ordinal,
                "surface_id": row["surface_id"],
                "semantic_group_id": row["semantic_group_id"],
                "evaluator_eligible": True,
                "expected_answer_liters": expected_answer_liters,
                "on_output_matches_expected_answer": (
                    records["on"]["output_value_liters"]
                    == expected_answer_liters
                ),
                "input_digest_sha256": _sha256(
                    canonical_json_bytes(safe_item)
                ),
                "choices_digest_sha256": _sha256(
                    canonical_json_bytes(safe_item["choices"])
                ),
                "primary_execution_order": primary_order,
                "replay_execution_order": list(reversed(primary_order)),
                "conditions": records,
                "off_to_on": _transition(records["off"], records["on"]),
                "replay": replay,
                "gold_absent_from_candidate_arguments": True,
            }
        )
    control_receipts = []
    for ordinal, row in enumerate(fixture["negative_controls"]):
        safe_item = _candidate_payload(row)
        primary_order = (
            ["off", "on"] if ordinal % 2 == 0 else ["on", "off"]
        )
        records, replay = _execute_pair(
            safe_item,
            stage=stage_snapshot,
            primary_order=primary_order,
            gold=None,
            base_state_digest=base_state_digest,
        )
        control_receipts.append(
            {
                "item_id": row["id"],
                "ordinal": ordinal,
                "control_type": row["control_type"],
                "evaluator_eligible": True,
                "input_digest_sha256": _sha256(
                    canonical_json_bytes(safe_item)
                ),
                "choices_digest_sha256": _sha256(
                    canonical_json_bytes(safe_item["choices"])
                ),
                "primary_execution_order": primary_order,
                "replay_execution_order": list(reversed(primary_order)),
                "conditions": records,
                "off_to_on": _transition(records["off"], records["on"]),
                "replay": replay,
                "gold_absent_from_candidate_arguments": True,
                "contract_passed": _control_contract_passed(
                    row,
                    records,
                    replay,
                ),
            }
        )
    staging_control_receipts = _run_staging_controls(repo_root)
    base_after = base_state_digest()
    scopes_after = _bind_receipt_scopes(repo_root)
    changed = [
        name
        for name in scopes_before
        if scopes_before[name] != scopes_after[name]
    ]
    if changed:
        raise BenchmarkEvidenceError(
            "bound bytes changed during scalar run: " + ", ".join(changed)
        )
    if base_before != base_after:
        raise BenchmarkEvidenceError(
            "receipt-owned evaluator sentinel changed during scalar run"
        )
    selection = _selection(fixture)
    metrics = _derive_metrics(
        item_receipts,
        control_receipts,
        staging_control_receipts,
        selection["semantic_groups"],
    )
    formula = stage_snapshot.formula_for(NEUTRALIZATION_FORMULA_ID)
    if formula is None:
        raise BenchmarkEvidenceError("validated scalar formula missing")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "protocol": _protocol(),
        "claims": _claims(
            metrics["e4_development_gate_passed"],
            metrics["controls"]["control_probe_gate_passed"],
        ),
        "seal": _seal(),
        **scopes_before,
        "fixture": {
            "path": FIXTURE_PATH,
            "frozen_expected_sha256": FROZEN_FIXTURE_SHA256,
            "actual_sha256": _sha256(fixture_bytes),
            "item_count": EXPECTED_ITEMS,
            "semantic_group_count": EXPECTED_SEMANTIC_GROUPS,
            "candidate_control_count": EXPECTED_CONTROLS,
            "staging_control_count": EXPECTED_STAGING_CONTROLS,
        },
        "stage_snapshot": {
            "stage_id": stage_snapshot.stage_id,
            "stage_digest_sha256": stage_snapshot.stage_digest_sha256,
            "manifest_checksum_sha256": (
                stage_snapshot.manifest_checksum_sha256
            ),
            "bound_bytes": stage_snapshot.bound_bytes,
            "species_count": len(stage_snapshot.species),
            "formula_count": len(stage_snapshot.formulas),
            "formula_expression_digest_sha256": (
                formula.expression_digest_sha256
            ),
            "external_authenticity_established": False,
        },
        "selection": selection,
        "metrics": metrics,
        "items": item_receipts,
        "controls": control_receipts,
        "staging_controls": staging_control_receipts,
        "integrity": {
            "source_same_before_after": True,
            "candidate_same_before_after": True,
            "dataset_same_before_after": True,
            "stage_same_before_after": True,
            "fixture_matches_frozen_hash": True,
            "same_items_choices_off_on": True,
            "gold_absent_from_candidate_arguments_all": True,
            "input_goal_replay_all": metrics["input_goal_replay_all"],
            "evaluator_sentinel_unchanged": (
                base_before == base_after
                and metrics["evaluator_sentinel_unchanged_all"] is True
            ),
            "off_stage_structurally_absent_all": metrics[
                "off_stage_structurally_absent_all"
            ],
            "candidate_control_probes_passed": metrics["controls"][
                "candidate_controls_all_passed"
            ],
            "staging_control_probes_passed": metrics["controls"][
                "staging_controls_all_passed"
            ],
            "fresh_process_current_replay_enforced": True,
            "process_resource_telemetry_omitted": True,
            "evaluator_sentinel_digest_before": base_before,
            "evaluator_sentinel_digest_after": base_after,
            "network_isolation_enforced": False,
            "shipped_graph_write_authority": False,
            "shipped_graph_immutability_observed": False,
            "production_authority": False,
            "hidden_holdout_claimed": False,
            "independent_evaluation_claimed": False,
            "external_authenticity_established": False,
            "coordinated_stage_rewrite_resistance_claimed": False,
            "resource_curve_established": False,
        },
    }
    return _finalize(payload)


def build_receipt(
    *,
    repo_root: Path = REPO,
) -> dict[str, Any]:
    """Build through a fresh interpreter so executed code follows disk bytes."""

    outer_scopes_before = _bind_receipt_scopes(repo_root)
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.science_stage_scalar_e4_receipt",
                "--internal-build-worker",
            ],
            cwd=repo_root,
            check=False,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BenchmarkEvidenceError(
            f"fresh scalar receipt worker failed: {type(exc).__name__}"
        ) from exc
    if completed.returncode != 0:
        raise BenchmarkEvidenceError(
            "fresh scalar receipt worker exited nonzero"
        )
    payload = completed.stdout
    if not payload or len(payload) > MAX_RECEIPT_BYTES:
        raise BenchmarkEvidenceError("fresh scalar receipt worker size invalid")
    manifest = strict_json_bytes(payload, label="fresh scalar receipt worker")
    if payload != canonical_json_bytes(manifest) + b"\n":
        raise BenchmarkEvidenceError(
            "fresh scalar receipt worker output is not canonical JSON"
        )
    outer_scopes_after = _bind_receipt_scopes(repo_root)
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
            "bound bytes changed across fresh scalar worker: "
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
            f"scalar receipt unreadable: {type(exc).__name__}"
        ) from exc
    if not payload or len(payload) > MAX_RECEIPT_BYTES:
        raise BenchmarkEvidenceError("scalar receipt size invalid")
    manifest = strict_json_bytes(payload, label="scalar receipt")
    if payload != canonical_json_bytes(manifest) + b"\n":
        raise BenchmarkEvidenceError(
            "scalar receipt is not canonical JSON with one trailing newline"
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
    """Verify bytes and, by default, rebuild every current semantic field."""

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
            "resource_curve_established": False,
            "checksum_sha256": None,
            "source_matches_current": False,
            "candidate_matches_current": False,
            "dataset_matches_current": False,
            "stage_matches_current": False,
            "findings": [str(exc)],
        }
    findings = validate_receipt(manifest)
    structure_valid = not findings
    current_scopes = {
        name: _scope_matches_current(manifest.get(name), repo_root)
        for name in ("source", "candidate", "dataset", "stage")
    }
    matches_current = all(current_scopes.values())
    if require_current:
        try:
            expected = build_receipt(repo_root=repo_root)
        except Exception as exc:
            findings.append(
                f"current scalar replay failed closed: {type(exc).__name__}"
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
            # Rebind after the current semantic replay so a source race cannot
            # hide behind the scopes captured at replay start.
            for name in ("source", "candidate", "dataset", "stage"):
                current_scopes[name] = _scope_matches_current(
                    manifest.get(name),
                    repo_root,
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
        "e5_claimed": manifest.get("claims", {}).get("e5_claimed") is True,
        "authenticity_established": False,
        "resource_curve_established": False,
        "checksum_sha256": manifest.get("manifest_checksum_sha256"),
        "source_matches_current": current_scopes["source"],
        "candidate_matches_current": current_scopes["candidate"],
        "dataset_matches_current": current_scopes["dataset"],
        "stage_matches_current": current_scopes["stage"],
        "findings": findings,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or verify the scalar science local receipt."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write once to this path; otherwise emit canonical JSON",
    )
    parser.add_argument(
        "--verify",
        type=Path,
        help="verify an existing receipt instead of building",
    )
    parser.add_argument(
        "--internal-build-worker",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.internal_build_worker:
        if args.verify is not None or args.output is not None:
            raise BenchmarkEvidenceError(
                "internal build worker cannot combine actions"
            )
        manifest = _build_receipt_in_process(repo_root=REPO)
        sys.stdout.buffer.write(canonical_json_bytes(manifest) + b"\n")
        return 0
    if args.verify is not None:
        report = verify_receipt(args.verify, repo_root=REPO)
        print(canonical_json_bytes(report).decode("utf-8"))
        return 0 if report["valid"] else 1
    manifest = build_receipt(repo_root=REPO)
    if args.output is not None:
        write_receipt_exclusive(args.output, manifest, repo_root=REPO)
    else:
        print(canonical_json_bytes(manifest).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
