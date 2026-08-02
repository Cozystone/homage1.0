# -*- coding: utf-8 -*-
"""Mechanism proof v0 (design docs/ATANOR_vjepa_fusion.md sec 9, the honest deliverable).

On TOY falling/deforming-body dynamics, measure whether JEPA-over-turbovec predicts the
next field-state BETTER than (a) a no-model persistence baseline and (b) a linear
forward-map baseline; whether physics-truth catches injected violations (quarantine, never
learned); whether it holds on HELD-OUT dynamics (generalization, not memorization); and
whether the latent avoids collapse.

This is the FIRST RUNG mechanism proof -- NOT a general real-world simulator, NOT
"real-time autonomous sim achieved". The verdict (BETTER / EQUAL / WORSE) is reported with
numbers, honestly, whatever it is.

Run foreground:  python -X utf8 -m packages.splatra_worldmodel.mechanism_proof
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .baselines import LinearForwardMap, PersistenceBaseline
from .forward_model import DynamicsParams, Episode, simulate_episode
from .jepa import JEPAConfig, TurbovecJEPA, train_jepa
from .physics_truth import PhysicsTruthGate
from .turbovec_field import FieldState, TurbovecFieldCodec


@dataclass
class ProofConfig:
    dynamics: DynamicsParams = field(default_factory=DynamicsParams)
    train_episodes: int = 24
    heldout_episodes: int = 8
    steps: int = 32
    epochs: int = 1500
    d_emb: int = 64
    d_hidden: int = 128
    seed: int = 0
    verbose: bool = False

    @staticmethod
    def fast() -> "ProofConfig":
        """A small, quick config for the test suite (seconds, not minutes)."""
        return ProofConfig(dynamics=DynamicsParams(count=200), train_episodes=8,
                           heldout_episodes=3, steps=16, epochs=250, seed=0)


# ---- data ------------------------------------------------------------------------------
def _build_episodes(cfg: ProofConfig) -> tuple[list[Episode], list[Episode]]:
    d = cfg.dynamics
    off_tr = np.random.default_rng(42)
    off_ho = np.random.default_rng(999)   # DISJOINT stream -> unseen initial conditions
    train = [
        simulate_episode(d, cfg.steps, seed=1000 + i,
                         init_offset=off_tr.uniform(-0.3, 0.3, 3),
                         init_vel=off_tr.uniform(-0.10, 0.10, 3))
        for i in range(cfg.train_episodes)
    ]
    heldout = [
        simulate_episode(d, cfg.steps, seed=5000 + j,
                         init_offset=off_ho.uniform(-0.45, 0.45, 3),   # wider -> real generalization
                         init_vel=off_ho.uniform(-0.15, 0.15, 3))
        for j in range(cfg.heldout_episodes)
    ]
    return train, heldout


@dataclass
class Dataset:
    light: np.ndarray       # (S, d_light)
    action: np.ndarray      # (S, 3)
    light_next: np.ndarray  # (S, d_light)
    pos: np.ndarray         # (S, N, 3)
    pos_next: np.ndarray    # (S, N, 3)
    delta: np.ndarray       # (S, N, 3)
    contact: np.ndarray     # (S,) bool


def _episodes_to_dataset(codec: TurbovecFieldCodec, episodes: list[Episode]) -> Dataset:
    light, action, light_next, pos, pos_next, delta, contact = [], [], [], [], [], [], []
    for ep in episodes:
        for t in range(len(ep.actions)):
            cur, nxt = ep.states[t], ep.states[t + 1]
            light.append(codec.encode(cur))
            light_next.append(codec.encode(nxt))
            action.append(ep.actions[t])
            pos.append(cur.pos)
            pos_next.append(nxt.pos)
            delta.append(nxt.pos - cur.pos)
            contact.append(ep.contacts[t])
    return Dataset(
        light=np.asarray(light), action=np.asarray(action),
        light_next=np.asarray(light_next), pos=np.asarray(pos),
        pos_next=np.asarray(pos_next), delta=np.asarray(delta),
        contact=np.asarray(contact, dtype=bool),
    )


# ---- metric ----------------------------------------------------------------------------
def _field_error(predict: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray],
                 ds: Dataset, mask: np.ndarray | None = None) -> float:
    """Mean per-particle L2 position error (world units) over the (masked) samples."""
    idx = np.arange(ds.light.shape[0]) if mask is None else np.where(mask)[0]
    if idx.size == 0:
        return float("nan")
    errs = []
    for i in idx:
        pred = predict(ds.light[i], ds.action[i], ds.pos[i])
        errs.append(np.linalg.norm(pred - ds.pos_next[i], axis=1).mean())
    return float(np.mean(errs))


def _violation_rate(predict: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray],
                    ds: Dataset, gate: PhysicsTruthGate) -> float:
    """Fraction of a model's PREDICTED next fields that the physics gate would reject."""
    n_bad = 0
    total = ds.light.shape[0]
    for i in range(total):
        pred_pos = predict(ds.light[i], ds.action[i], ds.pos[i])
        prev = FieldState(pos=ds.pos[i], vel=np.zeros_like(ds.pos[i]))
        cand = FieldState(pos=pred_pos, vel=np.zeros_like(pred_pos))
        if not gate.verify(prev, ds.action[i], cand).ok:
            n_bad += 1
    return n_bad / max(total, 1)


