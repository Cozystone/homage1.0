# -*- coding: utf-8 -*-
"""The JEPA dynamics predictor: budget, EMA stop-grad, collapse guard, learning."""
from __future__ import annotations

import numpy as np
import torch

from packages.splatra_worldmodel.jepa import (
    JEPAConfig,
    TurbovecJEPA,
    train_jepa,
    vicreg_terms,
)


def _toy_batch(n=200, d_light=120, n_particles=20, seed=0):
    rng = np.random.default_rng(seed)
    light = rng.normal(0, 1, (n, d_light))
    action = rng.normal(0, 0.05, (n, 3))
    # a smooth pseudo-dynamics so the predictor has real structure to learn
    light_next = light + 0.1 * np.roll(light, 1, axis=1) + 0.2 * action[:, :1]
    delta = rng.normal(0, 0.02, (n, n_particles, 3)) + action[:, None, :] * 0.5
    return light, action, light_next, delta


def test_param_budget_and_ema_stop_grad():
    cfg = JEPAConfig(d_light=1176, n_particles=196)
    model = TurbovecJEPA(cfg)
    pc = model.param_counts()
    assert pc["trainable_total"] < 25_000_000
    assert pc["total_incl_ema"] < 25_000_000
    # EMA target must not receive gradients (stop-grad)
    assert all(not p.requires_grad for p in model.target.parameters())
    assert all(p.requires_grad for p in model.context.parameters())


def test_vicreg_terms_shapes_and_sign():
    emb = torch.randn(32, 16)
    var_t, cov_t = vicreg_terms(emb)
    assert var_t.ndim == 0 and cov_t.ndim == 0
    assert var_t.item() >= 0.0 and cov_t.item() >= 0.0
    # a collapsed (constant) embedding must incur a large variance penalty
    collapsed = torch.zeros(32, 16)
    var_c, _ = vicreg_terms(collapsed)
    assert var_c.item() > var_t.item()


def test_ema_update_moves_target_toward_context():
    cfg = JEPAConfig(d_light=64, n_particles=8, ema_decay=0.5)
    model = TurbovecJEPA(cfg)
    # perturb the context encoder, then EMA-update and check the target moved toward it
    with torch.no_grad():
        for p in model.context.parameters():
            p.add_(1.0)
    before = [t.clone() for t in model.target.parameters()]
    model.update_target()
    for b, t in zip(before, model.target.parameters()):
        assert not torch.allclose(b, t)  # it moved


def test_training_reduces_prediction_loss_and_avoids_collapse():
    light, action, light_next, delta = _toy_batch()
    cfg = JEPAConfig(d_light=light.shape[1], n_particles=delta.shape[1], d_emb=32, d_hidden=64)
    model, report = train_jepa(cfg, light, action, light_next, delta,
                               epochs=300, seed=0)
    # collapse guard: no embedding dim shrinks to a constant
    assert report.emb_std_min > 0.1
    assert report.emb_std_mean > 0.3
    # decoder learns the delta map
    assert report.final_decode_loss < 0.05
    # inference API shapes
    cur_pos = np.zeros((delta.shape[1], 3))
    pred = model.predict_next_positions(light[0], action[0], cur_pos)
    assert pred.shape == (delta.shape[1], 3)
    s = model.latent_surprise(light[0], action[0], light_next[0])
    assert s >= 0.0
