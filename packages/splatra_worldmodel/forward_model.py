# -*- coding: utf-8 -*-
"""Toy hidden dynamics: a falling / deforming SPLATRA body (the ground truth to predict).

Design docs/ATANOR_vjepa_fusion.md sec 9 says: generalize the proven splatra_body forward
loop from a 9-d pose to the full turbovec FIELD-delta by WRAPPING/subclassing --
without editing embodiment/splatra_body.py.

``ToyDeformingBody`` SUBCLASSES ``SplatraBody`` and reuses, unchanged:
  * its particle cloud from ``synthesize_form`` (``self.pos``),
  * its HIDDEN action gain ``self._G`` (the body's own dynamics, unknown to any model),
  * its damping ``self._damp`` and irreducible sensorimotor noise ``self._noise``,
  * the ground plane ``_GROUND_Y``.

It adds ``step_field`` -- a per-particle dynamics (the base ``step`` is a rigid translate;
a world model needs a deforming field). The law is LINEAR (gravity + action-via-G + a
shape-cohesion spring + damping) EXCEPT for one hard NONLINEARITY: ground contact clips
position at ``_GROUND_Y`` and reflects the vertical velocity. That clip is exactly the
structure a linear forward-map baseline provably cannot represent and a nonlinear latent
predictor can -- it is the crux the mechanism proof measures.

Deterministic, numpy, CPU, No-LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Read-only import of the proven act->predict->surprise kernel (design sec 9).
from packages.embodiment.splatra_body import _GROUND_Y, SplatraBody

from .turbovec_field import FieldState


@dataclass
class DynamicsParams:
    concept: str = "arm"
    count: int = 200
    gravity: float = 2.0
    dt: float = 0.15
    k_spring: float = 6.0        # shape-cohesion stiffness (keeps the body's form as it moves)
    restitution: float = 0.30    # ground bounce (0 = fully inelastic, 1 = elastic)
    lift: float = 1.0            # initial height above rest so there is a fall to predict
    action_scale: float = 0.05   # babble action magnitude (matches splatra_body)


class ToyDeformingBody(SplatraBody):
    """A deforming particle body with gravity, action-via-hidden-G, cohesion and a ground.

    Subclass of SplatraBody: reuses ``self.pos`` (initial cloud), ``self._G`` (hidden gain),
    ``self._damp`` (damping), ``self._noise`` (body noise). The base ``step`` is left intact;
    ``step_field`` is the new per-particle law over the full field.
    """

    def __init__(self, params: DynamicsParams, seed: int = 0):
        super().__init__(params.concept, count=params.count, seed=seed)
        self.p = params
        self._dyn_rng = np.random.default_rng(seed + 7)
        # rest offsets relative to the body centroid -> a shape the cohesion spring restores.
        base = self.pos.copy()
        self._rest_offset = base - base.mean(0)
        # lift the whole body so it must fall toward the ground plane.
        self.pos = base + np.array([0.0, params.lift, 0.0])
        self.vel = np.zeros_like(self.pos)

    def reset(self, init_offset: np.ndarray | None = None,
              init_vel: np.ndarray | None = None) -> FieldState:
        """Re-place the body (new initial condition) and zero/seed its velocity."""
        base = (self.pos - self.vel * 0.0)  # keep shape; recompute from rest offsets
        centroid0 = np.array([0.0, self.p.lift, 0.0])
        if init_offset is not None:
            centroid0 = centroid0 + np.asarray(init_offset, dtype=np.float64).reshape(3)
        self.pos = self._rest_offset + centroid0
        self.vel = np.zeros_like(self.pos)
        if init_vel is not None:
            self.vel[:] = np.asarray(init_vel, dtype=np.float64).reshape(3)
        _ = base  # (kept for clarity; not used)
        return self.field_state()

    def field_state(self) -> FieldState:
        return FieldState(pos=self.pos.copy(), vel=self.vel.copy())

    def step_field(self, action: np.ndarray) -> FieldState:
        """Advance the full field one dt. Returns the NEW field state.

        Law (per particle i):
          v_i += (-g * y_hat) * dt                      # gravity
          v_i += (G @ action) * dt                      # action via the HIDDEN gain G
          v_i += k_spring * (centroid + rest_offset_i - p_i) * dt   # shape cohesion
          v_i *= damp ; v_i += noise
          p_i += v_i * dt
          if p_i.y < GROUND_Y:  p_i.y = GROUND_Y ; v_i.y = -restitution * v_i.y   # NONLINEAR
        """
        p, dt = self.p, self.p.dt
        action = np.asarray(action, dtype=np.float64).reshape(3)

        # gravity (down = -y)
        self.vel[:, 1] += -p.gravity * dt
        # action transformed by the body's hidden gain G (the splatra_body kernel), applied to all
        self.vel += (self._G @ action)[None, :] * dt
        # shape-cohesion spring: pull each particle toward its rest offset from the CURRENT centroid
        centroid = self.pos.mean(0)
        target = centroid[None, :] + self._rest_offset
        self.vel += p.k_spring * (target - self.pos) * dt
        # damping + irreducible body noise (schema can never predict this away)
        self.vel *= self._damp
        self.vel += self._dyn_rng.normal(0.0, self._noise, self.pos.shape)
        # integrate
        self.pos = self.pos + self.vel * dt
        # GROUND CONTACT -- the single hard nonlinearity
        below = self.pos[:, 1] < _GROUND_Y
        self.pos[below, 1] = _GROUND_Y
        self.vel[below, 1] = -p.restitution * self.vel[below, 1]
        return self.field_state()


@dataclass
class Transition:
    x_light: np.ndarray      # turbovec light vector of the current field (JEPA input)
    action: np.ndarray       # (3,)
    x_next_light: np.ndarray # turbovec light vector of the next field (EMA target input)
    pos: np.ndarray          # (N,3) TRUE current positions (for applying predicted delta)
    pos_next: np.ndarray     # (N,3) TRUE next positions (scorecard target)
    delta: np.ndarray        # (N,3) TRUE per-particle displacement (decoder target)
    contact: bool            # did this step involve ground contact (nonlinear regime)?


@dataclass
class Episode:
    states: list[FieldState] = field(default_factory=list)
    actions: list[np.ndarray] = field(default_factory=list)
    contacts: list[bool] = field(default_factory=list)


def simulate_episode(params: DynamicsParams, steps: int, seed: int,
                     init_offset: np.ndarray | None = None,
                     init_vel: np.ndarray | None = None) -> Episode:
    """Drop-and-deform: babble actions for ``steps`` and record the field trajectory."""
    body = ToyDeformingBody(params, seed=seed)
    st = body.reset(init_offset=init_offset, init_vel=init_vel)
    act_rng = np.random.default_rng(seed + 101)
    ep = Episode(states=[st])
    for _ in range(steps):
        action = act_rng.normal(0.0, params.action_scale, 3)
        prev_below = (body.pos[:, 1] <= _GROUND_Y + 1e-6).any()
        st = body.step_field(action)
        now_below = (body.pos[:, 1] <= _GROUND_Y + 1e-6).any()
        ep.actions.append(action)
        ep.states.append(st.copy())
        ep.contacts.append(bool(prev_below or now_below))
    return ep


def ground_y() -> float:
    """Expose the imported ground plane (read-only) for the physics gate + tests."""
    return float(_GROUND_Y)
