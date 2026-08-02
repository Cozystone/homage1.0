# -*- coding: utf-8 -*-
"""Predictive attention gate — the expensive detector runs on CHANGE, not on every frame
(owner: — )."""
from __future__ import annotations

import numpy as np

from packages.perception.attention import (
    change_energy,
    commit,
    decide,
    frame_signature,
    new_state,
)


def _frame(fill: int, size=(240, 320)) -> np.ndarray:
    return np.full((size[0], size[1], 3), fill, dtype=np.uint8)


def test_signature_is_stable_and_size_robust():
    a = frame_signature(_frame(120))
    b = frame_signature(_frame(120))
    assert a.shape == b.shape and np.allclose(a, b)          # same frame -> same code
    odd = frame_signature(_frame(120, size=(97, 53)))        # non-multiple size must not crash
    assert odd.shape == a.shape


def test_change_energy_zero_for_identical_high_for_different():
    a = frame_signature(_frame(30))
    b = frame_signature(_frame(30))
    c = frame_signature(_frame(220))
    assert change_energy(a, b) == 0.0
    assert change_energy(a, c) > 0.5                          # black vs bright -> large prediction error


def test_cold_start_always_detects():
    st = new_state()
    d = decide(st, frame_signature(_frame(100)), now=0.0)
    assert d["run"] and d["reason"] == "cold_start"


def test_static_scene_is_predicted_and_skipped():
    st = new_state()
    sig = frame_signature(_frame(100))
    d0 = decide(st, sig, now=0.0)
    assert d0["run"]
    commit(st, sig, now=0.0)
    # an identical frame a moment later -> predicted, no detection, cheap
    d1 = decide(st, frame_signature(_frame(100)), now=1.0)
    assert not d1["run"] and d1["reason"] == "predicted"


def test_motion_waits_then_detects_on_settle():
    st = new_state()
    base = frame_signature(_frame(100))
    commit(st, base, now=0.0)
    # a big change arrives -> we WAIT (mid-motion frame is blurry, bad to detect)
    moving = decide(st, frame_signature(_frame(210)), now=1.0)
    assert not moving["run"] and moving["reason"] == "moving_wait"
    # the scene settles back near the baseline -> NOW detect the new stable scene
    settled = decide(st, frame_signature(_frame(100)), now=2.0)
    assert settled["run"] and settled["reason"] == "settled"


def test_periodic_refresh_even_when_static():
    st = new_state()
    sig = frame_signature(_frame(100))
    commit(st, sig, now=0.0)
    # identical frame but a long time later -> refresh detection fires (slow-drift safety net)
    d = decide(st, frame_signature(_frame(100)), now=10.0)
    assert d["run"] and d["reason"] == "refresh"


def test_gate_saves_compute_over_a_static_run():
    """Over a static stretch, the detector should fire only a small number of times, not once
    per frame — the whole point of the gate."""
    st = new_state()
    runs = 0
    t = 0.0
    for _ in range(60):                      # 60 frames of an unchanging scene
        sig = frame_signature(_frame(100))
        d = decide(st, sig, now=t)
        if d["run"]:
            commit(st, sig, now=t)
            runs += 1
        t += 1.0
    # 60s static -> only cold_start + periodic refreshes (~1 per 6s), nowhere near 60
    assert runs <= 12
