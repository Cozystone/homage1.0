"""Instrumented candidate boundary for the scalar science development lane.

Only ``stem`` and ``choices`` cross the question boundary; item identifiers,
benchmark labels, controls, and gold remain evaluator-owned.  The stage is
structurally absent in OFF, all prompt values come from the immutable compiler
receipt, and a choice is accepted only after exact formula replay,
conservation, and three distinct provenance-bound stage leaves.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import hashlib
from typing import Any

from packages.cognitive_core.canonical import canonical_digest
from packages.reasoning_vm.deliberator.science_quantity_goal import (
    compile_neutralization_question,
)
from packages.reasoning_vm.deliberator.science_quantity_resolver import (
    ScalarQuantityResolver,
    verify_scalar_proof,
)
from packages.reasoning_vm.science_quantity_staging import (
    QuantityStageOverlay,
    ScienceQuantityStageSnapshot,
)


SCALAR_OUTCOME_SCHEMA = "atanor.instrumented-scalar-science-outcome.v1"


def _choice_digest(choice_key: str | None) -> str | None:
    if choice_key is None:
        return None
    return hashlib.sha256(choice_key.encode("utf-8")).hexdigest()


def _empty_binding() -> dict[str, Any]:
    return {
        "grounded_leaf_count": 0,
        "grounded_stage_leaf_count": 0,
        "evidence": [],
        "proof_digest_sha256": None,
        "provenance_digest_sha256": None,
    }


def answer_scalar_science_mcq(
    stem: Any,
    choices: Any,
    stage: ScienceQuantityStageSnapshot | None,
    *,
    overlay_enabled: bool,
    base_state_digest: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Run one argument-separated scalar candidate condition."""

    before_digest = None
    state_probe_error = None
    if base_state_digest is not None:
        try:
            before_digest = base_state_digest()
        except Exception as exc:
            state_probe_error = type(exc).__name__

    compilation = compile_neutralization_question(stem, choices)
    overlay: QuantityStageOverlay | None = None
    engine_output: dict[str, Any] = {}
    proof_binding = _empty_binding()
    choice_key: str | None = None
    raw_fired = False
    formula_fired = False
    accepted_fire = False
    grounded = False
    resolver_grounded = False
    candidate_proof_verified = False
    reason = compilation.reason
    error_kind = state_probe_error

    try:
        overlay = QuantityStageOverlay(
            stage,
            enabled=overlay_enabled,
        )
        if state_probe_error is not None:
            reason = "base_state_probe_failed_closed"
        elif compilation.compiled:
            resolution = ScalarQuantityResolver().resolve(
                compilation,
                overlay,
                stem=stem,
            )
            engine_output = resolution.to_engine_dict()
            raw_fired = resolution.raw_fired
            formula_fired = resolution.formula_fired
            resolver_grounded = resolution.grounded
            if resolution.proof is not None:
                candidate_proof_verified = verify_scalar_proof(
                    resolution.proof,
                    compilation,
                    overlay,
                    stem=stem,
                )
            proof_binding = overlay.bind_proof(resolution.proof)
            staged_ground = (
                proof_binding["grounded_leaf_count"] == 3
                and proof_binding["grounded_stage_leaf_count"] == 3
                and len(proof_binding["evidence"]) == 3
            )
            accepted_fire = (
                raw_fired
                and resolver_grounded
                and candidate_proof_verified
                and staged_ground
                and resolution.choice_key is not None
            )
            if accepted_fire:
                choice_key = resolution.choice_key
                grounded = True
                reason = "grounded_stage_formula_derivation"
            elif raw_fired:
                reason = (
                    "proof_replay_failed"
                    if not candidate_proof_verified
                    else "required_stage_provenance_unavailable"
                )
            else:
                reason = resolution.reason
    except Exception as exc:
        error_kind = type(exc).__name__
        reason = "candidate_error_fail_closed"
        choice_key = None
        raw_fired = False
        formula_fired = False
        accepted_fire = False
        grounded = False
        resolver_grounded = False
        candidate_proof_verified = False
        proof_binding = _empty_binding()

    after_digest = None
    if base_state_digest is not None and state_probe_error is None:
        try:
            after_digest = base_state_digest()
        except Exception as exc:
            error_kind = type(exc).__name__
            reason = "base_state_probe_failed_closed"
            choice_key = None
            accepted_fire = False
            grounded = False
    base_unchanged = (
        None
        if base_state_digest is None or error_kind is not None
        else before_digest == after_digest
    )
    if base_unchanged is False:
        error_kind = "BaseStateMutationDetected"
        reason = "base_state_mutated_fail_closed"
        choice_key = None
        accepted_fire = False
        grounded = False

    staging = (
        overlay.telemetry()
        if overlay is not None
        else {
            "enabled": bool(overlay_enabled),
            "profile": "scalar_quantity_resolve",
            "lookup_attempted": False,
            "lookup_count": 0,
            "species_lookup_count": 0,
            "formula_lookup_count": 0,
            "staged_hit_count": 0,
            "stage_digest_sha256": None,
            "stage_snapshot_bound_bytes": 0,
            "stage_bytes_read": 0,
        }
    )
    staging.update(
        {
            "grounded_leaf_count": proof_binding[
                "grounded_leaf_count"
            ],
            "grounded_stage_leaf_count": proof_binding[
                "grounded_stage_leaf_count"
            ],
            "provenance_digest_sha256": proof_binding[
                "provenance_digest_sha256"
            ],
            "evidence_ids": [
                row["evidence_id"] for row in proof_binding["evidence"]
            ],
            "external_authenticity_established": False,
        }
    )
    return {
        "schema_version": SCALAR_OUTCOME_SCHEMA,
        "choice_key": choice_key,
        "choice_digest_sha256": _choice_digest(choice_key),
        "mode": "grounded" if accepted_fire else "abstain",
        "reason": reason,
        "compiler": compilation.to_dict(),
        "staging": staging,
        "engine": {
            "raw_fired": raw_fired,
            "formula_fired": formula_fired,
            "resolver_grounded": resolver_grounded,
            "proof_replayed": candidate_proof_verified,
            "grounded": grounded,
            "accepted_fire": accepted_fire,
            "hops": int(engine_output.get("hops") or 0),
            "proof_digest_sha256": proof_binding[
                "proof_digest_sha256"
            ],
            "engine": "scalar_rational_stage_resolver",
        },
        "integrity": {
            "base_state_digest_before": before_digest,
            "base_state_digest_after": after_digest,
            "base_state_unchanged": base_unchanged,
            "stage_structurally_absent": (
                not overlay_enabled
                and stage is None
                and staging["stage_digest_sha256"] is None
                and staging["stage_snapshot_bound_bytes"] == 0
            ),
            "shipped_graph_write_authority": False,
            "gold_in_candidate_payload": False,
            "benchmark_metadata_in_candidate_payload": False,
            "process_resource_telemetry_omitted": True,
        },
        "error_kind": error_kind,
    }


def scalar_outcome_digest(outcome: Mapping[str, Any]) -> str:
    """Digest deterministic candidate semantics with no process telemetry."""

    return canonical_digest(
        {
            "schema_version": outcome.get("schema_version"),
            "choice_key": outcome.get("choice_key"),
            "mode": outcome.get("mode"),
            "reason": outcome.get("reason"),
            "compiler": outcome.get("compiler"),
            "staging": outcome.get("staging"),
            "engine": outcome.get("engine"),
            "integrity": outcome.get("integrity"),
            "error_kind": outcome.get("error_kind"),
        }
    )
