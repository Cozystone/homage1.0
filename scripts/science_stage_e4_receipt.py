"""Produce a strict, source-bound paired E4 science-staging receipt.

This is a self-measured development instrument.  It runs the same frozen 15
items and choices with the science stage structurally absent or read-only ON,
counterbalances condition order, and replays both conditions.  The candidate
worker never receives gold as an argument.  ``sealed`` has the deliberately
narrow meaning recorded in the receipt: exact evaluator/candidate/dataset/stage
bytes were stable during the run, the frozen fixture hash matched, semantic
replay matched, the base stayed immutable, and the receipt has a recomputable
checksum.  It does not mean a hidden holdout, independent evaluation,
authenticity, or E5 evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
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
from packages.reasoning_vm.science_exam import (  # noqa: E402
    answer_science_mcq,
    outcome_digest,
)
from packages.reasoning_vm.science_staging import (  # noqa: E402
    ScienceStageError,
    ScienceStageSnapshot,
    load_science_stage,
)


SCHEMA_VERSION = "atanor.science-stage-paired-e4-receipt.v3"
EVIDENCE_KIND = "strict_self_measured_e4_development_receipt"
FROZEN_FIXTURE_SHA256 = (
    "b0ae7a07694a40551659becba33370b3140fe7927ac846a180e87d84eb80c1b1"
)
EXPECTED_ITEMS = 15
EXPECTED_NEGATIVE_CONTROLS = 3
EXPECTED_STAGING_CONTROLS = 2

FIXTURE_PATH = (
    "packages/reasoning_vm/tests/fixtures/"
    "science_staging_e4_holdout_v1.json"
)
STAGE_ROOT = (
    "packages/reasoning_vm/tests/fixtures/"
    "science_stage_atomic_number_v1"
)
STAGE_PATHS = (
    f"{STAGE_ROOT}/evidence.jsonl",
    f"{STAGE_ROOT}/facts.jsonl",
    f"{STAGE_ROOT}/manifest.json",
)
SOURCE_PATHS = (
    "packages/eval_evidence/__init__.py",
    "packages/eval_evidence/receipt.py",
    "scripts/science_stage_e4_receipt.py",
)
CANDIDATE_PATHS = (
    "packages/__init__.py",
    "packages/cognitive_core/__init__.py",
    # Importing ``packages.cognitive_core.canonical`` first executes the
    # package initializer, which loads these transitive candidate modules.
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
    "packages/reasoning_vm/deduction.py",
    "packages/reasoning_vm/quantity.py",
    "packages/reasoning_vm/science_exam.py",
    "packages/reasoning_vm/science_staging.py",
    "packages/reasoning_vm/deliberator/__init__.py",
    "packages/reasoning_vm/deliberator/back_chain.py",
    "packages/reasoning_vm/deliberator/reasoner.py",
    "packages/reasoning_vm/deliberator/science_goal.py",
)
DATASET_PATHS = (FIXTURE_PATH,)

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
_CONDITION_FIELDS = frozenset(
    {
        "status",
        "choice_key",
        "choice_digest_sha256",
        "correct",
        "wrong_fire",
        "compiler",
        "raw_fired",
        "engine_fired",
        "grounded",
        "proof_digest_sha256",
        "provenance_digest_sha256",
        "evidence_ids",
        "grounded_leaf_count",
        "grounded_stage_leaf_count",
        "stage_hit_count",
        "stage_digest_sha256",
        "stage_snapshot_bound_bytes",
        "stage_bytes_read",
        "rss_delta_bytes",
        "reason",
        "error_kind",
        "semantic_outcome_digest_sha256",
        "base_state_unchanged",
    }
)
_COMPILER_FIELDS = frozenset(
    {
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
_TRANSITION_FIELDS = frozenset(
    {
        "label",
        "correct_delta",
        "firing_delta",
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
_SELECTION_FIELDS = frozenset(
    {
        "evaluator_owned_fixed_denominator",
        "expected_item_count",
        "expected_control_count",
        "item_ids",
        "item_ids_sha256",
        "input_choice_pairs_sha256",
        "control_ids",
        "control_ids_sha256",
        "control_input_choice_pairs_sha256",
    }
)
_CONTROL_ITEM_FIELDS = frozenset(
    (_ITEM_FIELDS - {"surface_id"}) | {"control_type"}
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
        "observed_loader_error",
        "observed_loader_error_sha256",
    }
)
_STAGE_SNAPSHOT_FIELDS = frozenset(
    {
        "stage_id",
        "stage_digest_sha256",
        "manifest_checksum_sha256",
        "bound_bytes",
        "row_count",
    }
)
_INTEGRITY_FIELDS = frozenset(
    {
        "source_same_before_after",
        "candidate_same_before_after",
        "dataset_same_before_after",
        "stage_same_before_after",
        "fixture_matches_frozen_hash",
        "same_items_choices_off_on",
        "gold_absent_from_candidate_arguments_all",
        "input_goal_replay_all",
        "base_state_immutable",
        "control_probes_passed",
        "base_state_digest_before",
        "base_state_digest_after",
        "network_isolation_enforced",
        "shipped_graph_write_authority",
        "production_authority",
        "process_resource_telemetry_omitted",
    }
)
_MAX_RECEIPT_BYTES = 16 * 1024 * 1024


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        raise BenchmarkEvidenceError("metric denominator must be positive")
    return round(numerator / denominator, 12)


def _base_digest(base: Mapping[str, Any]) -> str:
    return _sha256(canonical_json_bytes(base))


def _fixture(repo_root: Path) -> tuple[dict[str, Any], bytes]:
    path = repo_root / FIXTURE_PATH
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise BenchmarkEvidenceError(
            f"frozen E4 fixture unreadable: {type(exc).__name__}"
        ) from exc
    digest = _sha256(payload)
    if digest != FROZEN_FIXTURE_SHA256:
        raise BenchmarkEvidenceError(
            "frozen E4 fixture does not match its predeclared hash"
        )
    fixture = strict_json_bytes(payload, label="frozen science E4 fixture")
    if (
        fixture.get("classification") != "frozen_development_probe_not_e5"
        or fixture.get("claims", {}).get("e5_eligible") is not False
        or fixture.get("claims", {}).get("independent_evaluator_claimed")
        is not False
    ):
        raise BenchmarkEvidenceError("fixture authority claims are invalid")
    items = fixture.get("paired_items")
    if (
        not isinstance(items, list)
        or len(items) != EXPECTED_ITEMS
        or fixture.get("paired_protocol", {}).get("strict_denominator")
        != EXPECTED_ITEMS
    ):
        raise BenchmarkEvidenceError("frozen E4 denominator is not exactly 15")
    identifiers: set[str] = set()
    for ordinal, row in enumerate(items):
        if not isinstance(row, dict):
            raise BenchmarkEvidenceError(f"fixture item {ordinal} is not an object")
        item_id = row.get("id")
        question = row.get("question")
        choices = row.get("choices")
        gold = row.get("gold")
        if (
            not isinstance(item_id, str)
            or not item_id
            or item_id in identifiers
            or not isinstance(question, str)
            or not question
            or not isinstance(choices, dict)
            or not 2 <= len(choices) <= 8
            or not all(
                isinstance(key, str)
                and key
                and isinstance(value, str)
                and value
                for key, value in choices.items()
            )
            or not isinstance(gold, str)
            or gold not in choices
        ):
            raise BenchmarkEvidenceError(f"fixture item {ordinal} is malformed")
        identifiers.add(item_id)
    controls = fixture.get("negative_controls")
    if not isinstance(controls, list) or len(controls) != EXPECTED_NEGATIVE_CONTROLS:
        raise BenchmarkEvidenceError(
            "frozen E4 negative-control denominator is not exactly 3"
        )
    expected_control_types = {
        "unsupported_surface",
        "ambiguous_duplicate_choices",
        "unknown_entity",
    }
    seen_control_types: set[str] = set()
    for ordinal, row in enumerate(controls):
        if not isinstance(row, dict):
            raise BenchmarkEvidenceError(
                f"negative control {ordinal} is not an object"
            )
        item_id = row.get("id")
        control_type = row.get("control_type")
        question = row.get("question")
        choices = row.get("choices")
        if (
            not isinstance(item_id, str)
            or not item_id
            or item_id in identifiers
            or control_type not in expected_control_types
            or control_type in seen_control_types
            or not isinstance(question, str)
            or not question
            or not isinstance(choices, dict)
            or not 2 <= len(choices) <= 8
            or not all(
                isinstance(key, str)
                and key
                and isinstance(value, str)
                and value
                for key, value in choices.items()
            )
        ):
            raise BenchmarkEvidenceError(
                f"negative control {ordinal} is malformed"
            )
        identifiers.add(item_id)
        seen_control_types.add(control_type)
    if seen_control_types != expected_control_types:
        raise BenchmarkEvidenceError(
            "negative-control taxonomy is incomplete"
        )
    staging_controls = fixture.get("staging_control_metadata")
    if (
        not isinstance(staging_controls, dict)
        or frozenset(staging_controls)
        != {"corrupt_source", "quarantine_conflict"}
    ):
        raise BenchmarkEvidenceError(
            "staging-control taxonomy is incomplete"
        )
    return fixture, payload


def _assert_fixture_matches_stage(
    fixture: Mapping[str, Any],
    stage: ScienceStageSnapshot,
) -> None:
    staged = fixture.get("staged_facts")
    if not isinstance(staged, list) or len(staged) != len(stage.facts):
        raise BenchmarkEvidenceError("fixture and validated stage row counts differ")
    declared = [
        {
            "fact_id": row.get("fact_id"),
            "triple": row.get("triple"),
        }
        for row in staged
        if isinstance(row, Mapping)
    ]
    loaded = [
        {
            "fact_id": row.evidence.evidence_id,
            "triple": list(row.triple),
        }
        for row in stage.facts
    ]
    if declared != loaded:
        raise BenchmarkEvidenceError(
            "fixture facts do not exactly match the validated stage"
        )


def _canonical_jsonl(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def _refresh_mutated_stage_manifest(stage_root: Path) -> None:
    manifest_path = stage_root / "manifest.json"
    manifest = strict_json_bytes(
        manifest_path.read_bytes(),
        label="mutated science-stage manifest",
    )
    for field, name in (
        ("facts_file", "facts.jsonl"),
        ("evidence_file", "evidence.jsonl"),
    ):
        payload = (stage_root / name).read_bytes()
        manifest[field]["bytes"] = len(payload)
        manifest[field]["sha256"] = _sha256(payload)
    manifest.pop("manifest_checksum_sha256", None)
    manifest["manifest_checksum_sha256"] = _sha256(
        canonical_json_bytes(manifest)
    )
    manifest_path.write_bytes(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _stage_tree_content_digest(stage_root: Path) -> str:
    records: list[dict[str, Any]] = []
    for path in sorted(
        (candidate for candidate in stage_root.rglob("*") if candidate.is_file()),
        key=lambda candidate: candidate.relative_to(stage_root).as_posix(),
    ):
        payload = path.read_bytes()
        records.append(
            {
                "path": path.relative_to(stage_root).as_posix(),
                "bytes": len(payload),
                "sha256": _sha256(payload),
            }
        )
    return _sha256(canonical_json_bytes(records))


def _mutate_stage_control(
    stage_root: Path,
    *,
    control_type: str,
    metadata: Mapping[str, Any],
) -> None:
    candidate = metadata.get("candidate_fact")
    if not isinstance(candidate, Mapping):
        raise BenchmarkEvidenceError(
            f"{control_type} candidate metadata is malformed"
        )
    if control_type == "corrupt_source":
        path = stage_root / "evidence.jsonl"
        rows = [
            strict_json_bytes(line, label="stage evidence control row")
            for line in path.read_bytes().splitlines()
            if line
        ]
        matches = [
            row
            for row in rows
            if row.get("source_url") == candidate.get("source_url")
            and row.get("source_revision") == candidate.get("source_revision")
        ]
        if len(matches) != 1:
            raise BenchmarkEvidenceError(
                "corrupt-source control target is not unique"
            )
        matches[0]["source_record_id"] = candidate.get("source_record_id")
        path.write_bytes(_canonical_jsonl(rows))
    elif control_type == "quarantine_conflict":
        path = stage_root / "facts.jsonl"
        rows = [
            strict_json_bytes(line, label="stage fact control row")
            for line in path.read_bytes().splitlines()
            if line
        ]
        triple = candidate.get("triple")
        if (
            not isinstance(triple, list)
            or len(triple) != 3
            or not all(isinstance(value, str) for value in triple)
        ):
            raise BenchmarkEvidenceError(
                "quarantine-conflict triple is malformed"
            )
        matches = [
            row
            for row in rows
            if row.get("predicate") == triple[1]
            and row.get("object") == triple[2]
        ]
        if len(matches) != 1:
            raise BenchmarkEvidenceError(
                "quarantine-conflict control target is not unique"
            )
        # Admission is attempted with the conflict visible.  The loader must
        # reject it before any snapshot can be handed to the reasoner; the
        # evaluator then classifies that rejected candidate as quarantined.
        matches[0]["subject"] = triple[0]
        matches[0]["quarantined"] = False
        path.write_bytes(_canonical_jsonl(rows))
    else:
        raise BenchmarkEvidenceError(
            f"unsupported staging control: {control_type}"
        )
    _refresh_mutated_stage_manifest(stage_root)


def _run_staging_controls(
    repo_root: Path,
    fixture: Mapping[str, Any],
) -> list[dict[str, Any]]:
    metadata = fixture.get("staging_control_metadata")
    if not isinstance(metadata, Mapping):
        raise BenchmarkEvidenceError("staging-control metadata is missing")
    expected_messages = {
        "corrupt_source": "provenance identity mismatch",
        "quarantine_conflict": "functional predicate conflict",
    }
    recipe_ids = {
        "corrupt_source": "foreign_qid_source_record_v1",
        "quarantine_conflict": "functional_relation_subject_collision_v1",
    }
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="atanor-science-e4-control-") as tmp:
        temp_root = Path(tmp)
        for control_type in ("corrupt_source", "quarantine_conflict"):
            declared = metadata.get(control_type)
            if not isinstance(declared, Mapping):
                raise BenchmarkEvidenceError(
                    f"{control_type} metadata is malformed"
                )
            stage_root = temp_root / control_type
            shutil.copytree(repo_root / STAGE_ROOT, stage_root)
            _mutate_stage_control(
                stage_root,
                control_type=control_type,
                metadata=declared,
            )
            content_digest = _stage_tree_content_digest(stage_root)

            def observe() -> tuple[bool, bool, str | None, str | None]:
                try:
                    snapshot = load_science_stage(stage_root)
                except ScienceStageError as exc:
                    return False, False, type(exc).__name__, str(exc)
                return True, snapshot is not None, None, None

            primary = observe()
            replay = observe()
            (
                loader_accepted,
                snapshot_returned,
                error_kind,
                observed_error,
            ) = primary
            semantic_replay_same = primary == replay
            expected_message = expected_messages[control_type]
            expected_rejection = (
                not loader_accepted
                and not snapshot_returned
                and error_kind == "ScienceStageError"
                and isinstance(observed_error, str)
                and expected_message in observed_error
            )
            expected = declared.get("expected")
            reason = (
                expected.get("reason")
                if isinstance(expected, Mapping)
                else None
            )
            records.append(
                {
                    "control_id": declared.get("control_id"),
                    "control_type": control_type,
                    "mutation_recipe_id": recipe_ids[control_type],
                    "mutated_stage_content_sha256": content_digest,
                    "loader_accepted": loader_accepted,
                    "snapshot_returned": snapshot_returned,
                    "expected_rejection_observed": expected_rejection,
                    "semantic_replay_same": semantic_replay_same,
                    "contract_passed": (
                        expected_rejection and semantic_replay_same
                    ),
                    "reason": reason,
                    "error_kind": error_kind,
                    "observed_loader_error": observed_error,
                    "observed_loader_error_sha256": (
                        _sha256(observed_error.encode("utf-8"))
                        if isinstance(observed_error, str)
                        else None
                    ),
                }
            )
    return records


def _candidate_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    """Detach only evaluator-safe fields; labels and gold stay evaluator-side."""

    return {
        "item_id": "opaque-" + _sha256(row["id"].encode("utf-8")),
        "question": row["question"],
        "choices": json.loads(canonical_json_bytes(row["choices"])),
    }


def run_candidate(
    item: Mapping[str, Any],
    *,
    stage: ScienceStageSnapshot | None,
    overlay_enabled: bool,
    base_facts: Callable[[str], list[tuple[str, str, str]]],
    base_state_digest: Callable[[], str],
) -> dict[str, Any]:
    """Gold-blind worker boundary used by both paired conditions."""

    if not isinstance(item, Mapping) or frozenset(item) != {
        "item_id",
        "question",
        "choices",
    }:
        raise BenchmarkEvidenceError(
            "candidate item must contain only item_id, question, and choices"
        )
    if not isinstance(item["item_id"], str) or not item["item_id"]:
        raise BenchmarkEvidenceError("candidate item_id is invalid")
    if not isinstance(item["question"], str) or not isinstance(
        item["choices"], Mapping
    ):
        raise BenchmarkEvidenceError("candidate question or choices are invalid")
    return answer_science_mcq(
        item["question"],
        item["choices"],
        base_facts,
        stage,
        overlay_enabled=overlay_enabled,
        base_state_digest=base_state_digest,
    )


def _run_condition(
    safe_item: Mapping[str, Any],
    *,
    stage: ScienceStageSnapshot,
    enabled: bool,
    base_facts: Callable[[str], list[tuple[str, str, str]]],
    base_state_digest: Callable[[], str],
) -> dict[str, Any]:
    detached = json.loads(canonical_json_bytes(safe_item))
    before = canonical_json_bytes(detached)
    outcome = run_candidate(
        detached,
        stage=stage if enabled else None,
        overlay_enabled=enabled,
        base_facts=base_facts,
        base_state_digest=base_state_digest,
    )
    if canonical_json_bytes(detached) != before:
        raise BenchmarkEvidenceError("candidate mutated its item or choices")
    return outcome


def _compiler_record(outcome: Mapping[str, Any]) -> dict[str, Any]:
    compiler = outcome.get("compiler")
    if not isinstance(compiler, Mapping):
        raise BenchmarkEvidenceError("candidate compiler telemetry is missing")
    if type(compiler.get("input_valid")) is not bool:
        raise BenchmarkEvidenceError(
            "compiler must report input_valid independently of evaluator eligibility"
        )
    return {
        "input_valid": compiler["input_valid"],
        "compiled": compiler.get("compiled") is True,
        "status": compiler.get("status"),
        "reason": compiler.get("reason"),
        "input_fingerprint": compiler.get("input_fingerprint"),
        "goal_digest_sha256": compiler.get("goal_digest_sha256"),
        "surface_family": compiler.get("surface_family"),
        "compiler_rule": compiler.get("compiler_rule"),
    }


def _condition_record(
    outcome: Mapping[str, Any],
    *,
    gold: str | None,
) -> dict[str, Any]:
    engine = outcome.get("engine")
    staging = outcome.get("staging")
    integrity = outcome.get("integrity")
    resources = outcome.get("resources")
    if (
        not isinstance(engine, Mapping)
        or not isinstance(staging, Mapping)
        or not isinstance(integrity, Mapping)
        or not isinstance(resources, Mapping)
    ):
        raise BenchmarkEvidenceError("candidate telemetry is incomplete")
    fired = engine.get("accepted_fire") is True
    choice = outcome.get("choice_key")
    correct = gold is not None and choice == gold
    error_kind = outcome.get("error_kind")
    status = (
        "error"
        if error_kind is not None
        else "correct"
        if correct
        else "wrong"
        if fired
        else "abstain"
    )
    return {
        "status": status,
        "choice_key": choice,
        "choice_digest_sha256": outcome.get("choice_digest_sha256"),
        "correct": correct,
        "wrong_fire": fired and not correct,
        "compiler": _compiler_record(outcome),
        "raw_fired": engine.get("raw_fired") is True,
        "engine_fired": fired,
        "grounded": engine.get("grounded") is True,
        "proof_digest_sha256": engine.get("proof_digest_sha256"),
        "provenance_digest_sha256": staging.get(
            "provenance_digest_sha256"
        ),
        "evidence_ids": list(staging.get("evidence_ids") or []),
        "grounded_leaf_count": staging.get("grounded_leaf_count"),
        "grounded_stage_leaf_count": staging.get(
            "grounded_stage_leaf_count"
        ),
        "stage_hit_count": staging.get("staged_hit_count"),
        "stage_digest_sha256": staging.get("stage_digest_sha256"),
        "stage_snapshot_bound_bytes": staging.get(
            "stage_snapshot_bound_bytes"
        ),
        "stage_bytes_read": staging.get("stage_bytes_read"),
        # Process RSS is deliberately omitted: an unsigned self-checksum
        # cannot attest noisy process telemetry.
        "rss_delta_bytes": None,
        "reason": outcome.get("reason"),
        "error_kind": error_kind,
        "semantic_outcome_digest_sha256": outcome_digest(outcome),
        "base_state_unchanged": integrity.get("base_state_unchanged") is True,
    }


def _transition(off: Mapping[str, Any], on: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "label": f"{off['status']}_to_{on['status']}",
        "correct_delta": int(on["correct"]) - int(off["correct"]),
        "firing_delta": int(on["engine_fired"]) - int(off["engine_fired"]),
        "grounding_delta": int(on["grounded"]) - int(off["grounded"]),
        "wrong_fire_delta": int(on["wrong_fire"]) - int(off["wrong_fire"]),
    }


def _condition_semantics(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return every receipt condition field except process-noisy RSS."""

    return {
        field: record.get(field)
        for field in sorted(_CONDITION_FIELDS - {"rss_delta_bytes"})
    }


