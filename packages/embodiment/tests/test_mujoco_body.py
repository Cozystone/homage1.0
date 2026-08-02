# -*- coding: utf-8 -*-
"""Track E MuJoCo rigorous-physics gates. Skipped where mujoco isn't installed (the SPLATRA lane is
the always-on gate); where it is, physics-grade proprioception, contact, schema learning and surprise
are pinned. No RTX, no Isaac."""
from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from packages.embodiment.mujoco_body import MujocoBody, run_mujoco_babbling, run_self_other_attribution


def test_mujoco_body_boots_with_articulated_proprioception():
    body = MujocoBody()
    st = body.state()
    assert st.proprioception().shape == (9,)        # 3 joints + 3 joint-vel + tip(3)
    assert st.joints.shape == (3,)


def test_joint_schema_learns_error_converges():
    rep = run_mujoco_babbling(steps=400, seed=1)
    assert rep.init_error > 0
    assert rep.baseline_error < rep.init_error * 0.6   # body schema learned the joint dynamics
    assert rep.extra["converged"] is True


def test_surprise_spikes_on_unexpected_joint_shove():
    rep = run_mujoco_babbling(steps=400, seed=2)
    assert rep.surprise_ratio > 3.0                    # an uncommanded joint jolt is genuinely surprising


def test_rigorous_contact_produces_affordance():
    # the arm reaching the box registers a REAL MuJoCo contact -> an M2s affordance candidate.
    rep = run_mujoco_babbling(steps=600, seed=5)
    assert rep.object_contacts >= 1
    assert "can_push:target" in rep.affordances


def test_m3s_self_other_attribution_above_chance():
    # agency PPI: self-caused (predicted) vs external (unpredicted) motion must be separable, well
    # above the 0.5 chance line. This is the measured self/other boundary of a developmental self.
    r = run_self_other_attribution(trials=120, seed=1)
    assert r["attribution_accuracy"] > 0.7
