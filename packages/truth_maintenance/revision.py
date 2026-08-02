# -*- coding: utf-8 -*-
"""AGM belief revision with entrenchment = epistemic tier order.

Source of record
----------------
Carlos Alchourron, Peter Gardenfors, David Makinson, "On the Logic of Theory
Change: Partial Meet Contraction and Revision Functions", *Journal of Symbolic
Logic* 50(2), pp. 510-530 (1985). Entrenchment: Gardenfors & Makinson,
"Revisions of Knowledge Systems Using Epistemic Entrenchment" (1988). The
operator-core protection is **screened / non-prioritised revision** (Makinson,
"Screened Revision", *Theoria* 1997; Hansson et al., "Credibility-Limited
Revision", *JSL* 2001) -- see the honest deviation note below.

Faithful constructs from the paper
----------------------------------
* Three operations on a belief state: **expansion** ``K + p`` (add outright),
  **contraction** ``K - p`` (give up ``p``), **revision** ``K * p`` (add ``p``
  while restoring consistency).                                     (AGM §1)
* **Levi identity**: ``K * p = (K - not-p) + p`` -- revise by first contracting
  what ``p`` conflicts with, then expanding by ``p``.               (AGM §3)
* **Epistemic entrenchment**: a ranking of beliefs; contraction gives up the
  **least entrenched** beliefs first (minimal change under a priority). Here the
  entrenchment order *is* ATANOR's epistemic tier order:

      operator (3) > consensus (2) > single_source (1) > neural (0)

  -- so restoring consistency always drops the lowest-tier conflicting belief,
  and *never* the operator-signed one.       (docs/ATANOR_final_gate_research.md §2)
* **AGM postulates** are provided as executable checks in the tests
  (consistency + inclusion + success + vacuity for revision; success +
  inclusion + vacuity for contraction).

Graph-native notion of inconsistency
-------------------------------------
We operate over a finite **belief base** of ``Fact(subject, predicate, object,
tier)`` rather than a deductively-closed set. Two facts are contradictory iff
they share ``(subject, predicate)`` on a **functional** predicate but assert
different objects (a functional relation cannot take two distinct values), or
they are declared mutually negating. This is the crisp, graph-encodable
inconsistency a promotion gate can actually check.

Honest deviation (documented, tested)
-------------------------------------
Pure AGM revision satisfies **success**: ``p in K * p`` always. ATANOR needs the
operator core to be an **integrity constraint** -- it must never be given up to
accommodate a weaker incoming belief. So ``promote`` implements *screened
revision*: if the incoming fact is strictly less entrenched than a conflicting
belief (in particular any operator fact), the incoming fact is **rejected** and
``K`` is unchanged. Success is thus conditional on the incoming fact not being
screened off -- the standard, published relaxation for revision under
protected/entrenched cores. Base contraction also does not satisfy the
**recovery** postulate (a well-known property of base- vs theory-contraction,
Hansson 1991); we do not claim it.

No numpy; stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

# entrenchment = tier rank; higher is more entrenched (given up last)
OPERATOR = "operator"
CONSENSUS = "consensus"
SINGLE_SOURCE = "single_source"
NEURAL = "neural"

TIER_RANK = {OPERATOR: 3, CONSENSUS: 2, SINGLE_SOURCE: 1, NEURAL: 0}

# predicates whose object is functionally determined (at most one value per
# subject). Same (subject, predicate) with a different object => contradiction.
DEFAULT_FUNCTIONAL = frozenset(
    {"capital_of", "capital", "born_in", "located_in", "is_a_singleton",
     "can_fly", "cannot_fly", "atomic_number", "has_capital"}
)


@dataclass(frozen=True)
class Fact:
    subject: str
    predicate: str
    object: str
    tier: str = NEURAL

    @property
    def rank(self) -> int:
        return TIER_RANK.get(self.tier, 0)

    def key(self) -> tuple[str, str, str]:
        return (self.subject.lower(), self.predicate.lower(), self.object.lower())

    def sp(self) -> tuple[str, str]:
        return (self.subject.lower(), self.predicate.lower())


@dataclass
class RevisionResult:
    accepted: bool
    fact: Fact
    dropped: tuple[Fact, ...] = ()
    rejected_reason: str = ""
    beliefs: tuple[Fact, ...] = ()


class BeliefBase:
    """A finite belief base with AGM expansion / contraction / revision, where
    epistemic entrenchment is the tier order."""

    def __init__(
        self,
        facts: Iterable[Fact] = (),
        *,
        functional: Iterable[str] = DEFAULT_FUNCTIONAL,
        negates: Iterable[tuple[tuple[str, str, str], tuple[str, str, str]]] = (),
        tie_break_reject_incoming: bool = True,
    ) -> None:
        self._facts: dict[tuple[str, str, str], Fact] = {}
        for f in facts:
            self._facts[f.key()] = f
        self.functional = frozenset(p.lower() for p in functional)
        # explicit mutual-negation pairs (subject,predicate,object) tuples
        self._negates: set[frozenset] = {frozenset({a, b}) for a, b in negates}
        # on an entrenchment tie, default-deny (reject the incoming fact)
        self.tie_break_reject_incoming = tie_break_reject_incoming

    # ---- inspection -----------------------------------------------------------
    def facts(self) -> list[Fact]:
        return sorted(self._facts.values(), key=lambda f: f.key())

    def contains(self, fact: Fact) -> bool:
        return fact.key() in self._facts

    def is_consistent(self) -> bool:
        return not self._internal_conflicts()

    def conflicts_with(self, fact: Fact) -> list[Fact]:
        """Public, READ-ONLY: beliefs in the base that contradict ``fact`` (a functional
        ``(subject, predicate)`` clash with a different object, or a declared negation).

        Does not mutate the base. Used by the live-membrane nogood pre-check to detect a
        staged edge contradicting a seeded T0/operator fact before any promotion."""
        return self._conflicts_with(fact)

    # ---- conflict detection ---------------------------------------------------
    def _conflicts_with(self, fact: Fact) -> list[Fact]:
        out: list[Fact] = []
        for other in self._facts.values():
            if other.key() == fact.key():
                continue
            if self._contradict(fact, other):
                out.append(other)
        return out

    def _contradict(self, a: Fact, b: Fact) -> bool:
        # functional predicate: same (s,p), different object
        if a.sp() == b.sp() and a.predicate.lower() in self.functional:
            if a.object.lower() != b.object.lower():
                return True
        # explicit negation pair
        if frozenset({a.key(), b.key()}) in self._negates:
            return True
        return False

    def _internal_conflicts(self) -> list[tuple[Fact, Fact]]:
        vals = list(self._facts.values())
        out = []
        for i in range(len(vals)):
            for j in range(i + 1, len(vals)):
                if self._contradict(vals[i], vals[j]):
                    out.append((vals[i], vals[j]))
        return out

    # ---- AGM operations -------------------------------------------------------
    def expand(self, fact: Fact) -> None:
        """``K + p``: add without consistency check (AGM expansion)."""
        self._facts[fact.key()] = fact

    def contract(self, fact: Fact) -> RevisionResult:
        """``K - p``: give up ``fact`` (AGM contraction).

        Base contraction: remove the literal fact if present. Satisfies success
        (``p not in K - p``), inclusion (``K - p subset K``) and vacuity
        (``p not in K  =>  K - p = K``). Does not claim recovery.
        """
        if fact.key() not in self._facts:
            return RevisionResult(accepted=False, fact=fact,
                                  rejected_reason="vacuous_not_present",
                                  beliefs=tuple(self.facts()))
        removed = self._facts.pop(fact.key())
        return RevisionResult(accepted=True, fact=fact, dropped=(removed,),
                              beliefs=tuple(self.facts()))

    def promote(self, fact: Fact) -> RevisionResult:
        """``K * p``: revise by ``fact`` (Levi identity + entrenchment).

        If ``fact`` is consistent with ``K`` -> expand. Otherwise, for each
        conflicting belief, drop the strictly-less-entrenched side; if ``fact``
        is the least entrenched (in particular whenever it conflicts with an
        operator fact and is not itself operator), **reject** ``fact`` and leave
        ``K`` unchanged (screened revision -- the operator core is never given
        up). On an equal-tier conflict, default-deny (reject incoming).
        """
        conflicts = self._conflicts_with(fact)
        if not conflicts:
            self.expand(fact)
            return RevisionResult(accepted=True, fact=fact,
                                  beliefs=tuple(self.facts()))

        # An operator belief is an integrity constraint: never dropped.
        for c in conflicts:
            if c.tier == OPERATOR and fact.tier != OPERATOR:
                return RevisionResult(
                    accepted=False, fact=fact,
                    rejected_reason=f"conflicts_operator_core:{c.subject}.{c.predicate}",
                    beliefs=tuple(self.facts()))
            if c.tier == OPERATOR and fact.tier == OPERATOR:
                # two operator facts conflict: never drop the established one
                return RevisionResult(
                    accepted=False, fact=fact,
                    rejected_reason="operator_operator_conflict_reject_incoming",
                    beliefs=tuple(self.facts()))

        # decide, per conflict, who is less entrenched
        to_drop: list[Fact] = []
        for c in conflicts:
            if fact.rank > c.rank:
                to_drop.append(c)  # incoming more entrenched: drop existing
            elif fact.rank < c.rank:
                # incoming strictly less entrenched: reject incoming outright
                return RevisionResult(
                    accepted=False, fact=fact,
                    rejected_reason=(
                        f"incoming_less_entrenched_than:{c.tier}"),
                    beliefs=tuple(self.facts()))
            else:  # equal rank
                if self.tie_break_reject_incoming:
                    return RevisionResult(
                        accepted=False, fact=fact,
                        rejected_reason=f"equal_entrenchment_tie:{c.tier}",
                        beliefs=tuple(self.facts()))
                to_drop.append(c)

        # Levi: contract the conflicting (least-entrenched) beliefs, then expand
        dropped: list[Fact] = []
        for c in to_drop:
            removed = self._facts.pop(c.key(), None)
            if removed is not None:
                dropped.append(removed)
        self.expand(fact)
        return RevisionResult(accepted=True, fact=fact, dropped=tuple(dropped),
                              beliefs=tuple(self.facts()))
