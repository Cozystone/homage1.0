# -*- coding: utf-8 -*-
"""Defeasible reasoning: Reiter default logic + Pollock undercutting defeaters.

Source of record
----------------
* Raymond Reiter, "A Logic for Default Reasoning", *Artificial Intelligence*
  13(1-2), pp. 81-132 (1980). A **default** ``alpha : beta / gamma`` reads "if
  ``alpha`` holds and ``beta`` is consistent to assume, conclude ``gamma``". A
  **normal default** is ``alpha : gamma / gamma`` -- "believe ``gamma`` unless
  it is contradicted".
* John Pollock, "Defeasible Reasoning", *Cognitive Science* 11(4), pp. 481-518
  (1987) (and earlier work). Two kinds of defeater:
    - **rebutting** defeater -- a reason for the *opposite* conclusion
      (``not gamma``); it attacks the conclusion itself.
    - **undercutting** defeater -- a reason to doubt that the premise *supports*
      the conclusion (``not (premise => gamma)``); it withdraws the warrant
      **without asserting** ``not gamma``.

Why this is the mechanism M3 asked for
--------------------------------------
M3 (commit b7bd2292, docs/ATANOR_final_gate_research.md §2) localised a blind
spot: a **confidently-wrong STORED inherited fact** (an inheritance exception,
e.g. "penguin can_fly" inherited from "bird can_fly") has low entropy and high
resonance margin -- indistinguishable from clean-correct to the M3 signals. It
concluded such facts "need external consensus/override-risk or defeater-encoding
= M2/NS-3". This module is the defeater-encoding half.

An inheritance **exception** that is *encoded in the graph* -- e.g. the fact
"penguin cannot_fly" sitting next to the inherited default -- is registered as
an **undercutting defeater** of the inheritance step. It withdraws support for
"penguin can_fly" (status IN -> OUT/WITHDRAWN) **without the reasoner asserting
"penguin cannot_fly" as one of its own derived conclusions**. So a confidently-
wrong inherited fact becomes *detectable* (status is WITHDRAWN, not IN) and
*retractable*, exactly closing the blind spot for graph-encodable exceptions.

Native encoding (elegant, not a bolt-on)
----------------------------------------
Doyle already gave us nonmonotonic justifications: an SL-justification's
**outlist** must be OUT for the justification to hold. So a default is a
justification whose outlist contains its **undercutter node**; asserting the
undercutter flips it IN, which invalidates the default's justification, which
flips the default OUT -- pure dependency-directed propagation, no negation
asserted. This module is a thin, well-documented layer over :class:`JTMS` that
speaks Reiter/Pollock vocabulary and exposes the verifiable property
``asserted_negations() == set()`` for undercutting.

Honest scope (stated up front, repeated in the report)
------------------------------------------------------
This closes the blind spot **only for graph-encodable exceptions** -- there must
be a node/edge signal (an exception marker adjacent to the inherited default).
For a truly-hidden confidently-wrong fact with *no* graph signal at all, this
module does nothing: there is no defeater to fire. Those still require EXTERNAL
evidence (web consensus / operator override), precisely as M3 said. No magic.

No numpy; stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from packages.truth_maintenance.jtms import JTMS, IN, OUT

WITHDRAWN = "WITHDRAWN"  # a default whose warrant was undercut (distinct from plain OUT)


def undercut_node(conclusion: str) -> str:
    """The name of the undercutting-defeater node for a conclusion."""
    return f"undercut::{conclusion}"


@dataclass
class DefeasibleReasoner:
    """Reiter defaults with Pollock defeaters, over a JTMS.

    Vocabulary:
      * :meth:`add_fact`          -- an indefeasible (strict) belief / premise.
      * :meth:`add_default`       -- a normal default: conclude ``conclusion``
        from ``reasons`` unless undercut.
      * :meth:`add_inheritance_default` -- the property-inheritance default
        (``instance is_a cls`` & ``cls has prop`` ~> ``instance has prop``).
      * :meth:`add_undercutter`   -- a Pollock undercutting defeater: withdraw
        the warrant, assert no negation.
      * :meth:`add_exception`     -- a graph-encoded exception marker; registers
        the undercutter for you (the M3 blind-spot path).
      * :meth:`add_rebutter`      -- a Pollock rebutting defeater (asserts the
        opposite), provided for contrast/tests.
    """

    jtms: JTMS = field(default_factory=JTMS)
    #: conclusions that carry a defeasible (default) warrant
    _defaults: set[str] = field(default_factory=set)
    #: negations the reasoner has itself asserted (populated only by rebutters)
    _asserted_negations: set[str] = field(default_factory=set)

    # ---- strict facts ---------------------------------------------------------
    def add_fact(self, key: str, *, informant: str = "graph") -> None:
        """A strict, indefeasible premise (e.g. a stored ``is_a`` edge)."""
        self.jtms.add_premise(key, informant=informant)

    # ---- defaults (Reiter) ----------------------------------------------------
    def add_default(
        self,
        conclusion: str,
        reasons: list[str],
        *,
        informant: str = "default_rule",
    ) -> None:
        """Normal default ``reasons : conclusion / conclusion``.

        Encoded as a JTMS justification whose inlist is ``reasons`` and whose
        outlist is the conclusion's undercutter node -- so the conclusion is IN
        while its reasons hold and it is not undercut.
        """
        self._defaults.add(conclusion)
        self.jtms.node(undercut_node(conclusion))  # ensure defeater node exists (OUT)
        self.jtms.add_justified(
            conclusion,
            support=reasons,
            out_list=[undercut_node(conclusion)],
            informant=informant,
        )

    def add_inheritance_default(
        self, instance: str, cls: str, prop: str, *, informant: str = "inheritance"
    ) -> str:
        """The inheritance default: if ``instance is_a cls`` and ``cls`` has
        property ``prop``, then by default ``instance`` has ``prop``.

        Adds the two strict antecedents if absent and the defeasible conclusion
        ``prop(instance)``. Returns the conclusion key.
        """
        isa = f"is_a({instance},{cls})"
        clsprop = f"{prop}({cls})"
        conclusion = f"{prop}({instance})"
        self.add_fact(isa, informant="graph")
        self.add_fact(clsprop, informant="graph")
        self.add_default(conclusion, [isa, clsprop], informant=informant)
        return conclusion

    # ---- Pollock defeaters ----------------------------------------------------
    def add_undercutter(self, conclusion: str, *, informant: str = "exception") -> None:
        """Pollock **undercutting** defeater: assert the conclusion's undercutter
        node, withdrawing the default's warrant WITHOUT asserting ``not
        conclusion``.

        The reasoner's derived-negation set is deliberately left untouched --
        that is the whole distinction from a rebutter and is checked by
        :meth:`asserted_negations`.
        """
        self.jtms.add_premise(undercut_node(conclusion), informant=informant)

    def add_exception(
        self, instance: str, prop: str, *, marker: str | None = None,
        informant: str = "graph_exception",
    ) -> None:
        """A **graph-encoded exception** to an inherited property -- the M3
        blind-spot path.

        ``marker`` is the exception fact as it sits in the graph (e.g.
        "cannot_fly(penguin)"); it is recorded as an indefeasible fact for
        provenance/audit, and it is wired as the undercutter of ``prop(instance)``.
        Crucially, the *undercutting* action withdraws the inherited default's
        warrant; it does not make the reasoner assert the negation.
        """
        conclusion = f"{prop}({instance})"
        if marker:
            # record the exception marker as a real stored fact (audit trail),
            # but do NOT route it into the derived-negation set.
            self.jtms.add_premise(marker, informant=informant)
        self.add_undercutter(conclusion, informant=informant)

    def add_rebutter(self, conclusion: str, negation: str, *, informant: str = "rebuttal") -> None:
        """Pollock **rebutting** defeater (for contrast): assert a reason for the
        opposite conclusion. This DOES populate the derived-negation set -- the
        behaviour undercutting deliberately avoids."""
        self.jtms.add_premise(negation, informant=informant)
        self._asserted_negations.add(negation)
        # a rebuttal that also defeats the default is modelled by undercutting
        # the warrant as well (the conclusion should not remain IN alongside a
        # believed opposite); but the negation IS asserted here, unlike undercut.
        self.jtms.add_premise(undercut_node(conclusion), informant=informant)

    # ---- queries --------------------------------------------------------------
    def status(self, conclusion: str) -> str:
        """IN (warranted) / WITHDRAWN (a default whose warrant was undercut) /
        OUT (never supported)."""
        st = self.jtms.status(conclusion)
        if st == IN:
            return IN
        if conclusion in self._defaults and self.jtms.is_in(undercut_node(conclusion)):
            return WITHDRAWN
        return OUT

    def is_warranted(self, conclusion: str) -> bool:
        return self.jtms.is_in(conclusion)

    def asserted_negations(self) -> set[str]:
        """Negations the reasoner has itself asserted.

        For pure undercutting this is EMPTY -- the verifiable Pollock property
        that "undercutting withdraws support without asserting the negation".
        Only :meth:`add_rebutter` populates it.
        """
        return set(self._asserted_negations)

    def explanation(self, conclusion: str) -> dict:
        return self.jtms.explanation(conclusion)
