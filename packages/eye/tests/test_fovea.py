# -*- coding: utf-8 -*-
"""Does the retina actually cost less and keep the middle, and does the eye look at what changed?"""
from __future__ import annotations

import numpy as np
import pytest

from packages.eye.fovea import Retina, RetinaSpec, reconstruct, sample


def _scene(h=1080, w=1920, seed=0):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.zeros((h, w), np.float32)
    for _ in range(8):
        cy, cx = rng.uniform(0, h), rng.uniform(0, w)
        img += rng.uniform(40, 200) * np.exp(-((y - cy) ** 2 + (x - cx) ** 2) / rng.uniform(4e3, 9e4))
    img = np.clip(img, 0, 255)
    return np.repeat(img[:, :, None], 3, axis=2).astype(np.uint8)


def test_it_costs_far_less_than_the_frame():
    s = sample(_scene(), 0.5, 0.5)
    assert s["compression"] > 10, s["compression"]
    assert s["sampled_px"] < s["full_px"] * 0.1


def test_the_middle_is_kept_exactly():
    """The fovea is not resampled — a sense organ that blurs its own centre has no centre."""
    img = _scene()
    s = sample(img, 0.5, 0.5)
    x0, y0, x1, y1 = s["fovea_box"]
    assert np.array_equal(s["fovea"], img[y0:y1, x0:x1])


def test_detail_falls_off_with_eccentricity():
    """Each ring covers more ground on the same grid, so it must carry less detail per unit area."""
    s = sample(_scene(), 0.5, 0.5)
    scales = [lv["scale"] for lv in s["levels"]]
    assert scales == sorted(scales) and len(scales) >= 2
    assert scales[-1] > scales[0] * 2


def test_the_periphery_is_still_there():
    """A crop would score better on compression and could not decide where to look next."""
    img = _scene()
    s = sample(img, 0.2, 0.2)
    covered = s["levels"][-1]["box"]
    assert (covered[2] - covered[0]) > img.shape[1] * 0.5


def test_the_eye_moves_to_what_changed():
    a = _scene()
    b = a.copy()
    b[80:200, 1500:1700] = 255                      # something happens at the upper right
    r = Retina()
    r.look(a)                                        # establishes the prediction
    out = r.look(b)
    cx, cy = out["saccade_to"]
    assert cx > 0.55, f"did not look right: {out['saccade_to']}"
    assert cy < 0.45, f"did not look up: {out['saccade_to']}"


def test_a_still_world_costs_nothing_and_moves_nothing():
    a = _scene()
    r = Retina()
    r.look(a)
    out = r.look(a)
    assert out["surprise_total"] < 1e-6
    assert out["saccade_to"] is None, "the eye should stay put when nothing happened"


def test_reconstruction_keeps_the_centre_sharper_than_the_edge():
    """Measured, not asserted: error against the true frame must be lower in the fovea."""
    img = _scene()
    s = sample(img, 0.5, 0.5)
    rec = reconstruct(s, img.shape[:2])
    g = img.mean(axis=2)
    x0, y0, x1, y1 = s["fovea_box"]
    centre = np.abs(rec[y0:y1, x0:x1] - g[y0:y1, x0:x1]).mean()
    edge = np.abs(rec[:60, :60] - g[:60, :60]).mean()
    assert centre < edge, f"centre {centre:.3f} should beat edge {edge:.3f}"


def test_a_tiny_spec_still_covers_the_field():
    s = sample(_scene(), 0.9, 0.1, RetinaSpec(fovea_px=32, rings=6, ring_px=16))
    assert s["compression"] > 100
    assert len(s["levels"]) >= 3


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