# ---- quarantine demo -------------------------------------------------------------------
@dataclass
class CandidateSample:
    prev: FieldState
    action: np.ndarray
    candidate: FieldState
    tag: str
    index: int = -1   # index back into the source dataset (for gating the training set)

    def physics_fields(self):
        return self.prev, self.action, self.candidate


@dataclass
class QuarantineDemo:
    true_transitions_checked: int
    true_transitions_quarantined: int   # must be ~0: observed dynamics is physical
    injected_total: int
    injected_quarantined: int           # must equal injected_total: violations never learned
    example_reasons: list[str]
    kept_after_filter: int
    quarantined_after_filter: int


def _quarantine_demo(train_ds: Dataset, gate: PhysicsTruthGate, seed: int) -> QuarantineDemo:
    rng = np.random.default_rng(seed + 3)
    n = train_ds.light.shape[0]
    # 1. every TRUE observed transition must pass (the dynamics is physical).
    true_items = [
        CandidateSample(
            prev=FieldState(train_ds.pos[i], np.zeros_like(train_ds.pos[i])),
            action=train_ds.action[i],
            candidate=FieldState(train_ds.pos_next[i], np.zeros_like(train_ds.pos_next[i])),
            tag="true",
        )
        for i in range(n)
    ]
    true_res = gate.filter_transitions(true_items)

    # 2. inject deliberately physics-breaking predicted deltas and confirm all are caught.
    gy = gate.ground_plane
    injected: list[CandidateSample] = []
    pick = rng.choice(n, size=min(12, n), replace=False)
    for i in pick:
        prev = FieldState(train_ds.pos[i], np.zeros_like(train_ds.pos[i]))
        base = train_ds.pos[i]
        # (a) drive particles far below the floor -> interpenetration
        below = base.copy(); below[:, 1] = gy - 0.5
        injected.append(CandidateSample(prev, train_ds.action[i],
                                        FieldState(below, np.zeros_like(below)), "below_ground"))
        # (b) teleport all particles by a large jump -> momentum/energy violation
        tp = base.copy(); tp[:, 0] += 3.0
        injected.append(CandidateSample(prev, train_ds.action[i],
                                        FieldState(tp, np.zeros_like(tp)), "teleport"))
        # (c) collapse the field toward its centroid -> implosion / self-interpenetration
        imp = base.mean(0)[None, :] + 0.03 * (base - base.mean(0))
        injected.append(CandidateSample(prev, train_ds.action[i],
                                        FieldState(imp, np.zeros_like(imp)), "implosion"))

    inj_res = gate.filter_transitions(injected)

    # 3. a mixed buffer: clean transitions + the injected violations -> only clean survive.
    mixed = true_items[: min(20, n)] + injected
    mixed_res = gate.filter_transitions(mixed)

    return QuarantineDemo(
        true_transitions_checked=true_res.n_kept + true_res.n_quarantined,
        true_transitions_quarantined=true_res.n_quarantined,
        injected_total=len(injected),
        injected_quarantined=inj_res.n_quarantined,
        example_reasons=inj_res.reasons[:6],
        kept_after_filter=mixed_res.n_kept,
        quarantined_after_filter=mixed_res.n_quarantined,
    )


# ---- scorecard -------------------------------------------------------------------------
@dataclass
class Scorecard:
    n_particles: int
    light_dim: int
    compression_ratio: float
    codec_distortion: dict[str, float]
    contact_fraction_train: float
    contact_fraction_heldout: float
    param_counts: dict[str, int]
    train_report: object
    # field errors (mean per-particle L2, world units)
    persistence_heldout: float
    linear_heldout: float
    jepa_heldout: float
    persistence_train: float
    linear_train: float
    jepa_train: float
    # regime breakdown on held-out
    jepa_contact: float
    linear_contact: float
    persistence_contact: float
    jepa_freefall: float
    linear_freefall: float
    persistence_freefall: float
    # physics violation rates of each model's predictions (held-out)
    linear_violation_rate: float
    jepa_violation_rate: float
    quarantine: QuarantineDemo
    verdict: str
    jepa_vs_linear_ratio: float
    jepa_vs_persistence_ratio: float
    n_train_transitions: int = 0


