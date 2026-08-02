# -*- coding: utf-8 -*-
"""Latent predictive coder — the V-JEPA-principle organ (docs/ATANOR_vjepa_fusion.md §3).

These tests pin the organ's HONESTY: the manual backward pass is finite-difference correct, the model
is inside the neuro-budget by three orders of magnitude, it learns (loss falls), it does NOT collapse
(latent variance bounded away from zero), it is provably invariant to uniform lighting, and its latent
surprise spikes on a structural break — while Seam C (`latent_nonconformity`) exposes the raw signal
without touching the conformal gate."""
from __future__ import annotations

import numpy as np

from packages.perception.latent_predictor import (
    CoderConfig,
    LatentPredictiveCoder,
    OnlineLatentSurprise,
    latent_nonconformity,
)


def _shared_seq(seed: int, n: int = 70, dim: int = 256) -> np.ndarray:
    """A predictable stream from a SHARED sinusoid basis (same across seeds) with a per-seed phase —
    so a coder trained on several seeds genuinely generalizes to a new one (structure, not memory)."""
    r = np.random.default_rng(seed)
    t = np.arange(n)[:, None]
    freqs = np.array([[0.03, 0.05, 0.08, 0.12]])
    phase = r.uniform(0, 6.28, size=(1, 4))
    basis = np.random.default_rng(0).normal(size=(4, dim))         # shared across all seeds
    x = np.sin(2 * np.pi * t * freqs + phase) @ basis
    return (x - x.min()) / (np.ptp(x) + 1e-8)


def _small_coder(**kw) -> LatentPredictiveCoder:
    cfg = CoderConfig(input_dim=256, enc_hidden=32, latent_dim=16, pred_hidden=32, history_k=4, **kw)
    return LatentPredictiveCoder(cfg)


def test_backward_is_finite_difference_correct():
    """The whole organ's credibility rests on correct gradients — verify analytic == numeric."""
    c = LatentPredictiveCoder(CoderConfig(input_dim=48, enc_hidden=12, latent_dim=8,
                                          pred_hidden=12, history_k=3, seed=1))
    X = np.random.default_rng(2).normal(size=(14, 48))
    worst = max(c.grad_check(X, n_probe=5).values())
    assert worst < 1e-4, f"manual backprop disagrees with finite differences: {worst:.2e}"


def test_param_count_far_under_budget():
    """Neuro-budget N1-N3: single model <= 25M. We expect ~0.15M — report and enforce both."""
    c = LatentPredictiveCoder(CoderConfig())          # production shape
    assert c.param_count() < 1_000_000                # tiny by design
    assert c.param_count(include_target=True) <= 25_000_000


def test_training_reduces_loss():
    seqs = [_shared_seq(s) for s in range(5)]
    c = _small_coder(seed=0)
    hist = c.train(seqs, epochs=80)
    assert hist[-1]["total"] < 0.6 * hist[0]["total"], (hist[0]["total"], hist[-1]["total"])
    assert hist[-1]["pred"] < hist[0]["pred"]


def test_no_representational_collapse():
    """EMA asymmetry + the VICReg variance term must keep the latent alive (std bounded from zero)."""
    seqs = [_shared_seq(s) for s in range(5)]
    c = _small_coder(seed=0)
    c.train(seqs, epochs=80)
    rep = c.collapse_report(_shared_seq(999))
    assert rep["ok"] is True
    assert rep["latent_std_min"] > 1e-2, rep
    assert rep["surprise_std"] > 0.0                  # a collapsed predictor emits ~constant surprise


def test_encoder_is_invariant_to_uniform_lighting():
    """Non-generative lighting robustness: per-frame standardization makes a uniform brightness shift
    invisible to the latent — the property the pixel baseline lacks (proved exactly, not trained)."""
    c = _small_coder(seed=3)
    sig = _shared_seq(7)[30]
    z0, _ = c.encode(sig)
    z1, _ = c.encode(sig + 0.2)                       # add a uniform lighting offset
    assert float(np.linalg.norm(z0 - z1)) < 1e-6


def test_latent_surprise_spikes_on_structural_break():
    """Train on a predictable stream, then inject a discontinuity: the surprise at the broken frame
    must exceed both its own unbroken value and the sequence's baseline surprise."""
    seqs = [_shared_seq(s) for s in range(5)]
    c = _small_coder(seed=0)
    c.train(seqs, epochs=90)
    seq = _shared_seq(999)
    s_normal = c.surprise_stream(seq)
    baseline = float(s_normal[c.cfg.history_k:].mean())
    broken = seq.copy()
    broken[40] = np.random.default_rng(5).uniform(0, 1, size=seq.shape[1])   # a teleport at t=40
    s_break = c.surprise_stream(broken)
    assert s_break[40] > s_normal[40]
    assert s_break[40] > baseline


def test_surprise_stream_is_causal_and_cold_at_start():
    c = _small_coder(seed=0)
    s = c.surprise_stream(_shared_seq(1))
    assert s.shape[0] == 70
    assert np.all(s[:c.cfg.history_k] == 0.0)         # no context yet -> no surprise (cold start)


def test_online_surprise_and_seam_c_nonconformity():
    """The live per-frame stepper is causal (not ready until a full k-window exists) and Seam C's
    `latent_nonconformity` returns the raw s_t candidate WITHOUT importing the conformal gate."""
    c = _small_coder(seed=0)
    c.train([_shared_seq(s) for s in range(4)], epochs=40)
    seq = _shared_seq(555)
    online = OnlineLatentSurprise(coder=c)
    outs = [online.push(seq[t]) for t in range(20)]
    assert outs[0]["ready"] is False and outs[c.cfg.history_k]["ready"] is True
    assert online.latent_nonconformity() == online.last_raw     # Seam C read = last raw surprise
    # stateless Seam C helper returns the last frame's raw surprise for a recent window
    val = latent_nonconformity(c, seq[:12])
    assert isinstance(val, float) and val >= 0.0
