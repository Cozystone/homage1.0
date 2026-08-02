# -*- coding: utf-8 -*-
"""Event-transition graph — a directed Markov transition graph over the typed causal-action vocabulary.

Why this exists (the measured wall, 2026-07-23). The block-universe reasoner used to walk a single
1-D LEARNED phase coordinate (precedence_field: a Bradley-Terry phase per event token). The temporal
bidder started firing at ~75% on step-1 causal queries once the mined DIRECTED pair counts (typed
causal edges) re-ranked the step-1 successor — but ONLY step-1, because the multi-step walk still had
to climb the 1-D phase monotonically. A 1-D coordinate is structurally too weak for multi-step causal
reasoning:

  1. GLOBAL SINK. A 1-D coordinate has a single maximum. A monotone forward walk therefore FUNNELS
     every chain to the same phase-argmax token (measured on the real 19-token GDELT field: consult,
     appeal, aid, assault, diplomacy, cooperate all drift to `...statement -> yield`). `yield` is not
     the universal end of causation — it is merely argmax(phase).
  2. NO CYCLES. A monotone coordinate can never revisit a node, so a real diplomatic loop the data
     contains (appeal->consult, conflict->consult, consult->diplomacy, diplomacy->consult) is
     unrepresentable: once the walk leaves `consult` it can never return.
  3. DIRECTION-BLIND to real successors that sit EARLIER on the line. Any observed successor whose
     phase is lower than the anchor's (exactly the return/de-escalation edges) is invisible to an
     ahead-only phase walk — the walk can only ever express "later in canonical phase", not "what the
     corpus actually saw follow".

The fix is to walk the typed causal edges DIRECTLY as a transition graph:

  * successor(e)   = the observed-count distribution over next events (ranked by observed count),
                     read straight off the mined directed pair counts (causal_corpus._causal_pairs);
  * confidence(e->f) = precedence_field.posterior_direction(n_ef, n_fe): the Beta(1,1)-posterior mean
                     that e precedes f from the directed observations — NOT the 1-D phase sigmoid. So a
                     frequent-but-ambiguous edge (large reverse count) is correctly deflated, and a
                     rare-but-clean edge is trusted;
  * sense-aware order (where available): when a context-conditioned count store (EvidenceStore.ctx,
                     keyed (context_word, a, b)) has evidence for the edge under a query context word,
                     the context posterior OVERRIDES the global one (so a query-specific sense orders
                     the edge, not the corpus average). Wired and tested; in this corpus the clean
                     CAMEO x CAMEO ctx evidence is thin (see the honest ceiling note below), so it
                     rarely fires — hence it is an optional injected refinement, never a hot-path load.

The 1-D phase is DEMOTED to a count-tie tiebreak only (the "soonest confident step" among successors
the data saw equally often), never the driver of the walk.

Walks may REVISIT nodes — cycles are first-class — and TERMINATE HONESTLY (fail-closed) when a node
has no successor whose confidence clears the margin. Nothing here is authored: every edge, count and
order comes from the mined `causal_pairs` (and optional ctx) data. Every surfaced step stays a
HYPOTHESIS (the block-universe consumer stamps hypothesis=True and hedges in its own narrator voice).

HONEST UTILITY CEILING. The typed causal-action vocabulary is only ~19 GDELT/CAMEO root-action tokens
(statement, appeal, consult, diplomacy, cooperate, aid, yield, demand, disapprove, reject, threaten,
protest, assault, fight, force, coerce, conflict, intent, investigate). So this makes multi-step
causal projection genuinely walk real branching structure — but over a NARROW vocabulary. Broader
coverage is a data problem, not a representation problem: it needs a much larger mined typed-causal-
edge corpus (many more action/event types with directed counts). The graph machinery scales to any
vocabulary the moment the edges exist; today the edges cover ~19 tokens.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Iterable

from .precedence_field import MARKUP_STOP, posterior_direction

# A surfaced step must clear this posterior-direction confidence, matched to the block-universe
# _ORDER_MARGIN / workspace bidder _MIN_ORDER_CONFIDENCE gate so a step the graph surfaces actually
# clears the downstream threshold with real directional signal (fail-closed below it).
DEFAULT_MARGIN = 0.6


@dataclass
class Edge:
    """One directed transition a -> b with its evidence."""
    target: str
    count: int                 # observed directed count (typed causal edge)
    confidence: float          # posterior_direction(n_ab, n_ba) — global (or ctx-conditioned) posterior
    source: str = "global"     # "global" | "ctx" — which posterior produced `confidence`
    phase_gap: float = 0.0     # DEMOTED prior: signed phase distance target-anchor (tiebreak only)


class EventTransitionGraph:
    """A directed transition graph over the typed causal-action vocabulary.

    Built from the mined DIRECTED pair counts (typed causal edges). ``successor(e)`` yields the
    observed-count distribution over next events, each carrying its ``posterior_direction`` confidence;
    ``predecessor(e)`` yields the reverse. Walks follow the real high-count path, may revisit nodes
    (cycles are first-class), and abstain (fail-closed) when nothing clears the confidence margin.
    """

    def __init__(self, pairs: dict[tuple[str, str], int], *,
                 phase: dict[str, float] | None = None,
                 event_vocab: set[str] | None = None,
                 ctx: dict[tuple[str, str, str], int] | None = None,
                 min_count: int = 1) -> None:
        self.pairs: dict[tuple[str, str], int] = {k: v for k, v in (pairs or {}).items()
                                                  if v >= min_count and k[0] != k[1]}
        self.phase: dict[str, float] = dict(phase or {})
        # When set, the ONLY tokens the graph will surface as events (the clean causal vocabulary);
        # markup is filtered unconditionally. None -> any non-markup token that carries edges.
        self.event_vocab: set[str] | None = set(event_vocab) if event_vocab else None
        # Optional context-conditioned counts (context_word, a, b) -> n, for sense-aware order.
        self.ctx: dict[tuple[str, str, str], int] = dict(ctx or {})
        # adjacency: out[a][b] = count(a->b); inr[b][a] = count(a->b)
        self._out: dict[str, dict[str, int]] = {}
        self._in: dict[str, dict[str, int]] = {}
        self.nodes: set[str] = set()
        for (a, b), c in self.pairs.items():
            self._out.setdefault(a, {})[b] = c
            self._in.setdefault(b, {})[a] = c
            self.nodes.add(a)
            self.nodes.add(b)

    # ------------------------------------------------------------------ construction helpers
    @classmethod
    def from_field(cls, field: Any, *, ctx: dict | None = None,
                   min_count: int = 1) -> "EventTransitionGraph | None":
        """Build from a PrecedenceField that carries typed causal edges (``causal_pairs``). Returns
        None when the field has no directed pair evidence — the caller then keeps the phase path."""
        pairs = getattr(field, "causal_pairs", None)
        if not pairs:
            return None
        return cls(dict(pairs), phase=getattr(field, "phase", None),
                   event_vocab=getattr(field, "event_vocab", None), ctx=ctx, min_count=min_count)

    def has(self, tok: str) -> bool:
        return tok in self.nodes

    def _eligible(self, tok: str) -> bool:
        """A surfaceable event token: never register-pollution markup, and — when a clean event
        vocabulary is declared — a member of it (clean-causal dominance; single source of truth)."""
        if tok in MARKUP_STOP:
            return False
        return self.event_vocab is None or tok in self.event_vocab

    # ------------------------------------------------------------------ confidence
    def _confidence(self, a: str, b: str, ctx_tokens: Iterable[str] | None) -> tuple[float, str]:
        """posterior_direction that `a` precedes `b`. Sense-aware WHERE AVAILABLE: if the ctx store has
        directed evidence for (a,b) under a shared query-context word, that context posterior OVERRIDES
        the global one; otherwise the global directed posterior. Returns (confidence, source)."""
        if self.ctx and ctx_tokens:
            cn_ab = 0
            cn_ba = 0
            for c in ctx_tokens:
                cl = (c or "").lower()
                if not cl:
                    continue
                cn_ab += self.ctx.get((cl, a, b), 0)
                cn_ba += self.ctx.get((cl, b, a), 0)
            if cn_ab + cn_ba > 0:                       # sense-aware evidence exists for THIS query
                return posterior_direction(cn_ab, cn_ba), "ctx"
        n_ab = self.pairs.get((a, b), 0)
        n_ba = self.pairs.get((b, a), 0)
        return posterior_direction(n_ab, n_ba), "global"

    # ------------------------------------------------------------------ successor / predecessor
    def _rank(self, anchor: str, neighbours: dict[str, int], *, forward: bool,
              ctx_tokens: Iterable[str] | None, margin: float, k: int) -> list[Edge]:
        """The observed-count distribution over next (forward) or prior (backward) events, gated by
        confidence and RANKED BY OBSERVED COUNT. Ties are broken by the DEMOTED phase prior (the
        soonest confident step) then by confidence, so the ordering is deterministic. Fail-closed:
        an edge whose directional posterior does not clear the margin is dropped."""
        anchor_phase = self.phase.get(anchor)
        edges: list[Edge] = []
        for other, count in neighbours.items():
            if other == anchor or not self._eligible(other):
                continue
            a, b = (anchor, other) if forward else (other, anchor)
            conf, src = self._confidence(a, b, ctx_tokens)
            if conf < margin:                            # directional signal too weak -> abstain on it
                continue
            oph = self.phase.get(other)
            gap = 0.0
            if anchor_phase is not None and oph is not None:
                gap = (oph - anchor_phase) if forward else (anchor_phase - oph)
            edges.append(Edge(target=other, count=int(count), confidence=conf, source=src,
                              phase_gap=gap))
        # observed count first (the empirical successor distribution); the phase prior is a DEMOTED
        # tiebreak (soonest confident step, i.e. smallest positive gap) among equally-observed edges,
        # then confidence, then token for total determinism.
        edges.sort(key=lambda e: (-e.count, e.phase_gap, -e.confidence, e.target))
        return edges[:k] if k else edges

    def successors(self, e: str, *, ctx_tokens: Iterable[str] | None = None,
                   margin: float = DEFAULT_MARGIN, k: int = 0) -> list[Edge]:
        """The observed next-event distribution for `e`, count-ranked, each edge tagged with its
        posterior-direction confidence. [] when `e` is unknown or has no confident successor."""
        return self._rank(e, self._out.get(e, {}), forward=True,
                          ctx_tokens=ctx_tokens, margin=margin, k=k)

    def predecessors(self, e: str, *, ctx_tokens: Iterable[str] | None = None,
                     margin: float = DEFAULT_MARGIN, k: int = 0) -> list[Edge]:
        """The observed prior-event distribution for `e` (time-symmetric reverse walk)."""
        return self._rank(e, self._in.get(e, {}), forward=False,
                          ctx_tokens=ctx_tokens, margin=margin, k=k)

    # ------------------------------------------------------------------ multi-step walks
    def walk_forward(self, start: str, *, horizon: int = 3, ctx_tokens: Iterable[str] | None = None,
                     margin: float = DEFAULT_MARGIN) -> list[dict[str, Any]]:
        """Greedy multi-step forward projection over the REAL transition graph. At each step take the
        top-count confident successor; REVISIT is allowed (cycles are first-class), the walk is bounded
        by `horizon`, and it STOPS honestly the moment no successor clears the margin (fail-closed —
        never a fabricated step). Contrast with the old monotone phase walk, which could only climb to
        the global phase-argmax and could never revisit a node."""
        if not self.has(start):
            return []
        out: list[dict[str, Any]] = []
        cur = start
        for step in range(1, horizon + 1):
            nxt = self.successors(cur, ctx_tokens=ctx_tokens, margin=margin, k=1)
            if not nxt:
                break                                    # terminal / nothing confident -> honest stop
            e = nxt[0]
            out.append({"step": step, "after": cur, "event_token": e.target,
                        "count": e.count, "confidence": round(e.confidence, 3),
                        "confidence_source": e.source, "hypothesis": True})
            cur = e.target                               # revisit permitted: cur may equal an earlier node
        return out

    def walk_backward(self, start: str, *, horizon: int = 3, ctx_tokens: Iterable[str] | None = None,
                      margin: float = DEFAULT_MARGIN) -> list[dict[str, Any]]:
        """Greedy multi-step backward inference (time-symmetric): the top-count confident predecessor
        at each step. Revisit allowed, horizon-bounded, fail-closed like walk_forward."""
        if not self.has(start):
            return []
        out: list[dict[str, Any]] = []
        cur = start
        for step in range(1, horizon + 1):
            prv = self.predecessors(cur, ctx_tokens=ctx_tokens, margin=margin, k=1)
            if not prv:
                break
            e = prv[0]
            out.append({"step": step, "before": cur, "event_token": e.target,
                        "count": e.count, "confidence": round(e.confidence, 3),
                        "confidence_source": e.source, "hypothesis": True})
            cur = e.target
        return out

    def branches(self, start: str, *, depth: int = 2, k: int = 3,
                 ctx_tokens: Iterable[str] | None = None,
                 margin: float = DEFAULT_MARGIN) -> list[dict[str, Any]]:
        """Lay alternative futures side by side: the top-`k` confident successors of `start` as
        distinct first steps, each chained forward `depth` steps through the graph. Ranked by mean
        edge confidence. All hypothesis=True (branches the graph can rank, not worlds it visits)."""
        if not self.has(start):
            return []
        firsts = self.successors(start, ctx_tokens=ctx_tokens, margin=margin, k=k)
        paths: list[dict[str, Any]] = []
        for first in firsts:
            chain = [start, first.target]
            confs = [first.confidence]
            cur = first.target
            for _ in range(depth - 1):
                nxt = self.successors(cur, ctx_tokens=ctx_tokens, margin=margin, k=1)
                if not nxt:
                    break
                confs.append(nxt[0].confidence)
                chain.append(nxt[0].target)
                cur = nxt[0].target
            paths.append({"start": start, "first": first.target, "known": True, "path": chain,
                          "score": round(sum(confs) / len(confs), 3) if confs else None,
                          "hypothesis": True})
        paths.sort(key=lambda p: -(p["score"] or 0.0))
        return paths


def cameo_ctx_slice(ctx: dict[tuple[str, str, str], int],
                    vocab: set[str]) -> dict[tuple[str, str, str], int]:
    """Extract from a full EvidenceStore.ctx store ONLY the entries whose ordered pair is entirely
    inside the causal vocabulary (context_word, a, b) with a,b both action tokens — the sense-aware
    slice the transition graph can actually use. Reuses mined data; authors nothing. In this corpus
    the slice is thin (the honest ceiling)."""
    return {k: v for k, v in (ctx or {}).items()
            if len(k) == 3 and k[1] in vocab and k[2] in vocab}
