# -*- coding: utf-8 -*-
"""Rollout proof: can the VALIDATED one-step proposer actually SIMULATE, N steps deep?

v0.1 (rich_mechanism_proof) validated the mechanism ONE step deep. This runner answers the
named next rung with numbers, honestly:

  1. MULTI-STEP ROLLOUT -- feed the model's own prediction back, measure error-vs-horizon
     (H = 1,5,10,25,50,100) for JEPA vs the linear forward-map vs persistence, closed-loop,
     on HELD-OUT elastic dynamics. Does JEPA stay bounded while the linear map diverges?
  2. CHAOS CEILING -- the dynamics' OWN divergence under a tiny IC perturbation (model-free).
     Is a large rollout error the intrinsic chaos floor a perfect model also hits, or the
     MODEL failing earlier? Reported side by side, separated honestly.
  3. VELOCITY CODEC FIDELITY -- v0.1 flagged turbovec velocity distortion ~0.022 in the
     bounce. Retrain + roll with UNQUANTIZED velocity vs the default 8-bit codec: does higher
     velocity fidelity extend the stable horizon (is the codec a rollout bottleneck)?
  4. PHYSICS-TRUTH IN THE LOOP -- route every rollout step through the gate (clamp physics-
     violating predicted steps back to physical). Is the membrane a rollout STABILIZER, not
     just a one-step filter?

The verdict names the USABLE HORIZON (where JEPA rollout error stays below persistence / a
physical tolerance) and states plainly whether 'real-time autonomous sim' is earned or the
model is stable to only a few steps. Same model (<=25M), same codec, same gate, same held-out
protocol as v0.1; ONLY the evaluation is multi-step. No-LLM, non-generative.

Run foreground:
  python -X utf8 -m packages.splatra_worldmodel.rollout_proof            # full
  python -X utf8 -m packages.splatra_worldmodel.rollout_proof --fast     # smoke
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .baselines import LinearForwardMap, PersistenceBaseline
from .contact_dynamics import ContactDynamicsParams, simulate_contact_episode
from .forward_model import Episode
from .jepa import JEPAConfig, train_jepa
from .mechanism_proof import CandidateSample, Dataset, _field_error
from .physics_truth import PhysicsTruthGate
from .rollout import (
    HORIZONS,
    ChaosCurve,
    RolloutCurve,
    chaos_floor_for_model,
    default_encode,
    fit_hi_fidelity_velocity_codec,
    gate_project_fn,
    intrinsic_divergence,
    raw_velocity_encode,
    rollout_curve,
    usable_horizon,
)
from .turbovec_field import FIELD_NAMES, FieldState, TurbovecFieldCodec


# ============================ config =====================================================
@dataclass
class RolloutProofConfig:
    dynamics: ContactDynamicsParams = field(default_factory=ContactDynamicsParams.elastic)
    train_episodes: int = 48
    heldout_episodes: int = 12
    train_steps: int = 40        # one-step training data length
    rollout_steps: int = 100     # long held-out trajectories for the rollout curves
    epochs: int = 3000
    d_emb: int = 64
    d_hidden: int = 128
    seed: int = 0
    chaos_ic: int = 4            # held-out ICs used for the intrinsic divergence measurement
    chaos_eps: float = 1e-4
    tolerance_frac: float = 0.10  # physical tolerance = this fraction of the body diameter
    run_codec_sweep: bool = True
    run_gated: bool = True
    verbose: bool = False

    @staticmethod
    def fast() -> "RolloutProofConfig":
        return RolloutProofConfig(train_episodes=8, heldout_episodes=3, train_steps=16,
                                  rollout_steps=30, epochs=300, chaos_ic=2, seed=0)


# ============================ data =======================================================
def _build_episodes(cfg: RolloutProofConfig) -> tuple[list[Episode], list[Episode], list[int]]:
    """SAME disjoint-IC held-out protocol as v0.1; held-out episodes are LONG (rollout_steps)."""
    d = cfg.dynamics
    off_tr = np.random.default_rng(42)
    off_ho = np.random.default_rng(999)
    train = [
        simulate_contact_episode(d, cfg.train_steps, seed=1000 + i,
                                 init_offset=off_tr.uniform(-0.3, 0.3, 3),
                                 init_vel=off_tr.uniform(-0.10, 0.10, 3))
        for i in range(cfg.train_episodes)
    ]
    heldout_seeds = [5000 + j for j in range(cfg.heldout_episodes)]
    heldout = [
        simulate_contact_episode(d, cfg.rollout_steps, seed=heldout_seeds[j],
                                 init_offset=off_ho.uniform(-0.45, 0.45, 3),
                                 init_vel=off_ho.uniform(-0.15, 0.15, 3))
        for j in range(cfg.heldout_episodes)
    ]
    return train, heldout, heldout_seeds


def _build_dataset(encode: Callable[[FieldState], np.ndarray], episodes: list[Episode]) -> Dataset:
    """One-step dataset with a SWAPPABLE encoder (for the velocity-codec sweep)."""
    light, action, light_next, pos, pos_next, delta, contact = [], [], [], [], [], [], []
    for ep in episodes:
        for t in range(len(ep.actions)):
            cur, nxt = ep.states[t], ep.states[t + 1]
            light.append(encode(cur))
            light_next.append(encode(nxt))
            action.append(ep.actions[t])
            pos.append(cur.pos)
            pos_next.append(nxt.pos)
            delta.append(nxt.pos - cur.pos)
            contact.append(ep.contacts[t])
    return Dataset(light=np.asarray(light), action=np.asarray(action),
                   light_next=np.asarray(light_next), pos=np.asarray(pos),
                   pos_next=np.asarray(pos_next), delta=np.asarray(delta),
                   contact=np.asarray(contact, dtype=bool))


def _train_on(cfg: RolloutProofConfig, encode, train_eps, n_particles, light_dim, gate):
    """Train the SAME TurbovecJEPA on a dataset built with the given encoder (gate-filtered)."""
    ds = _build_dataset(encode, train_eps)
    verified = gate.filter_transitions([
        CandidateSample(FieldState(ds.pos[i], np.zeros_like(ds.pos[i])), ds.action[i],
                        FieldState(ds.pos_next[i], np.zeros_like(ds.pos_next[i])), "true", index=i)
        for i in range(ds.light.shape[0])
    ])
    keep = np.array([it.index for it in verified.kept], dtype=int)
    jcfg = JEPAConfig(d_light=light_dim, n_particles=n_particles, d_emb=cfg.d_emb, d_hidden=cfg.d_hidden)
    model, report = train_jepa(jcfg, ds.light[keep], ds.action[keep], ds.light_next[keep],
                               ds.delta[keep], epochs=cfg.epochs, seed=cfg.seed,
                               log_every=(max(1, cfg.epochs // 5) if cfg.verbose else 0))
    return model, report, ds


# ============================ scorecard ==================================================
@dataclass
class RolloutScorecard:
    n_particles: int
    light_dim: int
    param_counts: dict[str, int]
    compression_ratio: float
    codec_velocity_distortion: dict[str, float]
    body_diameter: float
    tolerance: float
    horizons: tuple[int, ...]
    # (1) error-vs-horizon (default codec, ungated)
    jepa: RolloutCurve
    linear: RolloutCurve
    persistence: RolloutCurve
    jepa_one_step: float
    linear_one_step: float
    # (2) chaos
    chaos: ChaosCurve
    chaos_floor_jepa: dict[int, float]
    # (3) velocity codec
    jepa_rawvel: RolloutCurve | None
    rawvel_velocity_distortion: dict[str, float] | None
    # (4) physics-truth in the loop
    jepa_gated: RolloutCurve | None
    jepa_gated_violation_free: bool
    # verdict
    usable: dict[str, object]
    usable_rawvel: dict[str, object] | None
    usable_gated: dict[str, object] | None
    verdict: str


def run_rollout_proof(cfg: RolloutProofConfig | None = None) -> RolloutScorecard:
    cfg = cfg or RolloutProofConfig()
    dt = cfg.dynamics.dt
    train_eps, heldout_eps, heldout_seeds = _build_episodes(cfg)

    train_states = [st for ep in train_eps for st in ep.states]
    codec = TurbovecFieldCodec.fit(train_states)
    n_particles = train_states[0].n
    light_dim = codec.light_vector_dim(n_particles)
    gate = PhysicsTruthGate()

    # --- train the VALIDATED proposer (default codec) ---
    enc_default = default_encode(codec)
    model, report, train_ds = _train_on(cfg, enc_default, train_eps, n_particles, light_dim, gate)

    persistence = PersistenceBaseline()
    linear = LinearForwardMap.fit(train_ds.light, train_ds.action, train_ds.delta)

    def jepa_predict(l, a, p):
        return model.predict_next_positions(l, a, p)

    # --- rollout episodes: (state_0, actions, true_states) on the LONG held-out set ---
    roll_eps = [(ep.states[0], ep.actions, ep.states) for ep in heldout_eps]

    # --- (1) error-vs-horizon, default codec, ungated ---
    jepa_curve = rollout_curve(jepa_predict, enc_default, roll_eps, dt, HORIZONS, label="JEPA")
    linear_curve = rollout_curve(linear.predict_next_positions, enc_default, roll_eps, dt,
                                 HORIZONS, label="linear")
    persist_curve = rollout_curve(persistence.predict_next_positions, enc_default, roll_eps, dt,
                                  HORIZONS, label="persistence")

    # one-step held-out field error (the model's effective per-step accuracy e1) via v0.1 metric.
    heldout_ds = _build_dataset(enc_default, heldout_eps)
    jepa_e1 = _field_error(jepa_predict, heldout_ds)
    linear_e1 = _field_error(linear.predict_next_positions, heldout_ds)

    # --- (2) chaos ceiling: intrinsic divergence of the TRUE dynamics ---
    ic_states = [(heldout_eps[j].states[0], heldout_eps[j].actions, heldout_seeds[j])
                 for j in range(min(cfg.chaos_ic, len(heldout_eps)))]
    chaos = intrinsic_divergence(cfg.dynamics, ic_states, HORIZONS, eps=cfg.chaos_eps, seed=cfg.seed)
    chaos_floor = chaos_floor_for_model(chaos, jepa_e1)

    # body scale + physical tolerance
    p0 = heldout_eps[0].states[0].pos
    diameter = float(np.linalg.norm(p0 - p0.mean(0), axis=1).max() * 2.0)
    tolerance = cfg.tolerance_frac * diameter

    # --- (3) velocity codec fidelity: retrain + roll with UNQUANTIZED velocity ---
    jepa_rawvel_curve = None
    rawvel_distortion = None
    usable_rawvel = None
    if cfg.run_codec_sweep:
        enc_raw = raw_velocity_encode(codec)
        model_raw, _, _ = _train_on(cfg, enc_raw, train_eps, n_particles, light_dim, gate)

        def jepa_raw_predict(l, a, p):
            return model_raw.predict_next_positions(l, a, p)

        jepa_rawvel_curve = rollout_curve(jepa_raw_predict, enc_raw, roll_eps, dt, HORIZONS,
                                          label="JEPA(raw-vel)")
        # velocity distortion of a near-lossless codec for reference (default vs hi-fidelity).
        hi = fit_hi_fidelity_velocity_codec(train_states, vel_bits=16)
        rawvel_distortion = {f: hi.distortion_pooled(train_states)[f] for f in ("vx", "vy", "vz")}
        usable_rawvel = usable_horizon(jepa_rawvel_curve, persist_curve, tolerance)

    # --- (4) physics-truth in the loop: gated rollout ---
    jepa_gated_curve = None
    gated_violation_free = False
    usable_gated = None
    if cfg.run_gated:
        proj = gate_project_fn(gate)
        jepa_gated_curve = rollout_curve(jepa_predict, enc_default, roll_eps, dt, HORIZONS,
                                         project=proj, label="JEPA(gated)")
        gated_violation_free = _gated_rollout_stays_physical(jepa_predict, enc_default, roll_eps,
                                                             dt, gate)
        usable_gated = usable_horizon(jepa_gated_curve, persist_curve, tolerance)

    usable = usable_horizon(jepa_curve, persist_curve, tolerance)

    verdict = _verdict(usable, jepa_curve, persist_curve, chaos, tolerance)

    vel_dist = {f: codec.distortion_pooled(train_states)[f] for f in ("vx", "vy", "vz")}
    return RolloutScorecard(
        n_particles=n_particles, light_dim=light_dim, param_counts=report.param_counts,
        compression_ratio=codec.compression_ratio, codec_velocity_distortion=vel_dist,
        body_diameter=diameter, tolerance=tolerance, horizons=HORIZONS,
        jepa=jepa_curve, linear=linear_curve, persistence=persist_curve,
        jepa_one_step=jepa_e1, linear_one_step=linear_e1,
        chaos=chaos, chaos_floor_jepa=chaos_floor,
        jepa_rawvel=jepa_rawvel_curve, rawvel_velocity_distortion=rawvel_distortion,
        jepa_gated=jepa_gated_curve, jepa_gated_violation_free=gated_violation_free,
        usable=usable, usable_rawvel=usable_rawvel, usable_gated=usable_gated, verdict=verdict,
    )


def _gated_rollout_stays_physical(predict, encode, roll_eps, dt, gate: PhysicsTruthGate) -> bool:
    """Confirm a gated rollout NEVER emits a physics-violating field (the membrane holds)."""
    from .rollout import rollout_closed_loop
    proj = gate_project_fn(gate)
    for init_state, actions, _true in roll_eps:
        traj = rollout_closed_loop(predict, encode, init_state, actions, dt, project=proj)
        for k in range(1, len(traj)):
            prev = FieldState(traj[k - 1].pos, np.zeros_like(traj[k - 1].pos))
            cand = FieldState(traj[k].pos, np.zeros_like(traj[k].pos))
            if not gate.verify(prev, actions[k - 1], cand).ok:
                return False
    return True


def _first_breakdown(curve: RolloutCurve, tol: float) -> int:
    """First horizon whose (finite) error reaches the tolerance; else the last finite horizon."""
    finite = [h for h in curve.horizons if np.isfinite(curve.at(h))]
    over = [h for h in finite if curve.at(h) >= tol]
    if over:
        return over[0]
    return finite[-1] if finite else curve.horizons[-1]


def _verdict(usable: dict, jepa: RolloutCurve, persist: RolloutCurve, chaos: ChaosCurve,
             tol: float) -> str:
    h_persist = int(usable["beats_persistence_through"])
    h_tol = int(usable.get("under_tolerance_through", 0))
    # is the model chaos-limited or model-limited at the first horizon it exceeds tolerance?
    breakdown = _first_breakdown(jepa, tol)
    chaos_at_breakdown = chaos.divergence.get(breakdown, float("nan"))
    model_limited = (np.isfinite(chaos_at_breakdown) and np.isfinite(jepa.at(breakdown))
                     and jepa.at(breakdown) > 10.0 * chaos_at_breakdown)
    tag = "MODEL-LIMITED" if model_limited else "CHAOS-LIMITED"
    return (f"usable horizon ~H{max(h_persist, h_tol)} "
            f"(beats persistence through H{h_persist}; under tol {tol:.3f} through H{h_tol}); "
            f"breakdown at H{breakdown} is {tag}")


# ============================ formatting =================================================
def _curve_row(name: str, c: RolloutCurve, hs) -> str:
    cells = "  ".join(f"{c.mean_error[h]:8.4f}" for h in hs)
    return f"  {name:16s} {cells}"


def format_rollout_scorecard(s: RolloutScorecard) -> str:
    hs = s.horizons
    pc = s.param_counts
    head = "  " + " " * 16 + "  ".join(f"H={h:<6d}" for h in hs)
    lines = [
        "=" * 92,
        "SPLATRA world model -- MULTI-STEP ROLLOUT proof (can the validated proposer SIMULATE?)",
        "=" * 92,
        f"particles={s.n_particles}  light_dim={s.light_dim}  compression={s.compression_ratio:.2f}x"
        f"  body_diameter~{s.body_diameter:.3f}",
        f"PREDICTOR params: trainable={pc['trainable_total']:,} (+EMA {pc['ema_target']:,} "
        f"-> total {pc['total_incl_ema']:,})   budget<=25,000,000",
        f"one-step held-out error (v0.1 metric): JEPA={s.jepa_one_step:.4f}  linear={s.linear_one_step:.4f}"
        f"   (JEPA/linear={s.jepa_one_step / max(s.linear_one_step, 1e-9):.3f})",
        f"codec velocity distortion (norm RMSE, 8-bit): " +
        ", ".join(f"{k}={v:.4f}" for k, v in s.codec_velocity_distortion.items()),
        "-" * 92,
        "(1) ROLLOUT ERROR vs HORIZON  (closed-loop, held-out, default codec, UNGATED; world units)",
        head,
        _curve_row("persistence", s.persistence, hs),
        _curve_row("linear fwd-map", s.linear, hs),
        _curve_row("JEPA", s.jepa, hs),
        "-" * 92,
        "(2) CHAOS CEILING  (TRUE-dynamics divergence under IC perturbation eps={:.0e}; model-free)".format(s.chaos.eps),
        f"   lyapunov(early)~{s.chaos.lyapunov:+.4f}   saturation~{s.chaos.saturation:.4f}  (attractor = settled body)",
        "  " + " " * 16 + "  ".join(f"H={h:<6d}" for h in hs),
        "  " + f"{'intrinsic diverge':16s} " + "  ".join(f"{s.chaos.divergence[h]:8.5f}" for h in hs),
        "  " + f"{'chaos-floor JEPA':16s} " + "  ".join(f"{s.chaos_floor_jepa[h]:8.4f}" for h in hs)
        + "   (= e1*amplification; JEPA can't beat this)",
        "  " + f"{'JEPA rollout':16s} " + "  ".join(f"{s.jepa.mean_error[h]:8.4f}" for h in hs),
    ]
    # separation statement
    sep_h = _first_breakdown(s.jepa, s.tolerance)
    lines.append(f"   -> at H{sep_h} JEPA rollout={s.jepa.mean_error[sep_h]:.4f} vs intrinsic "
                 f"chaos={s.chaos.divergence[sep_h]:.5f}  (ratio {s.jepa.mean_error[sep_h] / max(s.chaos.divergence[sep_h], 1e-9):.0f}x"
                 f" -> {'MODEL-limited' if s.jepa.mean_error[sep_h] > 10 * s.chaos.divergence[sep_h] else 'CHAOS-limited'})")
    lines.append("-" * 92)
    # (3) velocity codec
    if s.jepa_rawvel is not None:
        lines += [
            "(3) VELOCITY CODEC FIDELITY  (retrain + roll with UNQUANTIZED velocity vs 8-bit default)",
            head,
            _curve_row("JEPA 8-bit vel", s.jepa, hs),
            _curve_row("JEPA raw vel", s.jepa_rawvel, hs),
        ]
        better = sum(1 for h in hs if s.jepa_rawvel.mean_error[h] < s.jepa.mean_error[h] - 1e-6)
        lines.append(f"   raw-velocity better at {better}/{len(hs)} horizons -> "
                     f"{'codec IS a rollout bottleneck' if better >= len(hs) - 1 else 'codec is NOT the dominant rollout bottleneck'}")
        lines.append("-" * 92)
    # (4) physics-truth in the loop
    if s.jepa_gated is not None:
        lines += [
            "(4) PHYSICS-TRUTH IN THE LOOP  (clamp physics-violating predicted steps; membrane as stabilizer)",
            head,
            _curve_row("JEPA ungated", s.jepa, hs),
            _curve_row("JEPA gated", s.jepa_gated, hs),
            f"   gated rollout stays physics-valid at every step: {s.jepa_gated_violation_free}",
        ]
        g_better = sum(1 for h in hs if s.jepa_gated.mean_error[h] < s.jepa.mean_error[h] - 1e-6)
        lines.append(f"   gating lowers rollout error at {g_better}/{len(hs)} horizons -> "
                     f"{'membrane STABILIZES rollout' if g_better >= 2 else 'membrane keeps it physical but does not extend the horizon'}")
        lines.append("-" * 92)
    lines += [
        f"USABLE HORIZON: beats persistence through H{s.usable['beats_persistence_through']}"
        f"   under tol({s.tolerance:.3f}) through H{s.usable.get('under_tolerance_through', 0)}",
        f"VERDICT: {s.verdict}",
        "=" * 92,
    ]
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--epochs", type=int, default=0)
    ap.add_argument("--no-sweep", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    config = RolloutProofConfig.fast() if args.fast else RolloutProofConfig()
    if args.epochs:
        config.epochs = args.epochs
    if args.no_sweep:
        config.run_codec_sweep = False
    config.verbose = args.verbose
    print(f"[rollout proof] elastic bounce; epochs={config.epochs} "
          f"train_eps={config.train_episodes} rollout_steps={config.rollout_steps} "
          f"heldout={config.heldout_episodes}")
    scard = run_rollout_proof(config)
    print(format_rollout_scorecard(scard))
