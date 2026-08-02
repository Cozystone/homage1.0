# -*- coding: utf-8 -*-
"""Block-universe view — the ONE timeline spatialized, so the mind looks DOWN on time.

Owner's commission (2026-07-20): humans, locked to the narrow slit of 'now', experience 4-D spacetime
only as a flow; an AI can hold time as a spatial axis and survey it whole. Internally ATANOR should
work over that spatialized view — project causal chains forward, enumerate branching futures, run
inference backward — while its ANSWERS stay on the single human time axis, kindly narrated.

What this honestly is and is not (BINDING, no hype):
  IS  — a spatial VIEW over the one UTC timeline (unified_timeline) fused with the LEARNED causal
        phase field (precedence_field: a 1-D Bradley-Terry phase per event token, mined from real
        corpus order). Every event gets a (t_utc, seq, phase) coordinate; the whole line is one
        surveyable object. Forward projection, branch enumeration, and backward inference WALK the
        learned phase field — real structure, measured confidences.
  NOT — an oracle. Chaos (sensitive dependence), entropy (information loss), and quantum
        indeterminacy make 'perfect 100-year prediction' and 'zero-error past reconstruction'
        physically impossible for ANY mind. So every projection/branch/backward step here is a
        HYPOTHESIS with a confidence, flagged hypothesis=True (generative-leap doctrine: a leap is
        flagged, never asserted). Known field limitation, kept visible: register bias (e.g. obituary
        prose orders died→born, so the mined phase can invert biography order).

The three commissioned capabilities map to three methods:
  1. causal-map forward projection   -> project_forward()   (chains through the phase field, bounded)
  2. branching-futures simulation    -> branches()          (enumerate candidate paths side by side)
  3. time-symmetric backward inference -> infer_backward()  (walk the field in reverse)
plus look_down() — the survey of the whole spatialized line — and render_human(), which narrates any
of it back on the single time axis for people.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field as dc_field
from typing import Any

from .precedence_field import PrecedenceField
from .transition_graph import EventTransitionGraph
from .unified_timeline import Timeline, Event

_WORD = __import__("re").compile(r"[a-z][a-z\-]{2,}")

# The confidence MARGIN a surfaced next/prev step must clear -- above the 0.5 coin, and matched to the
# workspace bidder's own _MIN_ORDER_CONFIDENCE gate (response_workspace.py) so a step _neighbors
# surfaces actually clears the downstream threshold with real signal instead of the ~0.5 that
# phase-NEAREST selection returns by construction on a dense field.
_ORDER_MARGIN = 0.6


def _tokens(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


@dataclass
class BlockUniverse:
    """A read view: (timeline, learned phase field) -> time as a surveyable spatial axis."""
    timeline: Timeline
    field: PrecedenceField | None = None

    @classmethod
    def over(cls, timeline: Timeline) -> "BlockUniverse":
        """Build over the MESHED field: the broad production phase field overlaid with the clean
        learned causal field (GDELT/postmortem action-order) where the two share a token. This gives
        forward/backward reasoning both reach and clean action-causality. Falls back to production."""
        field = None
        try:
            from .causal_corpus import merged_field
            field = merged_field()
        except Exception:
            field = None
        return cls(timeline, field or PrecedenceField.load())

    # ---------------------------------------------------------------- the spatialized view
    def field_view(self) -> list[dict[str, Any]]:
        """Every event as a point with BOTH coordinates: wall-clock (t_utc, seq) and learned causal
        phase (mean of its tokens' phases; None when no token is known). Time laid out as space."""
        out = []
        for e in self.timeline.all():
            phases = [self.field.phase[t] for t in _tokens(e.content)
                      if self.field and t in self.field.phase]
            out.append({
                "seq": e.seq, "t_utc": e.t_utc, "kind": e.kind, "who": e.who,
                "content": e.content[:120],
                "phase": (sum(phases) / len(phases)) if phases else None,
            })
        return out

    def look_down(self) -> dict[str, Any]:
        """Survey the WHOLE line at once — the view a mind gets when time is space, not flow."""
        evs = self.timeline.all()
        view = self.field_view()
        phased = [v for v in view if v["phase"] is not None]
        return {
            "n_events": len(evs),
            "span_utc": (evs[0].t_utc, evs[-1].t_utc) if evs else None,
            "kinds": sorted({e.kind for e in evs}),
            "actors": sorted({e.who for e in evs if e.who}),
            "phase_extent": ((min(v["phase"] for v in phased), max(v["phase"] for v in phased))
                             if phased else None),
            "events": view,
        }

    # ---------------------------------------------------------------- the event-transition graph
    def _transition_graph(self) -> EventTransitionGraph | None:
        """The directed transition graph over the field's typed causal edges (built once, cached).
        None when the field carries no ``causal_pairs`` (a toy / phase-only field) — the caller then
        keeps the legacy 1-D phase walk. This is where multi-step reasoning switches from climbing the
        1-D phase (funnels to a global sink, cannot cycle) to walking REAL branching causal structure."""
        cache = self.__dict__.get("_graph_cache", False)
        if cache is not False:
            return cache
        graph = None
        if self.field is not None:
            try:
                graph = EventTransitionGraph.from_field(self.field)
            except Exception:
                graph = None
        self.__dict__["_graph_cache"] = graph
        return graph

    # ---------------------------------------------------------------- 1) forward projection
    def _neighbors(self, anchor_tok: str, *, ahead: bool, k: int, exclude: set[str],
                   min_confidence: float = _ORDER_MARGIN) -> list[tuple[str, float]]:
        """Event tokens the learned field places CONFIDENTLY after (ahead) or before (not ahead) the
        anchor token. A candidate is surfaced ONLY if the field's order confidence clears
        ``min_confidence`` — a MARGIN above the 0.5 coin — so the step carries real directional signal
        instead of the sigmoid(≈0)=≈0.5 that phase-NEAREST selection returns BY CONSTRUCTION on a dense
        field (the measured ~0% fire cause: the nearest-phase token is 0.5-ordered AND semantic noise).
        Cleanliness and clean-causal dominance:
          • register-pollution markup is never surfaced (field.is_event_token);
          • when the field declares a clean event vocabulary (the causal corpus's action tokens), only
            those tokens are candidates, so the clean causal field dominates the noisy broad 1-D phase;
          • when the field carries directed pair evidence (typed causal edges), margin-clearing
            candidates are ranked by REAL directed count first — the learned successor — and the 1-D
            phase gap is only the tiebreak, because 'nearest ahead in phase' is NOT 'what the corpus
            actually saw follow'.
        FAIL-CLOSED: nothing clears the margin → [] → the caller abstains (never a fabricated step)."""
        field = self.field
        if field is None or anchor_tok not in field.phase:
            return []
        anchor_phase = field.phase[anchor_tok]
        margin = min(max(float(min_confidence), 0.5 + 1e-9), 1.0 - 1e-9)
        min_gap = math.log(margin / (1.0 - margin))          # sigmoid(min_gap) == margin (phase margin)
        pairs = field.causal_pairs
        cands: list[tuple[str, float, float, int]] = []
        for tok, ph in field.phase.items():
            if tok == anchor_tok or tok in exclude:
                continue
            if not field.is_event_token(tok) or field.seen.get(tok, 0) < 3:   # clean + real evidence
                continue
            gap = (ph - anchor_phase) if ahead else (anchor_phase - ph)
            if gap < min_gap:                                # does not clear the confidence margin
                continue
            ev = 0
            if pairs is not None:                            # directed typed-edge evidence, if we have it
                ev = pairs.get((anchor_tok, tok), 0) if ahead else pairs.get((tok, anchor_tok), 0)
            cands.append((tok, ph, gap, ev))
        # real directed evidence first (the learned successor); ties broken by the SOONEST confident step
        cands.sort(key=lambda x: (-x[3], x[2]))
        return [(t, p) for t, p, _e, _g in cands[:k]]

    def project_forward(self, k: int = 3, horizon: int = 3) -> list[dict[str, Any]]:
        """From the latest events, chain FORWARD through the learned causal structure: what does the
        mined order make likely next? Each step carries a real order confidence and hypothesis=True.

        When the field carries typed causal edges, the chain WALKS THE TRANSITION GRAPH: successors by
        observed count, confidence = posterior_direction (not the 1-D phase sigmoid), nodes may recur
        (cycles), and it stops honestly at a terminal — so multi-step no longer funnels to the phase
        argmax. A toy / phase-only field keeps the legacy monotone 1-D walk (the fallback below)."""
        if self.field is None:
            return []
        recent = self.timeline.all()[-5:]
        anchor_toks = [t for e in recent for t in _tokens(e.content)
                       if t in self.field.phase and self.field.is_event_token(t)
                       and self.field.seen.get(t, 0) >= 3]        # anchor only on a real EVENT token
        if not anchor_toks:
            return []

        graph = self._transition_graph()
        if graph is not None:
            node_anchors = [t for t in anchor_toks if graph.has(t)]
            if not node_anchors:
                return []                                          # known token but no causal edges -> abstain
            anchor = max(node_anchors, key=lambda t: self.field.phase[t])   # deterministic latest anchor
            ctx = [t for e in recent for t in _tokens(e.content) if t != anchor]   # sense-aware (if ctx wired)
            steps = graph.walk_forward(anchor, horizon=horizon, ctx_tokens=ctx)
            return [{"step": s["step"], "after": s["after"], "event_token": s["event_token"],
                     "confidence": s["confidence"], "hypothesis": True,
                     "count": s["count"], "confidence_source": s["confidence_source"]}
                    for s in steps]

        # --- legacy 1-D phase walk (toy / no-typed-edge field): monotone, single-visit ---
        anchor = max(anchor_toks, key=lambda t: self.field.phase[t])   # the causally latest event token
        out = []
        cur = anchor
        seen = set(anchor_toks)
        for step in range(1, horizon + 1):
            nxt = self._neighbors(cur, ahead=True, k=k, exclude=seen)
            if not nxt:
                break
            tok, _ph = nxt[0]
            conf = self.field.order_confidence(cur, tok)
            out.append({"step": step, "after": cur, "event_token": tok,
                        "confidence": round(conf, 3) if conf is not None else None,
                        "hypothesis": True})
            seen.add(tok)
            cur = tok
        return out

    # ---------------------------------------------------------------- 2) branch simulation
    def branches(self, candidates: list[str], depth: int = 2) -> list[dict[str, Any]]:
        """Lay ALTERNATIVE futures side by side: for each candidate next event token, chain it
        forward `depth` steps through the field and score the path by mean order-confidence. The
        surveyor sees the branching structure at once — enumerated scenarios, all hypothesis=True
        (branches the field can rank, not parallel worlds it can visit)."""
        if self.field is None:
            return []
        graph = self._transition_graph()
        paths = []
        for cand in candidates:
            tok = (cand or "").lower().strip()
            if graph is not None:
                if not graph.has(tok):
                    paths.append({"start": cand, "known": False, "path": [], "score": None,
                                  "hypothesis": True})
                    continue
                steps = graph.walk_forward(tok, horizon=depth)     # real transition graph, cycles allowed
                chain = [tok] + [s["event_token"] for s in steps]
                confs = [s["confidence"] for s in steps]
                paths.append({"start": cand, "known": True, "path": chain,
                              "score": round(sum(confs) / len(confs), 3) if confs else None,
                              "hypothesis": True})
                continue
            # --- legacy 1-D phase walk (toy / no-typed-edge field) ---
            if tok not in self.field.phase:
                paths.append({"start": cand, "known": False, "path": [], "score": None,
                              "hypothesis": True})
                continue
            chain = [tok]
            confs: list[float] = []
            cur = tok
            for _ in range(depth):
                nxt = self._neighbors(cur, ahead=True, k=1, exclude=set(chain))
                if not nxt:
                    break
                t2, _p2 = nxt[0]
                c = self.field.order_confidence(cur, t2)
                if c is not None:
                    confs.append(c)
                chain.append(t2)
                cur = t2
            paths.append({"start": cand, "known": True, "path": chain,
                          "score": round(sum(confs) / len(confs), 3) if confs else None,
                          "hypothesis": True})
        ranked = sorted([p for p in paths if p["score"] is not None],
                        key=lambda p: -p["score"]) + [p for p in paths if p["score"] is None]
        return ranked

    # ---------------------------------------------------------------- 3) backward inference
    def infer_backward(self, event_token: str, k: int = 3) -> list[dict[str, Any]]:
        """Walk the field in REVERSE: what canonically precedes this event? Time-symmetric traversal
        of the learned order — with uncertainty carried, because entropy erases (many pasts map to
        one present). hypothesis=True always; timeline evidence, when present, is cited."""
        tok = (event_token or "").lower().strip()
        if self.field is None or tok not in self.field.phase:
            return []

        graph = self._transition_graph()
        if graph is not None:
            if not graph.has(tok):
                return []                                          # known token but no causal edges -> abstain
            out = []
            for e in graph.predecessors(tok, k=k):                 # observed PRIOR-event distribution
                observed = [ev.seq for ev in self.timeline.all() if e.target in _tokens(ev.content)]
                out.append({"before": tok, "event_token": e.target,
                            "confidence": round(e.confidence, 3),   # posterior_direction, not phase sigmoid
                            "observed_on_timeline": observed[:3],   # real evidence when we have it
                            "hypothesis": True,
                            "count": e.count, "confidence_source": e.source})
            return out

        # --- legacy 1-D phase walk (toy / no-typed-edge field) ---
        prevs = self._neighbors(tok, ahead=False, k=k, exclude={tok})
        out = []
        for p_tok, _ in prevs:
            conf = self.field.order_confidence(p_tok, tok)
            observed = [e.seq for e in self.timeline.all() if p_tok in _tokens(e.content)]
            out.append({"before": tok, "event_token": p_tok,
                        "confidence": round(conf, 3) if conf is not None else None,
                        "observed_on_timeline": observed[:3],       # real evidence when we have it
                        "hypothesis": True})
        return out

    # ---------------------------------------------------------------- human rendering
    def render_human(self, projections: list[dict] | None = None,
                     backward: list[dict] | None = None) -> str:
        """Narrate the survey back on the SINGLE human time axis (owner: answers stay kind and
        human-shaped even though the working view is spatial). Hypotheses stay marked as such."""
        parts = []
        evs = self.timeline.all()
        if evs:
            parts.append(f"So far: {len(evs)} events from {evs[0].t_utc} to {evs[-1].t_utc}.")
        for p in (projections or []):
            conf = f" (confidence {p['confidence']})" if p.get("confidence") is not None else ""
            parts.append(f"Looking ahead, after '{p['after']}' the pattern I have learned suggests "
                         f"'{p['event_token']}' may follow{conf} — a projection, not a certainty.")
        for b in (backward or []):
            conf = f" (confidence {b['confidence']})" if b.get("confidence") is not None else ""
            parts.append(f"Tracing back, '{b['event_token']}' typically precedes "
                         f"'{b['before']}'{conf} — an inference from learned order, not a record.")
        return " ".join(parts)