def _execute_runtime_pair(
    safe_item: Mapping[str, Any],
    *,
    stage: ScienceStageSnapshot,
    primary_order: Sequence[str],
    gold: str | None,
    base_facts: Callable[[str], list[tuple[str, str, str]]],
    base_state_digest: Callable[[], str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if list(primary_order) not in (["off", "on"], ["on", "off"]):
        raise BenchmarkEvidenceError("runtime pair order is invalid")
    replay_order = list(reversed(primary_order))
    primary: dict[str, dict[str, Any]] = {}
    repeated: dict[str, dict[str, Any]] = {}
    for condition in primary_order:
        primary[condition] = _run_condition(
            safe_item,
            stage=stage,
            enabled=condition == "on",
            base_facts=base_facts,
            base_state_digest=base_state_digest,
        )
    for condition in replay_order:
        repeated[condition] = _run_condition(
            safe_item,
            stage=stage,
            enabled=condition == "on",
            base_facts=base_facts,
            base_state_digest=base_state_digest,
        )
    records = {
        condition: _condition_record(primary[condition], gold=gold)
        for condition in ("off", "on")
    }
    compiler_records = [
        outcome["compiler"]
        for outcome in (
            primary["off"],
            primary["on"],
            repeated["off"],
            repeated["on"],
        )
    ]
    input_fingerprints = {
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
            len(input_fingerprints) == 1
            and None not in input_fingerprints
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
    return records, replay


def _condition_metrics(
    items: Sequence[Mapping[str, Any]],
    condition: str,
) -> dict[str, Any]:
    rows = [row["conditions"][condition] for row in items]
    n = len(rows)
    input_valid = sum(
        int(row["compiler"]["input_valid"] is True) for row in rows
    )
    compiled = sum(int(row["compiler"]["compiled"] is True) for row in rows)
    fired = sum(int(row["engine_fired"] is True) for row in rows)
    grounded = sum(int(row["grounded"] is True) for row in rows)
    correct = sum(int(row["correct"] is True) for row in rows)
    wrong_fire = sum(int(row["wrong_fire"] is True) for row in rows)
    abstain = sum(int(row["status"] == "abstain") for row in rows)
    error = sum(int(row["status"] == "error") for row in rows)
    return {
        "n": n,
        "input_valid": input_valid,
        "compiled": compiled,
        "fired": fired,
        "grounded": grounded,
        "correct": correct,
        "wrong_fire": wrong_fire,
        "abstain": abstain,
        "error": error,
        "input_valid_rate": _ratio(input_valid, n),
        "compiler_conformance_rate": _ratio(compiled, n),
        "engine_firing_rate": _ratio(fired, n),
        "grounded_coverage": _ratio(grounded, n),
        "strict_accuracy": _ratio(correct, n),
        "wrong_fire_rate": _ratio(wrong_fire, n),
        "abstention_rate": _ratio(abstain, n),
        "answered_accuracy": None if fired == 0 else _ratio(correct, fired),
    }


def _negative_condition_matches(
    record: Mapping[str, Any],
    *,
    input_valid: bool,
    compiled: bool,
    reason: str,
    stage_present: bool,
    compiler_status: str,
    compiler_reason: str,
    surface_family: str | None,
    compiler_rule: str | None,
) -> bool:
    compiler = record.get("compiler")
    return (
        isinstance(compiler, Mapping)
        and compiler.get("input_valid") is input_valid
        and compiler.get("compiled") is compiled
        and compiler.get("status") == compiler_status
        and compiler.get("reason") == compiler_reason
        and compiler.get("surface_family") == surface_family
        and compiler.get("compiler_rule") == compiler_rule
        and (
            isinstance(compiler.get("goal_digest_sha256"), str)
            and _SHA256.fullmatch(compiler["goal_digest_sha256"]) is not None
            if compiled
            else compiler.get("goal_digest_sha256") is None
        )
        and record.get("status") == "abstain"
        and record.get("choice_key") is None
        and record.get("choice_digest_sha256") is None
        and record.get("correct") is False
        and record.get("wrong_fire") is False
        and record.get("raw_fired") is False
        and record.get("engine_fired") is False
        and record.get("grounded") is False
        and record.get("proof_digest_sha256") is None
        and record.get("provenance_digest_sha256") is None
        and record.get("evidence_ids") == []
        and record.get("grounded_leaf_count") == 0
        and record.get("grounded_stage_leaf_count") == 0
        and record.get("stage_hit_count") == 0
        and (
            record.get("stage_snapshot_bound_bytes", 0) > 0
            if stage_present
            else record.get("stage_snapshot_bound_bytes") == 0
        )
        and (
            isinstance(record.get("stage_digest_sha256"), str)
            and _SHA256.fullmatch(record["stage_digest_sha256"]) is not None
            if stage_present
            else record.get("stage_digest_sha256") is None
        )
        and record.get("stage_bytes_read") == 0
        and record.get("reason") == reason
        and record.get("error_kind") is None
        and record.get("base_state_unchanged") is True
    )


def _negative_control_taxonomy_matches(
    row: Mapping[str, Any],
) -> bool:
    conditions = row.get("conditions")
    if not isinstance(conditions, Mapping):
        return False
    control_type = row.get("control_type")
    expected: dict[
        str,
        tuple[
            bool,
            bool,
            str,
            str,
            str,
            str | None,
            str | None,
        ],
    ]
    if control_type == "unsupported_surface":
        expected = {
            "off": (
                True,
                False,
                "unsupported_goal_family",
                "abstain",
                "unsupported_goal_family",
                None,
                None,
            ),
            "on": (
                True,
                False,
                "unsupported_goal_family",
                "abstain",
                "unsupported_goal_family",
                None,
                None,
            ),
        }
    elif control_type == "ambiguous_duplicate_choices":
        expected = {
            "off": (
                False,
                False,
                "duplicate_normalized_choices",
                "invalid",
                "duplicate_normalized_choices",
                None,
                None,
            ),
            "on": (
                False,
                False,
                "duplicate_normalized_choices",
                "invalid",
                "duplicate_normalized_choices",
                None,
                None,
            ),
        }
    elif control_type == "unknown_entity":
        expected = {
            "off": (
                True,
                True,
                "required_evidence_unavailable",
                "compiled",
                "typed_science_goal_emitted",
                "atomic_number_what_is",
                "atomic_number_what_is_v1",
            ),
            "on": (
                True,
                True,
                "entity_unresolved",
                "compiled",
                "typed_science_goal_emitted",
                "atomic_number_what_is",
                "atomic_number_what_is_v1",
            ),
        }
    else:
        return False
    return all(
        _negative_condition_matches(
            conditions[condition],
            input_valid=values[0],
            compiled=values[1],
            reason=values[2],
            stage_present=condition == "on",
            compiler_status=values[3],
            compiler_reason=values[4],
            surface_family=values[5],
            compiler_rule=values[6],
        )
        for condition, values in expected.items()
    )


def _derive_control_metrics(
    controls: Sequence[Mapping[str, Any]],
    staging_controls: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(controls) != EXPECTED_NEGATIVE_CONTROLS:
        raise BenchmarkEvidenceError(
            "candidate control denominator is not exactly 3"
        )
    if len(staging_controls) != EXPECTED_STAGING_CONTROLS:
        raise BenchmarkEvidenceError(
            "staging control denominator is not exactly 2"
        )
    off_rows = [row["conditions"]["off"] for row in controls]
    on_rows = [row["conditions"]["on"] for row in controls]
    all_rows = off_rows + on_rows
    replay_all = all(
        row["replay"]["input_fingerprint_same"] is True
        and row["replay"]["goal_digest_same"] is True
        and row["replay"]["off_semantic_outcome_same"] is True
        and row["replay"]["on_semantic_outcome_same"] is True
        for row in controls
    )
    base_all = all(
        record["base_state_unchanged"] is True
        for row in controls
        for record in row["conditions"].values()
    )
    taxonomy_all = all(
        _negative_control_taxonomy_matches(row) for row in controls
    )
    stage_rejection_all = all(
        row.get("loader_accepted") is False
        and row.get("snapshot_returned") is False
        and row.get("expected_rejection_observed") is True
        and row.get("semantic_replay_same") is True
        and row.get("contract_passed") is True
        and row.get("error_kind") == "ScienceStageError"
        for row in staging_controls
    )
    off_unexpected_fires = sum(
        int(row.get("engine_fired") is True) for row in off_rows
    )
    on_unexpected_fires = sum(
        int(row.get("engine_fired") is True) for row in on_rows
    )
    raw_control_fires = sum(
        int(row.get("raw_fired") is True) for row in all_rows
    )
    accepted_control_fires = (
        off_unexpected_fires + on_unexpected_fires
    )
    choice_without_accept = sum(
        int(
            row.get("choice_key") is not None
            and row.get("engine_fired") is not True
        )
        for row in all_rows
    )
    evidence_leaks = sum(
        int(
            row.get("proof_digest_sha256") is not None
            or row.get("provenance_digest_sha256") is not None
            or bool(row.get("evidence_ids"))
            or row.get("grounded_leaf_count") not in (0, None)
            or row.get("grounded_stage_leaf_count") not in (0, None)
            or row.get("stage_hit_count") not in (0, None)
        )
        for row in all_rows
    )
    errors = sum(
        int(row.get("error_kind") is not None) for row in all_rows
    )
    off_stage_snapshot_exposure = sum(
        int(
            row.get("stage_digest_sha256") is not None
            or row.get("stage_snapshot_bound_bytes") != 0
        )
        for row in off_rows
    )
    on_stage_snapshot_missing = sum(
        int(
            row.get("stage_digest_sha256") is None
            or not isinstance(row.get("stage_snapshot_bound_bytes"), int)
            or row.get("stage_snapshot_bound_bytes", 0) <= 0
        )
        for row in on_rows
    )
    return {
        "candidate": {
            "n": EXPECTED_NEGATIVE_CONTROLS,
            "condition_executions": EXPECTED_NEGATIVE_CONTROLS * 2,
            "off_abstain": sum(
                int(row.get("status") == "abstain") for row in off_rows
            ),
            "on_abstain": sum(
                int(row.get("status") == "abstain") for row in on_rows
            ),
            "invalid_reject": sum(
                int(
                    row.get("compiler", {}).get("input_valid") is False
                    and row.get("reason") == "duplicate_normalized_choices"
                )
                for row in all_rows
            ),
            "compiler_scope_abstain": sum(
                int(
                    row.get("compiler", {}).get("input_valid") is True
                    and row.get("compiler", {}).get("compiled") is False
                    and row.get("reason") == "unsupported_goal_family"
                )
                for row in all_rows
            ),
            "missing_stage_runtime_abstain": sum(
                int(row.get("reason") == "required_evidence_unavailable")
                for row in all_rows
            ),
            "unresolved_entity_runtime_abstain": sum(
                int(row.get("reason") == "entity_unresolved")
                for row in all_rows
            ),
            "raw_control_fire": raw_control_fires,
            "accepted_control_fire": accepted_control_fires,
            "off_unexpected_control_fire": off_unexpected_fires,
            "on_unexpected_control_fire": on_unexpected_fires,
            "unexpected_control_fire_rate": _ratio(
                accepted_control_fires,
                EXPECTED_NEGATIVE_CONTROLS * 2,
            ),
            "choice_without_accept": choice_without_accept,
            "evidence_leak": evidence_leaks,
            "error": errors,
            "off_stage_snapshot_exposure": off_stage_snapshot_exposure,
            "on_stage_snapshot_missing": on_stage_snapshot_missing,
            "taxonomy_matches_all": taxonomy_all,
            "semantic_replay_all": replay_all,
            "base_state_immutable_all": base_all,
        },
        "staging": {
            "n": EXPECTED_STAGING_CONTROLS,
            "rejected": sum(
                int(row.get("loader_accepted") is False)
                for row in staging_controls
            ),
            "snapshot_returned": sum(
                int(row.get("snapshot_returned") is True)
                for row in staging_controls
            ),
            "semantic_replay_all": all(
                row.get("semantic_replay_same") is True
                for row in staging_controls
            ),
            "expected_rejection_observed_all": stage_rejection_all,
        },
        "control_probe_gate_passed": (
            raw_control_fires == 0
            and accepted_control_fires == 0
            and choice_without_accept == 0
            and evidence_leaks == 0
            and errors == 0
            and off_stage_snapshot_exposure == 0
            and on_stage_snapshot_missing == 0
            and taxonomy_all
            and replay_all
            and base_all
            and stage_rejection_all
        ),
    }


def _derive_metrics(
    items: Sequence[Mapping[str, Any]],
    controls: Sequence[Mapping[str, Any]],
    staging_controls: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(items) != EXPECTED_ITEMS:
        raise BenchmarkEvidenceError("receipt denominator is not exactly 15")
    off = _condition_metrics(items, "off")
    on = _condition_metrics(items, "on")
    transitions = Counter(row["off_to_on"]["label"] for row in items)
    replay_all = all(
        row["replay"]["input_fingerprint_same"] is True
        and row["replay"]["goal_digest_same"] is True
        and row["replay"]["off_semantic_outcome_same"] is True
        and row["replay"]["on_semantic_outcome_same"] is True
        for row in items
    )
    base_all = all(
        row["conditions"][condition]["base_state_unchanged"] is True
        for row in items
        for condition in ("off", "on")
    )
    off_clean_control_all = all(
        row["conditions"]["off"]["compiler"]["input_valid"] is True
        and row["conditions"]["off"]["compiler"]["compiled"] is True
        and row["conditions"]["off"]["status"] == "abstain"
        and row["conditions"]["off"]["choice_key"] is None
        and row["conditions"]["off"]["choice_digest_sha256"] is None
        and row["conditions"]["off"]["correct"] is False
        and row["conditions"]["off"]["raw_fired"] is False
        and row["conditions"]["off"]["engine_fired"] is False
        and row["conditions"]["off"]["grounded"] is False
        and row["conditions"]["off"]["proof_digest_sha256"] is None
        and row["conditions"]["off"]["provenance_digest_sha256"] is None
        and row["conditions"]["off"]["evidence_ids"] == []
        and row["conditions"]["off"]["grounded_leaf_count"] == 0
        and row["conditions"]["off"]["grounded_stage_leaf_count"] == 0
        and row["conditions"]["off"]["stage_hit_count"] == 0
        and row["conditions"]["off"]["stage_digest_sha256"] is None
        and row["conditions"]["off"]["reason"]
        == "required_evidence_unavailable"
        and row["conditions"]["off"]["error_kind"] is None
        for row in items
    )
    on_proof_provenance_bound_all = all(
        row["conditions"]["on"]["compiler"]["input_valid"] is True
        and row["conditions"]["on"]["compiler"]["compiled"] is True
        and row["conditions"]["on"]["status"] == "correct"
        and row["conditions"]["on"]["correct"] is True
        and row["conditions"]["on"]["raw_fired"] is True
        and row["conditions"]["on"]["engine_fired"] is True
        and row["conditions"]["on"]["grounded"] is True
        and isinstance(
            row["conditions"]["on"]["proof_digest_sha256"], str
        )
        and _SHA256.fullmatch(
            row["conditions"]["on"]["proof_digest_sha256"]
        )
        is not None
        and isinstance(
            row["conditions"]["on"]["provenance_digest_sha256"], str
        )
        and _SHA256.fullmatch(
            row["conditions"]["on"]["provenance_digest_sha256"]
        )
        is not None
        and len(row["conditions"]["on"]["evidence_ids"]) == 1
        and row["conditions"]["on"]["grounded_leaf_count"] == 1
        and row["conditions"]["on"]["grounded_stage_leaf_count"] == 1
        and row["conditions"]["on"]["stage_hit_count"] == 1
        and isinstance(
            row["conditions"]["on"]["stage_digest_sha256"], str
        )
        and _SHA256.fullmatch(
            row["conditions"]["on"]["stage_digest_sha256"]
        )
        is not None
        and row["conditions"]["on"]["reason"] == "grounded_stage_proof"
        and row["conditions"]["on"]["error_kind"] is None
        for row in items
    )
    paired = {
        "strict_accuracy_delta": round(
            on["strict_accuracy"] - off["strict_accuracy"], 12
        ),
        "correct_delta": on["correct"] - off["correct"],
        "engine_firing_rate_delta": round(
            on["engine_firing_rate"] - off["engine_firing_rate"], 12
        ),
        "grounded_coverage_delta": round(
            on["grounded_coverage"] - off["grounded_coverage"], 12
        ),
        "wrong_fire_rate_delta": round(
            on["wrong_fire_rate"] - off["wrong_fire_rate"], 12
        ),
        "regressions": sum(
            int(
                row["conditions"]["off"]["correct"] is True
                and row["conditions"]["on"]["correct"] is not True
            )
            for row in items
        ),
        "transition_counts": dict(sorted(transitions.items())),
    }
    control_metrics = _derive_control_metrics(controls, staging_controls)
    gate_passed = (
        off["n"] == on["n"] == EXPECTED_ITEMS
        and off["input_valid"] == on["input_valid"] == EXPECTED_ITEMS
        and off["compiled"] == on["compiled"] == EXPECTED_ITEMS
        and off["fired"] == off["correct"] == off["wrong_fire"] == 0
        and on["fired"] == on["grounded"] == on["correct"] == EXPECTED_ITEMS
        and on["wrong_fire"] == on["error"] == 0
        and paired["regressions"] == 0
        and replay_all
        and base_all
        and off_clean_control_all
        and on_proof_provenance_bound_all
        and control_metrics["control_probe_gate_passed"]
    )
    return {
        "off": off,
        "on": on,
        "off_to_on": paired,
        "input_goal_replay_all": replay_all,
        "base_state_immutable_all": base_all,
        "off_clean_control_all": off_clean_control_all,
        "on_proof_provenance_bound_all": on_proof_provenance_bound_all,
        "control_probes": control_metrics,
        "e4_development_gate_passed": gate_passed,
    }


def _selection(fixture: Mapping[str, Any]) -> dict[str, Any]:
    rows = fixture["paired_items"]
    controls = fixture["negative_controls"]
    item_ids = [row["id"] for row in rows]
    control_ids = [row["id"] for row in controls]
    input_rows = [_candidate_payload(row) for row in rows]
    control_input_rows = [_candidate_payload(row) for row in controls]
    return {
        "evaluator_owned_fixed_denominator": True,
        "expected_item_count": EXPECTED_ITEMS,
        "expected_control_count": EXPECTED_NEGATIVE_CONTROLS,
        "item_ids": item_ids,
        "item_ids_sha256": _sha256(canonical_json_bytes(item_ids)),
        "input_choice_pairs_sha256": _sha256(
            canonical_json_bytes(input_rows)
        ),
        "control_ids": control_ids,
        "control_ids_sha256": _sha256(
            canonical_json_bytes(control_ids)
        ),
        "control_input_choice_pairs_sha256": _sha256(
            canonical_json_bytes(control_input_rows)
        ),
    }


def _protocol() -> dict[str, Any]:
    return {
        "pair": (
            "same frozen items and choices; only candidate access to the "
            "validated stage differs"
        ),
        "conditions": {
            "off": (
                "compiler enabled; no stage snapshot crosses the candidate boundary; "
                "no fallback or guessing"
            ),
            "on": (
                "same compiler/items/choices; validated read-only stage enabled"
            ),
        },
        "counterbalance": (
            "even ordinals OFF-then-ON, odd ordinals ON-then-OFF; semantic replay "
            "uses the reverse order"
        ),
        "off_first_items": 8,
        "on_first_items": 7,
        "strict_denominator": EXPECTED_ITEMS,
        "negative_control_denominator": EXPECTED_NEGATIVE_CONTROLS,
        "staging_control_denominator": EXPECTED_STAGING_CONTROLS,
        "control_probes": (
            "three frozen unsupported/ambiguous/unresolved candidates run "
            "OFF and ON with replay; two deterministic mutated-stage packs "
            "must be rejected before reasoner availability"
        ),
        "denominator_owner": "frozen evaluator selection, never compiler",
        "candidate_arguments_exclude_gold": True,
        "candidate_worker_boundary": (
            "function arguments contain only opaque item id, question, and "
            "choices; gold, expected outcome, and evaluator control labels "
            "remain outside that boundary"
        ),
        "separate_process_isolation_enforced": False,
        "unattested_runtime_metadata": (
            "timestamps, environment identity, and process resource telemetry "
            "are omitted"
        ),
        "output_modes": ["stdout", "exclusive_file"],
    }


def _scope_paths(scope: Any) -> list[str] | None:
    if not isinstance(scope, Mapping) or frozenset(scope) != _SCOPE_FIELDS:
        return None
    files = scope.get("files")
    if not isinstance(files, list) or not files:
        return None
    paths: list[str] = []
    for record in files:
        if not isinstance(record, Mapping) or frozenset(record) != _FILE_FIELDS:
            return None
        path = record.get("path")
        size = record.get("bytes")
        digest = record.get("sha256")
        if (
            not isinstance(path, str)
            or not path
            or type(size) is not int
            or size < 0
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
        ):
            return None
        paths.append(path)
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
    except BenchmarkEvidenceError:
        return False


def _checksum(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_checksum_sha256", None)
    return _sha256(canonical_json_bytes(unsigned))


def _validate_condition(
    value: Any,
    *,
    label: str,
    findings: list[str],
) -> None:
    if not isinstance(value, Mapping) or frozenset(value) != _CONDITION_FIELDS:
        findings.append(f"{label} fields mismatch")
        return
    compiler = value.get("compiler")
    if not isinstance(compiler, Mapping) or frozenset(compiler) != _COMPILER_FIELDS:
        findings.append(f"{label}.compiler fields mismatch")
    else:
        for field in ("input_valid", "compiled"):
            if type(compiler.get(field)) is not bool:
                findings.append(f"{label}.compiler.{field} must be boolean")
        for field in ("input_fingerprint", "goal_digest_sha256"):
            digest = compiler.get(field)
            if digest is not None and (
                not isinstance(digest, str) or _SHA256.fullmatch(digest) is None
            ):
                findings.append(f"{label}.compiler.{field} invalid")
    for field in (
        "correct",
        "wrong_fire",
        "raw_fired",
        "engine_fired",
        "grounded",
        "base_state_unchanged",
    ):
        if type(value.get(field)) is not bool:
            findings.append(f"{label}.{field} must be boolean")
    for field in (
        "choice_digest_sha256",
        "proof_digest_sha256",
        "provenance_digest_sha256",
        "stage_digest_sha256",
        "semantic_outcome_digest_sha256",
    ):
        digest = value.get(field)
        if digest is not None and (
            not isinstance(digest, str) or _SHA256.fullmatch(digest) is None
        ):
            findings.append(f"{label}.{field} invalid")
    if value.get("status") not in {"correct", "wrong", "abstain", "error"}:
        findings.append(f"{label}.status invalid")
    error_kind = value.get("error_kind")
    if error_kind is not None and (
        not isinstance(error_kind, str) or not error_kind
    ):
        findings.append(f"{label}.error_kind invalid")
    expected_status = (
        "error"
        if error_kind is not None
        else "correct"
        if value.get("correct") is True
        else "wrong"
        if value.get("engine_fired") is True
        else "abstain"
    )
    if value.get("status") != expected_status:
        findings.append(f"{label}.status is not derived")
    if value.get("wrong_fire") is not (
        value.get("engine_fired") is True and value.get("correct") is not True
    ):
        findings.append(f"{label}.wrong_fire is not derived")
    choice = value.get("choice_key")
    expected_choice_digest = (
        None
        if choice is None
        else _sha256(str(choice).encode("utf-8"))
    )
    if value.get("choice_digest_sha256") != expected_choice_digest:
        findings.append(f"{label}.choice digest is not derived")
    if choice is not None and value.get("engine_fired") is not True:
        findings.append(f"{label}.choice exists without an accepted fire")
    if value.get("correct") is True and value.get("engine_fired") is not True:
        findings.append(f"{label}.correct requires an accepted engine fire")
    if value.get("grounded") is True and value.get("engine_fired") is not True:
        findings.append(f"{label}.grounded requires an accepted engine fire")
    if value.get("engine_fired") is True:
        required_digests = (
            value.get("proof_digest_sha256"),
            value.get("provenance_digest_sha256"),
        )
        if (
            value.get("raw_fired") is not True
            or value.get("grounded") is not True
            or choice is None
            or any(
                not isinstance(digest, str)
                or _SHA256.fullmatch(digest) is None
                for digest in required_digests
            )
        ):
            findings.append(
                f"{label}.accepted fire lacks a grounded proof/provenance binding"
            )
        leaf_count = value.get("grounded_leaf_count")
        staged_leaf_count = value.get("grounded_stage_leaf_count")
        if (
            type(leaf_count) is not int
            or leaf_count <= 0
            or staged_leaf_count != leaf_count
        ):
            findings.append(
                f"{label}.accepted fire has incomplete staged leaf coverage"
            )
    evidence_ids = value.get("evidence_ids")
    if not isinstance(evidence_ids, list) or not all(
        isinstance(item, str) and item for item in evidence_ids
    ):
        findings.append(f"{label}.evidence_ids invalid")
    elif (
        evidence_ids != sorted(evidence_ids)
        or len(evidence_ids) != len(set(evidence_ids))
    ):
        findings.append(f"{label}.evidence_ids must be sorted and unique")
    elif value.get("engine_fired") is True and not evidence_ids:
        findings.append(f"{label}.accepted fire lacks staged evidence")
    for field in (
        "grounded_leaf_count",
        "grounded_stage_leaf_count",
        "stage_hit_count",
        "stage_snapshot_bound_bytes",
        "stage_bytes_read",
    ):
        number = value.get(field)
        if type(number) is not int or number < 0:
            findings.append(f"{label}.{field} must be a non-negative integer")
    if value.get("rss_delta_bytes") is not None:
        findings.append(f"{label}.process resource telemetry must be omitted")


def _validate_item(value: Any, index: int, findings: list[str]) -> None:
    label = f"items[{index}]"
    if not isinstance(value, Mapping) or frozenset(value) != _ITEM_FIELDS:
        findings.append(f"{label} fields mismatch")
        return
    if value.get("ordinal") != index:
        findings.append(f"{label}.ordinal mismatch")
    if value.get("evaluator_eligible") is not True:
        findings.append(f"{label}.evaluator_eligible must be true")
    if value.get("gold_absent_from_candidate_arguments") is not True:
        findings.append(
            f"{label}.gold_absent_from_candidate_arguments must be true"
        )
    primary = value.get("primary_execution_order")
    replay = value.get("replay_execution_order")
    expected_primary = ["off", "on"] if index % 2 == 0 else ["on", "off"]
    if primary != expected_primary:
        findings.append(f"{label}.primary_execution_order parity mismatch")
    if not isinstance(primary, list) or replay != list(reversed(primary)):
        findings.append(f"{label}.replay_execution_order is not counterbalanced")
    conditions = value.get("conditions")
    if not isinstance(conditions, Mapping) or frozenset(conditions) != {
        "off",
        "on",
    }:
        findings.append(f"{label}.conditions fields mismatch")
    else:
        _validate_condition(
            conditions["off"], label=f"{label}.conditions.off", findings=findings
        )
        _validate_condition(
            conditions["on"], label=f"{label}.conditions.on", findings=findings
        )
        if (
            isinstance(value.get("off_to_on"), Mapping)
            and frozenset(value["off_to_on"]) == _TRANSITION_FIELDS
            and value["off_to_on"] != _transition(
                conditions["off"], conditions["on"]
            )
        ):
            findings.append(f"{label}.off_to_on is not derived")
    transition = value.get("off_to_on")
    if not isinstance(transition, Mapping) or frozenset(transition) != (
        _TRANSITION_FIELDS
    ):
        findings.append(f"{label}.off_to_on fields mismatch")
    replay_record = value.get("replay")
    if not isinstance(replay_record, Mapping) or frozenset(replay_record) != (
        _REPLAY_FIELDS
    ):
        findings.append(f"{label}.replay fields mismatch")
    else:
        for field in (
            "input_fingerprint_same",
            "goal_digest_same",
            "off_semantic_outcome_same",
            "on_semantic_outcome_same",
        ):
            if type(replay_record.get(field)) is not bool:
                findings.append(f"{label}.replay.{field} must be boolean")
        for field in (
            "off_replay_digest_sha256",
            "on_replay_digest_sha256",
        ):
            digest = replay_record.get(field)
            if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
                findings.append(f"{label}.replay.{field} invalid")
        if isinstance(conditions, Mapping):
            off = conditions.get("off", {})
            on = conditions.get("on", {})
            if (
                replay_record.get("input_fingerprint_same") is True
                and off.get("compiler", {}).get("input_fingerprint")
                != on.get("compiler", {}).get("input_fingerprint")
            ):
                findings.append(
                    f"{label}.replay input fingerprint equality is not derived"
                )
            if (
                replay_record.get("goal_digest_same") is True
                and off.get("compiler", {}).get("goal_digest_sha256")
                != on.get("compiler", {}).get("goal_digest_sha256")
            ):
                findings.append(
                    f"{label}.replay goal digest equality is not derived"
                )
            if (
                replay_record.get("off_semantic_outcome_same") is True
                and replay_record.get("off_replay_digest_sha256")
                != off.get("semantic_outcome_digest_sha256")
            ):
                findings.append(
                    f"{label}.replay OFF semantic equality is not derived"
                )
            if (
                replay_record.get("on_semantic_outcome_same") is True
                and replay_record.get("on_replay_digest_sha256")
                != on.get("semantic_outcome_digest_sha256")
            ):
                findings.append(
                    f"{label}.replay ON semantic equality is not derived"
                )
    for field in ("input_digest_sha256", "choices_digest_sha256"):
        digest = value.get(field)
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            findings.append(f"{label}.{field} invalid")


def _validate_control_item(
    value: Any,
    index: int,
    findings: list[str],
) -> None:
    label = f"controls[{index}]"
    if (
        not isinstance(value, Mapping)
        or frozenset(value) != _CONTROL_ITEM_FIELDS
    ):
        findings.append(f"{label} fields mismatch")
        return
    control_type = value.get("control_type")
    if control_type not in {
        "unsupported_surface",
        "ambiguous_duplicate_choices",
        "unknown_entity",
    }:
        findings.append(f"{label}.control_type invalid")
    projected = dict(value)
    projected["surface_id"] = projected.pop("control_type")
    before = len(findings)
    _validate_item(projected, index, findings)
    for offset in range(before, len(findings)):
        findings[offset] = findings[offset].replace(
            f"items[{index}]", label
        )


def _validate_staging_control(
    value: Any,
    index: int,
    findings: list[str],
) -> None:
    label = f"staging_controls[{index}]"
    if (
        not isinstance(value, Mapping)
        or frozenset(value) != _STAGING_CONTROL_FIELDS
    ):
        findings.append(f"{label} fields mismatch")
        return
    control_type = value.get("control_type")
    expected = {
        "corrupt_source": (
            "provenance_entity_mismatch",
            "provenance identity mismatch",
            "foreign_qid_source_record_v1",
        ),
        "quarantine_conflict": (
            "functional_predicate_conflict",
            "functional predicate conflict",
            "functional_relation_subject_collision_v1",
        ),
    }.get(control_type)
    if expected is None:
        findings.append(f"{label}.control_type invalid")
        return
    control_id = value.get("control_id")
    if not isinstance(control_id, str) or not control_id:
        findings.append(f"{label}.control_id invalid")
    digest = value.get("mutated_stage_content_sha256")
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        findings.append(f"{label}.mutated stage digest invalid")
    if value.get("mutation_recipe_id") != expected[2]:
        findings.append(f"{label}.mutation_recipe_id invalid")
    for field in (
        "loader_accepted",
        "snapshot_returned",
        "expected_rejection_observed",
        "semantic_replay_same",
        "contract_passed",
    ):
        if type(value.get(field)) is not bool:
            findings.append(f"{label}.{field} must be boolean")
    if value.get("reason") != expected[0]:
        findings.append(f"{label}.reason does not match control taxonomy")
    observed = value.get("observed_loader_error")
    if not isinstance(observed, str) or expected[1] not in observed:
        findings.append(f"{label}.observed loader rejection mismatch")
    observed_digest = value.get("observed_loader_error_sha256")
    if (
        not isinstance(observed, str)
        or observed_digest != _sha256(observed.encode("utf-8"))
    ):
        findings.append(f"{label}.observed loader error digest mismatch")
    if (
        value.get("loader_accepted") is not False
        or value.get("snapshot_returned") is not False
        or value.get("expected_rejection_observed") is not True
        or value.get("semantic_replay_same") is not True
        or value.get("contract_passed") is not True
        or value.get("error_kind") != "ScienceStageError"
    ):
        findings.append(f"{label} did not fail closed as declared")


def validate_receipt(
    manifest: Mapping[str, Any],
    *,
    repo_root: Path = REPO,
    require_current: bool = False,
) -> list[str]:
    """Validate structure, derivations, checksum, and optionally current bytes."""

    findings: list[str] = []
    try:
        if not isinstance(manifest, Mapping) or frozenset(manifest) != _ROOT_FIELDS:
            return ["receipt root fields mismatch"]
        if manifest.get("schema_version") != SCHEMA_VERSION:
            findings.append("schema_version mismatch")
        if manifest.get("evidence_kind") != EVIDENCE_KIND:
            findings.append("evidence_kind mismatch")
        if manifest.get("protocol") != _protocol():
            findings.append("protocol mismatch")

        expected_scope_paths = {
            "source": sorted(SOURCE_PATHS),
            "candidate": sorted(CANDIDATE_PATHS),
            "dataset": sorted(DATASET_PATHS),
            "stage": sorted(STAGE_PATHS),
        }
        for name in ("source", "candidate", "dataset", "stage"):
            scope = manifest.get(name)
            paths = _scope_paths(scope)
            if paths is None:
                findings.append(f"{name} file scope invalid")
            elif paths != expected_scope_paths[name]:
                findings.append(f"{name} file scope paths mismatch")
            elif require_current and not _scope_matches_current(scope, repo_root):
                findings.append(f"{name} file scope does not match current tree")

        fixture = manifest.get("fixture")
        if fixture != {
            "path": FIXTURE_PATH,
            "frozen_expected_sha256": FROZEN_FIXTURE_SHA256,
            "actual_sha256": FROZEN_FIXTURE_SHA256,
            "item_count": EXPECTED_ITEMS,
            "negative_control_count": EXPECTED_NEGATIVE_CONTROLS,
            "staging_control_count": EXPECTED_STAGING_CONTROLS,
        }:
            findings.append("fixture binding mismatch")

        selection = manifest.get("selection")
        if (
            not isinstance(selection, Mapping)
            or frozenset(selection) != _SELECTION_FIELDS
        ):
            findings.append("selection invalid")
        else:
            item_ids = selection.get("item_ids")
            control_ids = selection.get("control_ids")
            if (
                selection.get("evaluator_owned_fixed_denominator") is not True
                or selection.get("expected_item_count") != EXPECTED_ITEMS
                or selection.get("expected_control_count")
                != EXPECTED_NEGATIVE_CONTROLS
                or not isinstance(item_ids, list)
                or len(item_ids) != EXPECTED_ITEMS
                or len(set(item_ids)) != EXPECTED_ITEMS
                or selection.get("item_ids_sha256")
                != _sha256(canonical_json_bytes(item_ids))
                or not isinstance(
                    selection.get("input_choice_pairs_sha256"), str
                )
                or _SHA256.fullmatch(
                    selection["input_choice_pairs_sha256"]
                )
                is None
                or not isinstance(control_ids, list)
                or len(control_ids) != EXPECTED_NEGATIVE_CONTROLS
                or len(set(control_ids)) != EXPECTED_NEGATIVE_CONTROLS
                or selection.get("control_ids_sha256")
                != _sha256(canonical_json_bytes(control_ids))
                or not isinstance(
                    selection.get("control_input_choice_pairs_sha256"),
                    str,
                )
                or _SHA256.fullmatch(
                    selection["control_input_choice_pairs_sha256"]
                )
                is None
            ):
                findings.append("selection denominator or identity invalid")

        items = manifest.get("items")
        if not isinstance(items, list) or len(items) != EXPECTED_ITEMS:
            findings.append("items must contain the exact 15-item denominator")
            items = []
        for index, row in enumerate(items):
            _validate_item(row, index, findings)
        controls = manifest.get("controls")
        if (
            not isinstance(controls, list)
            or len(controls) != EXPECTED_NEGATIVE_CONTROLS
        ):
            findings.append(
                "controls must contain the exact 3-item denominator"
            )
            controls = []
        for index, row in enumerate(controls):
            _validate_control_item(row, index, findings)
        staging_controls = manifest.get("staging_controls")
        if (
            not isinstance(staging_controls, list)
            or len(staging_controls) != EXPECTED_STAGING_CONTROLS
        ):
            findings.append(
                "staging_controls must contain the exact 2-control denominator"
            )
            staging_controls = []
        for index, row in enumerate(staging_controls):
            _validate_staging_control(row, index, findings)
        if items:
            if [row.get("item_id") for row in items] != (
                manifest.get("selection", {}).get("item_ids")
            ):
                findings.append("items do not match selection order")
            if [row.get("item_id") for row in controls] != (
                manifest.get("selection", {}).get("control_ids")
            ):
                findings.append("controls do not match selection order")
            try:
                expected_metrics = _derive_metrics(
                    items,
                    controls,
                    staging_controls,
                )
            except (BenchmarkEvidenceError, KeyError, TypeError, ValueError) as exc:
                findings.append(
                    f"metrics derivation failed closed: {type(exc).__name__}"
                )
            else:
                if manifest.get("metrics") != expected_metrics:
                    findings.append("metrics do not derive from item outcomes")
                claims = manifest.get("claims")
                if not isinstance(claims, Mapping) or (
                    claims.get("e4_development_gate_passed")
                    is not expected_metrics["e4_development_gate_passed"]
                ):
                    findings.append("E4 development claim does not derive")

        claims = manifest.get("claims")
        if not isinstance(claims, Mapping) or claims != {
            "classification": (
                "bounded_atomic_number_e4_with_controls_development_only"
            ),
            "e4_development_evidence": True,
            "e4_development_gate_passed": manifest.get("metrics", {}).get(
                "e4_development_gate_passed"
            ),
            "control_probe_evidence": True,
            "control_probe_gate_passed": manifest.get("metrics", {})
            .get("control_probes", {})
            .get("control_probe_gate_passed"),
            "e5_claimed": False,
            "independent": False,
            "externally_signed": False,
            "benchmark_capability_claimed": False,
            "process_resource_curve_claimed": False,
        }:
            findings.append("claims are invalid or overstate authority")

        seal = manifest.get("seal")
        if not isinstance(seal, Mapping) or seal != {
            "sealed": True,
            "scope": (
                "exact evaluator/candidate/dataset/stage bytes stable "
                "before-after + frozen fixture hash + paired semantic replay + "
                "negative/staging control probes + immutable base + "
                "deterministic semantic records + recomputable checksum"
            ),
            "git_clean_required": False,
            "hidden_holdout_claimed": False,
            "independent_evaluation_claimed": False,
            "authenticity_established": False,
            "e5_equivalent": False,
        }:
            findings.append("seal meaning is invalid")

        integrity = manifest.get("integrity")
        required_true = (
            "source_same_before_after",
            "candidate_same_before_after",
            "dataset_same_before_after",
            "stage_same_before_after",
            "fixture_matches_frozen_hash",
            "same_items_choices_off_on",
            "gold_absent_from_candidate_arguments_all",
            "input_goal_replay_all",
            "base_state_immutable",
            "control_probes_passed",
            "process_resource_telemetry_omitted",
        )
        required_false = (
            "network_isolation_enforced",
            "shipped_graph_write_authority",
            "production_authority",
        )
        if (
            not isinstance(integrity, Mapping)
            or frozenset(integrity) != _INTEGRITY_FIELDS
        ):
            findings.append("integrity invalid")
        else:
            for field in required_true:
                if integrity.get(field) is not True:
                    findings.append(f"integrity.{field} must be true")
            for field in required_false:
                if integrity.get(field) is not False:
                    findings.append(f"integrity.{field} must be false")
            before = integrity.get("base_state_digest_before")
            after = integrity.get("base_state_digest_after")
            if (
                not isinstance(before, str)
                or _SHA256.fullmatch(before) is None
                or after != before
            ):
                findings.append("base state digest is not immutable")

        stage_snapshot = manifest.get("stage_snapshot")
        if (
            not isinstance(stage_snapshot, Mapping)
            or frozenset(stage_snapshot) != _STAGE_SNAPSHOT_FIELDS
            or (
            not isinstance(stage_snapshot.get("stage_digest_sha256"), str)
            or _SHA256.fullmatch(stage_snapshot["stage_digest_sha256"]) is None
            or not isinstance(
                stage_snapshot.get("manifest_checksum_sha256"), str
            )
            or _SHA256.fullmatch(
                stage_snapshot["manifest_checksum_sha256"]
            )
            is None
            or type(stage_snapshot.get("bound_bytes")) is not int
            or stage_snapshot["bound_bytes"] <= 0
            or stage_snapshot.get("row_count") != EXPECTED_ITEMS
            )
        ):
            findings.append("stage snapshot metadata invalid")

        if require_current:
            try:
                current_fixture, _fixture_bytes = _fixture(repo_root)
                expected_selection = _selection(current_fixture)
                current_stage = load_science_stage(repo_root / STAGE_ROOT)
                current_staging_controls = _run_staging_controls(
                    repo_root,
                    current_fixture,
                )
            except Exception as exc:
                findings.append(
                    "current frozen inputs failed closed: "
                    f"{type(exc).__name__}"
                )
            else:
                verification_base: dict[
                    str,
                    list[tuple[str, str, str]],
                ] = {}

                def verification_base_facts(
                    subject: str,
                ) -> list[tuple[str, str, str]]:
                    return list(verification_base.get(subject, ()))

                def verification_base_digest() -> str:
                    return _base_digest(verification_base)

                if selection != expected_selection:
                    findings.append(
                        "selection does not derive from current frozen fixture"
                    )
                expected_stage_snapshot = {
                    "stage_id": current_stage.stage_id,
                    "stage_digest_sha256": current_stage.stage_digest_sha256,
                    "manifest_checksum_sha256": (
                        current_stage.manifest_checksum_sha256
                    ),
                    "bound_bytes": current_stage.bound_bytes,
                    "row_count": len(current_stage.facts),
                }
                if stage_snapshot != expected_stage_snapshot:
                    findings.append(
                        "stage snapshot does not match validated current stage"
                    )
                for index, (item, frozen) in enumerate(
                    zip(items, current_fixture["paired_items"], strict=True)
                ):
                    safe_item = _candidate_payload(frozen)
                    expected_records, expected_replay = _execute_runtime_pair(
                        safe_item,
                        stage=current_stage,
                        primary_order=(
                            ["off", "on"]
                            if index % 2 == 0
                            else ["on", "off"]
                        ),
                        gold=frozen["gold"],
                        base_facts=verification_base_facts,
                        base_state_digest=verification_base_digest,
                    )
                    for condition in ("off", "on"):
                        actual_record = item.get("conditions", {}).get(
                            condition, {}
                        )
                        if _condition_semantics(actual_record) != (
                            _condition_semantics(
                                expected_records[condition]
                            )
                        ):
                            findings.append(
                                f"items[{index}].conditions.{condition} "
                                "does not reproduce from current candidate"
                            )
                    if item.get("replay") != expected_replay:
                        findings.append(
                            f"items[{index}].replay does not reproduce "
                            "from current candidate"
                        )
                    if (
                        item.get("item_id") != frozen["id"]
                        or item.get("surface_id") != frozen["surface_id"]
                        or item.get("input_digest_sha256")
                        != _sha256(canonical_json_bytes(safe_item))
                        or item.get("choices_digest_sha256")
                        != _sha256(canonical_json_bytes(safe_item["choices"]))
                    ):
                        findings.append(
                            f"items[{index}] input binding does not match fixture"
                        )
                    off_record = item.get("conditions", {}).get("off", {})
                    on_record = item.get("conditions", {}).get("on", {})
                    expected_evidence_ids = frozen.get(
                        "expected_on", {}
                    ).get("evidence_fact_ids")
                    if (
                        off_record.get("evidence_ids") != []
                        or off_record.get("stage_hit_count") != 0
                        or on_record.get("evidence_ids")
                        != expected_evidence_ids
                        or on_record.get("stage_hit_count")
                        != len(expected_evidence_ids or [])
                        or off_record.get("stage_digest_sha256") is not None
                        or on_record.get("stage_digest_sha256")
                        != current_stage.stage_digest_sha256
                        or off_record.get("stage_snapshot_bound_bytes") != 0
                        or on_record.get("stage_snapshot_bound_bytes")
                        != current_stage.bound_bytes
                        or off_record.get("stage_bytes_read") != 0
                        or on_record.get("stage_bytes_read") != 0
                        or off_record.get("compiler", {}).get(
                            "surface_family"
                        )
                        != frozen["surface_id"]
                        or off_record.get("compiler", {}).get(
                            "compiler_rule"
                        )
                        != f"{frozen['surface_id']}_v1"
                        or on_record.get("compiler", {}).get(
                            "surface_family"
                        )
                        != frozen["surface_id"]
                        or on_record.get("compiler", {}).get(
                            "compiler_rule"
                        )
                        != f"{frozen['surface_id']}_v1"
                    ):
                        findings.append(
                            f"items[{index}] stage exposure or evidence binding "
                            "does not derive from the frozen stage"
                        )
                    for condition in ("off", "on"):
                        record = item.get("conditions", {}).get(condition, {})
                        choice = record.get("choice_key")
                        expected_correct = choice == frozen["gold"]
                        expected_wrong_fire = (
                            record.get("engine_fired") is True
                            and not expected_correct
                        )
                        expected_status = (
                            "error"
                            if record.get("error_kind") is not None
                            else "correct"
                            if expected_correct
                            else "wrong"
                            if record.get("engine_fired") is True
                            else "abstain"
                        )
                        expected_choice_digest = (
                            None
                            if choice is None
                            else _sha256(str(choice).encode("utf-8"))
                        )
                        if (
                            record.get("correct") is not expected_correct
                            or record.get("wrong_fire") is not expected_wrong_fire
                            or record.get("status") != expected_status
                            or record.get("choice_digest_sha256")
                            != expected_choice_digest
                        ):
                            findings.append(
                                f"items[{index}].conditions.{condition} "
                                "grading does not derive from fixture"
                            )
                for index, (control, frozen) in enumerate(
                    zip(
                        controls,
                        current_fixture["negative_controls"],
                        strict=True,
                    )
                ):
                    safe_item = _candidate_payload(frozen)
                    expected_records, expected_replay = _execute_runtime_pair(
                        safe_item,
                        stage=current_stage,
                        primary_order=(
                            ["off", "on"]
                            if index % 2 == 0
                            else ["on", "off"]
                        ),
                        gold=None,
                        base_facts=verification_base_facts,
                        base_state_digest=verification_base_digest,
                    )
                    for condition in ("off", "on"):
                        actual_record = control.get("conditions", {}).get(
                            condition, {}
                        )
                        if _condition_semantics(actual_record) != (
                            _condition_semantics(
                                expected_records[condition]
                            )
                        ):
                            findings.append(
                                f"controls[{index}].conditions.{condition} "
                                "does not reproduce from current candidate"
                            )
                    if control.get("replay") != expected_replay:
                        findings.append(
                            f"controls[{index}].replay does not reproduce "
                            "from current candidate"
                        )
                    if (
                        control.get("item_id") != frozen["id"]
                        or control.get("control_type")
                        != frozen["control_type"]
                        or control.get("input_digest_sha256")
                        != _sha256(canonical_json_bytes(safe_item))
                        or control.get("choices_digest_sha256")
                        != _sha256(
                            canonical_json_bytes(safe_item["choices"])
                        )
                    ):
                        findings.append(
                            f"controls[{index}] input binding does not "
                            "match fixture"
                        )
                    off_record = control.get("conditions", {}).get(
                        "off", {}
                    )
                    on_record = control.get("conditions", {}).get(
                        "on", {}
                    )
                    if (
                        off_record.get("stage_digest_sha256") is not None
                        or on_record.get("stage_digest_sha256")
                        != current_stage.stage_digest_sha256
                        or off_record.get("stage_snapshot_bound_bytes") != 0
                        or on_record.get("stage_snapshot_bound_bytes")
                        != current_stage.bound_bytes
                        or off_record.get("stage_bytes_read") != 0
                        or on_record.get("stage_bytes_read") != 0
                    ):
                        findings.append(
                            f"controls[{index}] stage isolation does not "
                            "derive from the frozen stage"
                        )
                    for condition in ("off", "on"):
                        record = control.get("conditions", {}).get(
                            condition, {}
                        )
                        expected_wrong_fire = (
                            record.get("engine_fired") is True
                        )
                        expected_status = (
                            "error"
                            if record.get("error_kind") is not None
                            else "wrong"
                            if expected_wrong_fire
                            else "abstain"
                        )
                        if (
                            record.get("correct") is not False
                            or record.get("wrong_fire")
                            is not expected_wrong_fire
                            or record.get("status") != expected_status
                        ):
                            findings.append(
                                f"controls[{index}].conditions.{condition} "
                                "negative grading is not derived"
                            )
                if staging_controls != current_staging_controls:
                    findings.append(
                        "staging controls do not reproduce from current "
                        "frozen inputs"
                    )
                for name in ("source", "candidate", "dataset", "stage"):
                    if not _scope_matches_current(
                        manifest.get(name),
                        repo_root,
                    ):
                        findings.append(
                            f"{name} scope differs after current semantic replay"
                        )

        digest = manifest.get("manifest_checksum_sha256")
        if (
            not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
            or digest != _checksum(manifest)
        ):
            findings.append("manifest checksum mismatch")
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
    manifest = json.loads(canonical_json_bytes(payload))
    if "manifest_checksum_sha256" in manifest:
        raise BenchmarkEvidenceError("checksum must not be supplied by caller")
    manifest["manifest_checksum_sha256"] = _checksum(manifest)
    findings = validate_receipt(manifest, require_current=True)
    if findings:
        raise BenchmarkEvidenceError("; ".join(findings))
    return manifest


def build_receipt(
    *,
    repo_root: Path = REPO,
) -> dict[str, Any]:
    """Run the fixed argument-separated pair/replay protocol."""

    fixture, fixture_bytes = _fixture(repo_root)
    stage_snapshot = load_science_stage(repo_root / STAGE_ROOT)
    _assert_fixture_matches_stage(fixture, stage_snapshot)

    scopes_before = {
        "source": bind_files(repo_root, SOURCE_PATHS),
        "candidate": bind_files(repo_root, CANDIDATE_PATHS),
        "dataset": bind_files(repo_root, DATASET_PATHS),
        "stage": bind_files(repo_root, STAGE_PATHS),
    }
    base: dict[str, list[tuple[str, str, str]]] = {}

    def base_facts(subject: str) -> list[tuple[str, str, str]]:
        return list(base.get(subject, ()))

    def base_state_digest() -> str:
        return _base_digest(base)

    base_before = base_state_digest()
    item_receipts: list[dict[str, Any]] = []
    for ordinal, row in enumerate(fixture["paired_items"]):
        safe_item = _candidate_payload(row)
        input_digest = _sha256(canonical_json_bytes(safe_item))
        choices_digest = _sha256(canonical_json_bytes(safe_item["choices"]))
        primary_order = (
            ["off", "on"] if ordinal % 2 == 0 else ["on", "off"]
        )
        replay_order = list(reversed(primary_order))
        primary: dict[str, dict[str, Any]] = {}
        for condition in primary_order:
            primary[condition] = _run_condition(
                safe_item,
                stage=stage_snapshot,
                enabled=condition == "on",
                base_facts=base_facts,
                base_state_digest=base_state_digest,
            )
        repeated: dict[str, dict[str, Any]] = {}
        for condition in replay_order:
            repeated[condition] = _run_condition(
                safe_item,
                stage=stage_snapshot,
                enabled=condition == "on",
                base_facts=base_facts,
                base_state_digest=base_state_digest,
            )

        off_record = _condition_record(primary["off"], gold=row["gold"])
        on_record = _condition_record(primary["on"], gold=row["gold"])
        off_replay_digest = outcome_digest(repeated["off"])
        on_replay_digest = outcome_digest(repeated["on"])
        compiler_records = [
            outcome["compiler"]
            for outcome in (
                primary["off"],
                primary["on"],
                repeated["off"],
                repeated["on"],
            )
        ]
        input_fingerprints = {
            record.get("input_fingerprint") for record in compiler_records
        }
        goal_digests = {
            record.get("goal_digest_sha256") for record in compiler_records
        }
        item_receipts.append(
            {
                "item_id": row["id"],
                "ordinal": ordinal,
                "surface_id": row["surface_id"],
                "evaluator_eligible": True,
                "input_digest_sha256": input_digest,
                "choices_digest_sha256": choices_digest,
                "primary_execution_order": primary_order,
                "replay_execution_order": replay_order,
                "conditions": {"off": off_record, "on": on_record},
                "off_to_on": _transition(off_record, on_record),
                "replay": {
                    "input_fingerprint_same": (
                        len(input_fingerprints) == 1
                        and None not in input_fingerprints
                    ),
                    "goal_digest_same": (
                        len(goal_digests) == 1 and None not in goal_digests
                    ),
                    "off_semantic_outcome_same": (
                        off_record["semantic_outcome_digest_sha256"]
                        == off_replay_digest
                    ),
                    "on_semantic_outcome_same": (
                        on_record["semantic_outcome_digest_sha256"]
                        == on_replay_digest
                    ),
                    "off_replay_digest_sha256": off_replay_digest,
                    "on_replay_digest_sha256": on_replay_digest,
                },
                "gold_absent_from_candidate_arguments": True,
            }
        )

    control_receipts: list[dict[str, Any]] = []
    for ordinal, row in enumerate(fixture["negative_controls"]):
        safe_item = _candidate_payload(row)
        primary_order = (
            ["off", "on"] if ordinal % 2 == 0 else ["on", "off"]
        )
        replay_order = list(reversed(primary_order))
        primary: dict[str, dict[str, Any]] = {}
        repeated: dict[str, dict[str, Any]] = {}
        for condition in primary_order:
            primary[condition] = _run_condition(
                safe_item,
                stage=stage_snapshot,
                enabled=condition == "on",
                base_facts=base_facts,
                base_state_digest=base_state_digest,
            )
        for condition in replay_order:
            repeated[condition] = _run_condition(
                safe_item,
                stage=stage_snapshot,
                enabled=condition == "on",
                base_facts=base_facts,
                base_state_digest=base_state_digest,
            )
        off_record = _condition_record(primary["off"], gold=None)
        on_record = _condition_record(primary["on"], gold=None)
        off_replay_digest = outcome_digest(repeated["off"])
        on_replay_digest = outcome_digest(repeated["on"])
        compiler_records = [
            outcome["compiler"]
            for outcome in (
                primary["off"],
                primary["on"],
                repeated["off"],
                repeated["on"],
            )
        ]
        input_fingerprints = {
            record.get("input_fingerprint") for record in compiler_records
        }
        goal_digests = {
            record.get("goal_digest_sha256") for record in compiler_records
        }
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
                "replay_execution_order": replay_order,
                "conditions": {"off": off_record, "on": on_record},
                "off_to_on": _transition(off_record, on_record),
                "replay": {
                    "input_fingerprint_same": (
                        len(input_fingerprints) == 1
                        and None not in input_fingerprints
                    ),
                    # Stable absence is the correct replay result for compiler
                    # rejects; a compiled unknown entity still binds a digest.
                    "goal_digest_same": len(goal_digests) == 1,
                    "off_semantic_outcome_same": (
                        off_record["semantic_outcome_digest_sha256"]
                        == off_replay_digest
                    ),
                    "on_semantic_outcome_same": (
                        on_record["semantic_outcome_digest_sha256"]
                        == on_replay_digest
                    ),
                    "off_replay_digest_sha256": off_replay_digest,
                    "on_replay_digest_sha256": on_replay_digest,
                },
                "gold_absent_from_candidate_arguments": True,
            }
        )

    staging_control_receipts = _run_staging_controls(repo_root, fixture)
    base_after = base_state_digest()
    scopes_after = {
        "source": bind_files(repo_root, SOURCE_PATHS),
        "candidate": bind_files(repo_root, CANDIDATE_PATHS),
        "dataset": bind_files(repo_root, DATASET_PATHS),
        "stage": bind_files(repo_root, STAGE_PATHS),
    }
    changed = [
        name for name in scopes_before if scopes_before[name] != scopes_after[name]
    ]
    if changed:
        raise BenchmarkEvidenceError(
            "bound bytes changed during run: " + ", ".join(changed)
        )
    if base_before != base_after:
        raise BenchmarkEvidenceError("base state changed during paired run")

    metrics = _derive_metrics(
        item_receipts,
        control_receipts,
        staging_control_receipts,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "protocol": _protocol(),
        "claims": {
            "classification": (
                "bounded_atomic_number_e4_with_controls_development_only"
            ),
            "e4_development_evidence": True,
            "e4_development_gate_passed": metrics[
                "e4_development_gate_passed"
            ],
            "control_probe_evidence": True,
            "control_probe_gate_passed": metrics["control_probes"][
                "control_probe_gate_passed"
            ],
            "e5_claimed": False,
            "independent": False,
            "externally_signed": False,
            "benchmark_capability_claimed": False,
            "process_resource_curve_claimed": False,
        },
        "seal": {
            "sealed": True,
            "scope": (
                "exact evaluator/candidate/dataset/stage bytes stable "
                "before-after + frozen fixture hash + paired semantic replay + "
                "negative/staging control probes + immutable base + "
                "deterministic semantic records + recomputable checksum"
            ),
            "git_clean_required": False,
            "hidden_holdout_claimed": False,
            "independent_evaluation_claimed": False,
            "authenticity_established": False,
            "e5_equivalent": False,
        },
        **scopes_before,
        "fixture": {
            "path": FIXTURE_PATH,
            "frozen_expected_sha256": FROZEN_FIXTURE_SHA256,
            "actual_sha256": _sha256(fixture_bytes),
            "item_count": EXPECTED_ITEMS,
            "negative_control_count": EXPECTED_NEGATIVE_CONTROLS,
            "staging_control_count": EXPECTED_STAGING_CONTROLS,
        },
        "stage_snapshot": {
            "stage_id": stage_snapshot.stage_id,
            "stage_digest_sha256": stage_snapshot.stage_digest_sha256,
            "manifest_checksum_sha256": (
                stage_snapshot.manifest_checksum_sha256
            ),
            "bound_bytes": stage_snapshot.bound_bytes,
            "row_count": len(stage_snapshot.facts),
        },
        "selection": _selection(fixture),
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
            "base_state_immutable": (
                base_before == base_after
                and metrics["base_state_immutable_all"] is True
            ),
            "control_probes_passed": metrics["control_probes"][
                "control_probe_gate_passed"
            ],
            "process_resource_telemetry_omitted": True,
            "base_state_digest_before": base_before,
            "base_state_digest_after": base_after,
            "network_isolation_enforced": False,
            "shipped_graph_write_authority": False,
            "production_authority": False,
        },
    }
    return _finalize(payload)


def read_receipt(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise BenchmarkEvidenceError(
            f"receipt unreadable: {type(exc).__name__}"
        ) from exc
    if len(payload) > _MAX_RECEIPT_BYTES:
        raise BenchmarkEvidenceError("receipt exceeds bounded size")
    manifest = strict_json_bytes(payload, label="science-stage E4 receipt")
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
            "checksum_sha256": None,
            "findings": [str(exc)],
        }
    structural = validate_receipt(
        manifest, repo_root=repo_root, require_current=False
    )
    if require_current:
        current = validate_receipt(
            manifest,
            repo_root=repo_root,
            require_current=True,
        )
        remaining_structural = Counter(structural)
        current_only: list[str] = []
        for finding in current:
            if remaining_structural[finding] > 0:
                remaining_structural[finding] -= 1
            else:
                current_only.append(finding)
        matches_current: bool | None = not current_only
    else:
        current = structural
        matches_current = None
    declared_sealed = manifest.get("seal", {}).get("sealed") is True
    verified_sealed = declared_sealed and not current and require_current
    return {
        "valid": not current,
        "structure_valid": not structural,
        "matches_current": matches_current,
        "declared_sealed": declared_sealed,
        "verified_sealed": verified_sealed,
        "sealed": verified_sealed,
        "e5_claimed": manifest.get("claims", {}).get("e5_claimed") is True,
        "checksum_sha256": manifest.get("manifest_checksum_sha256"),
        "findings": current,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--output",
        type=Path,
        help="write once to this path; default is canonical JSON on stdout",
    )
    mode.add_argument(
        "--verify",
        type=Path,
        help="verify an existing receipt instead of running the probe",
    )
    parser.add_argument(
        "--allow-historical",
        action="store_true",
        help="with --verify, validate checksum/structure without current-tree binding",
    )
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
        print(f"science-stage E4 receipt failed closed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
