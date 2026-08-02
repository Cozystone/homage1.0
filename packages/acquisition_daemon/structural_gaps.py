# -*- coding: utf-8 -*-
"""Intrinsic curiosity — the SECOND endogenous gap source: genuinely-valuable STRUCTURAL holes.

The recurrence source (``gap_signals.GapLedger``) only pursues a fact if the SAME question was
honestly abstained ≥ ``MIN_PRESSURE`` times — so a structural hole that nobody re-asks is invisible.
That is recurrence-of-DEMAND, not curiosity. This module closes that gap: it reads the SHIPPED graph
(READ-ONLY) and finds relations that the graph's OWN induced schema says an entity SHOULD have but
doesn't — a hole the system can want to fill under endogenous pressure, with no one asking.

Doctrine anchor (reuse, don't reinvent): this is the ``reasoning_vm.curiosity`` deficit-curriculum
idea (a gap drives a gated expedition) applied to the RELATIONAL graph, and it keeps the same
selection idiom as ``autonomy_kernel.intrinsic_drive._steer_topic`` (steer toward what we can't
ground). The novelty/priority signal is not invented here — it is the graph's own schema statistics.

Why the signal is PRINCIPLED, not a hardcoded target list
---------------------------------------------------------
A "structural hole" for entity ``e`` and relation ``r`` is scored by three graph-derived factors —
nothing about which entities or relations is written down in code:

  * SALIENCE(e)   — the entity's degree (edges in + out). A hole on a hub the graph leans on matters
                    more than a hole on a leaf. (Read from the columns, per entity.)
  * VALUE(T, r)   — TYPE-CONDITIONED COVERAGE: of the peers that share ``e``'s ``is_a`` type ``T``,
                    the fraction that possess relation ``r``. This is a schema INDUCED from the
                    graph: "entities like this one usually have this relation." It is exactly what
                    stops a nonsense hole — a Play's peers have no ``capital`` (coverage 0), so
                    ``capital of Hamlet`` is never proposed; a Country's peers nearly all have
                    ``population`` (coverage high), so a Country missing it is a real hole.
  * UNCERTAINTY(T, r) — normalized Shannon entropy of the OBJECTS peers hold for ``r``: how
                    unpredictable the answer is, i.e. how much is learned by filling it. A relation
                    whose answer is the same for every peer carries little information; one whose
                    answer differs per peer carries a lot. (Secondary modifier — see the honesty note.)

    score(e, r) = salience_norm(e) · coverage(T, r) · info(T, r)

Change the graph and every factor changes, so the priority FOLLOWS THE SIGNAL — the sealed gate
proves this by swapping the graph and watching the ordering flip (a hardcoded list could not).

Honesty (stated for the report): salience and coverage are the crisp, defensible drivers; the
entropy term is a gentle informativeness modifier bounded to ``[uncertainty_floor, 1.0]`` so it only
ever breaks ties between otherwise-equal holes — it is the thinnest of the three and is labelled as
such. Curiosity chooses only WHAT to investigate; it writes nothing and it weakens no gate — the
acquisition loop's ≥2-domain consensus still verifies every fact and the operator gate still guards
every write. A hole with no web evidence yields no consensus and is never queued (fabrication 0).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

try:
    import numpy as np
    _HAVE_NP = True
except Exception:  # pragma: no cover — numpy is a hard dep of the store
    _HAVE_NP = False

from packages.base_brain.relational_lookup import REL_SYNONYMS, graph_relations

from .gap_signals import gap_key as _gap_key

# The type edge the schema is induced over. is_a is the graph's own typing predicate.
_TYPE_PRED = "is_a"
# Predicates that are structure/aliasing, never askable relations.
_NON_RELATION_PREDS = frozenset({"is_a", "alias", "sense", "instance_of", "subclass_of"})


def _present_labels(rel_norm: str) -> frozenset[str]:
    """The graph predicate labels that count as "entity HAS relation ``rel_norm``" — the exact set
    ``relational_lookup._predicate_targets`` matches on re-answer, so detection and resolution agree."""
    labels = set(REL_SYNONYMS.get(rel_norm, frozenset()))
    labels.add(rel_norm.replace(" ", "_"))
    return frozenset(labels)


def _relation_groups(store: Any = None) -> list[dict[str, Any]]:
    """Askable relation GROUPS induced from the LAD relation vocabulary (relation NAMES — the
    permitted surface layer — not world facts). Synonymous relations that map to the SAME predicate
    label set are collapsed to one canonical group so a single hole is not proposed twice (e.g.
    ``author``/``writer``). Each group is a phrasing + the label set that means "present"."""
    by_labels: dict[frozenset[str], str] = {}
    for rel_norm in sorted(graph_relations(store)):   # curiosity ranges over what THIS graph has
        labels = _present_labels(rel_norm)
        prev = by_labels.get(labels)
        # canonical rel_norm for a label set: the lexicographically-smallest surface form (stable)
        if prev is None or rel_norm < prev:
            by_labels[labels] = rel_norm
    groups = []
    for labels, rel_norm in by_labels.items():
        groups.append({"rel_norm": rel_norm, "labels": labels,
                       "question": f"what is the {rel_norm} of {{entity}}?"})
    return groups


@dataclass
class StructuralHole:
    """One graph-derived structural hole: entity ``e`` of type ``T`` is missing relation ``rel_norm``
    that its peers have. ``score`` is the principled priority; ``components`` exposes every factor so
    the gate and the report can inspect exactly why it ranked where it did."""
    entity: str
    rel_norm: str
    type_label: str
    question: str
    gap_key: str
    score: float
    salience: int                     # raw degree of the entity (edges in + out)
    coverage: float                   # fraction of type peers that have this relation (schema value)
    info: float                       # object-entropy informativeness modifier in [floor, 1]
    n_type_peers: int
    n_peers_with_rel: int
    components: dict[str, Any] = field(default_factory=dict)

    def as_target(self) -> dict[str, Any]:
        """The shape ``GapLedger.pressured`` consumes as a second endogenous source."""
        return {"gap_key": self.gap_key, "question": self.question, "score": self.score,
                "pressure_sources": ["structural_curiosity"], "curiosity": self.components}


class StructuralGapScanner:
    """Reads a TripleStore (READ-ONLY) and returns the top structural holes ranked by the principled
    salience·coverage·uncertainty score. Bounded (caps on members and holes) so it is safe to point
    at a large store; deterministic so the sealed gate is reproducible. Writes NOTHING."""

    def __init__(self, store: Any, *, min_type_members: int = 3, min_coverage: float = 0.5,
                 max_holes: int = 64, max_holes_per_relation: int = 32,
                 uncertainty_floor: float = 0.5, type_pred: str = _TYPE_PRED):
        self.store = store
        self.min_type_members = int(min_type_members)
        self.min_coverage = float(min_coverage)
        self.max_holes = int(max_holes)
        self.max_holes_per_relation = int(max_holes_per_relation)
        self.uncertainty_floor = float(uncertainty_floor)
        self.type_pred = type_pred

    # ---- helpers ---------------------------------------------------------------------------------
    def _entropy_info(self, obj_ids: "np.ndarray") -> float:
        """Normalized-entropy informativeness of a relation's objects across peers, mapped into
        ``[uncertainty_floor, 1]``. All-same objects -> floor (predictable, low info); all-distinct
        -> 1 (maximally informative). Fewer than 2 samples -> floor (can't measure uncertainty)."""
        n = int(len(obj_ids))
        if n < 2:
            return self.uncertainty_floor
        _vals, counts = np.unique(obj_ids, return_counts=True)
        probs = counts / counts.sum()
        h = float(-(probs * np.log2(probs)).sum())
        h_norm = h / math.log2(n)            # divide by the max entropy for n samples -> [0, 1]
        return self.uncertainty_floor + (1.0 - self.uncertainty_floor) * h_norm

    # ---- the scan --------------------------------------------------------------------------------
    def scan(self) -> list[StructuralHole]:
        if not _HAVE_NP:
            return []
        store = self.store
        terms = store.terms
        cols = store.open_columns()
        s, p, o = cols["s"], cols["p"], cols["o"]
        if len(s) == 0:
            return []

        type_pid = terms.lookup(self.type_pred)
        if type_pid is None:
            return []                                       # no typing edge -> no induced schema

        # 1) DEGREE (salience): edges touching each term id, in + out. One vectorized pass.
        # `minlength` is a FLOOR, not a width: bincount returns max(minlength, ids.max()+1). On the
        # shipped store some ids appear only as subjects and others only as objects, so the two
        # counts came back 47,774,230 and 47,767,878 long and the add raised — curiosity crashed on
        # the real graph while every fixture (whose ids are dense and small) passed. Bind both to one
        # explicit width so the arrays are aligned by construction.
        width = int(max(len(terms), int(np.asarray(s).max()) + 1, int(np.asarray(o).max()) + 1))
        degree = (np.bincount(np.asarray(s), minlength=width)
                  + np.bincount(np.asarray(o), minlength=width))

        # 2) TYPES: entity id -> set(type ids), and type id -> member entity ids (from is_a rows).
        type_mask = np.asarray(p) == type_pid
        ent_ids = np.asarray(s)[type_mask]
        typ_ids = np.asarray(o)[type_mask]
        # Group by type with ONE sort, not one full-column mask per type. The shipped store has
        # 297,136 distinct types over 44,491,090 is_a rows, so `ent_ids[typ_ids == t]` in a loop is
        # 13.2 trillion element comparisons — the scan never returned on the real graph while every
        # fixture (a handful of types) finished instantly. Sorting once is O(n log n) and gives the
        # same grouping.
        order = np.argsort(typ_ids, kind="stable")
        typ_sorted, ent_sorted = typ_ids[order], ent_ids[order]
        bounds = np.flatnonzero(np.r_[True, typ_sorted[1:] != typ_sorted[:-1], True])
        members: dict[int, np.ndarray] = {}
        for lo, hi in zip(bounds[:-1], bounds[1:]):
            if hi - lo < self.min_type_members:
                continue                                    # cheap reject before the unique()
            m = np.unique(ent_sorted[lo:hi])
            if len(m) >= self.min_type_members:
                members[int(typ_sorted[lo])] = m

        if not members:
            return []

        # 3) RELATION GROUPS present in this store (askable schema; label ids that actually exist).
        groups = []
        for g in _relation_groups(store):
            lids = [terms.lookup(l) for l in g["labels"]]
            lids = [int(x) for x in lids if x is not None]
            if not lids:
                continue                                     # relation never appears here
            gmask = np.isin(np.asarray(p), np.asarray(lids, dtype=p.dtype))
            if not gmask.any():
                continue
            # Keep ONLY this relation's own rows, sorted by subject. Every later per-type step then
            # works over these (a few million at most, usually far fewer) instead of masking the full
            # 115M column again -- the second wall the argsort fix uncovered.
            sg = np.asarray(s)[gmask]
            og = np.asarray(o)[gmask]
            so = np.argsort(sg, kind="stable")
            sg, og = sg[so], og[so]
            groups.append({**g, "sg": sg, "og": og, "subj_with": np.unique(sg)})
        if not groups:
            return []

        # 4) HOLES: for each (type, relation) whose peer-coverage clears the value floor, each member
        #    that LACKS the relation is a structural hole scored by salience·coverage·uncertainty.
        holes: list[StructuralHole] = []
        info_cache: dict[tuple[int, int], float] = {}
        for gi, g in enumerate(groups):
            # One boolean lookup indexed by entity id, built once per relation, so the per-type
            # membership test below is an array index rather than a search. `np.isin` per (type,
            # relation) pair was the third wall: tens of thousands of types times ~46 relations is
            # millions of searches, and the scan still had not returned after 134 CPU-minutes.
            has_rel = np.zeros(width, dtype=bool)
            has_rel[g["subj_with"]] = True
            for tid, m in members.items():
                have = has_rel[m]
                n_with = int(have.sum())
                n_peers = int(len(m))
                coverage = n_with / n_peers if n_peers else 0.0
                if coverage < self.min_coverage:
                    continue                                 # not an INDUCED expectation -> not a hole
                missing = m[~have]                            # members that lack the expected relation
                if len(missing) == 0:
                    continue
                # informativeness of this relation's answer across the peers that DO have it
                key = (tid, gi)
                info = info_cache.get(key)
                if info is None:
                    # objects asserted for this relation by the type's members — over the group's
                    # own (sorted) rows, never the full column.
                    peer = np.isin(g["sg"], m, assume_unique=False)
                    info = self._entropy_info(g["og"][peer])
                    info_cache[key] = info
                type_label = terms.term(tid)
                # cap holes per (type, relation) to the most salient, so one common relation cannot
                # flood the list on a large store — bounded work, best-first.
                order = np.argsort(-degree[missing], kind="stable")[: self.max_holes_per_relation]
                for idx in order:
                    eid = int(missing[idx])
                    entity = terms.term(eid)
                    if not entity:
                        continue
                    question = g["question"].format(entity=entity)
                    gk = _gap_key(question)
                    if not gk:
                        continue                              # unparseable phrasing (defensive)
                    sal = int(degree[eid])
                    holes.append(StructuralHole(
                        entity=entity, rel_norm=g["rel_norm"], type_label=type_label,
                        question=question, gap_key=gk, score=0.0, salience=sal,
                        coverage=round(coverage, 4), info=round(info, 4),
                        n_type_peers=n_peers, n_peers_with_rel=n_with,
                        components={"salience": sal, "coverage": round(coverage, 4),
                                    "info": round(info, 4), "type": type_label,
                                    "n_type_peers": n_peers, "n_peers_with_rel": n_with}))

        if not holes:
            return []

        # 5) SCORE + RANK. Normalize salience by the max degree among hole entities so the score is a
        #    comparable product of three ~[0,1] factors. Ranking is within a graph (the whole point:
        #    swap the graph -> the factors change -> the order changes).
        max_deg = max(h.salience for h in holes) or 1
        for h in holes:
            sal_norm = h.salience / max_deg
            h.score = round(sal_norm * h.coverage * h.info, 6)
            h.components["salience_norm"] = round(sal_norm, 4)
            h.components["score"] = h.score
        holes.sort(key=lambda h: (-h.score, -h.salience, h.gap_key))
        return holes[: self.max_holes]

    def targets(self) -> list[dict[str, Any]]:
        """The ranked holes as ``pressured``-ready target dicts (second endogenous source)."""
        return [h.as_target() for h in self.scan()]
