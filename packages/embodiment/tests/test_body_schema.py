# -*- coding: utf-8 -*-
"""Body schema (M1) — the model-vs-lookup-table test, on a synthetic 2-link arm so it is fast and
deterministic (no MuJoCo needed). The property that matters: the forward kinematics learned from
one posture region GENERALIZES to a region it never saw — a memorized table cannot, a real body
schema can."""
from __future__ import annotations

import numpy as np

from packages.embodiment.body_schema import (ForwardKinematics, JointForwardModel,
                                             naive_baseline_error)

# a true planar 2-link arm: tip = l1*[cos t1, sin t1] + l2*[cos(t1+t2), sin(t1+t2)]
_L1, _L2 = 0.10, 0.11


def _true_tip(j: np.ndarray) -> np.ndarray:
    t1, t2 = j
    return np.array([_L1 * np.cos(t1) + _L2 * np.cos(t1 + t2),
                     _L1 * np.sin(t1) + _L2 * np.sin(t1 + t2)])


def _postures(n, lo, hi, seed):
    rng = np.random.default_rng(seed)
    js = np.column_stack([rng.uniform(lo, hi, n), rng.uniform(-np.pi, np.pi, n)])
    tips = np.stack([_true_tip(j) for j in js])
    return list(js), tips


def test_fk_recovers_true_geometry():
    js, tips = _postures(500, -1.0, 1.0, seed=0)
    fk = ForwardKinematics().fit(js, tips)
    err = np.mean([np.linalg.norm(fk.tip(j) - t) for j, t in zip(js, tips)])
    assert err < 1e-6                                  # the arm's geometry is recovered exactly


def test_fk_generalizes_to_unseen_postures():
    """The M1 gate in miniature: train on shoulder angles in one band, test on a DISJOINT band."""
    train_js, train_tips = _postures(800, -1.2, -0.2, seed=1)     # one region
    held_js, held_tips = _postures(300, 0.8, 1.8, seed=2)         # a region never trained on
    fk = ForwardKinematics().fit(train_js, train_tips)
    held_err = np.mean([np.linalg.norm(fk.tip(j) - t) for j, t in zip(held_js, held_tips)])
    # a lookup table would be lost here; the learned geometry transfers to sub-millimetre error
    assert held_err < 1e-4


def test_fk_beats_predict_the_mean_baseline():
    js, tips = _postures(600, -1.5, 1.5, seed=3)
    fk = ForwardKinematics().fit(js, tips)
    model_err = np.mean([np.linalg.norm(fk.tip(j) - t) for j, t in zip(js, tips)])
    mean_tip = tips.mean(axis=0)
    baseline = np.mean([np.linalg.norm(t - mean_tip) for t in tips])
    assert model_err < 0.25 * baseline                 # far below 'just guess the average hand'


def test_joint_dynamics_model_beats_no_motion():
    """The secondary readout: a smooth joint transition is predicted better than 'joints don't move'."""
    rng = np.random.default_rng(4)
    X, nxt = [], []
    j = np.array([0.1, -0.2]); v = np.array([0.0, 0.0])
    for _ in range(2000):
        a = rng.normal(0, 0.2, 2)
        j2 = j + 0.05 * v + 0.02 * a                   # smooth 2nd-order-ish joint dynamics
        v = 0.9 * v + a
        X.append((j.copy(), v.copy(), a.copy())); nxt.append(j2.copy())
        j = j2
    nxt = np.stack(nxt)
    model = JointForwardModel().fit(X, nxt)
    model_err = np.mean([np.linalg.norm(model.predict(*x) - y) for x, y in zip(X, nxt)])
    no_motion = naive_baseline_error(nxt - np.stack([x[0] for x in X]))
    assert model_err < 0.5 * no_motion                 # learns the dynamics, beats assuming stillness


def test_fk_is_not_a_memorized_lookup():
    """Directly: query a posture NOT in the training set and still get the right hand position."""
    js, tips = _postures(400, -1.0, 1.0, seed=5)
    fk = ForwardKinematics().fit(js, tips)
    novel = np.array([2.5, -2.0])                      # far outside the training band
    assert np.linalg.norm(fk.tip(novel) - _true_tip(novel)) < 1e-4
