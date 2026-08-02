# -*- coding: utf-8 -*-
"""Track E on SPLATRA — the Isaac-free embodiment substrate (M0s + M1s + reaction seed).

Isaac Sim M0 is blocked (Blackwell RTX renderer crashes; docs/ATANOR_isaac_sim_setup.md sec 4.3).
Track E pivots onto SPLATRA (docs/ATANOR_splatra_embodiment_track.md). This module is the SPLATRA
analogue of the Isaac headless-boot + babble gates — with NO renderer to crash, NO GPU, CPU only.

The developmental-self loop (the charter's real deliverable) runs here in full:

    act -> the body responds -> forward model PREDICTED the response -> measure prediction error
        -> error = surprise -> (habituates as the model learns; spikes on an unexpected perturbation)

Design (honest, No-LLM, deterministic):
  * BODY (M0s): a SPLATRA particle body from splatra_imagination.synthesize_form. Its felt state
    (proprioception) is a low-dim pose vector: centroid + extent + the reach LANDMARK (the tip
    particle farthest from the centroid — the body's "fingertip"). No camera frame is ever stored
    (perception charter); vision arrives later as depth via depth-anything.cpp.
  * MOTOR (borrowed/simple): an action is a desired tip velocity in R^3. The body's TRUE response is
    a fixed gain matrix G + damping the model does NOT know — the body's own dynamics to be learned.
  * FORWARD MODEL (M1s): predicts the next tip position from (tip, action) via a learned linear map W.
    Online gradient updates W toward the body's true G, so prediction error CONVERGES over babbling
    (the M1s gate). This is the body schema being learned from sensorimotor experience.
  * REACTION (M1s+): surprise = prediction error magnitude. An unexpected external perturbation adds
    displacement the action never commanded, so error SPIKES above the learned baseline -> a surprise
    Percept (routed via the sensory cortex as an internal non-fact event; reaction_engine_research).

Everything is measured, not asserted: no learning -> flat error curve -> the body schema failed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

_GROUND_Y = -1.9   # a floor plane; body particles below it are in contact


@dataclass
class BodyState:
    tip: np.ndarray                    # reach landmark position (3,)
    centroid: np.ndarray               # body centroid (3,)
    extent: np.ndarray                 # bounding extent (3,)
    contact: bool                      # any particle touching the ground plane

    def proprioception(self) -> np.ndarray:
        return np.concatenate([self.centroid, self.extent, self.tip])   # (9,)


class SplatraBody:
    """A SPLATRA particle body with proprioceptive + contact sensors and a learnable response.
    The body's true action->response gain G is HIDDEN from the forward model — it must be learned."""

    def __init__(self, concept: str = "arm", count: int = 400, seed: int = 0):
        from packages.splatra_imagination.generative import synthesize_form
        parts = synthesize_form(concept, count=count)
        self.pos = np.array([[p.x, p.y, p.z] for p in parts], dtype=np.float64)   # (N,3)
        self.concept = concept
        self._rng = np.random.default_rng(seed)
        # the body's TRUE dynamics: a per-axis gain + light cross-coupling + damping. Unknown to M1s.
        self._G = np.eye(3) * 0.6 + self._rng.normal(0, 0.08, (3, 3))
        self._damp = 0.9
        self._noise = 0.003     # irreducible sensorimotor noise — the schema can never predict it away
        self._tip_idx = int(np.argmax(np.linalg.norm(self.pos - self.pos.mean(0), axis=1)))

    def _state(self) -> BodyState:
        c = self.pos.mean(0)
        ext = self.pos.max(0) - self.pos.min(0)
        contact = bool((self.pos[:, 1] <= _GROUND_Y).any())
        return BodyState(tip=self.pos[self._tip_idx].copy(), centroid=c, extent=ext, contact=contact)

    def state(self) -> BodyState:
        return self._state()

    def step(self, action: np.ndarray, perturbation: np.ndarray | None = None) -> BodyState:
        """Advance the body: the commanded tip velocity is transformed by the hidden gain G (+ damping),
        applied as a rigid translation of the whole cloud; an optional external perturbation adds
        displacement the action never asked for (the source of genuine surprise)."""
        action = np.asarray(action, dtype=np.float64).reshape(3)
        delta = self._damp * (self._G @ action) + self._rng.normal(0, self._noise, 3)   # + body noise
        if perturbation is not None:
            delta = delta + np.asarray(perturbation, dtype=np.float64).reshape(3)
        self.pos = self.pos + delta                      # rigid move (M0s: whole-body actuation)
        return self._state()


