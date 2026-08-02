# -*- coding: utf-8 -*-
"""Discovery D0 — deductive closure over TRANSITIVE relations (the safe first rung of the D-ladder).

Discovery here is making IMPLICIT knowledge EXPLICIT, never inventing it: if the graph holds
→→ it ENTAILS is_a , even without that direct edge. This organ enumerates every
such entailed (subject, relation, ancestor) edge for the transitive relations (is_a, subclass_of,
part_of) — a deductively VALID derivation, so it is un-hallucinatable (it can be asserted, not merely
conjectured, unlike analogy/theory rungs which must stay hypotheses). Materializing the closure
densifies the graph, so discrimination / statement-entailment then verify more claims DIRECTLY.

Cycle-safe and bounded (depth + node cap). Read-only: it returns derived edges with provenance; a
separate gated step may persist them. Non-transitive relations are out of scope here (they would be
conjecture, which the honesty doctrine keeps as a QUESTION, not an asserted fact — see mint_*).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .statement_entailment import _norm, _rel

TRANSITIVE_RELS = ("is_a", "subclass_of", "part_of")


@dataclass
class Derived:
    subject: str
    relation: str
    obj: str
    hops: int                       # how many edges the derivation chained (≥2 → genuinely new)
    path: list[str]                 # the chain of intermediate nodes (auditable provenance)


def derive_transitive_closure(subject: str,
                              facts_about: Callable[[str], list[tuple[str, str, str]]],
                              *, rels: tuple[str, ...] = TRANSITIVE_RELS,
                              max_depth: int = 6, max_nodes: int = 400) -> list[Derived]:
    """Every (subject, R, ancestor) edge ENTAILED by transitive R but not DIRECTLY stored.

    Walks the R-backbone breadth-first; an ancestor first reached at depth ≥2 that the subject does
    not already link to directly is a genuine derivation. Deductively valid — un-hallucinatable."""
    out: list[Derived] = []
    relset = {r.lower() for r in rels}
    try:
        base = facts_about(subject) or []
    except Exception:
        return out
    # direct targets per relation — a derivation must be NEW (not already an edge)
    direct = {r: {_norm(o) for (s, p, o) in base if _rel(p) == r} for r in relset}
    seen: set[str] = {_norm(subject)}
    # frontier holds (node_label, relation_of_chain, hops, path_so_far)
    frontier: list[tuple[str, str, int, list[str]]] = []
    for (s, p, o) in base:
        r = _rel(p)
        if r in relset:
            frontier.append((o, r, 1, [subject, o]))
    emitted: set[tuple[str, str, str]] = set()
    while frontier:
        node, rel, hops, path = frontier.pop(0)
        key = _norm(node)
        if key in seen or len(seen) >= max_nodes or hops >= max_depth:
            continue
        seen.add(key)
        try:
            nf = facts_about(node) or []
        except Exception:
            nf = []
        for (s, p, o) in nf:
            r2 = _rel(p)
            if r2 not in relset:
                continue
            # transitive relations compose only within the SAME relation (is_a∘is_a, part_of∘part_of);
            # is_a and subclass_of also chain (both are taxonomy), so treat them as one backbone.
            if not _compatible(rel, r2):
                continue
            no = _norm(o)
            eff_rel = "is_a" if {rel, r2} <= {"is_a", "subclass_of"} else rel
            edge = (_norm(subject), eff_rel, no)
            if no != _norm(subject) and no not in direct.get(eff_rel, set()) and edge not in emitted:
                emitted.add(edge)
                out.append(Derived(subject, eff_rel, o, hops + 1, path + [o]))
            frontier.append((o, r2, hops + 1, path + [o]))
    return out


def _compatible(r1: str, r2: str) -> bool:
    """Two transitive relations compose iff they are the same, or both taxonomy (is_a/subclass_of)."""
    if r1 == r2:
        return True
    return {r1, r2} <= {"is_a", "subclass_of"}
