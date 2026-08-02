"""Relation-quality filter — drop extraction-noise IS_A edges using graph statistics, no rule table.

The learned graph's IS_A edges are dominated by extraction noise: adjectives/fragments parsed as
parents (American, , largest, historic, ) and polysemous one-off parents (→). Two pure
graph statistics separate a real hypernym from noise:

 1. concept-ness — a real category is itself used as a SUBJECT elsewhere (has outgoing edges).
 An adjective/fragment parent has outgoing == 0 (it only ever appears as a bare label).
 2. generality — a real category has MULTIPLE members (children >= 2). A one-off parent
 (children == 1) is idiosyncratic / polysemy.

A trustworthy IS_A parent satisfies BOTH. Non-IS_A relations (USED_FOR, HAS, CAUSES…) are kept as
is — they are far less noise-prone and the coverage gate handles their weight. No lexicon, no
per-entity rules; this strengthens automatically as the graph grows (better statistics).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

_ISA = {"IS_A", "IS-A", "ISA", "SUBCLASS_OF"}


def graph_stats(relations: list[dict[str, Any]], id_to_name: dict[str, str]) -> dict[str, Any]:
    children: dict[str, set[str]] = defaultdict(set)
    outgoing: Counter[str] = Counter()
    for r in relations:
        s = id_to_name.get(str(r.get("source_concept_id")))
        t = id_to_name.get(str(r.get("target_concept_id")))
        if not s or not t:
            continue
        outgoing[s] += 1
        if str(r.get("relation") or "").upper() in _ISA:
            children[t].add(s)
    return {"children": children, "outgoing": outgoing}


def isa_parent_trusted(parent_name: str, stats: dict[str, Any], *, min_children: int = 2) -> bool:
    """A trustworthy hypernym: a REAL concept (used as a subject → outgoing > 0) that categorises
    MULTIPLE things (children >= min_children). Filters adjective/fragment parents and one-off
    polysemy parents. Pure graph statistics."""
    return stats["outgoing"].get(parent_name, 0) > 0 and len(stats["children"].get(parent_name, set())) >= min_children


def filter_trusted_relations(
    relations: list[dict[str, Any]],
    id_to_name: dict[str, str],
    stats: dict[str, Any] | None = None,
    *,
    min_children: int = 2,
) -> list[dict[str, Any]]:
    """Return the relations with noise IS_A edges removed (non-IS_A kept as is)."""
    st = stats or graph_stats(relations, id_to_name)
    kept: list[dict[str, Any]] = []
    for r in relations:
        if str(r.get("relation") or "").upper() not in _ISA:
            kept.append(r)
            continue
        parent = id_to_name.get(str(r.get("target_concept_id")))
        if parent and isa_parent_trusted(parent, st, min_children=min_children):
            kept.append(r)
    return kept