class BodySchema:
    """M1s forward model: predict the next tip from (tip, action) with a learned linear map.
    Learns online (no pretrained weights, No-LLM) so prediction error converges as the schema forms."""

    def __init__(self, lr: float = 0.4):
        self.W = np.zeros((3, 3))       # tip_delta ~= W @ action  (learned toward the body's true G)
        self.lr = lr

    def predict(self, tip: np.ndarray, action: np.ndarray) -> np.ndarray:
        return np.asarray(tip, dtype=np.float64).reshape(3) + self.W @ np.asarray(action, dtype=np.float64).reshape(3)

    def learn(self, tip: np.ndarray, action: np.ndarray, next_tip: np.ndarray) -> float:
        """One online step; returns the prediction error (L2) BEFORE the update. Normalized LMS so the
        step size is independent of how hard the babble was — a tiny motion still teaches as much as a
        big one, which is what makes the body schema converge in tens of steps, not thousands."""
        action = np.asarray(action, dtype=np.float64).reshape(3)
        observed_delta = np.asarray(next_tip, dtype=np.float64).reshape(3) - np.asarray(tip, dtype=np.float64).reshape(3)
        pred_delta = self.W @ action
        err = observed_delta - pred_delta
        self.W = self.W + self.lr * np.outer(err, action) / (float(action @ action) + 1e-6)
        return float(np.linalg.norm(err))


@dataclass
class M0sReport:
    steps: int
    error_curve: list[float]
    baseline_error: float               # steady-state prediction error after learning
    perturbation_error: float           # error on the surprising (unexpected) step
    surprise_ratio: float               # perturbation_error / baseline_error
    contact_events: int
    grounded_percepts: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def run_babbling(concept: str = "arm", steps: int = 300, seed: int = 0,
                 store: Any = None) -> M0sReport:
    """The M0s + M1s + reaction loop: motor babbling learns the body schema (error converges), then a
    single unexpected perturbation is injected and the surprise (error spike vs learned baseline) is
    measured. Optionally grounds contact events as perceptual facts via the sensory cortex."""
    from packages.sensory_cortex import cortex as C

    body = SplatraBody(concept, seed=seed)
    schema = BodySchema()
    rng = np.random.default_rng(seed + 1)
    curve: list[float] = []
    contact_events = 0
    percepts: list[Any] = []

    st = body.state()
    for t in range(steps):
        action = rng.normal(0, 0.05, 3)                 # curious/random babble
        tip = st.tip.copy()
        st = body.step(action)
        err = schema.learn(tip, action, st.tip)
        curve.append(err)
        if st.contact:
            contact_events += 1
            percepts += C.from_touch([{"object": "ground", "force": 1.0}])

    baseline = float(np.mean(curve[-20:])) if len(curve) >= 20 else float(np.mean(curve))
    # now a SURPRISE: an unexpected external shove the action never commanded
    tip = st.tip.copy()
    action = rng.normal(0, 0.05, 3)
    st = body.step(action, perturbation=np.array([0.6, -0.4, 0.5]))
    pred = schema.predict(tip, action)
    perturb_err = float(np.linalg.norm(st.tip - pred))
    ratio = perturb_err / max(baseline, 1e-6)

    grounded = 0
    if store is not None or percepts:
        res = C.ground(C.integrate(percepts), store)
        grounded = res.get("stored", 0)

    init = float(np.mean(curve[:20])) if len(curve) >= 20 else float(np.mean(curve))
    converged = bool(baseline < init * 0.4)      # windowed means, not single noisy steps
    return M0sReport(steps=steps, error_curve=curve, baseline_error=baseline,
                     perturbation_error=perturb_err, surprise_ratio=ratio,
                     contact_events=contact_events, grounded_percepts=grounded,
                     extra={"concept": concept, "converged": converged, "init_error": init})
