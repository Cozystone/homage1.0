# -*- coding: utf-8 -*-
"""ladder — the discrete effort rungs (Milli/Lieder/Griffiths 2017: a small discrete ladder is
bounded-optimal; a few rungs, not a continuum). Each rung wraps a REAL engine and returns a uniform
``RungResult`` with (answer, confidence, cost, verifier_score). Nothing here fabricates an answer:
abstain is the floor.

  R0  CHEAP    packages.graph_scale.spreading_activation.spread — a shallow spread that reads the
               focus (intent) edge; the fast lookup + a felt confidence. This is System-1.
  R1  MID      packages.deliberator.controller.deliberate — the System-2 propose/verify/compose chain
               (capped: the declared plan, MEC re-steer on so a doomed chain abstains cheaply). When a
               query is a bare lookup with no plan, R1 is a DEEPER spread instead.
  R2  DEEP     the deepest budget: the deliberator's deep plan (adds a web/search hop) OR, for a bare
               lookup, a DEEP spread over local+web knowledge that INTEGRATES the whole lit subgraph
               and answers with its global argmax — holistic, and (honestly) the most exposed to a
               web distractor. This is where "more thinking can hurt" (Inverse Scaling, TMLR 2025) is
               a real, measured behaviour of the engine, not a stipulation.
  ABSTAIN      terminal floor — "I won't guess." Never fabricates.

COST is real work in a common op-unit derived from the codebase's OWN cost model:
  * a spread node-expansion (one facts_about call) = 1 op;
  * a deliberator step = COST_RANK[organ] ops (arithmetic 1 .. predicate 5), summed over executed steps.
Both count primitive reasoning operations, so a deep spread that lights 120 nodes and a predicate-
synthesis chain are on one honest scale. R2 costs more because it genuinely does more graph/organ work.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from packages.graph_scale.spreading_activation import spread, ActivatedSubgraph
from packages.deliberator.controller import deliberate
from packages.deliberator.steps import COST_RANK

from .signals import felt_confidence, x1_voc, edge_tree, known_blocks


# ── the uniform rung result ──────────────────────────────────────────────────────────────────────

@dataclass
class RungResult:
    rung: str                       # 'R0' | 'R1' | 'R2' | 'ABSTAIN'
    answer: str | None
    confidence: float               # felt confidence / grounding strength in [0, 1]
    cost: float                     # real work in op-units
    grounded: bool                  # did a real edge / verified chain produce the answer?
    abstained: bool
    verifier_score: float           # grounding quality in [0, 1] — the verifier-gated-stop signal
    candidates: list = field(default_factory=list)     # (label, activation) for the felt features
    top_activation: float = 0.0
    voc_blocks: list = field(default_factory=list)      # library for the X1 proxy
    answer_tree: tuple | None = None                    # answer encoded for the X1 proxy
    detail: dict = field(default_factory=dict)


# ── spread work counter (real op accounting) ─────────────────────────────────────────────────────

def spread_work_counter(facts_about: Callable[[str], list]):
    """Wrap a facts_about so every node-expansion (one lookup) is counted — the honest R0/R2 op cost."""
    box = {"n": 0}

    def wrapped(term: str):
        box["n"] += 1
        return facts_about(term)

    return wrapped, box


def _facts_fn(graph: dict[str, list]) -> Callable[[str], list]:
    g = {str(k).strip().lower(): v for k, v in (graph or {}).items()}
    return lambda term: g.get(str(term).strip().lower(), [])


def _merge(*graphs: dict[str, list]) -> dict[str, list]:
    out: dict[str, list] = {}
    for g in graphs:
        for k, v in (g or {}).items():
            out.setdefault(str(k).strip().lower(), []).extend(v)
    return out


# ── answer extraction from a lit subgraph ────────────────────────────────────────────────────────

def _intent_edge_answer(sg: ActivatedSubgraph, intent: tuple) -> tuple[str | None, float, bool]:
    """R0's LITERAL read: the object of the anchor's edge whose predicate is the asked (intent)
    relation, if present — a grounded direct answer. Falls back to the strongest neighbour concept as
    a GUESS (grounded=False) when the focus edge is absent."""
    for (s, p, o) in sg.anchor_facts():
        if p in intent:
            return o, sg.activation.get(o, 0.0), True
    tops = sg.top_concepts(1)
    if tops:
        return tops[0][0], tops[0][1], False
    return None, 0.0, False


def _global_argmax_answer(sg: ActivatedSubgraph, intent: tuple) -> tuple[str | None, float, bool]:
    """R2's HOLISTIC read: integrate the whole lit subgraph and answer with the single strongest
    concept overall (excluding the anchor). This is 'more thinking' — and, honestly, the read most
    exposed to a densely-connected web distractor. Grounded iff that concept is also the object of a
    real intent edge somewhere in the trace."""
    tops = sg.top_concepts(1)
    if not tops:
        return _intent_edge_answer(sg, intent)
    best, act = tops[0]
    grounded = any(p in intent and o == best for (s, p, o, _d) in sg.edges)
    return best, act, grounded


def _rivals(sg: ActivatedSubgraph, winner: str | None, k: int = 6) -> list[tuple[str, float]]:
    """The concepts that could threaten the winner: the strongest lit neighbours (excluding the
    winner and anchor), each with its accumulated activation. felt_confidence keeps only those that
    reach a real fraction of the winner — a distractor out-lighting the answer, or a competing answer."""
    return [(c, a) for c, a in sg.top_concepts(k) if c != winner]


# ── R0 — cheap spread + felt confidence ──────────────────────────────────────────────────────────

# shallow spread: a high floor and a small fan so only the strongly-lit, near neighbourhood answers.
_R0_KW = dict(threshold=0.18, max_nodes=24, decay=0.6)
# deeper spread for R1's lookup flavour.
_R1_KW = dict(threshold=0.10, max_nodes=80, decay=0.65)
# deep spread for R2: low floor, wide fan — integrates the whole field (and any web distractor).
_R2_KW = dict(threshold=0.05, max_nodes=200, decay=0.72)


def run_r0(query: Any, *, felt_context: Any = None) -> RungResult:
    """R0: the cheap rung. Shallow spread over LOCAL knowledge, read the focus edge, feel a confidence.
    ``query`` is duck-typed: .anchor, .intent, .facts_local, .text."""
    fn, box = spread_work_counter(_facts_fn(query.facts_local))
    sg = spread(str(query.anchor).strip().lower(), fn, intent_preds=tuple(query.intent), **_R0_KW)
    answer, top_act, grounded = _intent_edge_answer(sg, tuple(query.intent))
    rivals = _rivals(sg, answer)
    feats = felt_confidence(answer, top_act, rivals, grounded=grounded, context=felt_context)

    blocks = known_blocks(_facts_fn(query.facts_local), str(query.anchor).strip().lower())
    atree = edge_tree(query.anchor, query.intent[0] if query.intent else "?", answer) if (answer and grounded) else None

    return RungResult(
        rung="R0", answer=answer, confidence=feats["for_conf"], cost=float(box["n"]),
        grounded=grounded, abstained=(answer is None),
        verifier_score=(top_act if grounded else 0.0),
        candidates=rivals, top_activation=top_act, voc_blocks=blocks, answer_tree=atree,
        detail={"felt": feats, "nodes": box["n"], "read": "intent_edge"})


# ── R1 — deliberator (capped) or deeper spread ───────────────────────────────────────────────────

def _deliberate_cost(res: Any) -> float:
    """Real op cost of a deliberation = sum of COST_RANK over the steps it actually executed."""
    return float(sum(COST_RANK.get(s.organ, 3) for s in res.steps)) or 1.0


def _deliberate_verifier(res: Any) -> float:
    """Grounding quality of a deliberation, in [0,1]: fraction of executed steps grounded (1.0 for a
    fully verified composite, 0 for an all-abstain). The real verifier-gated-stop signal."""
    if not res.steps:
        return 0.0
    return sum(1 for s in res.steps if s.grounded) / len(res.steps)


def run_r1(query: Any, *, felt_context: Any = None) -> RungResult:
    """R1: System-2, capped. The declared deliberation plan through the REAL deliberator (MEC re-steer
    on). For a bare lookup with no plan, a DEEPER spread over local knowledge."""
    delib = getattr(query, "delib", None)
    if delib is not None:
        res = deliberate(delib, resteer=True, mec=False)
        ver = _deliberate_verifier(res)
        ans = res.answer
        atree = edge_tree(query.anchor, "chain", ans) if ans else None
        # a verified composite is SETTLED — register it as its own known block so the X1 VOC proxy
        # reads it as low-progress ("more compute won't change a verified answer"), not max-novelty.
        return RungResult(
            rung="R1", answer=ans, confidence=ver, cost=_deliberate_cost(res),
            grounded=(not res.abstained), abstained=res.abstained, verifier_score=ver,
            candidates=[], top_activation=0.0,
            voc_blocks=([atree] if atree else []), answer_tree=atree,
            detail={"engine": "deliberator", "hops": res.hops, "abstained": res.abstained,
                    "reason": res.reason})

    fn, box = spread_work_counter(_facts_fn(query.facts_local))
    sg = spread(str(query.anchor).strip().lower(), fn, intent_preds=tuple(query.intent), **_R1_KW)
    answer, top_act, grounded = _intent_edge_answer(sg, tuple(query.intent))
    return RungResult(
        rung="R1", answer=answer, confidence=(top_act if grounded else 0.0), cost=float(box["n"]),
        grounded=grounded, abstained=(answer is None), verifier_score=(top_act if grounded else 0.0),
        candidates=_rivals(sg, answer), top_activation=top_act,
        detail={"engine": "spread", "nodes": box["n"], "read": "intent_edge_deep"})


# ── R2 — deepest: deliberator deep + web, or deep integrative spread ──────────────────────────────

def run_r2(query: Any, *, felt_context: Any = None) -> RungResult:
    """R2: the deepest, largest-budget rung. A deep deliberation (adds the web/search hop) when a deep
    plan is declared; otherwise a DEEP spread over LOCAL+WEB knowledge that answers with the global
    argmax — the holistic read most exposed to a web distractor (the honest overthinking channel)."""
    explicit_deep = getattr(query, "delib_deep", None)
    plan_for_r2 = explicit_deep or getattr(query, "delib", None)
    web = getattr(query, "facts_web", None) or {}

    if plan_for_r2 is not None:
        res = deliberate(plan_for_r2, resteer=True, mec=False)
        ver = _deliberate_verifier(res)
        ans = res.answer
        atree = edge_tree(query.anchor, "chain", ans) if ans else None
        web_hop = 3.0 if explicit_deep is not None else 0.0     # the extra web/search hop's cost
        return RungResult(
            rung="R2", answer=ans, confidence=ver, cost=_deliberate_cost(res) + web_hop,
            grounded=(not res.abstained), abstained=res.abstained, verifier_score=ver,
            candidates=[], top_activation=0.0,
            voc_blocks=([atree] if atree else []), answer_tree=atree,
            detail={"engine": ("deliberator_deep" if explicit_deep else "deliberator"),
                    "hops": res.hops, "abstained": res.abstained})

    merged = _merge(query.facts_local, web)
    fn, box = spread_work_counter(_facts_fn(merged))
    sg = spread(str(query.anchor).strip().lower(), fn, intent_preds=tuple(query.intent), **_R2_KW)
    answer, top_act, grounded = _global_argmax_answer(sg, tuple(query.intent))
    return RungResult(
        rung="R2", answer=answer, confidence=(top_act if grounded else 0.0), cost=float(box["n"]),
        grounded=grounded, abstained=(answer is None), verifier_score=(top_act if grounded else 0.0),
        candidates=_rivals(sg, answer), top_activation=top_act,
        detail={"engine": "spread_deep", "nodes": box["n"], "read": "global_argmax",
                "web_terms": len(web)})


# ── ABSTAIN — the terminal floor ─────────────────────────────────────────────────────────────────

ABSTAIN = RungResult(rung="ABSTAIN", answer=None, confidence=0.0, cost=0.0, grounded=False,
                     abstained=True, verifier_score=0.0,
                     detail={"note": "honest abstention — no rung grounded an answer, so none is guessed"})
