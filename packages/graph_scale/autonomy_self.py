# -*- coding: utf-8 -*-
"""Self-judged autonomy — trust earns freedom, but a floor never moves.

Owner's directive (2026-07-09): as ATANOR accumulates real performance and
reliability, loosen its autonomy — let it act on its own for the everyday, and
require operator approval ONLY for things that would seriously break the system or
its functions. And let ATANOR judge that threshold itself.

The honest design that makes this safe:
 * TRUST is EARNED, measured from real signals (confirmed vs retired hypotheses,
 graph health, error rate) — not asserted. Low data → low trust → conservative.
 * ATANOR self-sets its auto-threshold ONLY over the REVERSIBLE, low-blast band;
 as trust rises, more of that band becomes autonomous.
 * A HARD CEILING never moves, no matter how high trust climbs: irreversible or
 system/function-breaking or outward-facing actions ALWAYS need an operator.
 The machine CANNOT lower this floor — that is precisely the ' 
 ' line, encoded so it can't be argued away.

This sits above agentic_micro_os.PermissionGate: it RECOMMENDS and self-decides
within the safe band; the gate + operator still own the dangerous scopes.
"""
from __future__ import annotations

from typing import Any

# The floor. These action classes ALWAYS require an operator, at ANY trust level —
# they can seriously break the system, are irreversible, or reach outside. ATANOR
# may PROPOSE them, never self-authorize them. (Mirrors the binding safety rules.)
HARD_CEILING = frozenset({
    "production_deploy", "store_truncate_or_delete", "git_push", "code_to_live",
    "access_control_change", "security_settings", "financial_transfer",
    "credential_entry", "mass_external_send", "full_host_authority",
})

# Reversible / low-blast classes that MAY become autonomous as trust grows.
_GRADUATED = {
    "read": 0.05, "draft_candidate": 0.10, "local_ledger_write": 0.25,
    "reversible_shard_write": 0.45, "staging_write": 0.55,
    "local_brain_write": 0.60, "restart_local_service": 0.75,
}


def trust_score() -> dict[str, Any]:
    """Earned reliability in [0, 1] from REAL signals — never a self-flattering
    constant. Sparse data keeps it low (conservative by default)."""
    confirmed = retired = 0
    try:
        from .fact_prediction import _rows as _pred_rows
        for r in _pred_rows():
            s = r.get("status")
            if s == "confirmed":
                confirmed += 1
            elif s == "retired":
                retired += 1
    except Exception:
        pass
    graph_ok = 0.5
    try:
        from .graph_health import health_report
        graph_ok = float(health_report().get("integrity_score", 0.5) or 0.5)
    except Exception:
        pass
    total = confirmed + retired
    # a track record of confirmed-over-retired predictions is the core signal;
    # with little history, evidence is weak and the score stays modest.
    hit_rate = (confirmed / total) if total else 0.0
    evidence = min(1.0, total / 50.0)                 # need ~50 settled to trust fully
    earned = 0.15 + 0.5 * hit_rate * evidence + 0.35 * graph_ok
    score = round(min(1.0, max(0.0, earned)), 3)
    return {"score": score, "confirmed_predictions": confirmed,
            "retired_predictions": retired, "graph_integrity": round(graph_ok, 3),
            "evidence_strength": round(evidence, 3),
            "note": "earned from confirmed/retired predictions + graph health; sparse data => low"}


def recommend_tier(score: float | None = None) -> dict[str, Any]:
    """The tier ATANOR judges it has earned — capped BELOW full host authority,
    which stays operator-only forever."""
    s = score if score is not None else trust_score()["score"]
    if s >= 0.75:
        tier = "SIGNED_DELEGATION"      # reversible autonomy within issued scopes
    elif s >= 0.45:
        tier = "DRAFT_PROPOSAL"
    else:
        tier = "OBSERVE_ONLY"
    return {"recommended_tier": tier, "trust": s,
            "ceiling": "FULL_HOST_AUTHORITY is operator-only and never self-recommended",
            "rationale": f"trust {s} earns up to {tier}; the hard ceiling is unaffected"}


def self_decide(action_class: str, *, reversible: bool = True, blast: float = 0.2,
                trust: float | None = None) -> dict[str, Any]:
    """The gate ATANOR applies to its OWN proposed action. Returns whether it may
    act autonomously or must ask an operator — and WHY. The hard ceiling wins over
    any trust level; the graduated band opens as trust rises."""
    s = trust if trust is not None else trust_score()["score"]
    if action_class in HARD_CEILING or not reversible:
        return {"mode": "needs_operator", "action_class": action_class, "trust": s,
                "ceiling_hit": True, "reversible": reversible,
                "reason": "hard ceiling — irreversible or system/function-breaking or "
                          "outward-facing action always requires an operator, at any trust"}
    base = _GRADUATED.get(action_class, 0.5)          # unknown class => cautious middle
    # the risk of THIS action = its class baseline lifted by its blast radius
    risk = min(1.0, base + 0.4 * max(0.0, min(1.0, blast)))
    # trust buys a proportional risk budget; below it, act; above it, ask
    budget = 0.15 + 0.7 * s
    auto = risk <= budget
    return {"mode": "auto" if auto else "needs_operator", "action_class": action_class,
            "trust": s, "risk": round(risk, 3), "auto_budget": round(budget, 3),
            "ceiling_hit": False, "reversible": True,
            "reason": ("within the earned, reversible autonomy band"
                       if auto else "above the earned budget — asks an operator")}
