"""Instrumented candidate boundary for the diagnostic relation sibling lane."""
from __future__ import annotations

from collections.abc import Callable, Mapping
import hashlib
from typing import Any

from packages.cognitive_core.canonical import canonical_digest
from packages.reasoning_vm.deliberator.science_relation_goal import (
    compile_typed_relation_select,
)
from packages.reasoning_vm.deliberator.science_relation_staging import (
    ScienceRelationStageSnapshot,
)


RELATION_OUTCOME_SCHEMA = (
    "atanor.instrumented-relation-science-outcome.v1"
)


def _choice_digest(choice_key: str | None) -> str | None:
    if choice_key is None:
        return None
    return hashlib.sha256(choice_key.encode("utf-8")).hexdigest()


def answer_relation_science_mcq(
    stem: Any,
    choices: Any,
    stage: ScienceRelationStageSnapshot | None,
    *,
    overlay_enabled: bool,
    base_state_digest: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Select only an exactly-one P17 proof; otherwise abstain fail-closed."""

    before_digest = None
    after_digest = None
    error_kind = None
    if base_state_digest is not None:
        try:
            before_digest = base_state_digest()
        except Exception as exc:
            error_kind = type(exc).__name__

    compilation = compile_typed_relation_select(stem, choices)
    proofs = ()
    choice_key: str | None = None
    accepted_fire = False
    reason = compilation.reason

    try:
        if type(overlay_enabled) is not bool:
            raise TypeError("overlay_enabled must be an exact bool")
        if stage is not None and type(stage) is not ScienceRelationStageSnapshot:
            raise TypeError("stage must be an exact relation snapshot")
        if overlay_enabled != (stage is not None):
            raise ValueError("stage presence and overlay flag differ")
        if error_kind is not None:
            reason = "base_state_probe_failed_closed"
        elif not compilation.compiled:
            reason = compilation.reason
        elif stage is None:
            reason = "required_relation_stage_unavailable"
        else:
            proofs = stage.proof_candidates(compilation)
            if len(proofs) == 1:
                choice_key = proofs[0].choice_key
                accepted_fire = True
                reason = "grounded_exactly_one_typed_relation_proof"
            elif not proofs:
                reason = "required_relation_proof_unavailable"
            else:
                reason = "multiple_relation_proofs_fail_closed"
    except Exception as exc:
        error_kind = type(exc).__name__
        proofs = ()
        choice_key = None
        accepted_fire = False
        reason = "candidate_error_fail_closed"

    if base_state_digest is not None and error_kind is None:
        try:
            after_digest = base_state_digest()
        except Exception as exc:
            error_kind = type(exc).__name__
            choice_key = None
            accepted_fire = False
            reason = "base_state_probe_failed_closed"
    base_unchanged = (
        None
        if base_state_digest is None or error_kind is not None
        else before_digest == after_digest
    )
    if base_unchanged is False:
        error_kind = "BaseStateMutationDetected"
        choice_key = None
        accepted_fire = False
        reason = "base_state_mutated_fail_closed"

    proof = proofs[0] if accepted_fire else None
    evidence_ids = (
        [row.evidence_id for row in proof.evidence]
        if proof is not None
        else []
    )
    return {
        "schema_version": RELATION_OUTCOME_SCHEMA,
        "choice_key": choice_key,
        "choice_digest_sha256": _choice_digest(choice_key),
        "mode": "grounded" if accepted_fire else "abstain",
        "reason": reason,
        "compiler": compilation.to_dict(),
        "staging": {
            "enabled": overlay_enabled,
            "profile": "typed_relation_select_located_in",
            "lookup_attempted": (
                compilation.compiled and overlay_enabled and stage is not None
            ),
            "proof_candidate_count": len(proofs),
            "stage_digest_sha256": (
                stage.stage_digest_sha256 if stage is not None else None
            ),
            "stage_snapshot_bound_bytes": (
                stage.bound_bytes if stage is not None else 0
            ),
            "source_property_id": (
                proof.relation.source_property_id
                if proof is not None
                else None
            ),
            "evidence_ids": evidence_ids,
            "provenance_digest_sha256": (
                proof.provenance_digest_sha256
                if proof is not None
                else None
            ),
            "external_authenticity_established": False,
        },
        "engine": {
            "raw_fired": bool(proofs),
            "proof_replayed": proof is not None,
            "grounded": accepted_fire,
            "accepted_fire": accepted_fire,
            "hops": 1 if accepted_fire else 0,
            "engine": "typed_relation_exact_stage_selector",
        },
        "integrity": {
            "base_state_digest_before": before_digest,
            "base_state_digest_after": after_digest,
            "base_state_unchanged": base_unchanged,
            "stage_structurally_absent": (
                not overlay_enabled and stage is None
            ),
            "shipped_graph_write_authority": False,
            "gold_in_candidate_payload": False,
            "benchmark_metadata_in_candidate_payload": False,
            "choice_ranking_used": False,
            "manual_predicate_expansion_allowed": False,
        },
        "error_kind": error_kind,
    }


def relation_outcome_digest(outcome: Mapping[str, Any]) -> str:
    """Digest deterministic diagnostic relation semantics."""

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
