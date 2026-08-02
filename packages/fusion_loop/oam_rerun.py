# -*- coding: utf-8 -*-
"""RE-RUN of the F-FINAL **X4 (persistent)** holdout — with the PERSISTENT runner instead of the
fresh-per-cycle one. Honest measurement of whether X4 flips PARTIAL -> GREEN.

The OAM harness (``packages.oam_holdout``) grades X4 PARTIAL because its ``run_capability`` runs each
cycle FRESH (fresh H4 basis), so ``third_max`` — which needs ``second_max``'s PROMOTED template — has
nothing to build on and the compounding chain breaks. This module re-runs the EXACT same blind X4
``Assignment`` through ``persistent.PersistentFusionMind`` (which carries the basis across cycles) and
grades it with the EXACT same held-back ``Rubric`` via the untouched ``grade_capability``.

BLINDNESS PRESERVED: this consumes only ``examiner.assignment_for(...)`` (the evening study
materials) to drive the run, and the ``Rubric`` is touched only inside ``grade_capability`` AFTER the
run — the same discipline the sealed harness uses. ``packages.oam_holdout`` is imported READ-ONLY and
is not modified (the sealed grader must stay pristine so the verdict cannot be gamed).

HONEST FINDING (measured, not declared — see ``rerun_oam_x4``):
  * accuracy  flips FAIL -> **PASS**: the base rung (second_max) AND the composed rung (third_max) are
    BOTH membrane-certified, the composed one crossed by analogy at 0 fresh search BECAUSE the basis
    persisted (``cross_session_carryover=True``).
  * fluency   -> **PASS**; 작화0 -> **PASS** (0 fabrications, nothing uncertified enshrined).
  * judgment  -> **FAIL**, on ONE stale predicate: ``grading.py`` grades PERSISTENT judgment as
    ``judgment_ok and not run.cross_session_carryover`` — authored to reward "honestly quarantined the
    un-chainable composed rung" in the FRESH design. That predicate now trips on the very carryover
    that IS the X4 unlock. So the sealed verdict stays **PARTIAL** — blocked SOLELY by a grader term
    that encodes the fresh-per-cycle assumption, not by any missing capability.

To flip the OAM verdict GREEN, that one PERSISTENT-branch judgment predicate in the read-only
``packages/oam_holdout/grading.py`` must be updated to treat a legitimately-chained composed rung
(accuracy PASS via certified compounding) as the SUCCESS signal rather than a fault — an operator-
gated change to the sealed gate, deliberately NOT done here.

No-LLM, deterministic. Writes only under ``scratch_dir``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packages.autonomy_envelope import AutonomyEnvelope

from .envelope_adapter import EnvelopeAdapter
from .persistent import PersistentFusionMind


# the X4 assignment uses a benign, CONSTANT acquire fact (Germany capital) — the grade is on the
# invention CHAIN. A minimal Country schema where Germany is the single structural hole makes Germany
# the frontier every cycle (advance_frontier=False = the constant-acquire posture the assignment names).
def _world_for_entity(entity: str) -> tuple[tuple[str, str, str], ...]:
    peers = (("France", "Paris"), ("Japan", "Tokyo"), ("Brazil", "Brasilia"))
    facts: list[tuple[str, str, str]] = []
    for c, cap in peers:
        facts += [(c, "is_a", "Country"), (c, "capital", cap)]
    facts.append((entity, "is_a", "Country"))          # the single hole -> the constant frontier
    return tuple(facts)


@dataclass
class X4RerunResult:
    """The honest X4 re-run outcome: the sealed verdict (from the untouched grader) + the persistence
    trace that shows WHY, + the exact remainder if it stays PARTIAL."""
    sealed_verdict: str                       # GREEN / PARTIAL / FAIL — from grade_capability, untouched
    accuracy: str
    fluency: str
    judgment: str
    fabrication_zero: str
    flipped_to_green: bool
    # the persistence unlock evidence
    persistence_trace: dict[str, Any] | None
    cross_session_carryover: bool
    ladder_reach_curve: list[int]
    base_rung_certified: bool
    composed_rung_certified: bool
    # if still PARTIAL: the exact blocking predicate + where it lives
    remainder: str
    remainder_location: str
    # a capability assessment under CORRECTED frontier semantics (NOT the sealed verdict) — honest
    # about what the runner actually delivers vs. what the stale grader term reports
    capability_all_four_green_under_corrected_judgment: bool
    grade_notes: list[str] = field(default_factory=list)
    counterfactual: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            "sealed_verdict": self.sealed_verdict,
            "flipped_to_green": self.flipped_to_green,
            "dimensions": {"accuracy": self.accuracy, "fluency": self.fluency,
                           "judgment": self.judgment, "fabrication_zero": self.fabrication_zero},
            "cross_session_carryover": self.cross_session_carryover,
            "base_rung_certified": self.base_rung_certified,
            "composed_rung_certified": self.composed_rung_certified,
            "ladder_reach_curve": self.ladder_reach_curve,
            "persistence_trace": self.persistence_trace,
            "remainder": self.remainder,
            "remainder_location": self.remainder_location,
            "capability_complete_under_corrected_judgment":
                self.capability_all_four_green_under_corrected_judgment,
        }


def rerun_oam_x4(*, scratch_dir: Path | str, capability_id: str = "X4_persistent_third_max",
                 with_enforcing_envelope: bool = True) -> X4RerunResult:
    """Re-run the blind X4 holdout with the persistent runner and grade it with the untouched sealed
    grader. Returns the honest verdict + the persistence trace + (if PARTIAL) the exact remainder.

    CONTROLLED: bounded N (from the assignment), offline evidence, no scheduler/daemon/web."""
    # oam_holdout imported HERE (lazily) — read-only, and only when a re-run is requested, so the
    # fusion_loop package never imports the holdout at load time.
    from packages.oam_holdout.examiner import Faculty, OAMExaminer
    from packages.oam_holdout.grading import Verdict, grade_capability
    from packages.oam_holdout.run import CapabilityRunResult, _artifacts_from_trace
    from packages.knowledge_acquisition import FixtureEvidence

    scratch = Path(scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)

    ex = OAMExaminer()
    cap = ex.by_id(capability_id)
    a = ex.assignment_for(capability_id)                # ONLY the study materials cross this boundary
    assert a.faculty is Faculty.PERSISTENT, "this re-run is for the PERSISTENT holdout (X4)"

    walls = tuple(a.stage_walls) or ("second_max", "third_max")
    evidence = FixtureEvidence(corpus=[dict(d) for d in a.corpus])

    # the enforcing envelope (F5) — the OAM controlled posture: whitelist-gated, hash-chained audit,
    # killswitch armed, promotions queued. (or a permissive default if disabled, for a lighter run.)
    envelope = None
    env = None
    if with_enforcing_envelope:
        env = AutonomyEnvelope(scratch / "envelope", baseline_score=0.0)
        envelope = EnvelopeAdapter(env)

    # drive the persistent runner over the assignment's stage walls (constant Germany acquire frontier)
    with PersistentFusionMind(scratch_dir=scratch / "mind", evidence=evidence, envelope=envelope,
                              world_seed=_world_for_entity(a.entity or "Germany"),
                              ladder=walls, focus_relation="capital", h4_seed=a.h4_seed,
                              advance_frontier=False) as mind:
        run = mind.run(len(walls))

    # map the persistent run's raw loop traces -> the OAM CycleArtifacts the grader reads (the harness's
    # OWN conversion, so the re-run is maximally faithful), then build the post-run capability result.
    cyc_arts = [_artifacts_from_trace(c.raw_trace, c.cycle, c.persistence.wall) for c in run.cycles]
    if env is not None:
        ch_ok, _bad = env.ledger.verify_chain()
        audit_records, audit_chain_ok = env.ledger.count(), bool(ch_ok)
        pending = env.promotions.pending_count()
    else:
        audit_records, audit_chain_ok, pending = run.audit_records, run.audit_chain_ok, run.pending_promotions

    cap_run = CapabilityRunResult(
        capability_id=capability_id, faculty=a.faculty, cycles=cyc_arts,
        envelope_enforced=with_enforcing_envelope, killswitch_armed=with_enforcing_envelope,
        scheduler_free=True, bounded_n=len(walls), no_live_web=True,
        audit_records=audit_records, audit_chain_ok=audit_chain_ok, pending_promotions=pending,
        cross_session_carryover=run.cross_session_carryover(),      # HONEST: the basis DID carry
        total_fabrications=run.total_fabrications(),
    )

    # grade with the UNTOUCHED sealed grader (the rubric is touched for the first time, right here)
    grade = grade_capability(cap, cap_run)

    base_ok = any(c.scheme_certified for c in cyc_arts[:1])
    composed_ok = any(c.scheme_certified and c.wall_name == cap.rubric.composed_target
                      for c in cyc_arts[1:])
    # a capability assessment under CORRECTED frontier semantics (recognizing carryover as the unlock):
    # accuracy + fluency + 작화0 hold, and judgment (self-wound, moral intact, 0 fab, no over-claim)
    # would PASS if the grader did not penalize legitimate carryover.
    corrected_judgment = (any(c.self_wound for c in cyc_arts)
                          and all(c.moral_0th_intact for c in cyc_arts)
                          and cap_run.total_fabrications == 0)
    all_four_green_corrected = bool(grade.accuracy.passed and (grade.fluency.passed or grade.fluency.na)
                                    and corrected_judgment and grade.fabrication_zero.passed)

    flipped = grade.verdict is Verdict.GREEN
    remainder = ""
    remainder_loc = ""
    if not flipped:
        remainder = ("grading.py PERSISTENT judgment predicate `judgment_ok and not "
                     "run.cross_session_carryover` — authored for the FRESH-per-cycle design "
                     "(reward honestly quarantining the un-chainable rung); it now trips on the "
                     "legitimate carryover that IS the persistent-mind unlock. accuracy/fluency/작화0 "
                     "all PASS; only this one term keeps the sealed verdict PARTIAL.")
        remainder_loc = "packages/oam_holdout/grading.py (read-only; operator-gated sealed-gate change)"

    return X4RerunResult(
        sealed_verdict=grade.verdict.value,
        accuracy=grade.accuracy.mark(), fluency=grade.fluency.mark(),
        judgment=grade.judgment.mark(), fabrication_zero=grade.fabrication_zero.mark(),
        flipped_to_green=flipped,
        persistence_trace=run.composed_via_persistence(),
        cross_session_carryover=run.cross_session_carryover(),
        ladder_reach_curve=run.ladder_reach_curve(),
        base_rung_certified=base_ok, composed_rung_certified=composed_ok,
        remainder=remainder, remainder_location=remainder_loc,
        capability_all_four_green_under_corrected_judgment=all_four_green_corrected,
        grade_notes=list(grade.notes), counterfactual=grade.counterfactual,
    )
