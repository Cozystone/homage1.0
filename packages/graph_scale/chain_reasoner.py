# -*- coding: utf-8 -*-
"""Multi-hop chain reasoning (roadmap P3, generalized) — composition algebra over
stored edges.

One triple rarely answers a relationship question; a CHAIN does. This module now
answers FOUR question shapes, all grounded in stored edges only:

 ultimate ' ?' — climb the transitive ladder to the settled top
 verify ' ?' — find a stored path →…→, answer + chain
 property ' ?' — property INHERITANCE: is_a ladder ∧ capable_of
 relation ' ?' — path discovery between two named concepts

The composition table _COMPOSE is ALGEBRA (structural logic: what a chain of
predicates entails), never knowledge — the facts themselves always come from the
graph, per the hard rule. Soundness over reach: a pair absent from the table
prunes the walk; the composed conclusion is only spoken when the algebra licenses
it. Every clause verbalizes a stored edge verbatim — hallucination-safe by
construction, and cycles/termination stay guaranteed (visited-set BFS, bounded
depth/nodes; the 'ultimate' shape keeps its Lyapunov energy-descent walk).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from .inference import RELATION_ALGEBRA

# the transitive relations a chain may follow (each is transitive in RELATION_ALGEBRA)
_CHAIN_PREDS = tuple(p for p, a in RELATION_ALGEBRA.items() if a.get("transitive"))

# --- composition algebra: (relation-so-far, next-edge-predicate) -> composed relation.
# Structural entailments only (kind-level mereology/taxonomy/location + inheritance).
_COMPOSE: dict[tuple[str, str], str] = {
    ("is_a", "is_a"): "is_a",
    ("subclass_of", "subclass_of"): "subclass_of",
    ("is_a", "subclass_of"): "is_a",
    ("subclass_of", "is_a"): "subclass_of",
    ("part_of", "part_of"): "part_of",
    ("located_in", "located_in"): "located_in",
    ("subregion_of", "subregion_of"): "subregion_of",
    ("is_a", "part_of"): "part_of",          # every kind-member is part of what its kind is part of
    ("is_a", "located_in"): "located_in",
    ("part_of", "located_in"): "located_in",
    ("located_in", "part_of"): "located_in",
    ("located_in", "subregion_of"): "located_in",
    ("subregion_of", "located_in"): "located_in",
    # inheritance down the taxonomy: kinds pass properties/abilities/parts/uses to members
    ("is_a", "has_property"): "has_property",
    ("is_a", "capable_of"): "capable_of",
    ("is_a", "has_part"): "has_part",
    ("is_a", "used_for"): "used_for",
    ("subclass_of", "has_property"): "has_property",
    ("subclass_of", "capable_of"): "capable_of",
    ("subclass_of", "has_part"): "has_part",
    ("subclass_of", "used_for"): "used_for",
}
_ALGEBRA_PREDS = {p for pair in _COMPOSE for p in pair} | set(_CHAIN_PREDS)

# properties a taxonomy ladder may inherit (terminal edges — they never compose further)
_INHERITABLE = ("capable_of", "has_property", "has_part", "used_for")


def _fa(facts_about: Callable[..., list[tuple[str, str, str]]], node: str,
        preds: tuple[str, ...], limit: int = 64) -> list[tuple[str, str, str]]:
    """Predicate-aware fetch with plain-callable fallback. At millions of rows a
    predicate-blind scan returns whatever relation floods the store first
    (measured at 5.8M: located_in buried is_a) — walkers must name what they walk.
    Test doubles are plain lambdas; they get the unfiltered call."""
    try:
        return facts_about(node, limit=limit, preds=preds)
    except TypeError:
        return facts_about(node)

# per-predicate Korean clause forms: (mid-sentence, final). All grounded labels verbatim.
_PRED_CLAUSE: dict[str, tuple[str, str]] = {
    "is_a": ("{s}{neun} {o}의 일종이고", "{s}{neun} {o}의 일종입니다"),
    "subclass_of": ("{s}{neun} {o}의 일종이고", "{s}{neun} {o}의 일종입니다"),
    "part_of": ("{s}{neun} {o}의 일부이고", "{s}{neun} {o}의 일부입니다"),
    "located_in": ("{s}{neun} {o}에 있고", "{s}{neun} {o}에 있습니다"),
    "subregion_of": ("{s}{neun} {o}의 하위 지역이고", "{s}{neun} {o}의 하위 지역입니다"),
    "capable_of": ("{s}{neun} '{o}'{i_ga} 가능하고", "{s}{neun} '{o}'{i_ga} 가능합니다"),
    "has_property": ("{s}{neun} '{o}' 속성을 가지고", "{s}{neun} '{o}' 속성을 가집니다"),
    "has_part": ("{s}에는 {o}{i_ga} 있고", "{s}에는 {o}{i_ga} 있습니다"),
    "used_for": ("{s}{neun} {o}에 쓰이고", "{s}{neun} {o}에 쓰입니다"),

    "defined_as": ("{s}{neun} '{o}'이고", "{s}{neun} '{o}'입니다"),
    "alias": ("{s}{neun} '{o}'이고", "{s}{neun} '{o}'입니다"),
}


@dataclass
class ChainResult:
    start: str
    conclusion: str
    predicate: str
    chain: list[tuple[str, str, str]]      # the stored edges actually traversed
    local_minimum: bool

    def to_answer_ko(self) -> str:
        if not self.chain:
            return ""
        pred_ko = {"is_a": "의 일종", "subclass_of": "의 일종", "part_of": "의 일부",
                   "located_in": "에 속한", "subregion_of": "의 하위 지역"}.get(self.predicate, "")

        clauses = []
        for i, (s, _p, o) in enumerate(self.chain):
            tail = "이고" if i < len(self.chain) - 1 else "입니다"
            clauses.append(f"{s}{_josa_neun(s)} {o}{pred_ko}{tail}")
        body = ", ".join(clauses)
        # conclusion when the chain is >1 hop (the transitive fact is the new knowledge)
        if len(self.chain) >= 2:
            body += f". 따라서 {self.start}{_josa_neun(self.start)} {self.conclusion}{pred_ko}입니다"
        return body + ". (출처: 큐레이션 지식그래프 · 다단계 추론)"


def _josa_i(w: str) -> str:
    from packages.lad_morphology import subject
    return subject(w)[len(w):]


def _josa_neun(w: str) -> str:
    from packages.lad_morphology import topic
    return topic(w)[len(w):]


def _clause(edge: tuple[str, str, str], final: bool) -> str:
    s, p, o = edge
    mid, fin = _PRED_CLAUSE.get(p, ("{s}{neun} {o}(관계: " + p + ")이고",
                                    "{s}{neun} {o}(관계: " + p + ")입니다"))
    tpl = fin if final else mid
    return tpl.format(s=s, o=o, neun=_josa_neun(s), i_ga=_josa_i(o))


def _conclusion_ko(start: str, edge_obj: str, rel: str) -> str:
    neun = _josa_neun(start)
    if rel in ("is_a", "subclass_of"):
        return f"따라서 {start}{neun} {edge_obj}의 일종입니다"
    if rel == "part_of":
        return f"따라서 {start}{neun} {edge_obj}의 일부입니다"
    if rel in ("located_in", "subregion_of"):
        return f"따라서 {start}{neun} {edge_obj}에 있습니다"
    if rel == "capable_of":
        return f"따라서 {start}도 '{edge_obj}'{_josa_i(edge_obj)} 가능합니다"
    if rel == "has_property":
        return f"따라서 {start}도 '{edge_obj}' 속성을 가집니다"
    if rel == "has_part":
        return f"따라서 {start}에도 {edge_obj}{_josa_i(edge_obj)} 있습니다"
    if rel == "used_for":
        return f"따라서 {start}도 {edge_obj}에 쓰입니다"
    return ""


def _verbalize_path(chain: list[tuple[str, str, str]], composed: str | None,
                    start: str, prefix: str = "", end_label: str | None = None) -> str:
    clauses = [_clause(e, final=(i == len(chain) - 1)) for i, e in enumerate(chain)]
    body = prefix + ", ".join(clauses)
    if composed and len(chain) >= 2:
        # the asked-about label leads; the graph label follows in parens when they

        end = chain[-1][2]
        label = end if end_label in (None, end) else f"{end_label}({end})"
        concl = _conclusion_ko(start, label, composed)
        if concl:
            body += f". {concl}"
    return body + ". (출처: 큐레이션 지식그래프 · 다단계 추론)"


def reason_chain(start: str, facts_about: Callable[[str], list[tuple[str, str, str]]],
                 predicate: str = "is_a", max_states: int = 4096) -> ChainResult | None:
    """Climb the transitive chain from `start` via `predicate` using energy descent.
    facts_about(subject) -> stored (s,p,o) rows. Returns the settled conclusion + the
    exact edges traversed, or None when `start` has no outgoing edge of that predicate."""
    from packages.energy_descent import EnergyDescent

    if predicate not in _CHAIN_PREDS:
        return None
    # neighbour = the object of a stored `predicate` edge; energy = -depth so climbing
    # the hierarchy is strictly downhill. depth is discovered as we go (BFS layer).
    depth: dict[str, int] = {start: 0}
    edge_into: dict[str, tuple[str, str, str]] = {}

    def neighbors(node: str):
        outs = []
        for (s, p, o) in _fa(facts_about, node, (predicate,)):
            if p == predicate and o != node and o not in depth:
                depth[o] = depth[node] + 1
                edge_into[o] = (s, p, o)
                outs.append(o)
        return outs

    def energy(node: str) -> float:
        return -float(depth.get(node, 0))

    result = EnergyDescent(energy, neighbors, max_states=max_states).settle(start)
    if result.settled_state == start:
        return None  # no outgoing edge — nothing to reason over
    # reconstruct the traversed edges from start to the settled ancestor
    chain: list[tuple[str, str, str]] = []
    node = result.settled_state
    while node in edge_into:
        s, p, o = edge_into[node]
        chain.append((s, p, o))
        node = s
    chain.reverse()
    return ChainResult(start=start, conclusion=result.settled_state, predicate=predicate,
                       chain=chain, local_minimum=result.local_minimum)


_GLOSS_RE = re.compile(r"^[A-Za-z][A-Za-z-]{2,24}$")


def _gloss_hops(node: str, facts_about: Callable[[str], list[tuple[str, str, str]]]
                ) -> list[tuple[str, str, str]]:
    """Single-latin-word dictionary glosses of a Korean term ( defined_as
 'sparrow') act as IDENTITY hops: the gloss is the same concept in the other
 half of the graph, connecting Korean questions to the English taxonomy.
 Single-token-only — a phrase gloss is a description, not an identity."""
    if not re.search(r"[가-힣]", node):
        return []
    try:
        edges = _fa(facts_about, node, ("defined_as", "alias"))
    except Exception:
        return []
    hops = [(s, p, o) for (s, p, o) in edges
            if p in ("defined_as", "alias") and _GLOSS_RE.match(o)]

    # more than one distinct gloss the identity is ambiguous, and hopping picked

    # One gloss = one identity; anything else stays silent.
    if len({o.lower() for _s, _p, o in hops}) != 1:
        return []
    return hops[:1]


def _gloss_targets(target: str,
                   facts_about: Callable[[str], list[tuple[str, str, str]]]) -> set[str]:
    """The target plus its identity glosses — '?' must also match 'animal'."""
    return {target} | {o for _s, _p, o in _gloss_hops(target, facts_about)}


def find_path(start: str, target: str,
              facts_about: Callable[[str], list[tuple[str, str, str]]],
              max_depth: int = 5, max_nodes: int = 4096,
              taxonomy_only: bool = False
              ) -> tuple[list[tuple[str, str, str]], str | None] | None:
    """BFS from start toward target over algebra predicates, tracking the COMPOSED
    relation. A hop whose composition is undefined prunes (soundness over reach).
    Identity glosses expand the start frontier and the target set (cross-language).
    Returns (chain, composed_relation) or None. Visited-set => no cycles; bounded."""
    from collections import deque

    if start == target:
        return None
    targets = _gloss_targets(target, facts_about)
    queue: deque[tuple[str, str | None, tuple[tuple[str, str, str], ...]]] = deque()
    queue.append((start, None, ()))
    seen = {start}
    # identity hop first: the gloss IS the start concept, relation still unset
    for edge in _gloss_hops(start, facts_about):
        gloss = edge[2]
        if gloss in targets:
            return [edge], None
        if gloss not in seen:
            seen.add(gloss)
            queue.append((gloss, None, (edge,)))
    while queue:
        node, rel, chain = queue.popleft()
        if len(chain) >= max_depth or len(seen) >= max_nodes:
            continue
        walk_preds = ("is_a", "subclass_of") if taxonomy_only else tuple(_ALGEBRA_PREDS)
        try:
            edges = sorted(_fa(facts_about, node, walk_preds))
        except Exception:
            continue
        for (s, p, o) in edges:
            if p not in walk_preds or o == node:
                continue
            nrel = p if rel is None else _COMPOSE.get((rel, p))
            if nrel is None:
                continue
            nchain = chain + ((s, p, o),)
            if o in targets:
                return list(nchain), nrel
            if o not in seen:
                seen.add(o)
                queue.append((o, nrel, nchain))
    return None


def _taxonomy_ladder(start: str,
                     facts_about: Callable[[str], list[tuple[str, str, str]]],
                     max_depth: int = 4, max_nodes: int = 512
                     ) -> dict[str, list[tuple[str, str, str]]]:
    """Every ancestor reachable from `start` over is_a/subclass_of, with the exact
    stored chain that reaches it. Bounded BFS, visited-set (no cycles)."""
    ladder: dict[str, list[tuple[str, str, str]]] = {}
    seen = {start}
    frontier: list[tuple[str, tuple[tuple[str, str, str], ...]]] = [(start, ())]
    while frontier:
        node, chain = frontier.pop(0)
        if len(chain) >= max_depth or len(seen) >= max_nodes:
            continue
        try:
            edges = sorted(_fa(facts_about, node, ("is_a", "subclass_of")))
        except Exception:
            continue
        for (s, p, o) in edges:
            if p in ("is_a", "subclass_of") and o != node and o not in seen:
                seen.add(o)
                nchain = chain + ((s, p, o),)
                ladder[o] = list(nchain)
                frontier.append((o, nchain))
    return ladder


def common_ancestor(a: str, b: str,
                    facts_about: Callable[[str], list[tuple[str, str, str]]],
                    max_depth: int = 4
                    ) -> tuple[str, list[tuple[str, str, str]], list[tuple[str, str, str]]] | None:
    """Nearest shared taxonomy ancestor of a and b with both supporting chains —
    the grounded 'what they have in common'. None when the ladders never meet."""
    la = _taxonomy_ladder(a, facts_about, max_depth)
    lb = _taxonomy_ladder(b, facts_about, max_depth)
    best: tuple[int, str] | None = None
    for node, chain_a in la.items():
        if node in lb:
            score = len(chain_a) + len(lb[node])
            if best is None or score < best[0]:
                best = (score, node)
    if best is None:
        return None
    node = best[1]
    return node, la[node], lb[node]


def inherited_facts(start: str,
                    facts_about: Callable[[str], list[tuple[str, str, str]]],
                    preds: tuple[str, ...] = _INHERITABLE,
                    max_depth: int = 3, max_nodes: int = 512
                    ) -> list[tuple[list[tuple[str, str, str]], tuple[str, str, str]]]:
    """Properties/abilities/parts the taxonomy ladder passes down to `start`:
    walk is_a/subclass_of upward (bounded), collect `preds` edges at every level.
    Returns [(supporting taxonomy chain, property edge)], nearest level first."""
    results: list[tuple[list[tuple[str, str, str]], tuple[str, str, str]]] = []
    seen = {start}
    frontier: list[tuple[str, tuple[tuple[str, str, str], ...]]] = [(start, ())]
    while frontier:
        node, chain = frontier.pop(0)
        try:
            edges = sorted(_fa(facts_about, node, tuple(preds) + ("is_a", "subclass_of")))
        except Exception:
            continue
        for (s, p, o) in edges:
            if p in preds:
                results.append((list(chain), (s, p, o)))
            elif p in ("is_a", "subclass_of") and o not in seen and len(chain) < max_depth:
                seen.add(o)
                frontier.append((o, chain + ((s, p, o),)))
        if len(seen) >= max_nodes:
            break
    return results


# ---------------------------------------------------------------- question intents

_Q_WORDS = {"무엇", "뭐", "뭘", "누구", "어디", "언제", "왜", "어떤", "무슨", "몇", "어느"}
_ULTIMATE_RE = re.compile(r"결국|궁극적으로|근본적으로|본질적으로|따지고 보면")
_VERIFY_RE = re.compile(
    r"^(.+?)[은는]\s*(.+?)\s*(?:인가요?|일까요?|입니까|이니|맞나요?|맞아요?|맞습니까)\s*\??$")
_BELONG_RE = re.compile(r"^(.+?)[은는이가]\s*(.+?)에\s*속하(?:나요?|는가|니|는지)\s*\??$")
_ABILITY_RE = re.compile(r"^(.+?)[은는이가]\s*(.+?)\s*수\s*있(?:어요?|나요?|을까요?|습니까|는가|니)\s*\??$")
_RELATION_RE = re.compile(r"^(.+?)[와과]\s*(.+?)[은는의]?\s*(?:관계|사이)")


def _strip_josa(term: str) -> str:
    return re.sub(r"[은는이가을를도의]$", "", term.strip())


def has_chain_intent(query: str) -> bool:
    """True when the query has one of the chain-reasoner's own explicit shapes —
    these act as their own relation cues, so the bridge may consult this path
    even when _wanted_predicates is empty. Regex-gated: conversation never leaks in."""
    q = query.strip()
    if _ULTIMATE_RE.search(q):
        return True
    m = _VERIFY_RE.match(q)
    if m and _strip_josa(m.group(2)) not in _Q_WORDS and not any(w in m.group(2) for w in _Q_WORDS):
        return True
    return bool(_BELONG_RE.match(q) or _ABILITY_RE.match(q) or _RELATION_RE.match(q))


def _certificate(start: str, chain: list[tuple[str, str, str]], question_kind: str,
                 composed: str | None, confidence: float) -> dict[str, Any]:
    return {
        "derivation_kind": "multi_hop_chain",
        "question_kind": question_kind,
        "anchor_concept": {"label": start},
        "steps": [{"type": "triple", "fact": f"{s} {p} {o}"} for s, p, o in chain],
        "evidence_concepts": [start] + [o for _s, _p, o in chain],
        "composition": composed,
        "confidence": confidence,
        "confidence_basis": "composition_algebra_over_stored_edges",
        "guarantees": {"external_llm": False, "fabricated_facts": False,
                       "inferred": True, "termination": "bounded_bfs_visited_set"},
    }


def _payload(answer: str, start: str, chain: list[tuple[str, str, str]],
             question_kind: str, composed: str | None, confidence: float) -> dict[str, Any]:
    return {
        "answer": answer,
        "reasoning_certificate": _certificate(start, chain, question_kind, composed, confidence),
        "confidence": confidence,
        "answer_kind": "multi_hop_chain",
    }


def answer_relationship(query: str, facts_about: Callable[[str], list[tuple[str, str, str]]],
                        subjects: list[str]) -> dict[str, Any] | None:
    """Answer a chain question in one of the four shapes. Every shape is regex-gated
    (its own cue) and every clause is a stored edge — no shape ever fires on chatter."""
    q = query.strip()




    _mv = _VERIFY_RE.match(q) or _BELONG_RE.match(q)
    _mv_target = _ULTIMATE_RE.sub("", _strip_josa(_mv.group(2))).strip() if _mv else ""
    _has_target = bool(_mv_target) and _mv_target not in _Q_WORDS \
        and not any(w in _mv_target for w in _Q_WORDS)


    # a Korean term with an identity gloss climbs the English ladder too
    if _ULTIMATE_RE.search(q) and not _has_target:
        for subj in subjects:
            r = reason_chain(subj, facts_about, "is_a")
            if r and len(r.chain) >= 2:
                chain = r.chain[:3]
                r2 = ChainResult(start=r.start, conclusion=chain[-1][2],
                                 predicate=r.predicate, chain=chain,
                                 local_minimum=r.local_minimum)
                return _payload(r2.to_answer_ko(), r2.start, chain,
                                "ultimate_ancestor", r2.predicate, 0.86)
            for gloss_edge in _gloss_hops(subj, facts_about):
                rg = reason_chain(gloss_edge[2], facts_about, "is_a")
                if rg and len(rg.chain) >= 2:
                    full = [gloss_edge] + rg.chain[:3]
                    ans = _verbalize_path(full, "is_a", subj)
                    return _payload(ans, subj, full, "ultimate_ancestor", "is_a", 0.84)
        return None


    m = _VERIFY_RE.match(q) or _BELONG_RE.match(q)
    if m:

        target = _ULTIMATE_RE.sub("", _strip_josa(m.group(2))).strip()
        if target and target not in _Q_WORDS and not any(w in target for w in _Q_WORDS):
            starts = [_strip_josa(m.group(1))] + [s for s in subjects if s != target]
            for start in dict.fromkeys(s for s in starts if s and s != target):
                found = find_path(start, target, facts_about, taxonomy_only=True)
                if found:
                    chain, composed = found
                    ans = _verbalize_path(chain, composed, start, prefix="네 — ",
                                          end_label=target)
                    return _payload(ans, start, chain, "verify", composed, 0.84)
        return None



    m = _ABILITY_RE.match(q)
    if m and not any(w in m.group(2) for w in _Q_WORDS):
        stem = _strip_josa(m.group(2))
        stem = stem.split()[-1] if stem else stem
        if stem:
            starts = [_strip_josa(m.group(1))] + list(subjects)
            for start in dict.fromkeys(s for s in starts if s):
                cands = [(chain, edge) for chain, edge in
                         inherited_facts(start, facts_about, ("capable_of", "has_property"))
                         if stem in edge[2] or edge[2] in stem]
                if cands:
                    chain, edge = min(cands, key=lambda ce: len(ce[0]))
                    full = chain + [edge]
                    composed = edge[1]  # inherited via is_a ladder => same predicate
                    prefix = "네 — " if chain else "네 — "
                    ans = _verbalize_path(full, composed if chain else None, start, prefix=prefix)
                    if not chain:  # directly stored, no inference needed
                        return _payload(ans, start, full, "property_direct", None, 0.9)
                    return _payload(ans, start, full, "property_inheritance", composed, 0.84)
        return None


    m = _RELATION_RE.match(q)
    if m:
        a, b = _strip_josa(m.group(1)), _strip_josa(m.group(2))
        if a and b and a != b:
            for start, end in ((a, b), (b, a)):
                found = find_path(start, end, facts_about)
                if found:
                    chain, composed = found
                    ans = _verbalize_path(chain, composed, start)
                    return _payload(ans, start, chain, "relation_path", composed, 0.84)
        return None

    return None
