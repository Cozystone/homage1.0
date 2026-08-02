"""Instrumented A-track science answer surface.

The candidate receives only an item without gold, a validated stage snapshot,
and a read-only base fact accessor.  It compiles raw NL, executes the typed goal
with DELIBERATOR, and accepts a result only when the proof can be rebound to an
exact staged evidence row.  The ordinary exam cascade remains an explicit,
separate fallback and the default shipped path is unchanged.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import hashlib
import os
import time
from typing import Any

from packages.cognitive_core.canonical import canonical_digest
from packages.reasoning_vm.deliberator.science_goal import (
    compile_science_question,
)
from packages.reasoning_vm.science_staging import (
    ScienceStageSnapshot,
    StagedKnowledgeOverlay,
)


def _rss_bytes() -> int | None:
    try:
        import psutil

        return int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:
        return None


def _choice_digest(choice_key: str | None) -> str | None:
    if choice_key is None:
        return None
    return hashlib.sha256(choice_key.encode("utf-8")).hexdigest()


def _empty_proof_binding() -> dict[str, Any]:
    return {
        "grounded_leaf_count": 0,
        "grounded_stage_leaf_count": 0,
        "evidence": [],
        "proof_digest_sha256": None,
        "provenance_digest_sha256": None,
    }


def answer_science_mcq(
    stem: Any,
    choices: Any,
    base_facts: Callable[[str], list[tuple[str, str, str]]],
    stage: ScienceStageSnapshot | None,
    *,
    overlay_enabled: bool,
    base_state_digest: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Run one gold-blind science candidate condition with complete telemetry."""

    wall_started = time.perf_counter_ns()
    cpu_started = time.process_time_ns()
    rss_started = _rss_bytes()
    before_digest = None
    state_probe_error = None
    if base_state_digest is not None:
        try:
            before_digest = base_state_digest()
        except Exception as exc:
            state_probe_error = type(exc).__name__

    compilation = compile_science_question(stem, choices)
    overlay = StagedKnowledgeOverlay(
        base_facts,
        stage,
        enabled=overlay_enabled,
    )
    engine_output: dict[str, Any] = {}
    proof_binding = _empty_proof_binding()
    choice_key: str | None = None
    raw_fired = False
    accepted_fire = False
    grounded = False
    reason = compilation.reason
    error_kind = state_probe_error

    try:
        if state_probe_error is not None:
            reason = "base_state_probe_failed_closed"
        elif compilation.compiled:
            if not isinstance(choices, Mapping):
                raise TypeError("compiled choices are not a mapping")
            goal = compilation.goals[0]
            from packages.reasoning_vm.deliberator.reasoner import Deliberator

            deliberator = Deliberator(
                overlay.facts_about,
                with_kernels=False,
                max_depth=3,
                budget=512,
            )
            engine_output = deliberator.answer_mcq_derive(
                goal.subject,
                goal.relation,
                dict(compilation.choice_items),
            )
            proof_binding = overlay.bind_proof(engine_output.get("proof"))
            proposed = engine_output.get("choice_key")
            raw_fired = (
                proposed is not None
                and engine_output.get("mode") == "grounded"
                and engine_output.get("proof") is not None
            )
            staged_ground = (
                proof_binding["grounded_leaf_count"] > 0
                and proof_binding["grounded_stage_leaf_count"]
                == proof_binding["grounded_leaf_count"]
            )
            accepted_fire = raw_fired and staged_ground
            grounded = accepted_fire
            if accepted_fire:
                choice_key = str(proposed)
                reason = "grounded_stage_proof"
            elif raw_fired:
                reason = "required_stage_provenance_unavailable"
            elif overlay_enabled and overlay.stage_hit_count == 0:
                reason = "entity_unresolved"
            elif not overlay_enabled:
                reason = "required_evidence_unavailable"
            else:
                reason = "typed_goal_not_uniquely_grounded"
    except Exception as exc:
        error_kind = type(exc).__name__
        reason = "candidate_error_fail_closed"
        choice_key = None
        raw_fired = False
        accepted_fire = False
        grounded = False
        proof_binding = _empty_proof_binding()

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

    wall_ms = round((time.perf_counter_ns() - wall_started) / 1_000_000, 6)
    cpu_ms = round((time.process_time_ns() - cpu_started) / 1_000_000, 6)
    rss_finished = _rss_bytes()
    rss_delta = (
        None
        if rss_started is None or rss_finished is None
        else max(0, rss_finished - rss_started)
    )
    return {
        "schema_version": "atanor.instrumented-science-outcome.v1",
        "choice_key": choice_key,
        "choice_digest_sha256": _choice_digest(choice_key),
        "mode": "grounded" if accepted_fire else "abstain",
        "reason": reason,
        "compiler": compilation.to_dict(),
        "staging": {
            **overlay.telemetry(),
            "grounded_leaf_count": proof_binding["grounded_leaf_count"],
            "grounded_stage_leaf_count": proof_binding[
                "grounded_stage_leaf_count"
            ],
            "provenance_digest_sha256": proof_binding[
                "provenance_digest_sha256"
            ],
            "evidence_ids": [
                row["evidence_id"] for row in proof_binding["evidence"]
            ],
        },
        "engine": {
            "raw_fired": raw_fired,
            "grounded": grounded,
            "accepted_fire": accepted_fire,
            "hops": int(engine_output.get("hops") or 0),
            "proof_digest_sha256": proof_binding["proof_digest_sha256"],
            "engine": "deliberator_back_chain",
        },
        "resources": {
            "wall_ms": wall_ms,
            "cpu_ms": cpu_ms,
            "rss_delta_bytes": rss_delta,
        },
        "integrity": {
            "base_state_digest_before": before_digest,
            "base_state_digest_after": after_digest,
            "base_state_unchanged": base_unchanged,
            "shipped_graph_write_authority": False,
            "gold_in_candidate_payload": False,
        },
        "error_kind": error_kind,
    }


