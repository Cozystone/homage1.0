# -*- coding: utf-8 -*-
"""Permanence, checked on scenarios built here — so the right answer is known by construction.

The episode run scores this against a simulator; these fix the BEHAVIOUR, so a later change that
still scores well on average but has stopped believing in hidden things fails here instead of
passing quietly.
"""
from __future__ import annotations

import numpy as np
import pytest

from packages.perception.object_permanence import Permanence, _cos, appearance, centroid

RED = np.concatenate([np.array([0, 0, 0, 0, 0, 0, 0, 1.0]), np.zeros(8), np.zeros(8)]).astype("f4")
BLUE = np.concatenate([np.zeros(8), np.zeros(8), np.array([0, 0, 0, 0, 0, 0, 0, 1.0])]).astype("f4")


def test_a_thing_that_keeps_moving_keeps_its_identity():
    p = Permanence()
    for t in range(5):
        p.observe([((10.0 + 5 * t, 20.0), RED)], t)
    assert len(p.tracks) == 1, "one thing seen five times is one thing"
    assert p.tracks[1].seen == 5


def test_identity_survives_a_gap_it_could_not_be_seen_through():
    """The whole point: vanish for several frames, reappear where the motion predicted."""
    p = Permanence()
    for t in range(4):
        p.observe([((10.0 + 5 * t, 20.0), RED)], t)
    for t in range(4, 9):
        p.observe([], t)                                  # gone behind something
        assert p.hidden_now(t), "a thing unseen for a moment is still believed in"
    out = p.observe([((10.0 + 5 * 9, 20.0), RED)], 9)     # emerges where it was heading
    assert out["bound"] == {0: 1}, "the thing that came out is the thing that went in"
    assert out["new"] == []


def test_prediction_is_what_carries_it_across_not_memory_of_where_it_stopped():
    """A thing hidden for five frames is NOT where it was last seen, and binding on last-seen
    position would fail here. This is the difference the owner's simulation idea makes."""
    p = Permanence(look_weight=0.0)                        # position only, so the claim is unmixed
    for t in range(4):
        p.observe([((10.0 + 40 * t, 20.0), RED)], t)
    # last seen at t=3 sitting at x=130 with vel 40/frame, so by t=9 it has coasted six frames.
    assert p.tracks[1].predict(9) == pytest.approx((130.0 + 40 * 6, 20.0)), "coasts at its velocity"
    out = p.observe([((370.0, 20.0), RED)], 9)
    assert out["bound"] == {0: 1}


def test_belief_expires_rather_than_lasting_forever():
    p = Permanence(gap_tolerance=3)
    p.observe([((10.0, 20.0), RED)], 0)
    assert p.hidden_now(3)
    assert not p.hidden_now(9), "believing in something unseen for ever is not permanence"
    out = p.observe([((10.0, 20.0), RED)], 9)
    assert out["new"] == [0], "after giving up, the same-looking thing is a new one, honestly"


def test_two_things_at_once_do_not_collapse_into_one():
    """The failure sprite_tracker's docstring records: nine chains all taking the nearest blob."""
    p = Permanence()
    for t in range(4):
        p.observe([((10.0 + 3 * t, 20.0), RED), ((300.0 - 3 * t, 400.0), BLUE)], t)
    assert len(p.tracks) == 2
    out = p.observe([((22.0, 20.0), RED), ((288.0, 400.0), BLUE)], 4)
    assert sorted(out["bound"].values()) == [1, 2], "one detection each, never the same track twice"


def test_appearance_separates_things_that_are_in_the_same_place():
    """Position alone cannot tell a red thing from a blue one that crossed it."""
    assert _cos(RED, BLUE) < 0.1
    assert _cos(RED, RED) == pytest.approx(1.0)


def test_centroid_and_appearance_survive_an_empty_mask():
    m = np.zeros((4, 4), dtype=bool)
    assert centroid(m) == (0.0, 0.0)
    assert appearance(np.zeros((4, 4, 3), dtype=np.uint8), m).shape == (24,)
