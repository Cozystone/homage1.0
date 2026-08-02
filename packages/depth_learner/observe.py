# -*- coding: utf-8 -*-
"""Score depth where depth is actually OBSERVABLE, and check the instrument before trusting it.

Owner, 2026-07-29, on the brain's efficiency: 시야의 중심만 고해상도로 보고 주변부는 형태만; 예측과
어긋날 때만 에너지를 쓴다. The measurement this module replaces was the opposite of that — a dense
average of photometric error over every pixel of the frame — and it failed in exactly the way that
predicts. Whole-frame scoring could not separate the CARLA depth map from a RANDOM one:

    no warp 0.07190    constant 0.07101    random 0.07137    CARLA 0.07129

All four in the fourth decimal, with constant winning. Roughly seventy per cent of a city frame is
sky, road and flat facade, and those pixels say nothing about depth however hard they are computed.
Averaging over them does not merely waste the computation, it DILUTES the thirty per cent that had
something to say until the answer is unreadable.

WHAT MAKES A PIXEL INFORMATIVE, DERIVED RATHER THAN GUESSED. How much does the photometric error at
a pixel change if the depth there is wrong? Differentiate: a depth error dZ moves the sampled point
by f*t*dZ/Z^2, and moving the sample point changes the sampled value in proportion to the local
image gradient. So

    d(error)/dZ  ~  |grad I| * f*t / Z^2

Two factors, and both are needed. `|grad I|` is texture — the foveation half, and what "score where
there is texture" would give on its own. `1/Z^2` is parallax sensitivity, and dropping it loses the
other half: far pixels are unobservable no matter how sharply textured, which is the same fact that
made unbounded depth run away to infinity. One expression covers both, and neither was chosen.

A SECOND INSTRUMENT, AND IT IS THE BETTER ONE. Photometric reconstruction reads depth through a warp
and a bilinear resample, and on smooth imagery a resample is nearly lossless wherever you sample it
— which is precisely why every depth map scored the same. But depth predicts something more direct
than an image: it predicts FLOW. Under translation a point at distance Z moves f*t/Z pixels, so
predicted flow is proportional to predicted DISPARITY, and flow can be measured on its own with
sparse tracking. Correlating measured flow against predicted disparity skips the reconstruction
entirely, is scale-free by construction (which suits a monocular depth that cannot know metres), and
is computed at a few hundred tracked corners instead of 76,800 pixels — cheaper AND sharper, which is
the shape of the owner's argument rather than a coincidence.

THE INSTRUMENT IS VALIDATED BEFORE IT IS BELIEVED. Both scores are run on CARLA, where ground truth
exists, against the true depth, a random one and a constant one. A measurement that cannot tell
truth from noise where the answer is known cannot be trusted where it is not, and reporting a verdict
from an unvalidated instrument is how the previous round produced a confident nothing.
"""
from __future__ import annotations

from typing import Any

import numpy as np


