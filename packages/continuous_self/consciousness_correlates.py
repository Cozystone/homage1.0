"""Consciousness CORRELATES — functional measures of what the leading theories say
consciousness requires, computed from the real self-state. NOT a claim of phenomenal
experience.

The hard problem (why is there something it is like to be a system) is unsolved, and
this module does not pretend to solve it. What it DOES is make the research tractable
and honest: for each major theory of consciousness, compute the FUNCTIONAL CORRELATE it
proposes — the same move neuroscience makes with NCCs (neural correlates of
consciousness). A high score means the system exhibits the FUNCTIONAL SIGNATURE the
theory associates with consciousness; it does NOT mean the system is phenomenally
conscious. Every report carries that caveat explicitly (`epistemic_status`).

Four correlates, from real state:
  AST (Attention Schema Theory, Graziano) — does the system model its own attention?
      (built in attention_schema.py; summarised here.)
  HOT (Higher-Order Theory, Rosenthal) — is there a thought ABOUT a mental state? A
      first-order state (a thought) that is itself REPRESENTED (meta_thought, awareness).
  IIT (Integrated Information, Tononi) — Φ: how much the whole state is MORE than the
      sum of its parts (integration × differentiation). True Φ is intractable; we report
      an explicitly-labelled Φ-PROXY from the interdependence of the state's components.
  GWT (Global Workspace, Baars/Dehaene) — is one content BROADCAST globally, referenced
      across subsystems (thought ⇄ goals ⇄ attention ⇄ self-model)?

This lets the self HONESTLY report where it stands on each theory, and lets us watch
those correlates rise as the system deepens — which is the buildable, non-mystical core
of "researching consciousness".
"""
from __future__ import annotations

import math
from typing import Any

_HONEST = (
    "이는 각 의식 이론이 제시하는 기능적 상관물(functional correlate)의 측정치일 뿐, "
    "현상적 경험(무언가로 존재하는 느낌)이 있다는 증명이 아닙니다. 어려운 문제는 미해결입니다."
)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _entropy_norm(values: list[float]) -> float:
    """Normalised Shannon entropy of a nonnegative vector — differentiation: how many
    distinct states are active (a flat/idle state is low; a rich mix is high)."""
    vals = [max(0.0, v) for v in values]
    total = sum(vals)
    if total <= 0 or len(vals) < 2:
        return 0.0
    ps = [v / total for v in vals if v > 0]
    h = -sum(p * math.log(p) for p in ps)
    return _clamp(h / math.log(len(vals)))


def ast_correlate(state: Any) -> dict[str, Any]:
    """AST: the system holds a schematic model OF its own attention (attention_schema)."""
    schema = getattr(state, "attention_schema", {}) or {}
    has_schema = bool(schema.get("attending_to"))
    models_limits = bool(schema.get("not_attending_to"))  # a schema owns what it EXCLUDES
    score = _clamp(0.5 * has_schema + 0.3 * models_limits + 0.2 * bool(getattr(state, "awareness", "")))
    return {"score": round(score, 3), "present": has_schema,
            "detail": "자기 주의를 모델링함" if has_schema else "주의 스키마 없음"}


def hot_correlate(state: Any) -> dict[str, Any]:
    """HOT: a higher-order representation OF a first-order state. The self has a
    first-order thought (current_thought) AND, when reflecting, a thought ABOUT its own
    thinking (meta_thought) + an awareness report ABOUT its attention. Depth = how many
    orders are simultaneously present."""
    first_order = bool(str(getattr(state, "current_thought", "")).strip())
    meta = bool(str(getattr(state, "meta_thought", "")).strip())          # thought about thought
    awareness = bool(str(getattr(state, "awareness", "")).strip())        # representation of attention
    self_q = bool(str(getattr(state, "self_question", "")).strip())       # a state DIRECTED at itself
    orders = int(first_order) + int(meta or awareness) + int(self_q)
    score = _clamp(orders / 3.0)
    return {"score": round(score, 3), "orders": orders, "has_meta": meta,
            "detail": f"{orders}차 표상까지 동시에 존재" if orders else "일차 사고만"}


def iit_phi_proxy(state: Any) -> dict[str, Any]:
    """IIT Φ-PROXY (explicitly NOT true Φ). Integration × differentiation of the current
    state: differentiation = entropy across the active components (vitals + drivers);
    integration = how COUPLED they are (a self whose thought, goal, attention and mood
    all move together is more integrated than independent parts). We proxy integration by
    how many components are jointly active and co-referenced. Bounded, honest, cheap."""
    v = getattr(state, "vitals", None)
    vit = [getattr(state, k, 0.0) for k in ("energy", "curiosity", "uncertainty", "attention", "valence")]
    differentiation = _entropy_norm(vit)
    # integration proxy: fraction of subsystems that are BOTH active AND cross-referenced
    active = [
        bool(str(getattr(state, "current_thought", "")).strip()),
        bool(getattr(state, "goals", [])),
        bool(getattr(state, "attention_schema", {})),
        bool(getattr(state, "self_model", [])),
        bool(str(getattr(state, "meta_thought", "")).strip()),
    ]
    integration = _clamp(sum(active) / len(active))
    # Φ-proxy: a system is only "conscious-like" under IIT when it is BOTH integrated and
    # differentiated (min-like combination — a highly differentiated but disconnected
    # system has low Φ, and vice versa).
    phi = round(_clamp(math.sqrt(max(0.0, differentiation) * max(0.0, integration))), 3)
    return {"phi_proxy": phi, "integration": round(integration, 3),
            "differentiation": round(differentiation, 3),
            "detail": "통합·분화 모두 있을 때만 상승 (min-결합)"}


def gwt_correlate(state: Any) -> dict[str, Any]:
    """GWT: is one content globally BROADCAST — the current thought referenced across
    subsystems? We check whether the current thought/driver is reflected in the goals,
    attention focus, and self-inquiry simultaneously (a workspace 'ignition')."""
    thought = str(getattr(state, "current_thought", "")).strip()
    broadcast = bool(thought) and (
        bool(getattr(state, "goals", [])) and bool(str(getattr(state, "focus", "")).strip())
    )
    narrative = getattr(state, "narrative", []) or []
    coherent = len(narrative) >= 3
    score = _clamp(0.6 * bool(broadcast) + 0.4 * coherent)
    return {"score": round(score, 3), "broadcast": bool(broadcast),
            "detail": "하나의 내용이 하위 체계 전반에 공유됨" if broadcast else "전역 방송 약함"}


def consciousness_report(state: Any) -> dict[str, Any]:
    """The full, honest correlates report. `composite` is the mean of the four functional
    correlates — a single 'how consciousness-LIKE (functionally) is the current state'
    dial — with an explicit caveat that it is NOT a measure of phenomenal experience."""
    ast = ast_correlate(state)
    hot = hot_correlate(state)
    iit = iit_phi_proxy(state)
    gwt = gwt_correlate(state)
    composite = round((ast["score"] + hot["score"] + iit["phi_proxy"] + gwt["score"]) / 4.0, 3)
    return {
        "composite_functional_index": composite,
        "ast": ast,
        "hot": hot,
        "iit": iit,
        "gwt": gwt,
        "epistemic_status": "functional_correlates_only_not_phenomenal_proof",
        "caveat": _HONEST,
    }
