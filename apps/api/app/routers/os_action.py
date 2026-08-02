# -*- coding: utf-8 -*-
"""OS Action Lane API — the orb's bridge to the real desktop.

POST /api/os-action/propose {text} -> classify+gate a natural request
POST /api/os-action/approve {token} -> run a held action (voice ''/click)
POST /api/os-action/reject {token}
GET /api/os-action/status -> tier, pending, kill state
POST /api/os-action/tier {tier} -> raise/lower trust (0..3)
POST /api/os-action/kill {on} -> kill switch

The lane starts in ASSIST: proposals are held until the local user explicitly
approves the one-shot pending token. This is an honest cooperative human-in-loop
M0 boundary, not cryptographic operator identity. Environment variables cannot
raise the tier; standing GUARDED/AUTONOMOUS authority remains unavailable.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from packages.os_action_lane import Action, OSActionLane, TrustTier
from packages.os_action_lane.backends import LinuxDesktopBackend
from packages.os_action_lane.intent import parse_intent

router = APIRouter(prefix="/api/os-action", tags=["os-action"])

_AUDIT = Path(__file__).resolve().parents[4] / "data" / "os_action" / "audit.jsonl"


# ASSIST is useful but non-autonomous: every effect remains held until an
# explicit one-shot approval.
_LANE = OSActionLane(
    LinuxDesktopBackend(),
    tier=TrustTier.ASSIST,
    audit_path=_AUDIT,
)


class ProposeIn(BaseModel):
    text: str = Field(..., max_length=1000)


class TokenIn(BaseModel):
    token: str = Field(..., max_length=64)


class TierIn(BaseModel):
    tier: int = Field(..., ge=0, le=3)
    operator_token: str = Field(default="", max_length=128)


class KillIn(BaseModel):
    on: bool = True


@router.post("/propose")
def propose(body: ProposeIn) -> dict[str, Any]:
    action = parse_intent(body.text)
    if action is None:
        return {"is_os_action": False, "reason": "not an OS command — answer as a question"}
    result = _LANE.propose(action)
    out = result.to_dict()
    out["is_os_action"] = True
    # surface the approval token cleanly when the action is held
    if result.outcome != 0 and result.stdout:  # NEEDS_APPROVAL/BLOCKED carry token in stdout
        out["approval_token"] = result.stdout
    return out


@router.post("/approve")
def approve(body: TokenIn) -> dict[str, Any]:
    if _LANE.tier is TrustTier.OBSERVE:
        return {
            "ok": False,
            "executed": False,
            "reason": "observe_only",
        }
    result = _LANE.approve(body.token)
    if result is None:
        return {
            "ok": False,
            "executed": False,
            "detail": "no such pending action",
        }
    return {**result.to_dict(), "approval_mode": "cooperative_local_m0"}


@router.post("/reject")
def reject(body: TokenIn) -> dict[str, Any]:
    return {"rejected": _LANE.reject(body.token)}


@router.get("/status")
def status() -> dict[str, Any]:
    return {"tier": int(_LANE.tier), "tier_name": _LANE.tier.name,
            "pending": _LANE.pending(), "killed": _LANE._killed,  # noqa: SLF001
            "audit_path": str(_AUDIT),
            "approval_mode": "cooperative_local_m0",
            "cryptographic_operator_identity": False}


@router.get("/trust-recommendation")
def trust_recommendation() -> dict[str, Any]:
    """Phase 5: evidence-backed tier-promotion recommendation from the audit
    track record. Reports only — the grant is always the user's (POST /tier)."""
    from packages.os_action_lane.trust_record import promotion_recommendation

    return promotion_recommendation(_AUDIT, _LANE.tier)


@router.post("/tier")
def set_tier(body: TierIn) -> dict[str, Any]:
    requested = TrustTier(body.tier)
    if requested in {TrustTier.OBSERVE, TrustTier.ASSIST}:
        _LANE.set_tier(requested)
        return {
            "ok": True,
            "tier": int(_LANE.tier),
            "tier_name": _LANE.tier.name,
            "per_action_approval_required": True,
        }
    # A one-shot effect approval must never become a standing autonomous grant.
    # GUARDED/AUTONOMOUS need a future purpose-specific signed lease boundary.
    return {
        "ok": False,
        "reason": "signed_operator_run_lease_required",
        "required_boundary": "common_operator_run_lease_gate",
        "tier": int(_LANE.tier),
        "tier_name": _LANE.tier.name,
    }


@router.post("/kill")
def kill(body: KillIn) -> dict[str, Any]:
    if body.on:
        _LANE.kill()
        return {"killed": bool(_LANE._killed)}  # noqa: SLF001
    _LANE.reset_kill()
    return {
        "killed": bool(_LANE._killed),  # noqa: SLF001
        "reset": True,
        "approval_mode": "cooperative_local_m0",
    }