def observability(rgb: np.ndarray, depth: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Per-pixel weight: how much this pixel's appearance depends on getting its depth right.

    |grad I| / Z^2, normalised to sum to 1 so it is a distribution over the frame rather than a
    quantity with units. Returned as a weight rather than a hard mask because informativeness is a
    matter of degree, and a threshold would be another number to justify."""
    g = rgb.mean(axis=2) if rgb.ndim == 3 else rgb
    gy, gx = np.gradient(g.astype(np.float32))
    tex = np.sqrt(gx ** 2 + gy ** 2)
    w = tex / (depth.astype(np.float32) ** 2 + eps)
    s = w.sum()
    return w / s if s > eps else np.full_like(w, 1.0 / w.size)


def foveal_error(err: np.ndarray, weight: np.ndarray) -> float:
    """Photometric error, averaged where depth is observable instead of everywhere."""
    return float((err * weight).sum() / max(weight.sum(), 1e-9))


def concentration(weight: np.ndarray, frac: float = 0.9) -> float:
    """What fraction of the pixels carry `frac` of the total observability.

    The efficiency number: if 90% of the information about depth sits in 8% of the frame, then 92%
    of a dense computation is spent on pixels that cannot answer the question being asked."""
    v = np.sort(weight.ravel())[::-1]
    c = np.cumsum(v) / max(v.sum(), 1e-12)
    return float((np.searchsorted(c, frac) + 1) / v.size)


# --- the flow instrument ---------------------------------------------------------------------------

def track(a_rgb: np.ndarray, b_rgb: np.ndarray, max_points: int = 600) -> dict[str, np.ndarray]:
    """Measure where a few hundred trackable corners went. Foveation, literally: the tracker picks
    the points worth looking at and the rest of the frame is never touched."""
    import cv2
    a = cv2.cvtColor(a_rgb, cv2.COLOR_RGB2GRAY) if a_rgb.ndim == 3 else a_rgb
    b = cv2.cvtColor(b_rgb, cv2.COLOR_RGB2GRAY) if b_rgb.ndim == 3 else b_rgb
    p0 = cv2.goodFeaturesToTrack(a, maxCorners=max_points, qualityLevel=0.01, minDistance=6)
    if p0 is None or len(p0) < 12:
        return {"xy": np.zeros((0, 2), np.float32), "flow": np.zeros((0,), np.float32)}
    p1, st, _ = cv2.calcOpticalFlowPyrLK(a, b, p0, None,
                                         winSize=(21, 21), maxLevel=3,
                                         criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
    ok = (st.ravel() == 1)
    p0, p1 = p0[ok].reshape(-1, 2), p1[ok].reshape(-1, 2)
    d = p1 - p0
    return {"xy": p0, "flow": np.sqrt((d ** 2).sum(1)), "dxy": d}


def _derotate(xy: np.ndarray, dxy: np.ndarray) -> np.ndarray:
    """Remove the part of the flow that does not depend on depth, and keep the part that does.

    A rotating camera moves every pixel the same way whatever its distance, so rotation contributes
    flow that carries NO depth information while adding freely to the magnitude being correlated. For
    small rotations that contribution is affine in the image coordinates. A translating camera's flow
    is (f*t - x*t_z)/Z, which is affine only if Z is constant — so subtracting the best-fit affine
    field removes the rotation and leaves precisely the depth-dependent variation.

    This is a subtraction, not a filter: it cannot invent agreement where there is none, because a
    random depth map is uncorrelated with the residual for the same reason it was uncorrelated with
    the raw flow. The CARLA validation is what checks that, and it is why both numbers are reported
    rather than only the flattering one."""
    A = np.column_stack([xy[:, 0], xy[:, 1], np.ones(len(xy))])
    resid = np.empty_like(dxy)
    for c in (0, 1):
        coef, *_ = np.linalg.lstsq(A, dxy[:, c], rcond=None)
        resid[:, c] = dxy[:, c] - A @ coef
    return np.sqrt((resid ** 2).sum(1))


def flow_agreement(a_rgb: np.ndarray, b_rgb: np.ndarray, depth: np.ndarray,
                   min_points: int = 30, derotate: bool = False) -> dict[str, Any]:
    """Does the predicted depth explain the flow that was actually measured?

    Under translation, flow ~ f*t/Z, so flow should rank the same way DISPARITY does. Spearman
    rather than Pearson, because the constant f*t is unknown and monocular depth has no scale — the
    ORDERING is the whole of what can be checked, and it is also the whole of what is claimed.

    Rotation is the honest caveat: it adds a nearly constant flow independent of depth, which drags
    the correlation toward zero whatever the depth map is. So a low score means "this pair could not
    discriminate" as much as it means "this depth is wrong", and the CARLA validation exists to say
    which regime a number is in."""
    t = track(a_rgb, b_rgb)
    if len(t["flow"]) < min_points:
        return {"rho": float("nan"), "n": int(len(t["flow"])), "reason": "too few tracked points"}
    xy = np.round(t["xy"]).astype(np.int32)
    h, w = depth.shape[:2]
    xs = np.clip(xy[:, 0], 0, w - 1)
    ys = np.clip(xy[:, 1], 0, h - 1)
    disp = 1.0 / np.clip(depth[ys, xs].astype(np.float64), 1e-3, None)
    f = (_derotate(t["xy"], t["dxy"]) if derotate else t["flow"]).astype(np.float64)
    if np.std(disp) < 1e-9 or np.std(f) < 1e-9:
        return {"rho": 0.0, "n": int(len(f)), "reason": "no variation to correlate"}
    rank = lambda v: np.argsort(np.argsort(v)).astype(np.float64)
    rd, rf = rank(disp), rank(f)
    rho = float(np.corrcoef(rd, rf)[0, 1])
    return {"rho": rho, "n": int(len(f)),
            "flow_px": {"median": round(float(np.median(f)), 2),
                        "p90": round(float(np.percentile(f, 90)), 2)}}