def run_mechanism_proof(cfg: ProofConfig | None = None) -> Scorecard:
    cfg = cfg or ProofConfig()
    train_eps, heldout_eps = _build_episodes(cfg)

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
    # training path, not just demonstrated. Each candidate carries its dataset index; the gate
    # returns the survivors and we gather exactly those rows. (The observed dynamics is
    # physical, so all true transitions pass; a corrupted observation would be dropped here.)
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

    # train the JEPA-over-turbovec predictor.
    jcfg = JEPAConfig(d_light=light_dim, n_particles=n_particles,
                      d_emb=cfg.d_emb, d_hidden=cfg.d_hidden)
    model, train_report = train_jepa(
        jcfg, tl, ta, tln, td, epochs=cfg.epochs, seed=cfg.seed,
        log_every=(max(1, cfg.epochs // 5) if cfg.verbose else 0),
    )

    # baselines fit on the SAME train data.
    persistence = PersistenceBaseline()
    linear = LinearForwardMap.fit(train_ds.light, train_ds.action, train_ds.delta)

    def jepa_predict(l, a, p):
        return model.predict_next_positions(l, a, p)

    # evaluate: mean per-particle L2 position error on train + held-out.
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

    # verdict (held-out, vs the LINEAR baseline; margin 5%).
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


def format_scorecard(s: Scorecard) -> str:
    pc = s.param_counts
    tr = s.train_report
    lines = [
        "=" * 74,
        "SPLATRA world model v0 -- JEPA-over-turbovec mechanism proof",
        "=" * 74,
        f"particles/body            : {s.n_particles}",
        f"turbovec light-vector dim : {s.light_dim}   (compression {s.compression_ratio:.2f}x vs float32)",
        f"codec distortion (norm.)  : " + ", ".join(f"{k}={v:.3f}" for k, v in s.codec_distortion.items()),
        f"contact fraction          : train={s.contact_fraction_train:.2f}  heldout={s.contact_fraction_heldout:.2f}",
        "-" * 74,
        f"PREDICTOR param count     : trainable={pc['trainable_total']:,}  (+EMA target {pc['ema_target']:,}"
        f" -> total {pc['total_incl_ema']:,})   budget<=25,000,000",
        f"  context f_theta={pc['context_encoder']:,}  predictor g_phi={pc['predictor']:,}  decoder h_psi={pc['decoder']:,}",
        f"final losses              : pred(latent)={tr.final_pred_loss:.5f}  decode={tr.final_decode_loss:.5f}"
        f"  var={tr.final_var_term:.4f}  cov={tr.final_cov_term:.4f}",
        f"collapse check (emb std)  : mean={tr.emb_std_mean:.3f}  min={tr.emb_std_min:.3f}  (bounded away from 0)",
        "-" * 74,
        "FIELD ERROR  (mean per-particle L2, world units; lower=better)",
        f"  HELD-OUT   persistence={s.persistence_heldout:.4f}   linear={s.linear_heldout:.4f}   JEPA={s.jepa_heldout:.4f}",
        f"  TRAIN      persistence={s.persistence_train:.4f}   linear={s.linear_train:.4f}   JEPA={s.jepa_train:.4f}",
        f"  held-out CONTACT frames  persistence={s.persistence_contact:.4f}  linear={s.linear_contact:.4f}  JEPA={s.jepa_contact:.4f}",
        f"  held-out FREEFALL frames persistence={s.persistence_freefall:.4f}  linear={s.linear_freefall:.4f}  JEPA={s.jepa_freefall:.4f}",
        "-" * 74,
        "PHYSICS-TRUTH membrane",
        f"  predicted-field violation rate (held-out): linear={s.linear_violation_rate:.3f}  JEPA={s.jepa_violation_rate:.3f}",
        f"  quarantine: true transitions checked={s.quarantine.true_transitions_checked} "
        f"quarantined={s.quarantine.true_transitions_quarantined} (must be 0)",
        f"  quarantine: injected violations={s.quarantine.injected_total} "
        f"caught={s.quarantine.injected_quarantined} (must equal injected)",
        f"  quarantine: mixed buffer -> kept={s.quarantine.kept_after_filter} "
        f"quarantined={s.quarantine.quarantined_after_filter}",
        f"  example caught reasons: {s.quarantine.example_reasons}",
        "-" * 74,
        f"jepa/linear (held-out) = {s.jepa_vs_linear_ratio:.3f}    jepa/persistence = {s.jepa_vs_persistence_ratio:.3f}",
        f"VERDICT (vs linear, 5% margin): {s.verdict}",
        "=" * 74,
    ]
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="quick config (for a smoke run)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    config = ProofConfig.fast() if args.fast else ProofConfig()
    config.verbose = args.verbose
    scorecard = run_mechanism_proof(config)
    print(format_scorecard(scorecard))
