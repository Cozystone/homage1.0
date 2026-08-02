# -*- coding: utf-8 -*-
"""Assumption-based Truth Maintenance System (ATMS).

Source of record
----------------
Johan de Kleer, "An Assumption-based TMS", *Artificial Intelligence* 28(2),
pp. 127-162 (1986). (Companions: "Extending the ATMS" and "Problem solving with
the ATMS", same issue.)

Faithful constructs from the paper
----------------------------------
* An **assumption** is a primitive datum taken as true by choice. An
  **environment** is a *set* of assumptions.                        (de Kleer §2)
* Every datum (node) carries a **label**: the set of environments under which it
  holds. The label is kept **minimal** (no environment subsumes another),
  **consistent** (no environment is a superset of a nogood), sound, and
  complete.                                                          (de Kleer §3)
* A **nogood** is an environment shown to be inconsistent (it entails the
  distinguished false node ``⊥``). Every superset of a nogood is also nogood.
  Recording contradictions as nogoods -- rather than backtracking -- is exactly
  what gives the ATMS its headline property: **"context switching is free"**,
  i.e. you can ask what holds under *this* set of assumptions vs *that* set
  without re-deriving anything.                                     (de Kleer §1)
* ``holds_under(datum, env)`` -- the datum holds in a context ``env`` iff some
  environment in its label is a subset of ``env`` and ``env`` is itself
  consistent.                                                        (de Kleer §4)

ATANOR mapping (docs/ATANOR_final_gate_research.md §2, NS-3)
-----------------------------------------------------------
Assumptions are the **epistemic tiers**::

    {T0_operator}     operator-signed ground truth (the adopted core)
    {consensus}       k-source cross-domain consensus
    {single_source}   one source only
    {neural}          neural/embedding proposal -- staging only, "forever hypothesis"

This turns quarantine (docs §2 stage ①) into de Kleer's decades-proven formalism:

* **safe mode**   = query under ``{T0_operator}``      -> only the operator core.
* **creative mode** = query under ``{T0_operator, neural}`` -> also entertains
  neural proposals -- and the switch is free (no re-derivation), per de Kleer.
* A neural datum that **contradicts** a T0 datum makes the joint environment
  ``{T0_operator, neural}`` a **nogood**; the neural datum can then hold in no
  consistent context that also carries the operator core, so it is
  **auto-invalidated**, while the T0 datum (label ``{{T0_operator}}``) is
  untouched. The asymmetry is *structural* -- the operator core is always
  adopted -- not a hand-tuned rule. Which environment becomes the nogood on a
  contradiction, and hence which datum survives, is the entrenchment decision
  that :mod:`revision` (AGM) owns; the ATMS only records and propagates.

No numpy; stdlib only. Environments and the nogood database are ``frozenset``s.
"""
from __future__ import annotations

from typing import Iterable

# canonical tier assumptions
T0 = "T0_operator"
CONSENSUS = "consensus"
SINGLE_SOURCE = "single_source"
NEURAL = "neural"

Env = frozenset  # an environment is a frozenset[str] of assumptions

FALSE = "__false__"  # de Kleer's distinguished contradiction node (⊥)


def env(*assumptions: str) -> "frozenset[str]":
    """Build an environment (a set of assumptions)."""
    return frozenset(assumptions)


