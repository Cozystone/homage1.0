# -*- coding: utf-8 -*-
"""Given several referents sharing one node, which edges can be ASSIGNED and which cannot.

This is the honest half of splitting a merged node, and it is deliberately built before any web
search: knowing which edges lack evidence is what tells the acquisition step what to go and look
for. Searching first would just produce facts with nowhere to attach.

WHY ATTRIBUTION IS HARD HERE, measured on the shipped store: `Athens` carries 147 edges --
is_a 41, located_in 35, country 5 -- pooled from at least five different Athenses (Greece, Ohio,
Ontario, Zimbabwe, plus a cargo ship). And `src.col` does not exist in this store: the ingest
disabled per-triple provenance on the reasoning that "Wikidata's provenance is uniform, so
per-triple src is pure overhead". So the graph itself holds ZERO evidence about which edge came
from which entity. Attribution has to be inferred from the edge's own content against what the
referents are known to be.

THE RULE THIS FILE ENFORCES: an edge is assigned only when the evidence names exactly one
referent. Anything else stays unassigned and is reported as such. Splitting a node by guessing
which edges belong where would fabricate structure that looks authoritative -- worse than the
merge it replaces, because the merge is at least visibly wrong.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class Referent:
    """One of the distinct things a merged node turned out to be.

    `markers` are terms that identify it -- normally supplied by the acquisition step from an
    external source (a disambiguation listing), never invented here."""
    key: str                                   # e.g. "Athens (Greece)"
    markers: frozenset[str] = frozenset()      # e.g. {"Greece", "Attica", "Achaea"}


@dataclass(frozen=True)
class Attribution:
    """The outcome for one merged node. `unassigned` is the point of the whole exercise."""
    subject: str
    assigned: dict[str, tuple[tuple[str, str, str], ...]] = field(default_factory=dict)
    unassigned: tuple[tuple[str, str, str], ...] = ()
    contested: tuple[tuple[str, str, str], ...] = ()     # evidence named MORE than one referent

    @property
    def total(self) -> int:
        return sum(len(v) for v in self.assigned.values()) + len(self.unassigned) + len(self.contested)

    @property
    def coverage(self) -> float:
        """Fraction of edges this split can actually place. A partial split is legitimate; a split
        claiming to be complete when it is not is the failure mode."""
        return (self.total - len(self.unassigned) - len(self.contested)) / self.total if self.total else 0.0

    def residual_questions(self, limit: int = 10) -> list[str]:
        """What acquisition must resolve next. Each names ONE unplaced edge, so a later round can
        measurably reduce the residue rather than restating the whole problem."""
        out = []
        for s, p, o in (self.unassigned + self.contested)[:limit]:
            out.append(f"Which '{s}' has {p} = '{o}'?")
        return out


def _terms(text: str) -> set[str]:
    return {t for t in str(text or "").lower().replace(",", " ").split() if len(t) > 2}


def attribute(subject: str, facts: Iterable[tuple[str, str, str]],
              referents: Iterable[Referent]) -> Attribution:
    """Place each edge with the referent its OBJECT identifies, or leave it unplaced.

    An edge is assigned when exactly one referent's markers appear in the object. Zero matches ->
    unassigned (no evidence). Two or more -> contested (ambiguous evidence, which is not the same
    as no evidence and is worth distinguishing: contested edges usually mean the marker sets
    themselves need refining, unassigned ones mean facts are missing)."""
    refs = list(referents)
    assigned: dict[str, list] = {r.key: [] for r in refs}
    unassigned: list = []
    contested: list = []

    for fact in facts:
        _s, _p, obj = fact
        obj_terms = _terms(obj)
        hits = [r for r in refs
                if any(m.lower() in str(obj).lower() or _terms(m) & obj_terms for m in r.markers)]
        if len(hits) == 1:
            assigned[hits[0].key].append(fact)
        elif len(hits) > 1:
            contested.append(fact)
        else:
            unassigned.append(fact)

    return Attribution(
        subject=subject,
        assigned={k: tuple(v) for k, v in assigned.items() if v},
        unassigned=tuple(unassigned),
        contested=tuple(contested),
    )
