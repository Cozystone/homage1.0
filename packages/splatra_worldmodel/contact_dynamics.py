# -*- coding: utf-8 -*-
"""RICH dynamics: a contact-rich / non-rigid / frictional body a GLOBAL LINEAR MAP CANNOT FIT.

The v0 mechanism proof (mechanism_proof.py, #74) landed an HONEST NEGATIVE: on the toy
falling/deforming body, JEPA-over-turbovec was ~2.6x WORSE than a global ridge linear
forward-map, because that toy is NEAR-LINEAR (gravity + hidden-gain action + a linear
cohesion spring; the only nonlinearity is a single ground clip). A full-dimensional linear
regressor over the light vector -- which carries velocity -- is near-optimal there.

#74 named the next rung: the mechanism can only pay off on dynamics a global linear map
genuinely CANNOT fit. This module builds exactly that, keeping EVERYTHING else identical
(same TurbovecJEPA, same baselines, same physics-truth gate, same held-out protocol); ONLY
the force law + initial configuration change. Three strong, physical nonlinearities are
added on top of the same skeleton (gravity + hidden-G action + ground):

  (1) PAIRWISE COLLISIONS / SELF-COLLISION (contact-rich, multi-body).  Each particle repels
      every OTHER particle it overlaps: F_i = sum_j hinge(2r - |p_i-p_j|) * k_c * unit(p_i-p_j).
      This is a function of pairwise Euclidean distances, their reciprocals, and an on/off
      hinge -- it is NOT in the span of any linear functional of the flattened state vector.
      A linear map's output for one coordinate is a FIXED linear combination of inputs; it
      cannot compute a norm |p_i-p_j|, a reciprocal 1/d, or a data-dependent contact mask.
      => provably irreducible error wherever the contact topology varies across samples.
  (2) NON-RIGID MATERIAL with CUBIC-STIFFENING springs (material stiffness, non-rigid
      deformation).  Each particle is bonded to its k nearest REST neighbors by a spring with
      a nonlinear restoring force f = k1*ext + k3*ext^3 (ext = extension). The cubic term is
      non-affine in position -> a deforming elastic solid, not a rigid translate.
  (3) CONTACT-GATED COULOMB FRICTION (velocity-dependent, piecewise).  Tangential velocity is
      damped ONLY where a particle is in contact (ground or a neighbor) -> a piecewise,
      velocity-dependent map.

The initial configuration is a PACKED GRANULAR BLOB rather than the toy's hollow supershape
shell: a shell has near-coincident particles (singular collision forces) and cannot
self-collide, so it is the wrong substrate for a contact regime. We still reuse the proven
SplatraBody kernel unchanged -- its HIDDEN gain ``_G``, its damping ``_damp``, its body
noise ``_noise``, its particle COUNT (so the light-vector dim is identical to #74), and the
ground plane ``_GROUND_Y`` -- and ``synthesize_form`` is still invoked by the base ctor. The
blob packing is the new regime's initial condition, the object under test.

Integration is EXPLICIT sub-stepped Euler (``substeps`` per recorded dt) for stability under
stiff contacts; the recorded transition (what every model predicts) is one full dt, i.e. the
composition of ``substeps`` nonlinear substeps -- which is MORE nonlinear, not less.

Deterministic (noise off => reproducible), numpy, CPU, No-LLM. Returns the SAME ``Episode``
dataclass as forward_model, so the proof's ``_episodes_to_dataset`` consumes it unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Read-only reuse of the proven kernel (hidden G, damping, body noise, ground plane, count).
from packages.embodiment.splatra_body import _GROUND_Y, SplatraBody

from .forward_model import Episode  # SAME Episode contract as the toy (states/actions/contacts)
from .turbovec_field import FieldState


@dataclass
class ContactDynamicsParams:
    """Physics knobs for the contact-rich regime + a complexity ladder for the crossover sweep.

    The ladder interpolates from a linear-friendly settle (level 0, ~the #74 toy's regime) to a
    strongly non-linear elastic bounce (level 3): raising restitution + cubic stiffness and
    LOWERING damping heats the contact topology so it VARIES across samples -- which is what
    makes the pairwise-collision nonlinearity impossible for a global linear map to fit.
    """

    count: int = 200            # -> synthesize_form -> 196 particles (identical light-dim to #74)
    spacing: float = 0.42       # granular-blob lattice spacing (world units)
    lift: float = 1.6           # drop height above the ground plane
    gravity: float = 2.0
    dt: float = 0.15            # recorded timestep (what every model predicts over)
    substeps: int = 8           # internal Euler substeps per recorded dt (stiff-contact stability)
    k_lattice: float = 8.0      # linear spring stiffness (rest-shape cohesion)
    k_cubic: float = 80.0       # CUBIC-stiffening term (the core material nonlinearity)
    k_contact: float = 25.0     # pairwise-collision repulsion stiffness
    contact_radius_frac: float = 0.60   # collision radius as a fraction of median rest spacing
    n_bonds: int = 6            # lattice bonds per particle (k nearest rest neighbors)
    restitution: float = 0.85   # ground bounce (elasticity)
    friction: float = 0.10      # contact-gated tangential velocity damping (Coulomb-like)
    damping: float | None = 0.995   # None -> reuse SplatraBody._damp; else override
    noise: float | None = 0.0       # None -> reuse SplatraBody._noise; 0.0 -> deterministic
    action_scale: float = 0.05

    # --- complexity ladder (crossover sweep) --------------------------------------------
    @classmethod
    def ladder(cls, level: int) -> "ContactDynamicsParams":
        """Increasing 'dynamics complexity' L0..L3. L0 ~ near-linear; L3 = strong nonlinear."""
        presets = {
            0: dict(restitution=0.10, damping=0.90, k_cubic=0.0, k_lattice=5.0,
                    k_contact=10.0, friction=0.30, noise=None, lift=1.2),   # ~toy-like settle
            1: dict(restitution=0.35, damping=0.94, k_cubic=40.0, k_lattice=6.0,
                    k_contact=16.0, friction=0.25, noise=0.0, lift=1.3),
            2: dict(restitution=0.60, damping=0.97, k_cubic=120.0, k_lattice=7.0,
                    k_contact=20.0, friction=0.18, noise=0.0, lift=1.5),
            3: dict(restitution=0.85, damping=0.995, k_cubic=80.0, k_lattice=8.0,
                    k_contact=25.0, friction=0.10, noise=0.0, lift=1.6),    # elastic bounce
        }
        if level not in presets:
            raise ValueError(f"ladder level must be 0..3, got {level}")
        return cls(**presets[level])

    @classmethod
    def elastic(cls) -> "ContactDynamicsParams":
        """The primary make-or-break regime (== ladder level 3)."""
        return cls.ladder(3)


def _packed_blob(n: int, seed: int, spacing: float) -> np.ndarray:
    """A compact jittered 3D grid of exactly ``n`` points (a granular blob), centered at 0."""
    rng = np.random.default_rng(seed)
    side = int(np.ceil(n ** (1.0 / 3.0)))
    xs = np.arange(side)
    grid = np.stack(np.meshgrid(xs, xs, xs, indexing="ij"), axis=-1).reshape(-1, 3).astype(np.float64)
    grid = grid[:n]
    grid = grid + rng.uniform(-0.12, 0.12, grid.shape)   # jitter off the perfect lattice
    grid = grid * float(spacing)
    grid = grid - grid.mean(0)
    return grid


class ContactLatticeBody(SplatraBody):
    """A packed granular / soft body with pairwise collisions, cubic springs, friction, ground.

    Subclass of SplatraBody: reuses the HIDDEN gain ``self._G``, damping ``self._damp``, body
    noise ``self._noise``, particle COUNT, and the ground plane. The base ``step`` (rigid
    translate) is left intact; ``step_field`` is the new per-particle contact law over the
    full field. ``synthesize_form`` is invoked by the base ctor; the granular blob is the new
    regime's initial condition (a shell cannot self-collide).
    """

    def __init__(self, params: ContactDynamicsParams, seed: int = 0):
        super().__init__("arm", count=params.count, seed=seed)
        self.p = params
        n = int(self.pos.shape[0])                 # exact particle count from synthesize_form
        self.n_particles = n
        self._dyn_rng = np.random.default_rng(seed + 7)
        self._damp_eff = self.p.damping if self.p.damping is not None else self._damp
        self._noise_eff = self.p.noise if self.p.noise is not None else self._noise
        # rest blob + its k-nearest-neighbor lattice bonds (computed once, in the rest shape).
        self._rest_blob = _packed_blob(n, seed, params.spacing)
        self._bond_idx, self._bond_len = self._build_lattice(self._rest_blob, params.n_bonds)
        med_nn = float(np.median(self._bond_len[:, 0]))
        self._r_contact = med_nn * params.contact_radius_frac
        # place the blob above the ground so it falls, contacts, deforms and (elastically) bounces.
        self.pos = self._rest_blob + np.array([0.0, params.lift, 0.0])
        self.vel = np.zeros_like(self.pos)

    # ---- lattice ----------------------------------------------------------------------
    @staticmethod
    def _build_lattice(blob: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        """k nearest rest neighbors per particle + their rest lengths (pure-numpy kNN)."""
        # O(N^2) once at construction; N is small (~196). No scipy dependency.
        diff = blob[:, None, :] - blob[None, :, :]
        dist = np.sqrt((diff ** 2).sum(-1))
        np.fill_diagonal(dist, np.inf)
        idx = np.argsort(dist, axis=1)[:, :k]
        rest = np.take_along_axis(dist, idx, axis=1)
        return idx.astype(np.int64), rest

    # ---- state ------------------------------------------------------------------------
    def field_state(self) -> FieldState:
        return FieldState(pos=self.pos.copy(), vel=self.vel.copy())

    def reset(self, init_offset: np.ndarray | None = None,
              init_vel: np.ndarray | None = None) -> FieldState:
        """Re-place the blob (new initial condition) and zero/seed its velocity."""
        centroid0 = np.array([0.0, self.p.lift, 0.0])
        if init_offset is not None:
            centroid0 = centroid0 + np.asarray(init_offset, dtype=np.float64).reshape(3)
        self.pos = self._rest_blob + centroid0
        self.vel = np.zeros_like(self.pos)
        if init_vel is not None:
            self.vel[:] = np.asarray(init_vel, dtype=np.float64).reshape(3)
        return self.field_state()

    # ---- the contact law --------------------------------------------------------------
    def step_field(self, action: np.ndarray) -> tuple[FieldState, bool]:
        """Advance one recorded dt via ``substeps`` nonlinear substeps. Returns (state, contact).

        Per substep (h = dt/substeps), for every particle i:
          a_i  = -g*y_hat                                            # gravity
          a_i += G @ action                                         # action via the HIDDEN gain
          a_i += sum_bonds -(k1*ext + k3*ext^3) * unit(p_i - p_j)   # cubic-stiffening lattice
          a_i += sum_j hinge(2r - |p_i-p_j|) * k_c * unit(p_i-p_j)  # PAIRWISE COLLISION (nonlinear)
          v_i += a_i * h
          if in_contact(i):  v_i.xz *= (1 - friction)               # contact-gated friction
          v_i *= damp ; v_i += noise
          p_i += v_i * h
          if p_i.y < GROUND: p_i.y = GROUND ; v_i.y = -restitution * v_i.y   # ground bounce
        """
        p = self.p
        h = p.dt / p.substeps
        action = np.asarray(action, dtype=np.float64).reshape(3)
        g_action = (self._G @ action)[None, :]
        contact_any = False
        two_r = 2.0 * self._r_contact

        for _ in range(p.substeps):
            acc = np.zeros_like(self.pos)
            acc[:, 1] -= p.gravity
            acc += g_action
            # (2) cubic-stiffening lattice springs (non-rigid material)
            if p.k_lattice or p.k_cubic:
                pj = self.pos[self._bond_idx]                     # (N, k, 3)
                dvec = self.pos[:, None, :] - pj                  # (N, k, 3)
                dist = np.sqrt((dvec ** 2).sum(-1)) + 1e-9        # (N, k)
                ext = dist - self._bond_len
                fmag = -(p.k_lattice * ext + p.k_cubic * ext ** 3)
                acc += (fmag[..., None] * (dvec / dist[..., None])).sum(1)
            # (1) pairwise collisions / self-collision (the star nonlinearity)
            diff = self.pos[:, None, :] - self.pos[None, :, :]    # (N, N, 3)
            dd = np.sqrt((diff ** 2).sum(-1)) + 1e-9              # (N, N)
            overlap = two_r - dd
            np.fill_diagonal(overlap, 0.0)
            active = overlap > 0.0
            if active.any():
                contact_any = True
            rep = np.where(active, p.k_contact * overlap, 0.0)    # (N, N)
            acc += (rep[..., None] * (diff / dd[..., None])).sum(1)
            # integrate velocity
            self.vel = self.vel + acc * h
            # (3) contact-gated Coulomb-like friction (velocity-dependent, piecewise)
            near_ground = self.pos[:, 1] < (_GROUND_Y + 0.05)
            in_contact = near_ground | active.any(1)
            if p.friction:
                self.vel[in_contact, 0] *= (1.0 - p.friction)
                self.vel[in_contact, 2] *= (1.0 - p.friction)
            # global damping + irreducible body noise
            self.vel *= self._damp_eff
            if self._noise_eff:
                self.vel += self._dyn_rng.normal(0.0, self._noise_eff, self.pos.shape)
            # integrate position
            self.pos = self.pos + self.vel * h
            # ground contact -- clip + reflect (nonlinear)
            below = self.pos[:, 1] < _GROUND_Y
            if below.any():
                contact_any = True
                self.pos[below, 1] = _GROUND_Y
                self.vel[below, 1] = -p.restitution * self.vel[below, 1]

        return self.field_state(), contact_any


def simulate_contact_episode(params: ContactDynamicsParams, steps: int, seed: int,
                             init_offset: np.ndarray | None = None,
                             init_vel: np.ndarray | None = None) -> Episode:
    """Drop-and-bounce a granular/soft body for ``steps`` and record the field trajectory.

    Returns the SAME ``Episode`` dataclass as the toy (states / actions / contacts), so the
    proof's ``_episodes_to_dataset`` consumes it with zero changes.
    """
    body = ContactLatticeBody(params, seed=seed)
    st = body.reset(init_offset=init_offset, init_vel=init_vel)
    act_rng = np.random.default_rng(seed + 101)
    ep = Episode(states=[st])
    for _ in range(steps):
        action = act_rng.normal(0.0, params.action_scale, 3)
        st, contact = body.step_field(action)
        ep.actions.append(action)
        ep.states.append(st.copy())
        ep.contacts.append(bool(contact))
    return ep


def contact_ground_y() -> float:
    """Expose the reused ground plane (read-only) for tests."""
    return float(_GROUND_Y)
