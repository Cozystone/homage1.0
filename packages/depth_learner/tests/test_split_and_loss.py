# -*- coding: utf-8 -*-
"""The two properties that decide whether the depth number means anything.

Neither is about the network. A depth model with a leaky split or a loss that secretly rewards
guessing the mean will report a good score and have learned nothing, and the loss curve will look
fine throughout. These are the checks that fail instead.
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from packages.depth_learner import data as D
from packages.depth_learner.model import DepthNet, metrics, silog_loss


# ---------------------------------------------------------------- the split

def _split_or_skip():
    if not D.ROOT.exists() or not any(D.ROOT.glob("ep*/meta.json")):
        pytest.skip("no CARLA corpus on this machine")
    return D.build_split()


def test_no_episode_is_in_two_splits():
    """The obvious leak. Cheap to check, fatal if missed."""
    s = _split_or_skip()
    sets = [set(s.train), set(s.val_town), set(s.val_episode)]
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            assert not (sets[i] & sets[j]), f"episode in two splits: {sets[i] & sets[j]}"


def test_val_town_episodes_come_from_towns_training_never_saw():
    """The leak that matters and that an episode-level split does NOT catch.

    Two drives through the same town share its buildings, its street widths, its skyline. A model
    can score well on a held-out EPISODE by having memorised the town, which is why `val_town`
    exists and why its towns must be absent from training entirely."""
    s = _split_or_skip()
    train_towns = {s.towns[e] for e in s.train}
    val_towns = {s.towns[e] for e in s.val_town}
    assert val_towns, "no held-out towns — the generalisation reading would be vacuous"
    assert not (train_towns & val_towns), f"town appears in both: {train_towns & val_towns}"


def test_sky_is_excluded_from_supervision():
    """Sky's ground truth is the 1000m far plane — a sentinel meaning "no surface", not a distance.

    It is also a large fraction of a city frame, so training on it would let it dominate the loss
    and pull every real prediction toward infinity."""
    s = _split_or_skip()
    paths = D.frames(s.train, stride=200)[:3]
    if not paths:
        pytest.skip("corpus too small")
    seen_sky = False
    for p in paths:
        _rgb, dep, valid = D.load(p)
        # Whatever the mask does elsewhere, no surviving pixel may be at or near the far plane —
        # that is the observable consequence of excluding sky, checked without re-deriving the
        # resize arithmetic the loader already did.
        assert dep[valid].max() <= 200.0 + 1e-3, "far-plane pixels survived the mask"
        assert dep[valid].min() >= 0.5 - 1e-3
        if (dep >= 999.0).any():
            seen_sky = True
            assert not valid[dep >= 999.0].any(), "a 1000m sentinel pixel was marked valid"
    assert seen_sky, "no far-plane pixels in the sample — the check never actually ran"


# ---------------------------------------------------------------- the loss

def test_silog_is_only_partially_scale_invariant_and_much_flatter_than_l2():
    """How much a global multiplier costs — measured against both ends, not asserted.

    Depth from a single image cannot determine absolute scale: a city and a scale model of it are
    identical pixels. A loss that fully punishes a global multiplier asks for something the input
    does not contain, and a network answers that by predicting the mean everywhere.

    This test began life asserting flat invariance and FAILED, correctly: at LAMBDA=0.85 a x0.5
    shift moves the loss 0.199 -> 0.334. That is deliberate — CARLA supplies real metres — but the
    docstring had called the loss "scale-invariant" without qualification, and the test is what
    caught the overstatement. What is actually true is checked here instead: the term is far flatter
    than plain log-L2, and setting LAMBDA=1.0 makes it exactly flat."""
    from packages.depth_learner import model as M

    rng = np.random.default_rng(0)
    target = torch.tensor(rng.uniform(2.0, 80.0, (2, 32, 32)).astype(np.float32))
    valid = torch.ones_like(target, dtype=torch.bool)
    pred = torch.log(target) + torch.tensor(rng.normal(0, 0.2, target.shape).astype(np.float32))
    shifted = pred + float(np.log(0.5))              # a global scale is an additive shift in log

    base = float(silog_loss(pred, target, valid))
    silog_grew = float(silog_loss(shifted, target, valid)) / base
    l2 = lambda p: float(torch.sqrt((((p - torch.log(target)) ** 2)[valid]).mean()))
    l2_grew = l2(shifted) / l2(pred)

    assert silog_grew < 0.6 * l2_grew, (
        f"silog grew x{silog_grew:.2f} under a x0.5 scale, plain log-L2 grew x{l2_grew:.2f} — "
        "the scale-invariant term is not buying much")

    old, M.LAMBDA = M.LAMBDA, 1.0                    # full invariance is the LAMBDA=1 limit
    try:
        assert abs(float(M.silog_loss(shifted, target, valid))
                   - float(M.silog_loss(pred, target, valid))) < 1e-4
    finally:
        M.LAMBDA = old


def test_loss_punishes_predicting_a_constant():
    """The failure mode the loss must NOT reward: one number everywhere.

    A scale-invariant loss that also ignored structure would be satisfied by a constant, and the
    model would learn nothing. Structure must score better than flatness."""
    rng = np.random.default_rng(1)
    target = torch.tensor(rng.uniform(2.0, 80.0, (2, 32, 32)).astype(np.float32))
    valid = torch.ones_like(target, dtype=torch.bool)
    good = torch.log(target) + 0.05 * torch.tensor(rng.normal(0, 1, target.shape).astype(np.float32))
    flat = torch.full_like(target, float(torch.log(target).mean()))
    assert float(silog_loss(good, target, valid)) < float(silog_loss(flat, target, valid))


def test_metrics_report_raw_and_scaled_separately():
    """A scale-invariant model scored raw looks worse than it is; scored only scaled it looks better
    than a user would experience. Both are reported so neither reading can stand alone."""
    rng = np.random.default_rng(2)
    target = torch.tensor(rng.uniform(2.0, 80.0, (1, 16, 16)).astype(np.float32))
    valid = torch.ones_like(target, dtype=torch.bool)
    pred = torch.log(target) + float(np.log(3.0))    # perfect structure, wrong scale by 3x
    m = metrics(pred, target, valid)
    assert m["absrel"] > 0.5, "raw absrel should expose the wrong global scale"
    assert m["absrel_scaled"] < 0.02, "median-scaled absrel should show the structure is right"


def test_model_shape_and_param_count_are_what_the_docstring_claims():
    net = DepthNet(width=32)
    n = sum(p.numel() for p in net.parameters())
    assert 3.0e6 < n < 3.7e6, f"docstring says 3.35M params, model has {n}"
    out = net(torch.zeros(1, 3, 240, 320))
    assert out.shape == (1, 240, 320)
