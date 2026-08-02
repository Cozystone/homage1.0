# -*- coding: utf-8 -*-
"""The two live seams of the V-JEPA fusion (docs/ATANOR_vjepa_fusion.md §4), verified to be ADDITIVE:

  Seam A (attention.decide)  — a latent-surprise gate; the pixel-delta path is preserved untouched as
                               the cold-start fallback (latent_surprise=None -> original behavior).
  Seam B (video_events.surprise) — latent surprise ALONGSIDE the symbolic surprise; think_harder =
                               symbolic OR latent; the latent read stays a flagged hypothesis (DATA).

Every test that supplies no latent surprise must reproduce the organs' pre-fusion behavior exactly —
'tests are constitution': nothing existing is weakened."""
from __future__ import annotations

import numpy as np

from packages.perception.attention import commit, decide, frame_signature, new_state
from packages.perception.video_events import (events_from_frames, predict_next, surprise)


def _frame(fill: int, size=(240, 320)) -> np.ndarray:
    return np.full((size[0], size[1], 3), fill, dtype=np.uint8)


def _g(nodes, edges):
    return {"nodes": [{"label": n, "count": 1} for n in nodes],
            "edges": [{"subject": s, "relation": r, "object": o} for s, r, o in edges]}


# ---- Seam A: attention.decide -------------------------------------------------------------
def test_seam_a_none_preserves_pixel_path():
    """No latent surprise -> the original pixel-delta decision, unchanged (a static frame is
    predicted and skipped)."""
    st = new_state()
    sig = frame_signature(_frame(100))
    commit(st, sig, now=0.0)
    d = decide(st, frame_signature(_frame(100)), now=1.0)          # no latent_surprise
    assert d["run"] is False and d["reason"] == "predicted"


def test_seam_a_fires_on_latent_change_even_when_pixels_static():
    """A SEMANTIC change with no pixel motion (identical frame) still fires the detector when latent
    surprise is high — the win the pixel delta cannot deliver."""
    st = new_state()
    sig = frame_signature(_frame(100))
    commit(st, sig, now=0.0)
    d = decide(st, sig, now=1.0, latent_surprise=3.0)              # high latent surprise, zero pixel delta
    assert d["run"] is True and d["reason"] == "latent_change"
    assert d["latent_surprise"] == 3.0


def test_seam_a_idles_through_high_pixel_lighting_when_latent_low():
    """A big PIXEL change (e.g. lighting/noise) that the latent predicted -> idle. The pixel path
    alone would have fired; the latent gate correctly suppresses the false alarm."""
    st = new_state()
    commit(st, frame_signature(_frame(40)), now=0.0)
    big_pixel_jump = frame_signature(_frame(210))                 # huge change_energy
    d = decide(st, big_pixel_jump, now=1.0, latent_surprise=0.2)  # but latent says 'predicted'
    assert d["run"] is False and d["reason"] == "latent_idle"
    assert d["energy"] > 0.5                                       # pixels really did move a lot


def test_seam_a_refresh_safety_net_still_wins_over_latent():
    """The periodic refresh sits beneath BOTH paths: even with a quiet latent, slow drift is re-read."""
    st = new_state()
    commit(st, frame_signature(_frame(100)), now=0.0)
    d = decide(st, frame_signature(_frame(100)), now=10.0, latent_surprise=0.0)
    assert d["run"] is True and d["reason"] == "refresh"


def test_seam_a_cold_start_unaffected():
    d = decide(new_state(), frame_signature(_frame(100)), now=0.0, latent_surprise=5.0)
    assert d["run"] is True and d["reason"] == "cold_start"


# ---- Seam B: video_events.surprise --------------------------------------------------------
def _quiet_prediction():
    """A prediction that expects nothing -> symbolic surprise 0 (symbolic think_harder False), so any
    think_harder must come from the latent seam."""
    frames = [_g(["a"], []), _g(["a"], [])]
    pred = predict_next(frames)
    return pred, frames[-1], events_from_frames(frames[-2:])


def test_seam_b_none_preserves_symbolic_behavior():
    pred, g, evs = _quiet_prediction()
    s = surprise(pred, g, evs)                                     # no latent
    assert 0.0 <= s["surprise"] <= 1.0
    assert s["think_harder"] is False and "latent" not in s


def test_seam_b_latent_triggers_think_harder_alongside_symbolic():
    pred, g, evs = _quiet_prediction()
    s = surprise(pred, g, evs, latent_surprise=2.5)               # symbolic quiet, latent loud
    assert s["think_harder"] is True                              # OR: latent lit it
    assert s["surprise"] == 0.0                                   # symbolic score itself unchanged


def test_seam_b_latent_is_a_flagged_hypothesis_not_fact():
    pred, g, evs = _quiet_prediction()
    s = surprise(pred, g, evs, latent_surprise=2.5)
    assert s["latent"]["is_hypothesis"] is True
    assert s["latent"]["source"] == "latent_predictor"
    assert s["latent"]["think_harder"] is True


def test_seam_b_low_latent_does_not_force_think_harder():
    pred, g, evs = _quiet_prediction()
    s = surprise(pred, g, evs, latent_surprise=0.3)               # both quiet
    assert s["think_harder"] is False
    assert s["latent"]["is_hypothesis"] is True                   # still reported as DATA
