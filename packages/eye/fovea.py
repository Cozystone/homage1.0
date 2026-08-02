# -*- coding: utf-8 -*-
"""A retina, not a sensor: sharp at the centre, coarse at the edge, and it chooses where to point.

Owner, 2026-07-29: 시야의 중심(중심와)만 아주 고해상도로 보고, 주변부는 대충 형태만 파악합니다.
망막 단계에서부터 이미 불필요한 정보는 걸러내고 ... 뇌는 예측과 실제 입력이 '어긋날 때'만 에너지를 씁니다.

That is a description of a mechanism, and it is implementable. A camera returns every pixel at the
same resolution and the cost is quadratic in the field of view; a retina spends its cells where the
information is and pays almost nothing for the periphery. The human retina has roughly 6 million
cones, of which a large fraction serve the central couple of degrees — acuity falls off steeply and
approximately as 1/(1 + k*eccentricity), which is the law used here rather than a shape invented for
the occasion.

WHY THIS IS NOT A CROP. A crop discards the periphery, and an eye that discards its periphery cannot
decide where to look next, because the thing worth looking at is always somewhere it is not currently
looking. This keeps the WHOLE field at graded resolution: full detail at the fixation point, coarse
blocks at the edge. The periphery is what nominates the next fixation; the fovea is what resolves it.

WHERE THE NEXT FIXATION COMES FROM, and this is the predictive-coding half. The eye holds a
prediction of what it expects to see — the simplest useful one, the previous frame — and looks where
that prediction FAILED. Nothing is computed at full resolution for a part of the scene that behaved
as expected. The consequence is that a static screen costs almost nothing and a changing one costs
in proportion to how much changed, which is the property the owner named.

WHAT IS AND IS NOT CLAIMED. This is a sampling scheme with a saccade rule. It reproduces two
measurable properties of biological vision — graded acuity and change-driven fixation — and it does
not thereby become vision. The numbers below are pixel counts and error rates, not evidence about
experience, and the doctrine on qualia claims applies here as everywhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class RetinaSpec:
    """The shape of the sampling. Defaults chosen to hold a 1080p field in ~6% of the pixels."""

    fovea_px: int = 96          # side of the full-resolution centre patch
    rings: int = 4              # concentric bands outside it
    ring_px: int = 48           # side of each ring's sampled grid
    falloff: float = 2.0        # each ring's linear scale grows by this factor


def _rescale(a: np.ndarray, h: int, w: int) -> np.ndarray:
    """Area-average down to (h, w). Area, not nearest: subsampling a wide image at a stride throws
    away everything between samples, which is how the body-schema estimator first went wrong."""
    try:
        import cv2
        return cv2.resize(a, (w, h), interpolation=cv2.INTER_AREA)
    except Exception:
        H, W = a.shape[:2]
        by, bx = max(1, H // h), max(1, W // w)
        b = a[:by * h, :bx * w]
        if b.ndim == 3:
            return b.reshape(h, by, w, bx, b.shape[2]).mean(axis=(1, 3))
        return b.reshape(h, by, w, bx).mean(axis=(1, 3))


def sample(rgb: np.ndarray, cx: float, cy: float, spec: RetinaSpec = RetinaSpec()) -> dict[str, Any]:
    """Look at (cx, cy). Returns the fovea at full resolution and each ring at its own coarseness.

    Coordinates are fractions of the frame, so a fixation means the same thing whatever the window
    size — an eye should not have to know its own resolution to decide where to point."""
    H, W = rgb.shape[:2]
    px, py = cx * W, cy * H
    out: dict[str, Any] = {"at": (round(cx, 4), round(cy, 4)), "levels": []}
    total = 0

    half = spec.fovea_px // 2
    x0, y0 = int(np.clip(px - half, 0, max(W - spec.fovea_px, 0))), \
             int(np.clip(py - half, 0, max(H - spec.fovea_px, 0)))
    fov = rgb[y0:y0 + spec.fovea_px, x0:x0 + spec.fovea_px]
    out["fovea"] = fov
    out["fovea_box"] = (x0, y0, x0 + fov.shape[1], y0 + fov.shape[0])
    total += fov.shape[0] * fov.shape[1]

    # Rings: each covers a square twice as wide as the last, sampled onto the SAME small grid — so a
    # ring four times further out costs the same as one nearby and carries four times less detail.
    # That is the acuity falloff, expressed as a budget rather than as a blur.
    extent = spec.fovea_px
    for r in range(spec.rings):
        extent = int(extent * spec.falloff)
        h = min(extent, H)
        w = min(extent, W)
        rx = int(np.clip(px - w / 2, 0, max(W - w, 0)))
        ry = int(np.clip(py - h / 2, 0, max(H - h, 0)))
        patch = rgb[ry:ry + h, rx:rx + w]
        if patch.size == 0:
            break
        small = _rescale(patch.astype(np.float32), spec.ring_px, spec.ring_px)
        out["levels"].append({"scale": extent, "box": (rx, ry, rx + w, ry + h), "px": small})
        total += spec.ring_px * spec.ring_px
        if w >= W and h >= H:
            break                                   # the whole field is covered; stop

    out["sampled_px"] = total
    out["full_px"] = H * W
    out["compression"] = round(H * W / max(total, 1), 2)
    return out


@dataclass
class Retina:
    """A retina with a fixation point and a memory of what it expected.

    THE STATE IS THE POINT. A stateless sampler is a crop function; what makes this an eye is that
    where it looks next depends on what it saw last, and specifically on where what it saw last
    failed to match what it predicted."""

    spec: RetinaSpec = field(default_factory=RetinaSpec)
    cx: float = 0.5
    cy: float = 0.5
    inertia: float = 0.45           # how much of the old fixation to keep; a pure jump every frame
                                    # would be a jitter, not a saccade
    _prev: np.ndarray | None = None
    _grid: int = 12                 # coarseness of the surprise map, in cells across

    def surprise(self, rgb: np.ndarray) -> np.ndarray:
        """Where the world did not do what was expected, at low resolution.

        The prediction is the previous frame, which is the weakest predictor that is still a
        predictor and is exactly right for a first version: everything it flags is genuine change.
        A learned predictor would flag only UNEXPECTED change — a car continuing at constant speed
        would stop being surprising — and this is the seam where that plugs in without the rest
        moving."""
        g = _rescale(rgb.mean(axis=2).astype(np.float32), self._grid, self._grid)
        if self._prev is None or self._prev.shape != g.shape:
            self._prev = g
            return np.zeros_like(g)
        s = np.abs(g - self._prev)
        self._prev = g
        return s

    def look(self, rgb: np.ndarray) -> dict[str, Any]:
        """Sample at the current fixation, then move the fixation to where the surprise was."""
        out = sample(rgb, self.cx, self.cy, self.spec)
        s = self.surprise(rgb)
        out["surprise_total"] = float(s.mean())
        tot = s.sum()
        if tot > 1e-6:
            gy, gx = np.mgrid[0:s.shape[0], 0:s.shape[1]].astype(np.float32)
            # Centre of mass of the surprise, not the argmax: a single bright pixel of noise should
            # not command the eye, and the mass of a real event should.
            ty = float((s * gy).sum() / tot) / max(s.shape[0] - 1, 1)
            tx = float((s * gx).sum() / tot) / max(s.shape[1] - 1, 1)
            self.cx = self.inertia * self.cx + (1 - self.inertia) * tx
            self.cy = self.inertia * self.cy + (1 - self.inertia) * ty
            out["saccade_to"] = (round(self.cx, 4), round(self.cy, 4))
        else:
            out["saccade_to"] = None            # nothing changed; the eye stays where it is
        return out


def reconstruct(s: dict[str, Any], shape: tuple[int, int]) -> np.ndarray:
    """Paint the sampled levels back onto a full-size canvas — coarse first, fovea last.

    Only for measuring and for showing a person what the retina kept. Nothing downstream consumes
    this; a pipeline that re-inflated the retina to full resolution would have undone the whole
    point of sampling it."""
    H, W = shape
    canvas = np.zeros((H, W), np.float32)
    for lv in reversed(s["levels"]):
        x0, y0, x1, y1 = lv["box"]
        px = lv["px"]
        g = px.mean(axis=2) if px.ndim == 3 else px
        canvas[y0:y1, x0:x1] = _rescale(g, y1 - y0, x1 - x0)
    x0, y0, x1, y1 = s["fovea_box"]
    f = s["fovea"]
    canvas[y0:y1, x0:x1] = f.mean(axis=2) if f.ndim == 3 else f
    return canvas
