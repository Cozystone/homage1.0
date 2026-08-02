# -*- coding: utf-8 -*-
"""Affordance API — perceive a state, get the walkable PATHS (never conditions).

POST /api/affordance/observe  {concepts?, emotion?, fatigue signals?, tier?} -> proposals
GET  /api/affordance/paths                                                   -> the registry

This is the owner's doctrine as an endpoint: perception hands over a distilled STATE, and the
engine lays down the paths that RESONATE with it — the internal particle path runs itself
(READONLY), external paths (asking, soothing) surface as tier-gated proposals for the human to
walk. Works for ANY observation source, not just the face, so context can be read flexibly.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from packages.affordance.context_affordance import Observation, load_affordances, propose
from packages.os_action_lane.models import TrustTier

router = APIRouter(prefix="/api/affordance", tags=["affordance"])


class ObserveIn(BaseModel):
    concepts: list[str] = Field(default_factory=list, max_length=32)
    emotion: str | None = Field(default=None, max_length=40)
    eye_openness: float | None = None
    blink_rate: float | None = None
    yawning: bool = False
    appearance_changed: bool = False
    tier: int = int(TrustTier.ASSIST)          # the human owns the dial; default = surface, don't act
    drive_particles: bool = True               # walk the internal particle path when it's the choice


@router.post("/observe")
def observe(body: ObserveIn) -> dict[str, Any]:
    """Distil the signals into a state, lay the paths. If the chosen path is the particle field
    (internal, READONLY) and it's clear to run, the AI expresses it immediately — its own hands on
    the space. External paths are returned gated; nothing outside the machine acts on its own."""
    from packages.perception.user_state import observe as distil

    obs: Observation = distil(
        emotion=body.emotion, eye_openness=body.eye_openness, blink_rate=body.blink_rate,
        yawning=body.yawning, appearance_changed=body.appearance_changed,
        extra_concepts=body.concepts, source="observe")
    tier = TrustTier(max(0, min(3, body.tier)))
    result = propose(obs, tier=tier)
    result["expressed"] = _maybe_express(result, obs) if body.drive_particles else None
    return result


def _maybe_express(result: dict[str, Any], obs: Observation) -> dict[str, Any] | None:
    """The particle field is the AI's expressive body: whenever perception carries real affect, it
    paints the felt state into the field — continuous embodiment, not a path that must WIN the
    resonance race (the same license the hormone→field bridge has). READONLY/internal → autonomous;
    a flat/neutral read leaves the field to rest."""
    if abs(obs.valence) <= 0.05 and abs(obs.energy - 0.5) <= 0.05:
        return None
    from packages.imagination.particle_intent import from_state

    return from_state(obs.concepts, valence=obs.valence, energy=obs.energy,
                      note="·".join(obs.concepts[:3]), source=obs.source)


@router.get("/paths")
def paths() -> dict[str, Any]:
    """The registry of walkable paths (DATA) — transparency: what ATANOR could ever choose to do."""
    return {"affordances": [{"id": a["id"], "label": a.get("label"), "effect": a.get("effect"),
                             "risk": a.get("risk"), "cues": a.get("cues", []),
                             "has_action": bool(isinstance(a.get("action"), dict)
                                                and a["action"].get("kind"))}
                            for a in load_affordances()]}



class EnactIn(BaseModel):
    affordance_id: str = Field(min_length=1, max_length=80)   # a TRUSTED registry id, never a spec
    intent: str = Field(default="", max_length=200)


@router.post("/enact")
def enact_path(body: EnactIn) -> dict[str, Any]:
    """Walk a path's DECLARED action through the OS Action Lane — classified, tier-gated, audited.
    Only the action declared in the trusted registry for this id runs; no caller-supplied command."""
    from packages.affordance.enact import enact

    return enact(body.affordance_id, intent=body.intent)


@router.get("/lane")
def lane() -> dict[str, Any]:
    """The operator's view: the trust dial, anything held for a yes, and whether the audit record
    has EARNED a promotion (recommended, never self-granted)."""
    from packages.affordance.enact import lane_status

    return lane_status()


class TierIn(BaseModel):
    tier: int = Field(ge=0, le=3)          # 0 OBSERVE · 1 ASSIST · 2 GUARDED · 3 AUTONOMOUS


@router.post("/lane/tier")
def lane_tier(body: TierIn) -> dict[str, Any]:
    """The human turns the dial. This is the ONLY way autonomy widens — the machine never self-promotes."""
    from packages.affordance.enact import set_tier

    return set_tier(body.tier)


class TokenIn(BaseModel):
    token: str = Field(min_length=1, max_length=64)


@router.post("/lane/approve")
def lane_approve(body: TokenIn) -> dict[str, Any]:
    from packages.affordance.enact import approve

    return approve(body.token)


@router.post("/lane/reject")
def lane_reject(body: TokenIn) -> dict[str, Any]:
    from packages.affordance.enact import reject

    return reject(body.token)


@router.post("/lane/kill")
def lane_kill() -> dict[str, Any]:
    """Emergency stop — every action blocks until reset, whatever the tier."""
    from packages.affordance.enact import kill

    return kill()


@router.post("/lane/reset")
def lane_reset() -> dict[str, Any]:
    from packages.affordance.enact import reset_kill

    return reset_kill()
