# -*- coding: utf-8 -*-
"""A small monocular depth net, and the loss that makes single-image depth learnable at all.

DELIBERATELY SMALL. The owner's constraint is that perception ships in the AlphaFramer plugin and
must not demand a top-tier machine — this box is the test rig, not the target. So this is a plain
encoder-decoder, **3.35M parameters at width=32** (measured, not estimated — an earlier draft of
this docstring said "a few hundred thousand", which was wrong by an order of magnitude), against the
100M+ of a pretrained depth backbone. It trains in minutes on this GPU, and the question it answers
— does CARLA depth supervision survive a change of world — does not need a bigger model to be
answered honestly. If the answer is yes, scaling up is a separate and much easier decision.

WHY SCALE-INVARIANT LOG LOSS. Depth from ONE image is ambiguous by construction: a photograph of a
real city and a photograph of a scale model of that city are the same pixels. No amount of data
removes that — it is geometry, not a data shortage. Plain L2 on metres therefore asks the network
for something the input does not determine, and it responds by predicting the dataset's mean depth
everywhere, which scores tolerably and sees nothing.

Eigen's scale-invariant term is the standard answer and it is what this uses: penalise the VARIANCE
of the log error while letting its mean go free, so the network is graded on relative structure —
this is nearer than that — and not on a global multiplier it cannot know.

PARTIALLY scale-invariant, and the word matters. Full invariance is LAMBDA=1.0, where a global
multiplier costs exactly nothing. At LAMBDA=0.85 a x0.5 error still moves the loss — measured, 0.199
to 0.334 — because CARLA supplies real metres and there is no reason to throw that away. An earlier
draft of this docstring called it "scale-invariant" flatly; `test_silog_is_scale_invariant` failed on
that claim, which is what the test was for. For reference, under the same x0.5 shift a plain
log-space L2 goes 0.199 to 0.735, so the term is doing most of what it exists to do.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

LAMBDA = 0.85          # 1.0 = fully scale-invariant; <1 keeps some absolute-scale pressure
MIN_M, MAX_M = 0.5, 200.0


def _block(cin: int, cout: int, stride: int = 1) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, stride, 1, bias=False),
        nn.BatchNorm2d(cout),
        nn.ReLU(inplace=True),
        nn.Conv2d(cout, cout, 3, 1, 1, bias=False),
        nn.BatchNorm2d(cout),
        nn.ReLU(inplace=True),
    )


class DepthNet(nn.Module):
    """U-net shaped encoder-decoder. Skip connections matter here more than depth of the stack:
    depth boundaries sit exactly on image boundaries, and without skips the decoder has to
    hallucinate them back from a coarse feature map."""

    def __init__(self, width: int = 32) -> None:
        super().__init__()
        w = width
        self.e1 = _block(3, w)                 # 1/1
        self.e2 = _block(w, w * 2, stride=2)   # 1/2
        self.e3 = _block(w * 2, w * 4, stride=2)   # 1/4
        self.e4 = _block(w * 4, w * 8, stride=2)   # 1/8
        self.bott = _block(w * 8, w * 8, stride=2)  # 1/16

        self.d4 = _block(w * 8 + w * 8, w * 4)
        self.d3 = _block(w * 4 + w * 4, w * 2)
        self.d2 = _block(w * 2 + w * 2, w)
        self.d1 = _block(w + w, w)
        self.out = nn.Conv2d(w, 1, 1)

    @staticmethod
    def _up(x: torch.Tensor, like: torch.Tensor) -> torch.Tensor:
        return F.interpolate(x, size=like.shape[-2:], mode="bilinear", align_corners=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        e1 = self.e1(x)
        e2 = self.e2(e1)
        e3 = self.e3(e2)
        e4 = self.e4(e3)
        b = self.bott(e4)
        d4 = self.d4(torch.cat([self._up(b, e4), e4], 1))
        d3 = self.d3(torch.cat([self._up(d4, e3), e3], 1))
        d2 = self.d2(torch.cat([self._up(d3, e2), e2], 1))
        d1 = self.d1(torch.cat([self._up(d2, e1), e1], 1))
        # The head predicts LOG depth. Predicting metres directly forces the last layer to span
        # 0.5..200 linearly, so near-field precision -- where most of the useful signal is -- gets
        # the same resolution as the far field, which needs almost none.
        return self.out(d1).squeeze(1)


def silog_loss(pred_log: torch.Tensor, target_m: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
    """Scale-invariant log loss (Eigen et al.), computed only where the ground truth is a surface."""
    t = torch.log(target_m.clamp(MIN_M, MAX_M))
    d = (pred_log - t)[valid]
    if d.numel() == 0:
        return pred_log.sum() * 0.0
    return torch.sqrt((d ** 2).mean() - LAMBDA * d.mean() ** 2 + 1e-8)


@torch.no_grad()
def metrics(pred_log: torch.Tensor, target_m: torch.Tensor, valid: torch.Tensor) -> dict[str, float]:
    """The standard monocular-depth set, plus the median-scaled variant.

    `absrel_scaled` applies the single best global multiplier before scoring -- the conventional way
    to report a scale-invariant model, since the raw number otherwise punishes it for the one thing
    the loss deliberately did not ask it to learn. BOTH are reported: the raw number is what a user
    would get with no calibration, the scaled one is what the geometry actually recovered."""
    p = torch.exp(pred_log).clamp(MIN_M, MAX_M)
    g = target_m.clamp(MIN_M, MAX_M)
    p, g = p[valid], g[valid]
    if p.numel() == 0:
        return {}
    ratio = torch.median(g) / torch.median(p)
    ps = (p * ratio).clamp(MIN_M, MAX_M)
    thr = torch.maximum(g / ps, ps / g)
    return {
        "absrel": float(((p - g).abs() / g).mean()),
        "absrel_scaled": float(((ps - g).abs() / g).mean()),
        "rmse": float(torch.sqrt(((ps - g) ** 2).mean())),
        "rmse_log": float(torch.sqrt(((torch.log(ps) - torch.log(g)) ** 2).mean())),
        "delta1": float((thr < 1.25).float().mean()),
        "delta2": float((thr < 1.25 ** 2).float().mean()),
        "median_scale": float(ratio),
        "n_px": int(p.numel()),
    }
