# -*- coding: utf-8 -*-
"""RICH mechanism proof -- the MAKE-OR-BREAK test of #74's honest negative.

#74's verdict: JEPA-over-turbovec was ~2.6x WORSE than a global ridge linear forward-map on
the NEAR-LINEAR toy, and named the next rung: measure the mechanism on dynamics a global
linear map genuinely CANNOT fit. This runner does exactly that -- it swaps the toy dynamics
for the contact-rich / non-rigid / frictional regime in ``contact_dynamics.py`` and keeps
EVERYTHING else byte-for-byte identical to #74:

  * SAME representation codec (TurbovecFieldCodec, calibrated on train states only),
  * SAME predictor (TurbovecJEPA, train_jepa) -- d_emb is a config knob the task permits
    widening within the <=25M budget; the architecture is unchanged,
  * SAME two baselines (PersistenceBaseline, LinearForwardMap),
  * SAME physics-truth gate (PhysicsTruthGate) wired into the training path,
  * SAME held-out protocol (disjoint IC rng streams), SAME scorecard + format.

The ONLY thing that changes is the dynamics regime. The verdict (BETTER / EQUAL / WORSE vs
the linear map) is reported with numbers, honestly, whatever it is. ``crossover_sweep`` runs
the proof across a complexity ladder (settle -> elastic bounce) to locate where -- if
anywhere -- JEPA overtakes the linear map.

Run foreground:
  python -X utf8 -m packages.splatra_worldmodel.rich_mechanism_proof            # full elastic
  python -X utf8 -m packages.splatra_worldmodel.rich_mechanism_proof --sweep    # crossover ladder
  python -X utf8 -m packages.splatra_worldmodel.rich_mechanism_proof --fast     # smoke
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .baselines import LinearForwardMap, PersistenceBaseline
from .contact_dynamics import ContactDynamicsParams, simulate_contact_episode
from .forward_model import Episode
from .jepa import JEPAConfig, train_jepa
# Reuse the EXACT proof internals so the comparison is identical, not a re-implementation.
from .mechanism_proof import (
    CandidateSample,
    Scorecard,
    _episodes_to_dataset,
    _field_error,
    _quarantine_demo,
    _violation_rate,
    format_scorecard,
)
from .physics_truth import PhysicsTruthGate
from .turbovec_field import FieldState, TurbovecFieldCodec


@dataclass
class RichProofConfig:
    dynamics: ContactDynamicsParams = field(default_factory=ContactDynamicsParams.elastic)
    train_episodes: int = 48
    heldout_episodes: int = 12
    steps: int = 40
    epochs: int = 4000
    d_emb: int = 64
    d_hidden: int = 128
    seed: int = 0
    verbose: bool = False

    @staticmethod
    def fast() -> "RichProofConfig":
        """Small, quick config for the test suite (seconds, not minutes)."""
        return RichProofConfig(dynamics=ContactDynamicsParams.elastic(),
                               train_episodes=8, heldout_episodes=3, steps=16,
                               epochs=300, seed=0)


def _build_contact_episodes(cfg: RichProofConfig) -> tuple[list[Episode], list[Episode]]:
    """SAME disjoint-IC held-out protocol as mechanism_proof._build_episodes -- contact dynamics."""
    d = cfg.dynamics
    off_tr = np.random.default_rng(42)
    off_ho = np.random.default_rng(999)   # DISJOINT stream -> unseen initial conditions
    train = [
        simulate_contact_episode(d, cfg.steps, seed=1000 + i,
                                 init_offset=off_tr.uniform(-0.3, 0.3, 3),
                                 init_vel=off_tr.uniform(-0.10, 0.10, 3))
        for i in range(cfg.train_episodes)
    ]
    heldout = [
        simulate_contact_episode(d, cfg.steps, seed=5000 + j,
                                 init_offset=off_ho.uniform(-0.45, 0.45, 3),  # wider -> real gen.
                                 init_vel=off_ho.uniform(-0.15, 0.15, 3))
        for j in range(cfg.heldout_episodes)
    ]
    return train, heldout


def run_rich_mechanism_proof(cfg: RichProofConfig | None = None) -> Scorecard:
    """Identical to run_mechanism_proof but on the contact-rich dynamics + widenable d_emb."""
    cfg = cfg or RichProofConfig()
    train_eps, heldout_eps = _build_contact_episodes(cfg)

    # calibrate the turbovec light-vector codec on TRAIN states only (no leakage).
    train_states = [st for ep in train_eps for st in ep.states]
    codec = TurbovecFieldCodec.fit(train_states)
    n_particles = train_states[0].n
    light_dim = codec.light_vector_dim(n_particles)

    train_ds = _episodes_to_dataset(codec, train_eps)
    heldout_ds = _episodes_to_dataset(codec, heldout_eps)

    # physics-truth gate: verify observed transitions, quarantine injected violations.
    gate = PhysicsTruthGate()
    quarantine = _quarantine_demo(train_ds, gate, cfg.seed)

    # Only clean (verified) transitions train the model -- the quarantine is WIRED into the
    # training path (identical to #74). The observed contact dynamics is physical, so all
    # true transitions pass; a corrupted observation would be dropped here.
    verified = gate.filter_transitions([
        CandidateSample(
            FieldState(train_ds.pos[i], np.zeros_like(train_ds.pos[i])),
            train_ds.action[i],
            FieldState(train_ds.pos_next[i], np.zeros_like(train_ds.pos_next[i])),
            "true", index=i,
        )
        for i in range(train_ds.light.shape[0])
    ])
    keep_idx = np.array([it.index for it in verified.kept], dtype=int)
    tl, ta, tln, td = (train_ds.light[keep_idx], train_ds.action[keep_idx],
                       train_ds.light_next[keep_idx], train_ds.delta[keep_idx])

    # train the SAME JEPA-over-turbovec predictor (d_emb widenable within budget).
    jcfg = JEPAConfig(d_light=light_dim, n_particles=n_particles,
                      d_emb=cfg.d_emb, d_hidden=cfg.d_hidden)
    model, train_report = train_jepa(
        jcfg, tl, ta, tln, td, epochs=cfg.epochs, seed=cfg.seed,
        log_every=(max(1, cfg.epochs // 5) if cfg.verbose else 0),
    )

    # SAME baselines fit on the SAME train data.
    persistence = PersistenceBaseline()
    linear = LinearForwardMap.fit(train_ds.light, train_ds.action, train_ds.delta)

    def jepa_predict(l, a, p):
        return model.predict_next_positions(l, a, p)

    scard = Scorecard(
        n_particles=n_particles,
        light_dim=light_dim,
        compression_ratio=codec.compression_ratio,
        codec_distortion=codec.distortion_pooled(train_states),
        contact_fraction_train=float(train_ds.contact.mean()),
        contact_fraction_heldout=float(heldout_ds.contact.mean()),
        param_counts=train_report.param_counts,
        train_report=train_report,
        persistence_heldout=_field_error(persistence.predict_next_positions, heldout_ds),
        linear_heldout=_field_error(linear.predict_next_positions, heldout_ds),
        jepa_heldout=_field_error(jepa_predict, heldout_ds),
        persistence_train=_field_error(persistence.predict_next_positions, train_ds),
        linear_train=_field_error(linear.predict_next_positions, train_ds),
        jepa_train=_field_error(jepa_predict, train_ds),
        jepa_contact=_field_error(jepa_predict, heldout_ds, heldout_ds.contact),
        linear_contact=_field_error(linear.predict_next_positions, heldout_ds, heldout_ds.contact),
        persistence_contact=_field_error(persistence.predict_next_positions, heldout_ds, heldout_ds.contact),
        jepa_freefall=_field_error(jepa_predict, heldout_ds, ~heldout_ds.contact),
        linear_freefall=_field_error(linear.predict_next_positions, heldout_ds, ~heldout_ds.contact),
        persistence_freefall=_field_error(persistence.predict_next_positions, heldout_ds, ~heldout_ds.contact),
        linear_violation_rate=_violation_rate(linear.predict_next_positions, heldout_ds, gate),
        jepa_violation_rate=_violation_rate(jepa_predict, heldout_ds, gate),
        quarantine=quarantine,
        verdict="",
        jepa_vs_linear_ratio=0.0,
        jepa_vs_persistence_ratio=0.0,
    )

    ratio_lin = scard.jepa_heldout / max(scard.linear_heldout, 1e-9)
    ratio_per = scard.jepa_heldout / max(scard.persistence_heldout, 1e-9)
    scard.jepa_vs_linear_ratio = ratio_lin
    scard.jepa_vs_persistence_ratio = ratio_per
    if ratio_lin < 0.95:
        scard.verdict = "BETTER"
    elif ratio_lin > 1.05:
        scard.verdict = "WORSE"
    else:
        scard.verdict = "EQUAL"
    scard.n_train_transitions = int(keep_idx.size)
    return scard


# ---- crossover sweep -------------------------------------------------------------------
@dataclass
class CrossoverRow:
    level: int
    persistence: float
    linear: float
    jepa: float
    lin_over_persist: float     # >1 => linear is WORSE than doing nothing (provably can't fit)
    jepa_over_linear: float     # <1 => JEPA BEATS the linear map (mechanism pays off)
    verdict: str


def crossover_sweep(levels=(0, 1, 2, 3), *, train_episodes=32, heldout_episodes=10,
                    steps=32, epochs=2500, d_emb=64, d_hidden=128, seed=0,
                    verbose=True) -> list[CrossoverRow]:
    """Run the proof across the complexity ladder and locate the JEPA-vs-linear crossover."""
    rows: list[CrossoverRow] = []
    for lv in levels:
        cfg = RichProofConfig(dynamics=ContactDynamicsParams.ladder(lv),
                              train_episodes=train_episodes, heldout_episodes=heldout_episodes,
                              steps=steps, epochs=epochs, d_emb=d_emb, d_hidden=d_hidden, seed=seed)
        s = run_rich_mechanism_proof(cfg)
        row = CrossoverRow(
            level=lv, persistence=s.persistence_heldout, linear=s.linear_heldout,
            jepa=s.jepa_heldout,
            lin_over_persist=s.linear_heldout / max(s.persistence_heldout, 1e-9),
            jepa_over_linear=s.jepa_vs_linear_ratio, verdict=s.verdict,
        )
        rows.append(row)
        if verbose:
            print(f"[L{lv}] persist={row.persistence:.4f} linear={row.linear:.4f} "
                  f"JEPA={row.jepa:.4f} | lin/persist={row.lin_over_persist:.2f} "
                  f"JEPA/linear={row.jepa_over_linear:.3f} -> {row.verdict}")
    return rows


def format_crossover(rows: list[CrossoverRow]) -> str:
    lines = [
        "=" * 74,
        "CROSSOVER SWEEP -- JEPA-over-turbovec vs global linear map, by dynamics complexity",
        "=" * 74,
        "  L  persist  linear   JEPA   | lin/persist  JEPA/linear  verdict",
        "-" * 74,
    ]
    for r in rows:
        lines.append(f"  {r.level}  {r.persistence:.4f}  {r.linear:.4f}  {r.jepa:.4f} | "
                     f"   {r.lin_over_persist:.2f}        {r.jepa_over_linear:.3f}      {r.verdict}")
    # locate the crossover (first level where JEPA beats linear)
    crossed = [r.level for r in rows if r.jepa_over_linear < 1.0]
    lines.append("-" * 74)
    if crossed:
        lines.append(f"CROSSOVER: JEPA first beats the linear map at complexity level L{min(crossed)}"
                     f" (lin/persist={next(r.lin_over_persist for r in rows if r.level == min(crossed)):.2f}).")
    else:
        lines.append("CROSSOVER: NONE -- JEPA never beats the linear map across the ladder.")
    lines.append("=" * 74)
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="quick smoke config")
    ap.add_argument("--sweep", action="store_true", help="crossover ladder (settle -> elastic)")
    ap.add_argument("--d-emb", type=int, default=64, help="predictive latent width (<=25M budget)")
    ap.add_argument("--epochs", type=int, default=0, help="override epochs")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.sweep:
        sweep_rows = crossover_sweep(epochs=(args.epochs or 2500), d_emb=args.d_emb)
        print(format_crossover(sweep_rows))
    else:
        config = RichProofConfig.fast() if args.fast else RichProofConfig()
        config.d_emb = args.d_emb
        if args.epochs:
            config.epochs = args.epochs
        config.verbose = args.verbose
        print(f"[rich regime] elastic bouncing soft body (contact_dynamics.ladder(3)); "
              f"d_emb={config.d_emb} epochs={config.epochs} "
              f"train_eps={config.train_episodes} steps={config.steps}")
        scorecard = run_rich_mechanism_proof(config)
        print(format_scorecard(scorecard))
