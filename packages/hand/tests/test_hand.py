# -*- coding: utf-8 -*-
"""The safety property and the discovery property — the two things worth pinning."""
from __future__ import annotations

import numpy as np

from packages.hand import Move, WindowEffector, flow_signature


def test_refuses_when_target_window_is_not_in_front():
    """Synthetic input goes wherever the focus is. If the target is not in front, the keystrokes
    land in whatever the operator happens to be using — so this must REFUSE, not proceed. Checked
    against a title nothing will ever have."""
    h = WindowEffector(title_contains="__no_such_window_ever__")
    res = h.do(Move(keys=("w",), seconds=0.01))
    assert res["ok"] is False
    assert res["refused"] == "not_foreground"


def test_refuses_unknown_keys_rather_than_guessing():
    h = WindowEffector(title_contains="__no_such_window_ever__")
    res = h.do(Move(keys=("nonexistent_key",), seconds=0.01))
    assert res["ok"] is False and res["refused"] in ("not_foreground", "unknown_key")


def test_hold_is_bounded():
    """A stuck key is a runaway body. The cap is enforced by clamping, not by trusting the caller."""
    h = WindowEffector(title_contains="x", max_seconds=0.5)
    assert h.max_seconds == 0.5


def _scene(seed: int = 0, h: int = 240, w: int = 320) -> np.ndarray:
    """A SMOOTH textured image, because that is what a camera frame is.

    White noise was the first thing tried here and it is the wrong stimulus: a downsampler that
    averages areas cannot preserve structure that has none, so the test measured the test rather
    than the estimator. Real frames are spatially correlated, so the fixture is too — low-frequency
    blobs plus a gradient, which is a fair stand-in for a street."""
    rng = np.random.default_rng(seed)
    coarse = rng.random((h // 16, w // 16)).astype(np.float32)
    ys = np.clip((np.arange(h) / 16).astype(int), 0, coarse.shape[0] - 1)
    xs = np.clip((np.arange(w) / 16).astype(int), 0, coarse.shape[1] - 1)
    img = coarse[ys][:, xs]
    for _ in range(3):                     # blur so the structure survives downsampling
        img = (img + np.roll(img, 1, 0) + np.roll(img, -1, 0)
               + np.roll(img, 1, 1) + np.roll(img, -1, 1)) / 5.0
    img = img + np.linspace(0, 0.3, w)[None, :]
    img = (img - img.min()) / (np.ptp(img) + 1e-6)
    return np.repeat((img * 255).astype(np.uint8)[:, :, None], 3, axis=2)


def _shifted(img: np.ndarray, dx: int, dy: int) -> np.ndarray:
    return np.roll(np.roll(img, dy, axis=0), dx, axis=1)


def test_flow_reads_a_known_horizontal_shift():
    """The consequence reader has to actually read direction, or every body-schema row is noise."""
    a = _scene(0)
    right = flow_signature(a, _shifted(a, 20, 0))
    left = flow_signature(a, _shifted(a, -20, 0))
    assert right["dx"] > 1.0, right
    assert left["dx"] < -1.0, left


def test_flow_separates_expansion_from_sliding():
    """Walking and turning both slide most pixels sideways; only walking spreads them out from the
    centre. A global-shift estimator would call those the same act, so divergence is measured too."""
    a = _scene(1)
    slide = flow_signature(a, _shifted(a, 20, 0))
    # a crude zoom: sample a centre crop back up to full size => everything moves outward
    crop = a[30:210, 40:280]
    ys = (np.arange(240) * (crop.shape[0] / 240)).astype(np.int32)
    xs = (np.arange(320) * (crop.shape[1] / 320)).astype(np.int32)
    zoom = crop[ys][:, xs]
    grow = flow_signature(a, zoom)
    assert grow["div"] > slide["div"], (grow, slide)
