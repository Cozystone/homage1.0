# -*- coding: utf-8 -*-
"""Is the geometry right? A wrong warp trains silently and looks fine the whole way.

The load-bearing test is the first one: build a scene where the true depth and the true camera
motion are both known, and check that warping with the TRUTH beats warping with anything else. If
that fails, every loss curve produced by this module is meaningless, and nothing downstream would
say so — the net would converge happily onto a wrong objective.
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from packages.depth_learner.selfsup import (D_MAX, PoseNet, _pose_to_matrix, bounded_log_depth,
                                            intrinsics, photometric, selfsup_loss, smoothness, warp)

H, W = 96, 128


def _scene(shift_px: float = 6.0):
    """Two views of a slanted plane, made by construction rather than by rendering.

    The plane is nearer at the bottom of the image, so its parallax varies down the frame — which is
    what makes the test discriminating. A constant-depth scene would be warped correctly by any
    depth-plus-matching-translation pair and would not test anything."""
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    depth = 8.0 + 22.0 * (1.0 - ys / H)                      # 8m at the bottom, 30m at the top
    tex = (np.sin(xs / 5.0) * np.cos(ys / 7.0) + np.sin((xs + ys) / 3.0)) * 0.25 + 0.5

    K = intrinsics(H, W)
    f = float(K[0, 0])
    tx = shift_px * float(depth.mean()) / f                  # sideways move, in metres

    # THE SIGN, and getting it backwards is what the first run of this file caught. `warp` samples
    # the source at `u + f*tx/Z`, so for the warp to RECOVER the target the source must hold the
    # target's content shifted the other way: src[x] = tex[x - f*tx/Z]. Built with `+` instead, the
    # fixture applies the parallax twice, true depth reconstructs nothing, and the test correctly
    # reported that the truth was no better than a wrong answer.
    #
    # This works exactly, rather than approximately, only because `depth` varies with y alone: the
    # shift is then constant along each row, so a row-wise resample is the true inverse warp and
    # there is no interpolation error pretending to be a geometry error.
    src_x = xs - f * tx / depth
    src = np.zeros_like(tex)
    x0 = np.clip(src_x, 0, W - 1)
    xi = x0.astype(np.int32)
    xf = x0 - xi
    xi1 = np.clip(xi + 1, 0, W - 1)
    src = tex[ys.astype(np.int32), xi] * (1 - xf) + tex[ys.astype(np.int32), xi1] * xf

    t = lambda a: torch.from_numpy(np.ascontiguousarray(a)).float()[None, None].repeat(1, 3, 1, 1)
    pose = _pose_to_matrix(torch.zeros(1, 3), torch.tensor([[tx, 0.0, 0.0]]))
    return t(tex), t(src), t(depth)[:, :1], pose, K


def test_the_true_depth_warps_better_than_a_wrong_one():
    """THE ONE THAT MATTERS. Truth must beat every alternative, including plausible ones."""
    tgt, src, depth, pose, K = _scene()
    err_true = photometric(warp(src, depth, pose, K), tgt).mean().item()
    for name, wrong in (("half", depth * 0.5), ("double", depth * 2.0),
                        ("flat", torch.full_like(depth, float(depth.mean()))),
                        ("inverted", depth.max() + depth.min() - depth)):
        err = photometric(warp(src, wrong, pose, K), tgt).mean().item()
        assert err > err_true * 1.15, f"{name} depth scored {err:.5f} vs true {err_true:.5f}"


def test_a_zero_pose_leaves_the_image_alone():
    tgt, src, depth, _, K = _scene()
    ident = _pose_to_matrix(torch.zeros(1, 3), torch.zeros(1, 3))
    out = warp(src, depth, ident, K)
    assert (out - src).abs().mean().item() < 1e-4


def test_rodrigues_is_a_rotation():
    ax = torch.tensor([[0.3, -0.2, 0.7]])
    R = _pose_to_matrix(ax, torch.zeros(1, 3))[:, :3, :3]
    assert torch.allclose(R @ R.transpose(1, 2), torch.eye(3)[None], atol=1e-5)
    assert abs(torch.det(R).item() - 1.0) < 1e-5


def test_the_automask_drops_pixels_that_did_not_need_the_warp():
    """A frame that is identical to its neighbour carries no parallax anywhere, so the mask should
    keep almost nothing. This is the mechanism that stops a car moving with the camera from being
    learned as infinitely far away."""
    tgt, _, depth, _, K = _scene()
    still = tgt.clone()
    pose = _pose_to_matrix(torch.zeros(1, 3), torch.tensor([[0.4, 0.0, 0.0]]))
    out = selfsup_loss(tgt, [still], depth, [pose], K)
    assert out["kept"].item() < 0.15, f"kept {out['kept'].item():.3f} of a frame with no motion"


def test_the_automask_keeps_pixels_that_did():
    tgt, src, depth, pose, K = _scene()
    out = selfsup_loss(tgt, [src], depth, [pose], K)
    assert out["kept"].item() > 0.5, f"kept only {out['kept'].item():.3f} of a genuinely moved frame"


def test_min_over_neighbours_survives_an_occluded_one():
    """One neighbour that cannot explain the pixel must not drag the loss up when another can."""
    tgt, src, depth, pose, K = _scene()
    blocked = torch.rand_like(src)            # a neighbour that sees something else entirely
    both = selfsup_loss(tgt, [src, blocked], depth, [pose, pose], K)["photo"].item()
    good = selfsup_loss(tgt, [src], depth, [pose], K)["photo"].item()
    assert both < good * 1.25, f"the useless neighbour cost {both:.5f} vs {good:.5f}"


def test_smoothness_allows_a_depth_edge_where_the_image_has_one():
    img = torch.zeros(1, 3, H, W)
    img[..., W // 2:] = 1.0
    step = torch.ones(1, 1, H, W)
    step[..., W // 2:] = 4.0
    aligned = smoothness(step, img).item()
    misaligned = smoothness(step.roll(W // 4, dims=3), img).item()
    assert aligned < misaligned, f"edge-aligned {aligned:.5f} should cost less than {misaligned:.5f}"


def test_the_pose_net_starts_near_identity():
    """Unscaled initial poses fling the camera out of the scene and every warp samples off the edge,
    so the first gradients are noise. It must start almost still."""
    net = PoseNet()
    a, b = torch.rand(2, 3, H, W), torch.rand(2, 3, H, W)
    ax, tr = net(a, b)
    assert ax.abs().max().item() < 0.1 and tr.abs().max().item() < 0.1


def _fit(steps: int, bounded: bool, smooth_w: float = 1e-3):
    """Optimise a free depth map against the objective alone, and report where it ended up."""
    tgt, src, truth, pose, K = _scene()
    raw = torch.full_like(truth, float(np.log(19.0))).requires_grad_(True)      # flat, wrong
    opt = torch.optim.Adam([raw], lr=0.02)
    dep = lambda: (bounded_log_depth(raw) if bounded else raw).exp()
    start = (dep().detach() - truth).abs().mean().item()
    for _ in range(steps):
        opt.zero_grad()
        selfsup_loss(tgt, [src], dep(), [pose], K, smooth_w=smooth_w)["loss"].backward()
        opt.step()
    d = dep().detach()
    # It cannot recover scale — halving depth and halving translation warp identically — so absolute
    # error is the wrong yardstick. What must improve is the STRUCTURE, after the best global scale
    # is divided out.
    s = (truth.flatten() @ d.flatten()) / (d.flatten() ** 2).sum()
    return {"start": start, "scaled_err": ((d * s) - truth).abs().mean().item(),
            "max": d.max().item()}


def test_the_objective_can_actually_recover_depth():
    """The real question: does optimising against the objective alone move depth TOWARD the truth?

    A loss that falls while the answer gets worse is the failure this catches, and it is completely
    invisible from a training curve — which is why it is checked against a known scene rather than
    inferred from convergence."""
    r = _fit(500, bounded=True)
    assert r["scaled_err"] < r["start"] * 0.7, r
    assert r["max"] <= D_MAX * 1.01, r


def test_without_the_bound_the_loss_improves_while_the_answer_gets_worse():
    """The counterfactual for `bounded_log_depth`, measured on the same scene rather than asserted.

    Far parallax is sub-pixel, so the far field is unconstrained by the data and escapes to infinity
    while the photometric loss keeps improving. Without this test, the bound would look like an
    arbitrary clamp someone added for tidiness."""
    r = _fit(500, bounded=False)
    assert r["max"] > 500, f"the runaway must actually run away: {r}"
    assert r["scaled_err"] > r["start"], f"unbounded should end up WORSE than the flat start: {r}"


def test_smoothness_alone_does_not_stop_the_runaway():
    """And neither does turning the usual regulariser up: it slows the escape and spoils the fit.
    Recorded because 'add smoothness' is the obvious thing to try instead of bounding the output."""
    r = _fit(500, bounded=False, smooth_w=5e-2)
    assert r["max"] > 300, f"smoothness at 50x the standard weight still did not hold it: {r}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
