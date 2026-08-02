# -*- coding: utf-8 -*-
"""Brain-like spreading activation over the knowledge graph.

The old answer path read ONE edge and stamped a template (" ") — a
lookup, not reasoning. A brain does not stop at one hop: a concept lights up, activation
spreads to its neighbours, attenuating with distance, and the lit-up subgraph — not a single
fact — is what the answer is composed from. Context is maintained across arbitrarily many hops
because it lives in the ACTIVATION FIELD (concept -> activation), not in a fixed-depth counter.

Design (grounded, No-LLM, hallucination-safe by construction — every node/edge is a stored fact):
 - activation(anchor) = 1.0.
 - spread along RELATIONAL edges only; each hop multiplies by the relation's weight and a decay,
 and accumulates at the target (re-visited concepts reinforce, like the brain).
 - UNBOUNDED depth — the walk stops when delivered activation falls below a threshold, so
 strongly-relevant paths run deep and weak ones die out. max_nodes only bounds runaway fan-out.
 - intent bias: edges whose predicate matches the question's focus relation are boosted, so
 " ?" lights brightest while still illuminating its neighbourhood.
 - terminal PROPERTY edges (defined_as / / …) are collected for generation but not
 recursed through (their object is a gloss/scalar, not a concept to spread from).

The relation weights are INITIAL PRIORS (relation-type, ~two dozen entries — NOT per-entity rules);
Phase B (accelerating-returns evolution) evolves them against sealed-holdout answer fitness.
"""
from __future__ import annotations

import heapq
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# --- relation-type priors (Phase-B-evolvable). Spread FOLLOWS these (object is a concept). ---
_SPREAD_W: dict[str, float] = {
    "is_a": 0.85, "subclass_of": 0.85, "instance_of": 0.8,
    "part_of": 0.8, "has_part": 0.7, "member_of": 0.7,
    "located_in": 0.75, "country": 0.75, "대륙": 0.6, "subregion_of": 0.7,
    "capital": 0.9, "수도": 0.9,
    "causes": 0.7, "결과": 0.55, "used_for": 0.6, "produces": 0.6,
    "requires": 0.55, "depends_on": 0.55, "enables": 0.55,
    "created_by": 0.7, "manufacturer": 0.6, "발견": 0.7, "발명": 0.7,
    "similar_to": 0.4, "contrasts_with": 0.4, "related_to": 0.35,
}
# collected for the answer but NOT recursed (terminal properties / scalars / glosses)
_COLLECT_PREDS = frozenset({
    "defined_as", "has_property", "인구", "면적", "넓이", "설립", "언어", "공용어",
    "통화", "화폐", "원자번호", "population", "area",
})
# never used for answering (surface-form redirects and word-sense tags)
_SKIP_PREDS = frozenset({"alias", "sense"})

_DEFAULT_SPREAD_W = 0.3          # an unlisted relational predicate still spreads, weakly
_INTENT_BOOST = 2.2              # edges matching the question's focus relation
_DECAY = 0.6                     # per-hop attenuation
_THRESHOLD = 0.09               # activation floor: below this a path dies out (bounds depth)

# EVOLVED GENOME (Phase B): evolve_traversal.py writes the sealed-holdout-fittest weights/params
# here; loading them at import means the LIVE traversal answers with the evolved policy, while the
# module defaults above are the honest fallback if evolution has never run.
_GENOME_PATH = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "traversal_genome.json"


