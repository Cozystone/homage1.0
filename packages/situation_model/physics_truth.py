# -*- coding: utf-8 -*-
"""Physics-truth gate — keep ATANOR's physics knowledge clean when it learns from a world.

Owner (2026-07-21): make Realcity's physics real (via a real rigid-body engine) "so that ATANOR is
not contaminated." ATANOR now perceives the digital twin and folds it into its lived record (R3);
as it learns HOW the world works by watching the city, the city's physics must be TRUE or ATANOR
would absorb false law (a cup that floats, a bus that drives through a wall). Two guarantees stack:

  1. BODY: the city runs on a real solver (Rapier), so its events are physically true by construction
     (verified headless: free-fall = 1/2 g t^2, support holds, restitution <= 1, momentum conserved).
  2. GATE (this module): ATANOR never trusts the engine blindly. Every physics event the city reports
     is checked against domain-blind physical INVARIANTS before ATANOR may learn from it. An event
     that violates an invariant (an unsupported thing that rises, motion through a blocked path, a
     rebound higher than the drop) is QUARANTINED as a twin-bug and never enters the lived record.

This is the same doctrine as [[external-minds-are-data]]: the world is DATA passing a gate, not an
authority. And the same structure as mechanism.py — a small finite set of composable, domain-blind
laws that carry no commitment to any subject. The gate reuses those law names so a city observation
and ATANOR's own mechanism reasoning speak one physics.

Honesty floor (mirrors mechanism.py): when an observation lacks the conditions needed to judge it,
the gate returns UNDECIDED — ATANOR abstains from learning it rather than guessing it true or false.
Material properties the observation does not state (is the vase fragile? will ice melt?) are never
invented here; they are learned knowledge, grounded elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ACCEPTED = "accepted"       # physically consistent -> ATANOR may learn from it
QUARANTINED = "quarantined"  # violates a physical invariant -> twin-bug, never learned
UNDECIDED = "undecided"      # not enough stated conditions to judge -> abstain from learning


@dataclass
class PhysicsObservation:
    """A single event the city reports about how something behaved — structured, domain-blind.

    kind: fall | rest | rise | traverse | bounce | collide | slide
    conditions: stated facts the law operates on (supported, disturbed, at_edge, blocked, solid,
                applied_force, path ...). Absent keys mean 'not stated' -> may force UNDECIDED.
    outcome: measured numbers where relevant (drop, apex, y_before, y_after, dt, penetration ...).
    """
    kind: str
    subject: str = "object"
    conditions: dict[str, Any] = field(default_factory=dict)
    outcome: dict[str, Any] = field(default_factory=dict)
    source: str = "realcity"


@dataclass
class Verdict:
    status: str                 # ACCEPTED | QUARANTINED | UNDECIDED
    law: str                    # the invariant applied
    reason: str
    observation: PhysicsObservation | None = None

    @property
    def learnable(self) -> bool:
        return self.status == ACCEPTED


def _accept(law: str, reason: str) -> Verdict:
    return Verdict(ACCEPTED, law, reason)


def _reject(law: str, reason: str) -> Verdict:
    return Verdict(QUARANTINED, law, reason)


def _undecided(reason: str) -> Verdict:
    return Verdict(UNDECIDED, "insufficient-stated-conditions", reason)


# tolerance: physics engines carry small numerical error; a violation must exceed it to count
_EPS = 0.02


def verify(obs: PhysicsObservation) -> Verdict:
    """Judge one physics observation against domain-blind physical invariants."""
    k = (obs.kind or "").lower().strip()
    c, o = obs.conditions, obs.outcome

    # INVARIANT gravity/support: a thing that fell must have been UNSUPPORTED (no support, or at an
    # edge, or its support was disturbed/removed). A supported, undisturbed thing that fell is a
    # support violation — the twin broke its own physics, do not learn "supported things fall".
    if k == "fall":
        supported = c.get("supported")
        disturbed = c.get("disturbed") or c.get("support_removed") or c.get("at_edge")
        if supported and not disturbed:
            return _reject("support-holds",
                           "a supported, undisturbed object must not fall — support was violated")
        if supported is None and not disturbed and "at_edge" not in c:
            return _undecided("fall with unknown support/disturbance — cannot judge")
        return _accept("unsupported-things-fall", "an unsupported/disturbed object falls")

    # INVARIANT gravity: nothing rises or hovers on its own. A thing that rose/stayed-up needs an
    # applied force or a support; without either it is a gravity violation.
    if k in ("rise", "hover", "float"):
        if c.get("applied_force") or c.get("supported"):
            return _accept("force-or-support-lifts", "rise/hover explained by force or support")
        return _reject("gravity-pulls-down",
                       "an unsupported object cannot rise or hover with no applied force")

    # INVARIANT impenetrability: a blocked or solid path cannot be traversed. Motion THROUGH it is a
    # tunnelling violation (the arcade-physics 'taxi drives through the wall').
    if k in ("traverse", "pass", "move_through"):
        if c.get("blocked") or c.get("solid"):
            return _reject("blocked-path-is-impassable",
                           "a blocked/solid path cannot be traversed — object tunnelled through")
        if c.get("blocked") is None and c.get("solid") is None:
            return _undecided("traverse with unknown path solidity — cannot judge")
        return _accept("open-path-traversable", "an open path can be traversed")

    # INVARIANT energy: a passive rebound cannot exceed the drop that caused it (restitution <= 1).
    # A bounce higher than the drop is energy from nowhere.
    if k == "bounce":
        apex, drop = o.get("apex"), o.get("drop")
        if apex is None or drop is None or drop <= 0:
            return _undecided("bounce without measured apex/drop — cannot judge")
        if apex > drop * (1.0 + _EPS):
            return _reject("energy-not-created",
                           f"rebound apex {apex:.3f} exceeds drop {drop:.3f}: restitution>1 is impossible")
        return _accept("restitution-bounded", "a passive rebound stays at or below the drop height")

    # INVARIANT continuity: an object's centre cannot deeply interpenetrate a solid (soft contact
    # aside). Reported penetration beyond tolerance means the solver let it pass into a solid.
    if k in ("rest", "collide"):
        pen = o.get("penetration")
        if pen is not None and pen > _EPS:
            return _reject("no-deep-interpenetration",
                           f"penetration {pen:.3f} into a solid exceeds contact tolerance")
        return _accept("contact-resolves", "the contact resolved without deep interpenetration")

    return _undecided(f"unmodelled event kind '{k}' — no invariant to judge it")


def screen(observations: list[PhysicsObservation]) -> dict[str, list[Verdict]]:
    """The ingestion gate: split a stream of city physics events into what ATANOR may learn from
    (accepted), what it must refuse (quarantined twin-bugs), and what it abstains on (undecided)."""
    out: dict[str, list[Verdict]] = {ACCEPTED: [], QUARANTINED: [], UNDECIDED: []}
    for obs in observations:
        v = verify(obs)
        v.observation = obs
        out[v.status].append(v)
    return out


def from_trajectory(subject: str, ys: list[float], *, support_y: float | None = None,
                    conditions: dict[str, Any] | None = None) -> PhysicsObservation:
    """Classify a vertical trajectory (an object's y over time) into a physics event, so a real
    engine's output can be fed to the gate. Detects fall→rest, spontaneous rise, and bounce."""
    conds = dict(conditions or {})
    if len(ys) < 2:
        return PhysicsObservation("rest", subject, conds, {})
    y0, yend = ys[0], ys[-1]
    ymin, ymax = min(ys), max(ys)
    # rose overall with no downward-first phase -> rise event
    if yend > y0 + _EPS and ymin >= y0 - _EPS:
        return PhysicsObservation("rise", subject, conds, {"y_before": y0, "y_after": yend})
    # went down then came back up appreciably -> bounce; apex is the post-contact maximum
    trough_i = ys.index(ymin)
    apex_after = max(ys[trough_i:]) if trough_i < len(ys) - 1 else ymin
    if apex_after > ymin + 0.1 and support_y is not None:
        drop = y0 - support_y
        return PhysicsObservation("bounce", subject, conds,
                                  {"drop": max(0.0, drop), "apex": apex_after - support_y})
    # settled near a support and stopped descending -> rest (with penetration if it sank past it)
    if support_y is not None:
        pen = max(0.0, support_y - ymin)
        return PhysicsObservation("rest", subject, {**conds, "supported": True},
                                  {"penetration": pen, "y_after": yend})
    # net descent -> fall
    return PhysicsObservation("fall", subject, conds, {"y_before": y0, "y_after": yend})