class ATMS:
    """An assumption-based TMS over tier assumptions.

    ``core`` is the always-adopted environment (the operator ground truth,
    ``{T0_operator}`` by default). A datum is *invalidated* when it can hold in
    no consistent context that also carries the core.
    """

    def __init__(self, core: Iterable[str] = (T0,)) -> None:
        self.core: frozenset[str] = frozenset(core)
        self.assumptions: set[str] = set(self.core)
        # datum -> label (set of minimal, consistent environments)
        self._labels: dict[str, set[frozenset[str]]] = {}
        # the nogood database (minimal inconsistent environments)
        self._nogoods: set[frozenset[str]] = set()

    # ---- assumptions / data ---------------------------------------------------
    def add_assumption(self, name: str) -> None:
        self.assumptions.add(name)

    def assume(self, datum: str, environment: Iterable[str]) -> None:
        """Record that ``datum`` holds under ``environment`` (a set of tiers).

        Adds the environment to the datum's label, keeping the label minimal
        (subsumption) and consistent (drops any environment that is a superset
        of a known nogood).
        """
        e = frozenset(environment)
        self.assumptions.update(e)
        label = self._labels.setdefault(datum, set())
        self._add_env(label, e)
        self._prune_label(label)

    def datum(self, name: str) -> None:
        self._labels.setdefault(name, set())

    # ---- contradictions / nogoods --------------------------------------------
    def mark_nogood(self, environment: Iterable[str]) -> None:
        """Declare ``environment`` inconsistent (entails ``⊥``).

        Any existing superset nogood is subsumed; then every datum label is
        re-pruned so environments that became inconsistent drop out (a datum
        supported only by nogood environments is auto-invalidated -- its label
        goes empty)."""
        e = frozenset(environment)
        # keep the nogood DB minimal
        if any(ng <= e for ng in self._nogoods):
            return
        self._nogoods = {ng for ng in self._nogoods if not e <= ng}
        self._nogoods.add(e)
        for label in self._labels.values():
            self._prune_label(label)

    def register_contradiction(self, datum_a: str, datum_b: str) -> list[frozenset[str]]:
        """Record that ``datum_a`` and ``datum_b`` cannot both hold.

        Following de Kleer: a ``⊥`` node justified by both data has label =
        ``{ Ea ∪ Eb : Ea ∈ label(a), Eb ∈ label(b) }``; every such combined
        environment is a nogood. Returns the nogoods added.
        """
        la = self._labels.get(datum_a, set())
        lb = self._labels.get(datum_b, set())
        added: list[frozenset[str]] = []
        for ea in list(la):
            for eb in list(lb):
                combined = ea | eb
                added.append(combined)
                self.mark_nogood(combined)
        return added

    # ---- queries --------------------------------------------------------------
    def is_nogood(self, environment: Iterable[str]) -> bool:
        """True iff ``environment`` is a superset of some recorded nogood."""
        e = frozenset(environment)
        return any(ng <= e for ng in self._nogoods)

    def label(self, datum: str) -> set[frozenset[str]]:
        """The datum's current (minimal, consistent) label."""
        return set(self._labels.get(datum, set()))

    def holds_under(self, datum: str, environment: Iterable[str]) -> bool:
        """Does ``datum`` hold in context ``environment``? (de Kleer §4)

        True iff the context is consistent (not a superset of any nogood) and
        some environment in the datum's label is a subset of the context.
        """
        e = frozenset(environment)
        if self.is_nogood(e):
            return False
        label = self._labels.get(datum, set())
        return any(supp <= e for supp in label)

    def invalidated(self, datum: str) -> bool:
        """True iff ``datum`` can hold in no consistent context that also
        carries the operator core.

        For every supporting environment ``E`` in the label, ``E ∪ core`` is a
        nogood (or the label is empty). This is the tier-aware invalidation the
        firewall relies on: a neural datum that contradicts the T0 core cannot
        survive alongside the ever-present core, while the T0 datum can.
        """
        label = self._labels.get(datum, set())
        if not label:
            return True
        return all(self.is_nogood(e | self.core) for e in label)

    def valid(self, datum: str) -> bool:
        return not self.invalidated(datum)

    def safe_query(self, datum: str) -> bool:
        """Hold under the operator core only (``{T0_operator}``)."""
        return self.holds_under(datum, self.core)

    def creative_query(self, datum: str, *, tiers: Iterable[str] = (NEURAL,)) -> bool:
        """Hold under the operator core plus additional entertained tiers
        (``{T0_operator, neural}`` by default)."""
        return self.holds_under(datum, self.core | frozenset(tiers))

    def context(self, environment: Iterable[str]) -> list[str]:
        """All data that hold under ``environment`` (a materialised context).

        Free context switching: call with ``{T0}`` for safe, ``{T0, neural}``
        for creative -- no re-derivation between them."""
        e = frozenset(environment)
        if self.is_nogood(e):
            return []
        return sorted(d for d in self._labels if self.holds_under(d, e))

    def nogoods(self) -> set[frozenset[str]]:
        return set(self._nogoods)

    # ---- internals ------------------------------------------------------------
    @staticmethod
    def _add_env(label: set[frozenset[str]], e: frozenset[str]) -> None:
        # subsumption: skip if a subset already present; drop existing supersets
        if any(existing <= e for existing in label):
            return
        for existing in list(label):
            if e <= existing:
                label.discard(existing)
        label.add(e)

    def _prune_label(self, label: set[frozenset[str]]) -> None:
        # drop environments that are inconsistent (superset of a nogood)
        for e in list(label):
            if self.is_nogood(e):
                label.discard(e)