def _load_genome() -> None:
    global _INTENT_BOOST, _DECAY, _THRESHOLD, _DEFAULT_SPREAD_W
    try:
        g = json.loads(_GENOME_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    _SPREAD_W.update({k: float(v) for k, v in (g.get("weights") or {}).items()})
    _INTENT_BOOST = float(g.get("intent_boost", _INTENT_BOOST))
    _DECAY = float(g.get("decay", _DECAY))
    _THRESHOLD = float(g.get("threshold", _THRESHOLD))
    _DEFAULT_SPREAD_W = float(g.get("default_w", _DEFAULT_SPREAD_W))


_load_genome()


@dataclass
class ActivatedSubgraph:
    anchor: str
    activation: dict[str, float]                       # concept -> accumulated activation (context)
    edges: list[tuple[str, str, str, float]]           # (s, p, o, delivered) — the reasoning trace
    properties: dict[str, list[tuple[str, str, str]]]  # concept -> its collected property facts

    def top_concepts(self, k: int = 6, *, exclude: tuple[str, ...] = ()) -> list[tuple[str, float]]:
        items = [(c, a) for c, a in self.activation.items()
                 if c != self.anchor and c not in exclude]
        items.sort(key=lambda x: x[1], reverse=True)
        return items[:k]

    def anchor_facts(self) -> list[tuple[str, str, str]]:
        """The anchor's own directly-stated facts (properties + first-hop relations),
        activation-ordered — the skeleton a definition/relation answer is realized from."""
        rels = [(s, p, o) for (s, p, o, _d) in self.edges if s == self.anchor]
        props = self.properties.get(self.anchor, [])
        return props + rels


def spread(anchor: str,
           facts_about: Callable[[str], list[tuple[str, str, str]]],
           *, intent_preds: tuple[str, ...] = (), decay: float | None = None,
           threshold: float | None = None, max_nodes: int = 160, row_cap: int = 24,
           weights: dict[str, float] | None = None, default_w: float | None = None,
           intent_boost: float | None = None) -> ActivatedSubgraph:
    """Spread activation outward from `anchor`. `facts_about(term)` returns that term's
    stored triples. Returns the lit-up subgraph (concepts + edges + collected properties).
    The weight/decay/threshold/intent_boost knobs default to the (possibly evolved) module
    genome; evolve_traversal.py passes explicit values to score a candidate genome."""
    decay = _DECAY if decay is None else decay
    threshold = _THRESHOLD if threshold is None else threshold
    w_table = weights if weights is not None else _SPREAD_W
    dflt_w = _DEFAULT_SPREAD_W if default_w is None else default_w
    boost = _INTENT_BOOST if intent_boost is None else intent_boost
    activation: dict[str, float] = {anchor: 1.0}
    edges: list[tuple[str, str, str, float]] = []
    properties: dict[str, list[tuple[str, str, str]]] = {}
    intent = set(intent_preds)
    # max-heap by activation (negate for heapq)
    frontier: list[tuple[float, str]] = [(-1.0, anchor)]
    visited: set[str] = set()

    while frontier and len(visited) < max_nodes:
        neg_a, node = heapq.heappop(frontier)
        if node in visited:
            continue
        visited.add(node)
        a = -neg_a
        try:
            rows = facts_about(node) or []
        except Exception:
            rows = []
        for s, p, o in rows[:row_cap]:
            p = str(p)
            o = str(o)
            if not o or o == node or p in _SKIP_PREDS:
                continue
            if p in _COLLECT_PREDS or (o and not _looks_like_concept(o) and p not in w_table):
                properties.setdefault(node, []).append((str(s), p, o))
                continue
            w = w_table.get(p, dflt_w)
            if p in intent and node == anchor:
                w *= boost
            delivered = a * w * decay
            if delivered < threshold:
                continue
            activation[o] = activation.get(o, 0.0) + delivered
            edges.append((str(s), p, o, delivered))
            if o not in visited:
                heapq.heappush(frontier, (-activation[o], o))

    return ActivatedSubgraph(anchor=anchor, activation=activation,
                             edges=edges, properties=properties)


def _looks_like_concept(o: str) -> bool:
    """A spread target must be a concept (short noun-ish label), not a sentence-length gloss
    or a bare scalar. Prose definitions and numbers are terminal properties, not nodes to walk."""
    o = o.strip()
    if not o or len(o) > 24:
        return False
    if o.replace(",", "").replace(".", "").isdigit():
        return False
    # a gloss reads like a clause (spaces + a predicate ending); a concept label does not
    if o.count(" ") >= 2:
        return False
    return True
