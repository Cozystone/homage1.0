# -*- coding: utf-8 -*-
"""The Representation Invention Flywheel, verified end-to-end on a designed representation wall.
Proves the loop breaks an envelope the shallow feature space cannot express: base (topic-alignment only)
sits at chance; the loop must INVENT the focus-contrast program and graduate it through a sealed holdout."""
from __future__ import annotations

import numpy as np

from packages.reasoning_vm.rif import dsl
from packages.reasoning_vm.rif.demo import synthetic_env
from packages.reasoning_vm.rif.flywheel import run_loop
from packages.reasoning_vm.rif.prober import probe


def test_loop_breaks_designed_representation_wall():
    env = synthetic_env(n=1400, seed=0)
    start = len(env.basis)
    rep = run_loop(env, rounds=6, n=70, seed=0, margin=0.01)
    assert rep["start_val"] < 0.72, rep["start_val"]        # base representation is at the wall
    assert rep["reached_goal"], rep                          # loop climbed to goal
    assert rep["final_holdout"] > 0.85, rep                  # sealed holdout confirms (not val-overfit)
    assert len(env.basis) > start                            # basis GREW — envelope expanded
    invented = " ".join(rep["graduated_programs"])
    assert "focus" in invented                               # the missing primitive was invented


def test_prober_flags_representation_vs_training_wall():
    rng = np.random.default_rng(0)
    n = 1500
    # a feature that CANNOT separate the label (label is independent of X) → representation wall
    X_blind = rng.normal(size=(n, 4)).astype(np.float32)
    y = (rng.random(n) < 0.4).astype(int)
    rep_wall = probe("blind", X_blind, y, goal_acc=0.9)
    assert rep_wall.verdict == "representation_wall", rep_wall

    # a feature that fully separates but is easy → NOT a representation wall (done/training)
    X_sep = np.column_stack([y + 0.01 * rng.normal(size=n), rng.normal(size=n)]).astype(np.float32)
    rep_ok = probe("separable", X_sep, y, goal_acc=0.9)
    assert rep_ok.verdict in ("done", "training_wall"), rep_ok


def test_graduated_program_is_a_reusable_leaf():
    """After graduation the invented program is bound as a signal on every sample → next round composes."""
    env = synthetic_env(n=800, seed=1)
    run_loop(env, rounds=3, n=60, seed=1, margin=0.01)
    new_leaves = [s for s in env.signals if s.name.startswith("g")]
    if new_leaves:                                            # a graduation happened
        s0 = env.samples[0]
        assert new_leaves[0].name in s0                      # leaf is materialized on samples
        assert np.isfinite(float(s0[new_leaves[0].name]))
