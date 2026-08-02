# -*- coding: utf-8 -*-
"""One round of incremental purification, and the measurement that says whether it worked.

The loop this closes: a merged node is noticed during use (conflict_ledger), the edges evidence
can place are placed and the rest are reported (attribution), the unplaced ones become narrow
questions for acquisition, and the NEXT round re-measures. Coverage rising across rounds is what
"repetition improves it" means as a number rather than a hope.

WHY A PROGRESS MEASURE IS THE POINT. The repository already has many loops -- fusion_loop,
advisor_loop, policy_loop, the acquisition daemon -- and each runs a fixed body for a fixed number
of cycles. None of them can say whether a cycle helped. A loop that cannot tell progress from
motion cannot decide to stop, cannot detect that it is stuck, and cannot be handed to anything
that would compose loops on its own. `PurificationRound` exists so this one can.

Two ways a round can fail, and they are recorded differently on purpose:
  * coverage rose but residue did not fall -> new referents were learned, no edges were placed;
  * neither moved -> the questions asked are not the ones the evidence source can answer, which
    is a signal about the QUESTIONS, not about the graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from packages.knowledge_repair.attribution import Attribution, Referent, attribute


@dataclass(frozen=True)
class PurificationRound:
    """What one round changed. `improved` is deliberately strict: motion is not progress."""
    subject: str
    round_index: int
    coverage_before: float
    coverage_after: float
    residue_before: int
    residue_after: int
    referents: int
    questions_asked: tuple[str, ...] = ()

    @property
    def placed(self) -> int:
        return self.residue_before - self.residue_after

    @property
    def improved(self) -> bool:
        """Edges actually moved out of the residue. Learning a referent without placing anything
        is not an improvement to the graph, however encouraging it looks."""
        return self.residue_after < self.residue_before

    @property
    def stalled(self) -> bool:
        """Nothing moved at all -- the loop is spending rounds without effect and should stop or
        change what it asks."""
        return self.residue_after >= self.residue_before and self.coverage_after <= self.coverage_before

    def as_dict(self) -> dict[str, Any]:
        return {"subject": self.subject, "round": self.round_index,
                "coverage_before": round(self.coverage_before, 4),
                "coverage_after": round(self.coverage_after, 4),
                "residue_before": self.residue_before, "residue_after": self.residue_after,
                "placed": self.placed, "referents": self.referents,
                "improved": self.improved, "stalled": self.stalled}


def purify_round(subject: str, facts: Iterable[tuple[str, str, str]],
                 referents_before: Iterable[Referent],
                 referents_after: Iterable[Referent],
                 *, round_index: int = 0, questions: Iterable[str] = ()) -> PurificationRound:
    """Attribute with the referents known BEFORE and AFTER a round of acquisition, and report the
    difference. Pure measurement: it changes no store and decides no promotion."""
    facts = tuple(facts)
    before = attribute(subject, facts, referents_before)
    after = attribute(subject, facts, referents_after)
    return PurificationRound(
        subject=subject, round_index=round_index,
        coverage_before=before.coverage, coverage_after=after.coverage,
        residue_before=len(before.unassigned) + len(before.contested),
        residue_after=len(after.unassigned) + len(after.contested),
        referents=len(tuple(referents_after)),
        questions_asked=tuple(questions),
    )


def acquisition_targets(attribution: Attribution, *, limit: int = 20) -> list[dict[str, Any]]:
    """Unplaced edges as targets in the shape `GapLedger.pressured` already consumes.

    Deliberately the SAME contract `structural_gaps.StructuralHole.as_target` uses, so merged-node
    residue enters through the existing second endogenous source rather than a third pipe. A new
    pipe would be a parallel path to maintain and to forget to wire."""
    out: list[dict[str, Any]] = []
    for i, q in enumerate(attribution.residual_questions(limit)):
        out.append({
            "gap_key": f"merge_residue::{attribution.subject}::{i}",
            "question": q,
            # Residue on a node the system keeps tripping over is worth more than residue on one
            # nobody asks about; the caller supplies that weight via the conflict ledger's hits.
            "score": 1.0,
            "pressure_sources": ["merge_residue"],
            "curiosity": {"subject": attribution.subject,
                          "unassigned": len(attribution.unassigned),
                          "contested": len(attribution.contested)},
        })
    return out
