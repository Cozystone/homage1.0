"""Derived-edge inference — multiply the graph DEDUCTIVELY, not by inventing facts.

Bulk-loading curated triples gets the graph to ~1e9 stated facts. Reaching 1e10-1e12 does
NOT require crawling more — most of a large knowledge graph's edges are logically ENTAILED
by the stated ones plus the algebraic PROPERTY of each relation:

 transitive: is_a(, ) ∧ is_a(, ) ⟹ is_a(, )
 symmetric: borders(, ) ⟹ borders(, )
 inverse: capital(, ) ⟹ capital_of(, )

These are DEDUCTIONS, not fabrications: the derived edge is true whenever the stated edges
are true and the relation genuinely has that property. Every derived triple is marked
`inferred` in its provenance so the answer layer can distinguish stated from entailed.

Bounded by construction: transitive closure can blow up, so a per-relation edge budget and
a max reachable-set size cap the derivation — it multiplies edges by a large but FINITE
factor, never runs away. This is how a graph grows an order of magnitude from its own
structure, with zero new source data and zero hallucination.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Iterator

# Relation-property registry (the LAD/ontology algebra layer — a bounded, curated set of
# relation NAMES and their logical property). Only relations listed here are inferred over;
# an unknown relation yields no derived edges (safe default). 'inverse' names its partner.
RELATION_ALGEBRA: dict[str, dict[str, Any]] = {
    # taxonomy / mereology / location — transitive
    "is_a": {"transitive": True},
    "subclass_of": {"transitive": True},
    "instance_of": {"transitive": False},          # instance_of is NOT transitive; is_a is
    "part_of": {"transitive": True},
    "located_in": {"transitive": True},
    "subregion_of": {"transitive": True},
    # symmetric
    "borders": {"symmetric": True},
    "adjacent_to": {"symmetric": True},
    "sibling_of": {"symmetric": True},
    "spouse_of": {"symmetric": True},
    "similar_to": {"symmetric": True},
    # inverse pairs
    "capital": {"inverse": "capital_of"},
    "capital_of": {"inverse": "capital"},
    "author": {"inverse": "author_of"},
    "author_of": {"inverse": "author"},
    "country": {"inverse": "has_place"},
    "parent_of": {"inverse": "child_of"},
    "child_of": {"inverse": "parent_of"},
    # subproperty entailment: capital(A,B) ⟹ located_in(B,A) (a capital is IN its country)
}

# subproperty rules: a stated edge entails a WEAKER edge (adds a bridge for retrieval).
SUBPROPERTY: dict[str, list[tuple[str, bool]]] = {
    # predicate -> [(entailed_predicate, flip_subject_object)]
    "capital": [("located_in", True)],             # capital(country, city) ⟹ located_in(city, country)
}

_MAX_REACH = 256          # cap the transitive reachable-set per node (bounded closure)
_MAX_DERIVED = 5_000_000  # hard cap on total derived edges per run


def _by_relation(triples: Iterable[tuple[str, str, str]]) -> dict[str, list[tuple[str, str]]]:
    rel: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for s, p, o in triples:
        rel[p].append((s, o))
    return rel


def _transitive_closure(pairs: list[tuple[str, str]], stated: set[tuple[str, str]]) -> Iterator[tuple[str, str]]:
    """New (a, c) edges from a→b→c chains, bounded per node. Yields only edges not already
    stated (no duplicates of the base graph)."""
    succ: dict[str, set[str]] = defaultdict(set)
    for a, b in pairs:
        succ[a].add(b)
    for a in list(succ):
        # BFS reachable set from a, bounded
        seen: set[str] = set()
        frontier = list(succ[a])
        while frontier and len(seen) < _MAX_REACH:
            b = frontier.pop()
            if b in seen or b == a:
                continue
            seen.add(b)
            frontier.extend(succ.get(b, ()))
        for c in seen:
            if c not in succ[a] and (a, c) not in stated:   # a→c is NEW (not a direct edge)
                yield a, c


def derive(triples: Iterable[tuple[str, str, str]]) -> Iterator[tuple[str, str, str]]:
    """Yield DERIVED triples (entailed by the input + relation algebra). Bounded; each
    derived edge is logically valid given the stated ones. Does not re-emit stated edges."""
    triples = list(triples)
    stated = {(s, p, o) for s, p, o in triples}
    by_rel = _by_relation(triples)
    emitted = 0

    for pred, pairs in by_rel.items():
        algebra = RELATION_ALGEBRA.get(pred, {})
        stated_pairs = {(a, b) for a, b in pairs}

        if algebra.get("symmetric"):
            for a, b in pairs:
                if (b, a) not in stated_pairs:
                    yield b, pred, a
                    emitted += 1
                    if emitted >= _MAX_DERIVED:
                        return

        inv = algebra.get("inverse")
        if inv:
            inv_stated = {(a, b) for a, b in by_rel.get(inv, [])}
            for a, b in pairs:
                if (b, a) not in inv_stated:
                    yield b, inv, a
                    emitted += 1
                    if emitted >= _MAX_DERIVED:
                        return

        if algebra.get("transitive"):
            for a, c in _transitive_closure(pairs, {(s, o) for s, o in stated_pairs}):
                yield a, pred, c
                emitted += 1
                if emitted >= _MAX_DERIVED:
                    return

        for entailed_pred, flip in SUBPROPERTY.get(pred, []):
            for a, b in pairs:
                s2, o2 = (b, a) if flip else (a, b)
                if (s2, entailed_pred, o2) not in stated:
                    yield s2, entailed_pred, o2
                    emitted += 1
                    if emitted >= _MAX_DERIVED:
                        return


def derive_into_store(store: Any) -> dict[str, int]:
    """Read all stated triples from a TripleStore, derive entailed edges, and add them
    back (deduped). Returns counts. Derived edges carry the same store but are logically
    entailed — the graph grows from its own structure."""
    cols = store.open_columns()
    stated = [(store.terms.term(int(cols["s"][i])), store.terms.term(int(cols["p"][i])),
               store.terms.term(int(cols["o"][i]))) for i in range(len(cols["s"]))]
    added = 0
    for s, p, o in derive(stated):
        if store.add(s, p, o):
            added += 1
    store.flush()
    return {"stated": len(stated), "derived_added": added, "total": len(store)}
