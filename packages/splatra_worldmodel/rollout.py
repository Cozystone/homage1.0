# -*- coding: utf-8 -*-
"""Multi-step rollout: does the VALIDATED one-step proposer actually SIMULATE?

v0.1 (rich_mechanism_proof, commit c37506e9) VALIDATED the mechanism ONE STEP deep: on
contact-rich elastic dynamics a global linear map cannot fit, the same TurbovecJEPA beat the
linear forward-map ~3x, generalized (held-out/train ~1.25) where the linear map memorized,
and the physics-truth gate held. The named next rung was multi-step rollout stability -- feed
the model's OWN prediction back as the next input, N steps deep, and see whether it stays
bounded or diverges. This module builds exactly that, additively, importing v0.1 read-only.

THE ROLLOUT LOOP (closed-loop, autonomous -- no ground truth after step 0):

    state_0 = true (pos_0, vel_0)                       # only the seed state is real
    for k in 0..H-1:
        light_k   = codec.encode(pos_k, vel_k)          # turbovec light vector (quantized)
        pos_{k+1} = model.predict_next_positions(light_k, action_k, pos_k)   # the proposer
        pos_{k+1} = project(pos_{k+1})                  # OPTIONAL physics-truth membrane
        vel_{k+1} = (pos_{k+1} - pos_k) / dt            # reconstruct velocity from motion
    error(H)  = mean per-particle L2 || pos_H - true_pos_H ||

THE VELOCITY RECONSTRUCTION is the honest consequence of a POSITION-ONLY decoder (jepa.py's
FieldDecoder emits a 3N position delta, no velocity head): to re-encode the next light vector
we must recover velocity, and finite-differencing the model's own predicted motion is the only
ground-truth-free option. It couples position error into the velocity channel, which then
feeds the next light vector -- the genuine compounding a simulator must survive. (The true
simulator stores instantaneous END-of-substep velocity; the average velocity delta/dt differs
during a bounce -- a representation mismatch this module measures, not hides.)

Non-generative, No-LLM, numpy + the existing torch model. WRITES ONLY here; imports v0.1
(contact_dynamics, turbovec_field, physics_truth, baselines, jepa) read-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

from .contact_dynamics import ContactDynamicsParams, ContactLatticeBody
from .physics_truth import PhysicsTruthGate
from .turbovec_field import FIELD_NAMES, FieldState, TurbovecFieldCodec

# A next-position predictor: (light_vector, action, cur_pos) -> predicted next pos (N,3).
PredictFn = Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray]
# A physics projection: (prev_pos, action, cand_pos) -> physical cand_pos (N,3).
ProjectFn = Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray]
# An encoder: FieldState -> flat light vector (lets us swap velocity fidelity).
EncodeFn = Callable[[FieldState], np.ndarray]

HORIZONS: tuple[int, ...] = (1, 5, 10, 25, 50, 100)


# ============================ true dynamics (for chaos + reference) ======================
class TrueDynamics:
    """Roll the EXACT contact simulator forward from an ARBITRARY (pos, vel) state.

    Reconstructs a ContactLatticeBody at the given seed (same rest blob, same lattice bonds,
    same hidden gain, same ground plane as the episode that used that seed), overwrites its
    state, and steps the true nonlinear contact law. In the elastic regime noise=0, so this is
    deterministic and reproduces the recorded episode bit-for-bit from its state_0 -- which is
    also how we get a model-independent divergence floor (perturb IC, re-run truth).
    """

    def __init__(self, params: ContactDynamicsParams, seed: int = 0):
        self.params = params
        self.seed = seed
        self._body = ContactLatticeBody(params, seed=seed)

    def rollout(self, pos0: np.ndarray, vel0: np.ndarray,
                actions: Sequence[np.ndarray]) -> list[FieldState]:
        self._body.pos = np.asarray(pos0, dtype=np.float64).copy()
        self._body.vel = np.asarray(vel0, dtype=np.float64).copy()
        self._body._dyn_rng = np.random.default_rng(self.seed + 7)  # reset (noise=0: unused)
        out = [FieldState(self._body.pos.copy(), self._body.vel.copy())]
        for a in actions:
            st, _ = self._body.step_field(a)
            out.append(st.copy())
        return out


# ============================ velocity-fidelity codec variants ===========================
def default_encode(codec: TurbovecFieldCodec) -> EncodeFn:
    """The v0.1 encoder: every field (position AND velocity) quantized by the fitted codebooks."""
    return codec.encode


def raw_velocity_encode(codec: TurbovecFieldCodec) -> EncodeFn:
    """Quantize POSITION with the codec, pass VELOCITY through UNQUANTIZED (float).

    Isolates the velocity codec as a rollout variable: the light-vector DIM is unchanged
    (n_particles * 6), only the velocity channel's fidelity rises to full float. Position is
    still quantized identically, so any rollout delta is attributable to velocity fidelity.
    """
    from packages.splatra_turbovec.field_quantizer import dequantize_field, quantize_field

    pos_fields = ("x", "y", "z")

    def _encode(state: FieldState) -> np.ndarray:
        cols = state.columns()
        recon: dict[str, np.ndarray] = {}
        for f in FIELD_NAMES:
            if f in pos_fields:
                cb = codec.codebooks[f]
                recon[f] = dequantize_field(cb, quantize_field(cb, cols[f]))
            else:
                recon[f] = np.asarray(cols[f], dtype=np.float64)  # raw velocity, no quantization
        stacked = np.stack([recon[f] for f in FIELD_NAMES], axis=1)
        return stacked.reshape(-1).astype(np.float64)

    return _encode


def fit_hi_fidelity_velocity_codec(train_states: list[FieldState], vel_bits: int = 16
                                   ) -> TurbovecFieldCodec:
    """A codec identical to the default but with high-bit (near-lossless) velocity fields."""
    bits = {"x": 10, "y": 10, "z": 10, "vx": vel_bits, "vy": vel_bits, "vz": vel_bits}
    return TurbovecFieldCodec.fit(train_states, bits=bits)


# ============================ physics-truth projection (membrane in the loop) =============
def project_to_physical(gate: PhysicsTruthGate, prev_pos: np.ndarray, action: np.ndarray,
                        cand_pos: np.ndarray) -> np.ndarray:
    """Project a predicted next field back onto the physical set the gate defines.

    Uses ONLY the gate's invariants (ground plane, teleport cap, implosion floor) -- NEVER
    ground truth. This is the honest 'membrane as rollout stabilizer' operator: a quarantined
    (physics-violating) predicted step is not discarded mid-rollout (that would stall the sim);
    it is CLAMPED back to the nearest physical state and the rollout continues from there.
    """
    prev = np.asarray(prev_pos, dtype=np.float64)
    pos = np.asarray(cand_pos, dtype=np.float64).copy()
    gy = gate.ground_plane

    # 1. ground: lift any particle that penetrated the floor back to the floor.
    pos[:, 1] = np.maximum(pos[:, 1], gy)

    # 2. teleport: cap each particle's per-step displacement at the gate's max_disp.
    disp = pos - prev
    d = np.linalg.norm(disp, axis=1)
    over = d > gate.max_disp
    if over.any():
        scale = gate.max_disp / (d[over] + 1e-9)
        pos[over] = prev[over] + disp[over] * scale[:, None]

    # 3. implosion: if the field collapsed toward its centroid, rescale it back out to the
    #    gate's minimum admissible spread (keeps distinct particles from crashing together).
    prev_c = prev - prev.mean(0)
    prev_spread = float(np.linalg.norm(prev_c, axis=1).mean())
    cand_c = pos - pos.mean(0)
    cand_spread = float(np.linalg.norm(cand_c, axis=1).mean())
    floor = gate.implosion_frac * prev_spread
    if prev_spread > 1e-9 and cand_spread < floor and cand_spread > 1e-9:
        pos = pos.mean(0)[None, :] + cand_c * (floor / cand_spread)
        pos[:, 1] = np.maximum(pos[:, 1], gy)  # re-clamp after rescale
    return pos


def gate_project_fn(gate: PhysicsTruthGate) -> ProjectFn:
    return lambda prev, action, cand: project_to_physical(gate, prev, action, cand)


# ============================ the closed-loop rollout ====================================
def rollout_closed_loop(predict: PredictFn, encode: EncodeFn, init_state: FieldState,
                        actions: Sequence[np.ndarray], dt: float,
                        project: ProjectFn | None = None) -> list[FieldState]:
    """Feed the model's OWN prediction back as the next input, len(actions) steps deep.

    Returns the rolled-out trajectory (len(actions)+1 states). Velocity is reconstructed from
    the model's predicted motion (delta/dt) -- the only ground-truth-free option with a
    position-only decoder. Only init_state is real; every later state is the model's own.
    """
    pos = np.asarray(init_state.pos, dtype=np.float64).copy()
    vel = np.asarray(init_state.vel, dtype=np.float64).copy()
    traj = [FieldState(pos.copy(), vel.copy())]
    for a in actions:
        light = encode(FieldState(pos.copy(), vel.copy()))
        pred = np.asarray(predict(light, np.asarray(a, dtype=np.float64), pos), dtype=np.float64)
        if project is not None:
            pred = project(pos, np.asarray(a, dtype=np.float64), pred)
        vel = (pred - pos) / dt           # reconstruct velocity from the model's own motion
        pos = pred
        traj.append(FieldState(pos.copy(), vel.copy()))
    return traj


def field_error(a: np.ndarray, b: np.ndarray) -> float:
    """Mean per-particle L2 position error (world units) -- the same metric as v0.1."""
    return float(np.linalg.norm(np.asarray(a) - np.asarray(b), axis=1).mean())


# ============================ error-vs-horizon over held-out episodes =====================
@dataclass
class RolloutCurve:
    """Rollout error at each horizon, averaged over held-out episodes (+ per-episode spread)."""
    horizons: tuple[int, ...]
    mean_error: dict[int, float]
    std_error: dict[int, float]
    n_episodes: int
    label: str = ""

    def at(self, h: int) -> float:
        return self.mean_error[h]


def rollout_curve(predict: PredictFn, encode: EncodeFn,
                  episodes: list[tuple[FieldState, list[np.ndarray], list[FieldState]]],
                  dt: float, horizons: Sequence[int] = HORIZONS,
                  project: ProjectFn | None = None, label: str = "") -> RolloutCurve:
    """For each held-out episode (init_state, actions, true_states), roll closed-loop and
    record error at each horizon; average across episodes. episodes[j] = (state_0, actions,
    true_states) with len(true_states) == len(actions)+1 and enough length for max(horizons)."""
    hs = tuple(int(h) for h in horizons)
    per_h: dict[int, list[float]] = {h: [] for h in hs}
    for init_state, actions, true_states in episodes:
        hmax = min(max(hs), len(actions))
        traj = rollout_closed_loop(predict, encode, init_state, actions[:hmax], dt, project=project)
        for h in hs:
            if h < len(traj) and h < len(true_states):
                per_h[h].append(field_error(traj[h].pos, true_states[h].pos))
    mean = {h: (float(np.mean(per_h[h])) if per_h[h] else float("nan")) for h in hs}
    std = {h: (float(np.std(per_h[h])) if per_h[h] else float("nan")) for h in hs}
    n = len(episodes)
    return RolloutCurve(horizons=hs, mean_error=mean, std_error=std, n_episodes=n, label=label)


# ============================ chaos ceiling (intrinsic divergence) ========================
@dataclass
class ChaosCurve:
    """Model-independent divergence of the TRUE dynamics under a tiny IC perturbation eps.

    divergence[H] = mean per-particle L2 between two TRUE trajectories that started eps apart
    and ran the SAME actions. lyapunov is the fitted early-horizon exponential growth rate of
    divergence/eps (a positive value = sensitive dependence = a chaos floor a perfect model
    cannot beat). saturation is the plateau (attractor size) the divergence approaches.
    """
    horizons: tuple[int, ...]
    eps: float
    divergence: dict[int, float]
    amplification: dict[int, float]     # divergence[H] / eps
    lyapunov: float
    saturation: float
    n_ic: int


def intrinsic_divergence(params: ContactDynamicsParams,
                         ic_states: list[tuple[FieldState, list[np.ndarray], int]],
                         horizons: Sequence[int] = HORIZONS, eps: float = 1e-4,
                         n_dirs: int = 3, seed: int = 0) -> ChaosCurve:
    """Perturb each IC's positions by eps in random directions, re-run TRUTH, measure how fast
    the two true trajectories separate. This is the dynamics' OWN chaos, model-free: it upper-
    bounds how stable ANY rollout can be given a state error of size eps."""
    hs = tuple(int(h) for h in horizons)
    rng = np.random.default_rng(seed + 77)
    per_h: dict[int, list[float]] = {h: [] for h in hs}
    for state0, actions, ep_seed in ic_states:
        truth = TrueDynamics(params, seed=ep_seed)
        ref = truth.rollout(state0.pos, state0.vel, actions)
        for _ in range(n_dirs):
            direction = rng.normal(0.0, 1.0, state0.pos.shape)
            direction /= (np.linalg.norm(direction) + 1e-12)
            pos0p = state0.pos + eps * direction
            per = truth.rollout(pos0p, state0.vel, actions)
            for h in hs:
                if h < len(ref) and h < len(per):
                    per_h[h].append(field_error(ref[h].pos, per[h].pos))
    diverge = {h: (float(np.mean(per_h[h])) if per_h[h] else float("nan")) for h in hs}
    amp = {h: (diverge[h] / eps if np.isfinite(diverge[h]) else float("nan")) for h in hs}
    # fit a Lyapunov-like exponent on the early, pre-saturation horizons (log-linear slope).
    small = [h for h in hs if np.isfinite(diverge[h]) and diverge[h] > 0]
    lyap = float("nan")
    if len(small) >= 2:
        early = small[: max(2, len(small) // 2 + 1)]
        xs = np.array(early, dtype=np.float64)
        ys = np.log(np.array([diverge[h] for h in early], dtype=np.float64))
        lyap = float(np.polyfit(xs, ys, 1)[0])
    sat = float(np.nanmax(list(diverge.values()))) if diverge else float("nan")
    return ChaosCurve(horizons=hs, eps=eps, divergence=diverge, amplification=amp,
                      lyapunov=lyap, saturation=sat, n_ic=len(ic_states))


def chaos_floor_for_model(chaos: ChaosCurve, model_one_step_error: float) -> dict[int, float]:
    """Scale the model-free amplification A(H)=divergence/eps by the model's OWN one-step error
    to get the chaos-limited IDEAL for a propagator of that accuracy: e1 * A(H). If the model's
    rollout curve tracks this, it is chaos-limited (as good as possible); if it rises far above,
    the MODEL is failing earlier than the dynamics' intrinsic chaos would force."""
    return {h: (model_one_step_error * chaos.amplification[h]
                if np.isfinite(chaos.amplification[h]) else float("nan"))
            for h in chaos.horizons}


# ============================ usable-horizon verdict =====================================
def usable_horizon(model_curve: RolloutCurve, persistence_curve: RolloutCurve,
                   tolerance: float | None = None) -> dict[str, object]:
    """Locate the horizon where the model stops being useful.

    vs_persistence: largest horizon H at which model error < persistence error (beyond it the
        model is worse than doing nothing).
    vs_tolerance: largest H at which model error < a fixed physical tolerance (if given).
    """
    hs = model_curve.horizons
    beats_persist = [h for h in hs
                     if np.isfinite(model_curve.at(h)) and np.isfinite(persistence_curve.at(h))
                     and model_curve.at(h) < persistence_curve.at(h)]
    out: dict[str, object] = {
        "beats_persistence_through": (max(beats_persist) if beats_persist else 0),
        "beats_persistence_at": {h: (model_curve.at(h) < persistence_curve.at(h)) for h in hs},
    }
    if tolerance is not None:
        under_tol = [h for h in hs if np.isfinite(model_curve.at(h)) and model_curve.at(h) < tolerance]
        out["tolerance"] = tolerance
        out["under_tolerance_through"] = (max(under_tol) if under_tol else 0)
    return out
