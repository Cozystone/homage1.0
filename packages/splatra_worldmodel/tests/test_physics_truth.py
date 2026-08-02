# -*- coding: utf-8 -*-
"""The symbolic membrane in 3D: physics-truth VERIFY + quarantine (violations never learned)."""
from __future__ import annotations

import numpy as np

from packages.splatra_worldmodel.forward_model import DynamicsParams, ground_y, simulate_episode
from packages.splatra_worldmodel.physics_truth import PhysicsTruthGate
from packages.splatra_worldmodel.turbovec_field import FieldState


def _prev_next():
    d = DynamicsParams(count=200)
    ep = simulate_episode(d, steps=16, seed=5, init_offset=np.zeros(3), init_vel=np.zeros(3))
    prev = FieldState(ep.states[4].pos, np.zeros_like(ep.states[4].pos))
    nxt = FieldState(ep.states[5].pos, np.zeros_like(ep.states[5].pos))
    return prev, ep.actions[4], nxt


def test_true_transition_passes():
    prev, action, nxt = _prev_next()
    gate = PhysicsTruthGate()
    v = gate.verify(prev, action, nxt)
    assert v.ok, v.as_reason()


def test_below_ground_is_caught():
    prev, action, nxt = _prev_next()
    gate = PhysicsTruthGate()
    bad = nxt.pos.copy(); bad[:, 1] = ground_y() - 0.4
    v = gate.verify(prev, action, FieldState(bad, np.zeros_like(bad)))
    assert not v.ok
    assert "ground_penetration" in v.violations


def test_teleport_is_caught():
    prev, action, nxt = _prev_next()
    gate = PhysicsTruthGate()
    bad = nxt.pos.copy(); bad[:, 0] += 5.0
    v = gate.verify(prev, action, FieldState(bad, np.zeros_like(bad)))
    assert not v.ok
    assert "teleport" in v.violations


def test_implosion_is_caught():
    prev, action, nxt = _prev_next()
    gate = PhysicsTruthGate()
    c = nxt.pos.mean(0)
    imp = c[None, :] + 0.02 * (nxt.pos - c)   # collapse toward the centroid
    v = gate.verify(prev, action, FieldState(imp, np.zeros_like(imp)))
    assert not v.ok
    assert "implosion" in v.violations


def test_filter_quarantines_only_violations():
    prev, action, nxt = _prev_next()
    gate = PhysicsTruthGate()
    good = (prev, action, nxt)
    below = nxt.pos.copy(); below[:, 1] = ground_y() - 0.5
    bad = (prev, action, FieldState(below, np.zeros_like(below)))
    res = gate.filter_transitions([good, bad, good, bad, good])
    assert res.n_kept == 3
    assert res.n_quarantined == 2
    assert all("ground_penetration" in r for r in res.reasons)


def test_ground_plane_matches_splatra_body():
    from packages.embodiment.splatra_body import _GROUND_Y
    assert PhysicsTruthGate().ground_plane == float(_GROUND_Y)
