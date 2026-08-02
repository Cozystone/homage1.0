# -*- coding: utf-8 -*-
"""One full repair round: acquire referents, place what can be placed, detach what is not this
word, and report whether the round actually moved anything.

Ties A1a (`disambiguation`) and A1b (`edge_attribution`) into the shape `purification` measures.
`purify_round` alone cannot express the outcome: it counts residue as unassigned + contested, and
knows nothing of `foreign`. An edge belonging to a different lexeme sharing the surface is
FINISHED business -- it simply is not this node's -- and leaving it in the residue would make the
loop chase "the Athens that the genitalia belongs to" forever.

Three referent sources, cheapest first, because the measurement said so:

  1. THE GRAPH ITSELF. Measured on the real node: the object text of `defined_as` supplied 17
     referents (Arkansas, Illinois, Kentucky, Louisiana, Maine, ...) that no web query had to
     find. For a merged node the local disambiguation is often the richest one, and it costs
     nothing.
  2. THE KINDS THE NODE CLAIMS TO BE (A1c), when a store is supplied. `Athens` asserts `is_a
     painting`, `is_a literary work`, `is_a hill`, and the graph's other paintings say what a
     painting has. This is a separate source and not a fallback: it reaches edges 1 cannot, because
     its evidence is the PROPERTY, not the object text.
  3. ACQUISITION, corroborated across ≥2 sources.
  4. Nothing else. Referents are never invented to make a round look better.

Reports only. No store is written; splitting a node is an operator-gated mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from packages.knowledge_repair.attribution import Referent, attribute
from packages.knowledge_repair.edge_attribution import (
    attribute_edges, referents_from_edges, summarise)

Edge = tuple[str, str, str]


@dataclass(frozen=True)
class RoundResult:
    """What one full round did to a merged node. Counts are CUMULATIVE over the node."""
    subject: str
    round_index: int
    total_edges: int
    referents: int
    placed: int
    foreign: int
    unresolved: int
    resolved_before: int
    open_questions: tuple[str, ...] = field(default_factory=tuple)
    settled: tuple[tuple[Edge, str], ...] = field(default_factory=tuple)

    @property
    def resolved(self) -> int:
        """Placed on a referent OR shown to belong to another word. Both are settled."""
        return self.placed + self.foreign

    @property
    def resolution(self) -> float:
        return self.resolved / self.total_edges if self.total_edges else 0.0

    @property
    def gained(self) -> int:
        return self.resolved - self.resolved_before

    @property
    def improved(self) -> bool:
        return self.gained > 0

    @property
    def stalled(self) -> bool:
        """No edge settled this round. The loop should stop or change what it asks -- learning a
        referent that places nothing is motion, not progress."""
        return self.gained <= 0

    def as_dict(self) -> dict[str, Any]:
        return {"subject": self.subject, "round": self.round_index,
                "total": self.total_edges, "referents": self.referents,
                "placed": self.placed, "foreign": self.foreign,
                "unresolved": self.unresolved, "resolved": self.resolved,
                "resolution": round(self.resolution, 4), "gained": self.gained,
                "improved": self.improved, "stalled": self.stalled}


def repair_round(subject: str, facts: Sequence[Edge], *, evidence: Any = None,
                 known: Iterable[Referent] = (), round_index: int = 0,
                 resolved_before: int | None = None,
                 settled_before: Sequence[tuple[Edge, str]] = (),
                 alias_hints: dict[str, str] | None = None,
                 store: Any = None) -> tuple[RoundResult, list[Referent]]:
    """Run one round over the edges NOT YET SETTLED. Returns the result and the referent set to
    carry into the next.

    `settled_before` is what makes this a round rather than a repeated pass, and it was added
    because the first real run measured the defect: rounds 2..n came back bit-identical to round 1
    on all three merged nodes. `foreign_vocabulary` is documented as detaching ONE cohesive cluster
    per pass, so that the next cluster is measured "against a cleaner background" -- but the loop
    was re-feeding the whole edge set every round, so the background was never cleaner and the
    successive-round shape existed only in the docstring.

    Referents are still derived from ALL facts: an edge already placed still names a referent.
    Only ATTRIBUTION runs on the residue.

    `evidence=None` runs graph-only, which is not a degraded mode: it is the cheapest source and
    on the measured node it was also the most productive."""
    facts = tuple(facts)
    done: dict[Edge, str] = {tuple(e): o for e, o in settled_before}
    if resolved_before is None:
        resolved_before = sum(1 for e in facts if e in done)
    refs: list[Referent] = list(known)
    seen = {r.key for r in refs}

    def _add(new: Iterable[Referent]) -> None:
        for r in new:
            if r.key not in seen:
                seen.add(r.key)
                refs.append(r)

    # 1) what the graph already states about itself
    _add(referents_from_edges(subject, facts))

    # 2) what sources state, corroborated -- only if a source was supplied
    if evidence is not None:
        try:
            from packages.knowledge_repair.disambiguation import acquire_referents
            _add(p.as_referent() for p in acquire_referents(subject, evidence))
        except Exception:
            pass                                  # a source failure must not fail the round

    pending = tuple(e for e in facts if e not in done)
    placed_pass = attribute(subject, pending, refs)
    for ref_key, edges in placed_pass.assigned.items():
        for e in edges:
            done[tuple(e)] = "assigned"
    verdicts = attribute_edges(subject, placed_pass.unassigned + placed_pass.contested, refs,
                               alias_hints=alias_hints)
    for v in verdicts:
        if v.outcome in ("assigned", "foreign"):
            done[tuple(v.edge)] = v.outcome

    # A1c on whatever text-based attribution could not reach. Measured on the real node: after A1b
    # 36 edges remained and `foreign_vocabulary` returned EMPTY over them, because their objects
    # are one or two words -- there is no text left to read. Their evidence is the PREDICATE.
    still = [v.edge for v in verdicts if v.outcome == "unknown"]
    if store is not None and still:
        try:
            from packages.knowledge_repair.type_affinity import (
                attribute_by_kind, kind_referents, type_profiles, types_declared)
            profiles = type_profiles(store, types_declared(subject, facts))
            if profiles:
                _add(kind_referents(subject, profiles))
                kind_verdicts = attribute_by_kind(subject, still, profiles)
                for v in kind_verdicts:
                    if v.placed:
                        done[tuple(v.edge)] = "assigned"
                verdicts = [v for v in verdicts if v.outcome != "unknown"] + kind_verdicts
        except Exception:
            pass                                  # a store failure must not fail the round
    s = summarise(verdicts)

    # Counted over the WHOLE node, not this pass, so `resolution` stays comparable across rounds
    # and duplicate edges cannot make the three buckets stop summing to the node's size.
    placed = sum(1 for e in facts if done.get(e) == "assigned")
    foreign = sum(1 for e in facts if done.get(e) == "foreign")

    return RoundResult(
        subject=subject, round_index=round_index, total_edges=len(facts), referents=len(refs),
        placed=placed, foreign=foreign, unresolved=len(facts) - placed - foreign,
        resolved_before=resolved_before,
        open_questions=tuple(s["open_questions"]),
        settled=tuple(sorted(done.items())),
    ), refs


def repair_until_stalled(subject: str, facts: Sequence[Edge], *, evidence: Any = None,
                         max_rounds: int = 6, store: Any = None,
                         alias_hints: dict[str, str] | None = None) -> list[RoundResult]:
    """Round after round until a round settles nothing new.

    The termination is the measurement, not a fixed count: `stalled` means this round placed and
    detached nothing beyond the last, so another identical round would too. A loop that cannot
    detect that is the thing the plan calls unable to be composed.

    Settled edges are carried forward, which is what lets a later round see a cluster the first one
    could not: cohesion is measured against the residue, and the residue shrinks."""
    refs: list[Referent] = []
    settled: tuple[tuple[Edge, str], ...] = ()
    resolved = 0
    out: list[RoundResult] = []
    for i in range(1, max_rounds + 1):
        res, refs = repair_round(subject, facts, evidence=evidence, known=refs, round_index=i,
                                 resolved_before=resolved, settled_before=settled,
                                 alias_hints=alias_hints, store=store)
        out.append(res)
        if res.stalled:
            break
        resolved, settled = res.resolved, res.settled
    return out
