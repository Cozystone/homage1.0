# -*- coding: utf-8 -*-
"""Fractal reasoner — a CONTROLLED special move: on a hard, low-confidence query the atom-self
briefly splits into two grounded stances that debate ONLY in SemanticFrame terms, then collapses
back to one honest answer. Scaffold per the owner's 2026-07-10 design (4-stage brake+fuse).

Why this is the No-LLM-SAFE form of "debate / self-consistency":
  * The debate happens over SemanticFrame / grounded-edge objects, NEVER free-text tokens — so no
    hallucination can re-enter through the back door (that is the whole trick).
  * The two stances share ONE read-only graph pointer + the SAME moral-invariant core; only their
    CONSTRAINT differs (A gathers support, B gathers contradiction). Bones identical, lens flipped.
  * It is GATED: it engages only on a complex act at low confidence, runs a bounded number of ticks,
    and then the split state is discarded (collapse) — no persistent sub-selves, no resource drain.
  * If the stances don't converge, the honest output is *uncertainty*, never a forced answer.

HONEST SCOPE (this is a skeleton, labeled as one): its SHARPNESS depends on two things still being
matured — (1) a calibrated ANSWER-confidence metric to trigger it (today we approximate from the
frame + grounding), and (2) richer per-stance evidence gathering. It fabricates nothing and writes
nothing; today it structures pro/con GROUNDED evidence and reports consensus-or-uncertainty. Off by
default (ATANOR_FRACTAL=1 to enable the orchestrator hook).
"""
from __future__ import annotations

import os
from typing import Any

_COMPLEX_ACTS = {"opinion"}                     # conversational complex acts
_COMPLEX_FACT_INTENTS = {"cause", "compare", "strategy", "open_ended"}
_DEFAULT_MAX_TICKS = 3
_CONF_FLOOR = 0.4                               # engage only when confidence dips toward abstention


def should_engage(frame: Any, *, answer_confidence: float) -> bool:
    """Gate 1 — the special move unlocks ONLY when BOTH hold: the query is complex (a strategy /
    cause / compare / open-ended judgement, not a simple fact lookup) AND the first-pass confidence
    is low enough to risk a bad answer or abstention. Otherwise the fast single path answers."""
    if answer_confidence >= _CONF_FLOOR:
        return False
    fi = getattr(frame, "fact_intent", "") or ""
    act = getattr(frame, "act", "") or ""
    return (fi in _COMPLEX_FACT_INTENTS) or (act in _COMPLEX_ACTS)


def _moral_ok() -> bool:
    try:
        from packages.graph_scale.moral_invariants import verify_integrity
        return verify_integrity().get("ok") is True
    except Exception:
        return False


def _gather(store: Any, subject: str, *, limit: int = 40) -> list[tuple[str, str, str]]:
    """Read-only grounded evidence about the subject — the shared graph both stances see."""
    try:
        return list(store.facts_about(subject, limit=limit) or [])
    except Exception:
        return []


def _stance_support(edges, target: str) -> list[tuple[str, str, str]]:
    """Stance A: edges that AFFIRM the hypothesis about `target` (supporting evidence)."""
    return [(s, p, o) for (s, p, o) in edges if target and (target in o or target in s)]


def _stance_contradict(store: Any, edges, subject: str, target: str) -> list[dict[str, Any]]:
    """Stance B: structural CONTRADICTIONS the hypothesis would create (the flipped lens). Uses the
    algebraic contradiction gate — a rejected edge is grounded evidence AGAINST."""
    try:
        from packages.graph_scale.contradiction_gate import check_edges
        rep = check_edges(store, [(subject, target)]) if (subject and target) else {"rejected": []}
        return rep.get("rejected", [])
    except Exception:
        return []


def deliberate(query: str, store: Any, *, frame: Any = None, target: str = "",
               max_ticks: int = _DEFAULT_MAX_TICKS) -> dict[str, Any]:
    """Run the bounded internal debate and collapse to one honest verdict. Read-only; never writes,
    never fabricates. Returns {verdict, support, against, ticks, collapsed, honest_note}."""
    if not _moral_ok():
        return {"verdict": "aborted", "reason": "moral_core_integrity_failed", "collapsed": True}
    subject = (getattr(frame, "subject", "") if frame else "") or ""
    target = target or (getattr(frame, "verify_target", "") if frame else "") or ""
    edges = _gather(store, subject)

    support = against = []
    ticks = 0
    for ticks in range(1, max_ticks + 1):
        support = _stance_support(edges, target)
        against = _stance_contradict(store, edges, subject, target)
        # convergence: one side clearly dominates → stop early (no need to burn ticks)
        if bool(support) != bool(against):
            break

    # Gate 4 — metacognitive synthesis + immediate collapse (state discarded on return).
    if support and not against:
        verdict = "supported"
    elif against and not support:
        verdict = "contradicted"
    elif support and against:
        verdict = "unstable"          # both sides have grounded evidence — honest tension
    else:
        verdict = "insufficient_evidence"
    return {
        "verdict": verdict,
        "subject": subject, "target": target,
        "support_count": len(support), "against_count": len(against),
        "support": support[:5], "against": against[:5],
        "ticks": ticks, "collapsed": True,
        "honest_note": ("가설 A(지지)와 B(반박)가 팽팽 — 하나로 압축 불가, 정직하게 불확실성 보고"
                        if verdict == "unstable" else
                        "내부 토론 후 단일 원자아로 환원; 근거 없으면 지어내지 않고 부족을 보고"),
    }


def maybe_deliberate(query: str, store: Any, *, frame: Any, answer_confidence: float) -> dict[str, Any] | None:
    """Orchestrator hook: engage the special move only if enabled AND the gate opens. Returns None
    when the fast single path should answer (the common case)."""
    if os.getenv("ATANOR_FRACTAL") != "1":
        return None
    if not should_engage(frame, answer_confidence=answer_confidence):
        return None
    return deliberate(query, store, frame=frame)
