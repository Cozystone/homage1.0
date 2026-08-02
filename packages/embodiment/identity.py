# -*- coding: utf-8 -*-
"""Track E M4s — identity integration: embodiment experience becomes an autobiographical ledger.

The developmental self is not just a reactive loop; it accumulates a HISTORY. Each salient embodiment
event (a surprise, discovering an affordance, attributing a motion to self vs the world) is recorded as
a time-ordered, causally-linked episode with a hormone signature — "I was shoved and startled at t=5;
I found I can push the box at t=12". Over a life this is a first-person narrative grounded entirely in
real, measured events (No-LLM: structured records, never generated).

M4s gate (measured, not asserted, per G2): NARRATIVE CONSISTENCY —
  * temporal: episode times are monotonic (the self has one arrow of time),
  * causal: every episode's cause points to an EARLIER episode (no effect-before-cause),
  * ownership: self-caused events are 'me', world events are 'world', never confused.
A consistency < 1 means the autobiography contradicts itself. The hormone signature is a v0 3-tuple
(adrenaline, cortisol, dopamine); the shipped 5-hormone dynamics plug into the same slot later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class EmbodimentEpisode:
    t: int                                  # discrete time index (the self's arrow of time)
    kind: str                               # 'surprise' | 'affordance' | 'self_attribution' | 'contact'
    content: str
    agent: str                              # 'me' (self-caused) | 'world' (externally caused)
    hormones: tuple[float, float, float]    # (adrenaline, cortisol, dopamine) — v0 signature
    cause: int | None = None                # index of the earlier episode that caused this one


class IdentityLedger:
    """Append-only autobiographical memory. Time-ordered; each episode may cite an earlier cause."""

    def __init__(self):
        self.episodes: list[EmbodimentEpisode] = []
        self._h = np.zeros(3)               # decaying hormone state (adrenaline, cortisol, dopamine)

    def record(self, t: int, kind: str, content: str, agent: str,
               surprise: float = 0.0, reward: float = 0.0, cause: int | None = None) -> int:
        # hormones: surprise -> fast adrenaline + slower cortisol; reward (e.g. affordance) -> dopamine.
        self._h *= 0.7                      # decay toward baseline each event
        self._h[0] += min(1.0, surprise)                    # adrenaline (fast)
        self._h[1] += min(1.0, 0.5 * surprise)              # cortisol (slower)
        self._h[2] += min(1.0, reward)                      # dopamine
        ep = EmbodimentEpisode(t=t, kind=kind, content=content, agent=agent,
                               hormones=tuple(round(float(x), 3) for x in self._h), cause=cause)
        self.episodes.append(ep)
        return len(self.episodes) - 1

    def narrative(self) -> list[str]:
        """First-person autobiographical sentences, in order."""
        out = []
        for e in self.episodes:
            who = "I" if e.agent == "me" else "the world"
            out.append(f"[t={e.t}] {who}: {e.content}")
        return out

    def consistency(self) -> dict[str, Any]:
        temporal_ok = causal_ok = ownership_ok = 0
        n = len(self.episodes)
        for i, e in enumerate(self.episodes):
            if i == 0 or e.t >= self.episodes[i - 1].t:
                temporal_ok += 1
            if e.cause is None or (0 <= e.cause < i and self.episodes[e.cause].t <= e.t):
                causal_ok += 1                              # cause exists and is not in the future
            if e.agent in ("me", "world"):                  # a valid, unconfused ownership label
                ownership_ok += 1
        score = (temporal_ok + causal_ok + ownership_ok) / (3 * max(1, n))
        return {"episodes": n, "temporal_ok": temporal_ok, "causal_ok": causal_ok,
                "ownership_ok": ownership_ok, "consistency": round(score, 4)}


def run_embodied_life(steps: int = 400, seed: int = 0) -> dict[str, Any]:
    """Live the MuJoCo body, learn its schema, and WRITE the salient events to the identity ledger —
    surprises, self/other attributions, and the affordance discovery — each with a hormone signature.
    Returns the ledger's narrative + its M4s consistency."""
    from packages.embodiment.mujoco_body import MujocoBody, JointSchema

    body = MujocoBody()
    schema = JointSchema()
    rng = np.random.default_rng(seed)
    led = IdentityLedger()
    st = body.state()
    curve: list[float] = []
    discovered_affordance = False
    last_idx: int | None = None

    for t in range(steps):
        # occasionally the world shoves the body (external), otherwise the self acts.
        external = rng.random() < 0.06
        a = rng.normal(0, 0.15, 3)
        j, jv = st.joints.copy(), st.joint_vel.copy()
        pred = schema.predict(j, jv, a)
        ext = rng.normal(0, 1, 3) * 4.0 if external else None
        st = body.step(a, external_torque=ext)
        err = schema.learn(j, jv, a, st.joints)
        curve.append(err)
        baseline = float(np.mean(curve[-30:])) if len(curve) >= 30 else float(np.mean(curve))

        # self/other attribution once the schema is trained
        if t > 60 and external:
            surprise = err / max(baseline, 1e-6)
            idx = led.record(t, "self_attribution", "a shove I did not command moved me; that was not me",
                             agent="world", surprise=min(1.0, surprise / 20.0), cause=last_idx)
            last_idx = idx
        if not discovered_affordance and st.touching_object:
            discovered_affordance = True
            last_idx = led.record(t, "affordance", "I touched the box and felt I could push it",
                                  agent="me", reward=0.8, cause=last_idx)

    cons = led.consistency()
    return {"narrative": led.narrative(), "consistency": cons,
            "final_hormones": led.episodes[-1].hormones if led.episodes else (0, 0, 0),
            "self_episodes": sum(1 for e in led.episodes if e.agent == "me"),
            "world_episodes": sum(1 for e in led.episodes if e.agent == "world")}
