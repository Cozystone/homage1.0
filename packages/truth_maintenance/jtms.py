# -*- coding: utf-8 -*-
"""Justification-based Truth Maintenance System (JTMS).

Source of record
----------------
Jon Doyle, "A Truth Maintenance System", *Artificial Intelligence* 12(3),
pp. 231-272 (1979). Also: Forbus & de Kleer, *Building Problem Solvers* (1993),
ch. 7, for the well-founded labelling algorithm reproduced here.

Faithful constructs from the paper
----------------------------------
* Every belief is a **node** with a support **status**: ``IN`` (currently
  believed) or ``OUT`` (not currently believed).                    (Doyle §2)
* A node's belief rests on its **justifications**. This module uses Doyle's
  **support-list (SL) justification**: ``(inlist, outlist)`` -- the node is
  supported by that justification iff every node in ``inlist`` is IN and every
  node in ``outlist`` is OUT.                                        (Doyle §3)
* A **premise** is a node with an SL-justification ``([], [])`` -- valid
  unconditionally, so the node is IN with no antecedents. A node with a
  non-empty ``outlist`` is an **assumption** (its belief is nonmonotonic).
* A node is IN iff it has at least one **valid** justification whose support is
  **well-founded** (grounded -- no belief may be justified only through a cycle
  of its own support).                                              (Doyle §5)
* **Dependency-directed retraction**: when a premise is withdrawn, the labels of
  *every* node reachable through the justification graph are recomputed, so each
  descendant that has lost all support flips to OUT automatically. Doyle's whole
  point: retraction is not a garbage-collection pass bolted on afterwards -- it
  is the native consequence of recomputing well-founded support. This is what
  makes an unsupported belief (a "hallucination" with no surviving evidence)
  *structurally* impermanent rather than something a cleaner has to chase.

Why this matters for ATANOR (docs/ATANOR_final_gate_research.md §2, NS-3):
a promoted fact records the JTMS justification that supports it; if its source
is later invalidated, ``retract`` flips the fact and everything derived from it
to OUT with no separate sweep -- the contamination cannot linger.

Implementation notes (honest)
-----------------------------
The labelling is the **grounded / well-founded** model computed by a monotone
fixpoint over settled labels (a node is proven IN only from already-IN
antecedents; proven OUT only when every justification is defeated by already
settled nodes). This is exact for acyclic and stratified dependency graphs --
the shape a staging/promotion firewall actually produces. Genuinely odd
(non-stratified) negative cycles have no grounded model; such nodes are left OUT
(the conservative, default-deny choice) and reported via :meth:`unresolved`.
No numpy; stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

IN = "IN"
OUT = "OUT"


@dataclass(frozen=True)
class Justification:
    """An SL (support-list) justification (Doyle 1979 §3).

    The node it justifies is *valid under this justification* iff every key in
    ``in_list`` is IN and every key in ``out_list`` is OUT. ``informant`` is the
    provenance -- the rule, source, or agent that supplied the justification
    (Doyle's "informant"; PROV-O ``wasGeneratedBy`` in modern terms).
    """

    in_list: tuple[str, ...] = ()
    out_list: tuple[str, ...] = ()
    informant: str = ""

    @property
    def is_premise(self) -> bool:
        return not self.in_list and not self.out_list


@dataclass
class Node:
    """A belief node (Doyle 1979 §2)."""

    key: str
    justifications: list[Justification] = field(default_factory=list)
    status: str = OUT
    #: the justification currently supporting the node (its "well-founded
    #: support"), or None when the node is OUT.
    support: Justification | None = None


class JTMS:
    """A justification-based truth maintenance system.

    Typical use::

        j = JTMS()
        j.add_premise("wiki:paris", informant="wikidata")
        j.add_justified("capital(france)=paris",
                        support=["wiki:paris"], informant="relation_lane")
        j.is_in("capital(france)=paris")          # -> True
        j.retract("wiki:paris")                    # source invalidated
        j.is_in("capital(france)=paris")          # -> False  (auto-OUT)
    """

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._unresolved: set[str] = set()

    # ---- construction ---------------------------------------------------------
    def node(self, key: str) -> Node:
        n = self._nodes.get(key)
        if n is None:
            n = Node(key=key)
            self._nodes[key] = n
        return n

    def add_premise(self, key: str, *, informant: str = "") -> Node:
        """Assert ``key`` as a premise: SL-justification ``([], [])``.

        A premise is believed unconditionally (Doyle §3) -- this is how an
        external assertion / a source enters the system. Retracting the premise
        (:meth:`retract`) is what triggers dependency-directed propagation.
        """
        n = self.node(key)
        prem = Justification(informant=informant)
        if prem not in n.justifications:
            n.justifications.append(prem)
        self._relabel()
        return n

    def add_justified(
        self,
        key: str,
        support: Sequence[str],
        *,
        out_list: Sequence[str] = (),
        informant: str = "",
    ) -> Node:
        """Add an SL-justification for ``key``.

        ``support`` (the inlist) must all be IN and ``out_list`` (the defeaters)
        must all be OUT for the justification to be valid. A non-empty
        ``out_list`` makes ``key`` an *assumption* -- the native Doyle encoding
        of a nonmonotonic default (used by :mod:`defeasible`).
        """
        for dep in tuple(support) + tuple(out_list):
            self.node(dep)  # ensure antecedent nodes exist (default OUT)
        n = self.node(key)
        just = Justification(
            in_list=tuple(support), out_list=tuple(out_list), informant=informant
        )
        if just not in n.justifications:
            n.justifications.append(just)
        self._relabel()
        return n

    def retract(self, key: str) -> None:
        """Withdraw ``key`` as a premise and recompute all affected labels.

        Removes the *premise* justifications of ``key`` (the external assertions
        of it). Derived justifications that merely mention ``key`` are left
        intact -- they simply become invalid once ``key`` goes OUT, which is the
        whole point: dependency-directed retraction lets the well-founded
        recompute flip every now-unsupported descendant to OUT automatically.
        """
        n = self._nodes.get(key)
        if n is None:
            return
        n.justifications = [j for j in n.justifications if not j.is_premise]
        self._relabel()

    def retract_justification(self, key: str, informant: str) -> None:
        """Remove justifications for ``key`` that came from a given informant.

        Models "this *source* was invalidated": every justification whose
        informant is ``informant`` is dropped, then labels are recomputed so
        beliefs resting on that source (and their descendants) flip OUT.
        """
        n = self._nodes.get(key)
        if n is None:
            return
        n.justifications = [j for j in n.justifications if j.informant != informant]
        self._relabel()

    def invalidate_informant(self, informant: str) -> list[str]:
        """Drop *every* justification supplied by ``informant`` across all nodes,
        then relabel. Returns the keys that flipped to OUT.

        This is the firewall's "source invalidation" primitive: one bad source
        withdraws all the beliefs it (transitively) supported.
        """
        before = {k for k, v in self._nodes.items() if v.status == IN}
        for n in self._nodes.values():
            n.justifications = [j for j in n.justifications if j.informant != informant]
        self._relabel()
        after = {k for k, v in self._nodes.items() if v.status == IN}
        return sorted(before - after)

    # ---- labelling (well-founded / grounded model) ----------------------------
    def _relabel(self) -> None:
        """Recompute IN/OUT for all nodes as the grounded model.

        Monotone fixpoint over settled labels:
          * prove IN  -- some justification has every inlist node already IN and
            every outlist node already OUT;
          * prove OUT -- *every* justification is already defeated (some inlist
            node OUT, or some outlist node IN) by settled labels.
        A premise proves IN immediately (all() over empty lists); a node with no
        justification proves OUT immediately. Iterating to a fixpoint yields the
        well-founded support relation (Doyle §5).
        """
        label: dict[str, str] = {}
        support: dict[str, Justification | None] = {}
        nodes = list(self._nodes.values())

        changed = True
        while changed:
            changed = False
            for n in nodes:
                if n.key in label:
                    continue
                won: Justification | None = None
                for j in n.justifications:
                    if all(label.get(d) == IN for d in j.in_list) and all(
                        label.get(d) == OUT for d in j.out_list
                    ):
                        won = j
                        break
                if won is not None:
                    label[n.key] = IN
                    support[n.key] = won
                    changed = True
                    continue
                # provable OUT: every justification already defeated by settled labels
                def defeated(j: Justification) -> bool:
                    return any(label.get(d) == OUT for d in j.in_list) or any(
                        label.get(d) == IN for d in j.out_list
                    )

                if all(defeated(j) for j in n.justifications):
                    label[n.key] = OUT
                    support[n.key] = None
                    changed = True

        # any node left unlabelled sits in an odd negative loop -> no grounded
        # model; default to OUT (conservative / default-deny) and record it.
        self._unresolved = {n.key for n in nodes if n.key not in label}
        for n in nodes:
            n.status = label.get(n.key, OUT)
            n.support = support.get(n.key)

    # ---- queries --------------------------------------------------------------
    def status(self, key: str) -> str:
        n = self._nodes.get(key)
        return n.status if n is not None else OUT

    def is_in(self, key: str) -> bool:
        return self.status(key) == IN

    def unresolved(self) -> set[str]:
        """Keys with no grounded label (odd negative cycle) -- left OUT."""
        return set(self._unresolved)

    def beliefs(self) -> list[str]:
        """All currently-IN belief keys."""
        return sorted(k for k, n in self._nodes.items() if n.status == IN)

    def explanation(self, key: str) -> dict:
        """The well-founded support of ``key``: its supporting justification and
        the recursive support of each antecedent (Doyle's explanation)."""
        n = self._nodes.get(key)
        if n is None or n.status != IN or n.support is None:
            return {"key": key, "status": self.status(key), "support": None}
        j = n.support
        return {
            "key": key,
            "status": IN,
            "informant": j.informant,
            "in": {d: self.explanation(d) for d in j.in_list},
            "out": {d: self.status(d) for d in j.out_list},
        }

    def dependents(self, key: str) -> list[str]:
        """Keys whose justifications mention ``key`` (its consequences)."""
        out = []
        for k, n in self._nodes.items():
            for j in n.justifications:
                if key in j.in_list or key in j.out_list:
                    out.append(k)
                    break
        return sorted(out)
