# -*- coding: utf-8 -*-
"""Track E SPLATRA M0s/M1s gates — pinned as measurable behaviour (No-LLM, CPU, no Isaac, no GPU).
The body schema MUST learn (error converges) and surprise MUST fire on the unexpected (spike vs
baseline). A flat curve = the schema failed; equal errors = no surprise = the reaction is fake."""
from __future__ import annotations

from packages.embodiment.splatra_body import SplatraBody, BodySchema, run_babbling


def test_body_boots_with_proprioception_and_no_renderer():
    body = SplatraBody("arm", count=300, seed=0)
    st = body.state()
    assert st.proprioception().shape == (9,)          # centroid + extent + tip
    assert st.tip.shape == (3,)


def test_body_schema_learns_error_converges():
    # M1s gate: prediction error after babbling is well below the initial error (windowed means).
    rep = run_babbling("arm", steps=300, seed=1)
    assert rep.extra["init_error"] > 0
    assert rep.baseline_error < rep.extra["init_error"] * 0.4   # learned the body's action->response map
    assert rep.extra["converged"] is True


def test_surprise_spikes_on_unexpected_perturbation():
    # M1s+ reaction gate: an external shove the action never commanded errors FAR above the learned
    # baseline -> surprise. If the ratio were ~1, the reaction would be measuring nothing.
    rep = run_babbling("arm", steps=300, seed=2)
    assert rep.surprise_ratio > 3.0                        # the unexpected is genuinely surprising


def test_forward_model_is_learned_not_hardcoded():
    # a fresh schema predicts poorly (W=0 -> predicts no motion); it must improve with experience.
    body = SplatraBody("arm", seed=3)
    schema = BodySchema()
    st = body.state()
    import numpy as np
    rng = np.random.default_rng(0)
    errs = []
    for t in range(200):
        a = rng.normal(0, 0.05, 3)
        tip = st.tip.copy()
        st = body.step(a)
        errs.append(schema.learn(tip, a, st.tip))
    assert np.mean(errs[-20:]) < np.mean(errs[:20]) * 0.5   # schema improved from data, not a rule