def answer_exam_with_science_stage(
    stem: str,
    choices: dict[str, str],
    base_facts: Callable[[str], list[tuple[str, str, str]]],
    stage: ScienceStageSnapshot,
    *,
    overlay_enabled: bool = False,
    base_state_digest: Callable[[], str] | None = None,
    passages: dict | None = None,
    content_index: Any = None,
) -> dict[str, Any]:
    """Explicit candidate+fallback cascade; stage authority is default-off."""

    candidate = answer_science_mcq(
        stem,
        choices,
        base_facts,
        stage if overlay_enabled else None,
        overlay_enabled=overlay_enabled,
        base_state_digest=base_state_digest,
    )
    if candidate["engine"]["accepted_fire"]:
        return {
            "choice_key": candidate["choice_key"],
            "mode": "grounded",
            "confidence": 0.9,
            "basis": "A-track typed goal with provenance-bound staged proof",
            "candidate_trace": candidate,
        }
    if (
        candidate["error_kind"] is not None
        or candidate["integrity"]["base_state_unchanged"] is False
    ):
        return {
            "choice_key": None,
            "mode": "error",
            "confidence": 0.0,
            "basis": "A-track safety fault; fallback refused",
            "candidate_trace": candidate,
        }

    from packages.reasoning_vm.exam_answer import answer_exam

    fallback = answer_exam(
        stem,
        choices,
        base_facts,
        passages=passages,
        content_index=content_index,
    )
    return {
        **fallback,
        "candidate_trace": candidate,
    }


def outcome_digest(outcome: Mapping[str, Any]) -> str:
    """Digest deterministic candidate semantics while excluding timing noise."""

    return canonical_digest(
        {
            "schema_version": outcome.get("schema_version"),
            "choice_key": outcome.get("choice_key"),
            "mode": outcome.get("mode"),
            "reason": outcome.get("reason"),
            "compiler": outcome.get("compiler"),
            "staging": {
                key: outcome.get("staging", {}).get(key)
                for key in (
                    "enabled",
                    "lookup_attempted",
                    "lookup_count",
                    "base_row_count",
                    "staged_hit_count",
                    "stage_digest_sha256",
                    "stage_snapshot_bound_bytes",
                    "stage_bytes_read",
                    "grounded_leaf_count",
                    "grounded_stage_leaf_count",
                    "provenance_digest_sha256",
                    "evidence_ids",
                )
            },
            "engine": outcome.get("engine"),
            "integrity": outcome.get("integrity"),
            "error_kind": outcome.get("error_kind"),
        }
    )
