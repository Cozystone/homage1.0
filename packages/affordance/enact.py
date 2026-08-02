# -*- coding: utf-8 -*-
"""Enactment — the bridge from a resonant affordance to a REAL, gated action (owner's " 
", 2026-07-12). context_affordance lays the walkable paths; this walks one, but ONLY through the
OS Action Lane, so trust is earned and the human holds the dial.

The whole safety model is inherited from os_action_lane, not reinvented:
 * the machine NEVER promotes its own tier — the operator raises it (set_tier), and trust_record
 only RECOMMENDS promotion from a clean audit record;
 * every action is classified (risk.py, rounds UP when unsure), gated (risk × tier), and audited
 (append-only) — at a low tier a real-world action is HELD for an explicit yes, not run;
 * a kill switch stops the lane instantly.

SECURITY: enact takes an affordance_id and runs the action DECLARED IN THE TRUSTED REGISTRY for it —
never a caller-supplied action spec. A client cannot inject an arbitrary command through this path.
The backend is MockBackend by default (records, never touches the machine); the real desktop
backend belongs to the ATANOR OS target and is wired there, not on a dev box.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.os_action_lane import Action, GateOutcome, OSActionLane, TrustTier
from packages.os_action_lane.backends import MockBackend

from .context_affordance import load_affordances

_ROOT = Path(__file__).resolve().parents[2] / "data" / "os_action_lane"
_TIER_FILE = _ROOT / "affordance_tier.json"
_AUDIT = _ROOT / "affordance_audit.jsonl"
_LANE: OSActionLane | None = None


def _load_tier() -> TrustTier:
    try:
        return TrustTier(int(json.loads(_TIER_FILE.read_text(encoding="utf-8"))["tier"]))
    except Exception:
        return TrustTier.ASSIST          # trust is EARNED — default is approve-every-action


def get_lane() -> OSActionLane:
    """The one process-wide lane: MockBackend (safe), tier restored from the operator's last dial,
    audit persisted so trust_record can read the track record."""
    global _LANE
    if _LANE is None:
        _LANE = OSActionLane(MockBackend(), tier=_load_tier(), audit_path=_AUDIT)
    return _LANE


def set_tier(tier: int) -> dict[str, Any]:
    """The human turns the dial. The machine never calls this on itself."""
    lane = get_lane()
    t = TrustTier(max(0, min(3, int(tier))))
    lane.set_tier(t)
    try:
        _ROOT.mkdir(parents=True, exist_ok=True)
        _TIER_FILE.write_text(json.dumps({"tier": int(t)}), encoding="utf-8")
    except Exception:
        pass
    return {"tier": int(t), "tier_name": t.name}


def _action_for(affordance_id: str) -> dict[str, Any] | None:
    for a in load_affordances():
        if a.get("id") == affordance_id:
            spec = a.get("action")
            return spec if isinstance(spec, dict) and spec.get("kind") else None
    return None


def enact(affordance_id: str, *, intent: str = "") -> dict[str, Any]:
    """Walk a path's declared action through the lane. Internal/utterance paths (no declared action)
    aren't OS actions → nothing to enact. Otherwise the lane classifies+gates+audits: EXECUTE ran it
    (only when the tier has earned that risk), NEEDS_APPROVAL parked it with a token, BLOCKED refused."""
    spec = _action_for(affordance_id)
    if spec is None:
        return {"enacted": False, "reason": "no_action", "affordance_id": affordance_id}
    lane = get_lane()
    act = Action(kind=str(spec["kind"]), args=dict(spec.get("args") or {}),
                 intent=intent or affordance_id, origin="affordance")
    res = lane.propose(act)
    held = res.outcome == GateOutcome.NEEDS_APPROVAL
    return {"enacted": bool(res.executed), "outcome": int(res.outcome), "risk": int(res.risk),
            "audit_id": res.audit_id, "approval_token": res.stdout if held else None,
            "tier": int(lane.tier), "tier_name": lane.tier.name, "detail": res.detail}


def lane_status() -> dict[str, Any]:
    """What the operator sees: the dial, anything held for a yes, and — from the audit track record
    — whether the lane has EARNED a promotion (trust_record recommends; the human decides)."""
    lane = get_lane()
    from packages.os_action_lane.trust_record import promotion_recommendation

    try:
        rec = promotion_recommendation(_AUDIT, lane.tier)
    except Exception:
        rec = {"recommend": False}
    return {"tier": int(lane.tier), "tier_name": lane.tier.name, "killed": lane._killed,
            "pending": lane.pending(), "promotion": rec}


def approve(token: str) -> dict[str, Any]:
    res = get_lane().approve(token)
    if res is None:
        return {"ok": False, "reason": "unknown_or_killed"}
    return {"ok": bool(res.ok), "executed": res.executed, "audit_id": res.audit_id}


def reject(token: str) -> dict[str, Any]:
    return {"rejected": get_lane().reject(token)}


def kill() -> dict[str, Any]:
    get_lane().kill()
    return {"killed": True}


def reset_kill() -> dict[str, Any]:
    get_lane().reset_kill()
    return {"killed": False}
