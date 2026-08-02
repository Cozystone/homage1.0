# -*- coding: utf-8 -*-
"""The toy deforming body: subclasses SplatraBody, falls, contacts the ground, deterministic."""
from __future__ import annotations

import numpy as np

from packages.embodiment.splatra_body import SplatraBody
from packages.splatra_worldmodel.forward_model import (
    DynamicsParams,
    ToyDeformingBody,
    ground_y,
    simulate_episode,
)


def test_is_a_subclass_not_an_edit():
    # We WRAP/subclass the proven kernel; we never edit it.
    assert issubclass(ToyDeformingBody, SplatraBody)


def test_ground_plane_is_reused_from_splatra_body():
    from packages.embodiment.splatra_body import _GROUND_Y
    assert ground_y() == float(_GROUND_Y)


def test_episode_shapes():
    d = DynamicsParams(count=200)
    ep = simulate_episode(d, steps=20, seed=7)
    assert len(ep.states) == 21          # T+1 states
    assert len(ep.actions) == 20
    assert len(ep.contacts) == 20
    assert ep.states[0].pos.shape[1] == 3


def test_body_falls_and_contacts_ground():
    d = DynamicsParams(count=200)
    ep = simulate_episode(d, steps=32, seed=7, init_offset=np.zeros(3), init_vel=np.zeros(3))
    top_start = ep.states[0].pos[:, 1].min()
    bottom_end = ep.states[-1].pos[:, 1].min()
    # it starts above the floor and descends to rest on the floor
    assert top_start > ground_y() + 0.5
    assert abs(bottom_end - ground_y()) < 1e-2
    assert any(ep.contacts), "expected at least one ground-contact frame"


def test_never_penetrates_ground():
    d = DynamicsParams(count=200)
    ep = simulate_episode(d, steps=40, seed=11)
    for st in ep.states:
        assert st.pos[:, 1].min() >= ground_y() - 1e-6


def test_determinism():
    d = DynamicsParams(count=200)
    a = simulate_episode(d, steps=16, seed=3, init_offset=np.zeros(3), init_vel=np.zeros(3))
    b = simulate_episode(d, steps=16, seed=3, init_offset=np.zeros(3), init_vel=np.zeros(3))
    for sa, sb in zip(a.states, b.states):
        assert np.allclose(sa.pos, sb.pos)
        assert np.allclose(sa.vel, sb.vel)


def test_contact_frames_carry_motion():
    # the contact regime is a live squash/rebound, not dead rest -- a meaningful test bed.
    d = DynamicsParams(count=200)
    ep = simulate_episode(d, steps=32, seed=7, init_offset=np.zeros(3), init_vel=np.zeros(3))
    motion = [float(np.linalg.norm(ep.states[t + 1].pos - ep.states[t].pos, axis=1).mean())
              for t in range(len(ep.actions))]
    contact_motion = [m for m, c in zip(motion, ep.contacts) if c]
    assert np.mean(contact_motion) > 0.01
