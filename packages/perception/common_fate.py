# -*- coding: utf-8 -*-
"""Cut the world into THINGS, before anything is called anything.

Owner, 2026-07-29: "저게 어디에 있는 어떤 입체 덩어리인가"는 완벽하게 알아채고 있으니, 거기에
"사람", "자동차" 같은 언어적 이름표를 매칭하는 단계로.

The second half is the right next step and the first half is not yet true, which is why this file
exists. What the depth work produced is a per-pixel ORDERING — for any two points it can say which
is nearer, at about 0.81 on unseen towns. That is a field, not a set of objects. Nothing in it groups
pixels into a lump, so there is no lump to hang a word on. A label needs a referent, and the referent
has to be found first.

HOW A THING IS FOUND WITHOUT BEING TOLD WHAT THINGS THERE ARE. Two surfaces belong to one object when
they move together and lie at the same distance. That is common fate plus depth coherence, it is the
principle infants segment objects by before they have a single word, and it needs no vocabulary,
no class list and no annotation — which is the whole reason to use it here rather than run a detector
and call its boxes objects. A detector's boxes are only ever the things somebody listed.

WHAT THIS CANNOT DO, said plainly because the failures are structural rather than tuning:

  A STATIONARY OBJECT AGAINST A STATIONARY BACKGROUND AT THE SAME DEPTH IS INVISIBLE TO IT. Common
  fate requires fate. A parked car flush against a wall is one region here, and correctly so — from
  motion alone there is no evidence it is two things.

  IT UNDER-SEGMENTS THINGS THAT MOVE TOGETHER. A person walking beside a bicycle they are pushing is
  one region. That is not an error to be tuned away; it is what the evidence supports, and splitting
  them would need a cue this does not have.

  IT OVER-SEGMENTS ARTICULATED THINGS. Arms and legs move differently from a torso, so a walking
  person can come apart. Whether that is wrong depends on what the parts are for.

So the output is REGIONS — candidate things, each with a boundary, a depth and a motion — and the
naming step must be able to say "I do not know" about any of them.

IT DOES NOT WORK ON DRIVING FOOTAGE, AND THAT IS MEASURED RATHER THAN SUSPECTED. Scored against
CARLA's semantic ground truth, the regions this produces are no purer than blobs of the same size
and shape dropped at random in the same image: 0.782 against a shuffled control of 0.802, beating
the control on 42% of regions. It is slicing the picture, not finding things.

The cue distributions say why, and they are worth writing down because they rule out tuning:

    adjacent cells, SAME object        flow diff median 0.19   depth ratio 0.023
    adjacent cells, DIFFERENT object   flow diff median 0.29   depth ratio 0.034

    flow tol 0.9    keeps 77% of same-object joins and 78% of cross-object joins
    flow tol 3.0    keeps 94%                    and 96%
    depth tol 0.05  keeps 78%                    and 67%

Every flow threshold admits cross-object joins at the same rate as same-object ones — the
distributions are on top of each other. That is not a badly chosen tolerance, it is the absence of a
signal, and the reason is the caveat above being much larger than it looked: common fate separates
things that move INDEPENDENTLY, and in a street seen from a moving car almost nothing does. Parked
cars, poles, facades and road all have the flow their depth and image position dictate, so two cells
either side of a real boundary at similar distance move nearly identically.

Depth is the cue that carries something (78% against 67%) and it is thin, because a ranking loss
fitted at sparse tracked corners produces a smooth field with no sharp edges — exactly what a
boundary detector needs and the least of what that training produces.

WHAT THIS MEANS FOR NAMING. Words need referents and this does not supply them, so a naming step
built on top of these regions would be attaching labels to slices of picture. The honest route is
the other way round: let a detector LOCALISE a candidate word, and keep for ATANOR the part a
detector cannot do — noticing that it does not know, and going to find out. The detector is then a
tool for testing a word against an image, never a source of the words, which is the line that
matters.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class Region:
    """A candidate thing: some pixels that moved together at a common distance."""

    mask: np.ndarray                 # bool, full frame
    box: tuple[int, int, int, int]   # x0, y0, x1, y1
    flow: tuple[float, float]        # median (dx, dy) of its cells
    depth_rank: float                # median predicted depth, in whatever units the net used
    cells: int
    area_frac: float

    def as_dict(self) -> dict[str, Any]:
        return {"box": self.box, "flow": [round(v, 2) for v in self.flow],
                "depth_rank": round(self.depth_rank, 3), "cells": self.cells,
                "area_frac": round(self.area_frac, 4)}


def dense_flow(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per-pixel (dx, dy). Farneback — dense is needed here because a boundary is a place where flow
    CHANGES, and sparse corners do not say where between two corners the change happened."""
    import cv2
    ga = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY) if a.ndim == 3 else a
    gb = cv2.cvtColor(b, cv2.COLOR_RGB2GRAY) if b.ndim == 3 else b
    return cv2.calcOpticalFlowFarneback(ga, gb, None, 0.5, 3, 21, 3, 5, 1.2, 0)


def _cell_stats(flow: np.ndarray, depth: np.ndarray | None, cell: int) -> dict[str, np.ndarray]:
    H, W = flow.shape[:2]
    gh, gw = H // cell, W // cell
    f = flow[:gh * cell, :gw * cell].reshape(gh, cell, gw, cell, 2)
    fx = np.median(f[..., 0], axis=(1, 3))
    fy = np.median(f[..., 1], axis=(1, 3))
    out = {"fx": fx, "fy": fy}
    if depth is not None:
        d = depth[:gh * cell, :gw * cell].reshape(gh, cell, gw, cell)
        out["z"] = np.median(d, axis=(1, 3))
    return out


def segment(a: np.ndarray, b: np.ndarray, depth: np.ndarray | None = None, *,
            cell: int = 8, flow_tol: float = 0.9, depth_tol: float = 0.28,
            min_cells: int = 6, max_regions: int = 24) -> list[Region]:
    """Group cells that agree about where they are going and how far away they are.

    `flow_tol` is in pixels and `depth_tol` is a RATIO, because depth agreement should mean the same
    at 5m as at 50m — an absolute metre tolerance would fuse the whole far field into one region and
    shatter the near one."""
    H, W = a.shape[:2]
    st = _cell_stats(dense_flow(a, b), depth, cell)
    fx, fy = st["fx"], st["fy"]
    z = st.get("z")
    gh, gw = fx.shape

    label = -np.ones((gh, gw), np.int32)
    regions: list[Region] = []
    order = np.argsort(-(fx ** 2 + fy ** 2).ravel())        # start from what moves most

    for seed in order:
        sy, sx = divmod(int(seed), gw)
        if label[sy, sx] >= 0:
            continue
        rid = len(regions)
        stack = [(sy, sx)]
        label[sy, sx] = rid
        members = [(sy, sx)]
        while stack:
            cy, cx = stack.pop()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if not (0 <= ny < gh and 0 <= nx < gw) or label[ny, nx] >= 0:
                    continue
                if abs(fx[ny, nx] - fx[cy, cx]) > flow_tol or abs(fy[ny, nx] - fy[cy, cx]) > flow_tol:
                    continue
                if z is not None:
                    hi = max(z[ny, nx], z[cy, cx])
                    lo = max(min(z[ny, nx], z[cy, cx]), 1e-6)
                    if (hi - lo) / lo > depth_tol:
                        continue
                label[ny, nx] = rid
                members.append((ny, nx))
                stack.append((ny, nx))

        if len(members) < min_cells:
            for my, mx in members:
                label[my, mx] = -2                          # too small to be a thing; not reused
            continue

        ys = np.array([m[0] for m in members])
        xs = np.array([m[1] for m in members])
        mask = np.zeros((H, W), bool)
        for my, mx in members:
            mask[my * cell:(my + 1) * cell, mx * cell:(mx + 1) * cell] = True
        regions.append(Region(
            mask=mask,
            box=(int(xs.min() * cell), int(ys.min() * cell),
                 int((xs.max() + 1) * cell), int((ys.max() + 1) * cell)),
            flow=(float(np.median(fx[ys, xs])), float(np.median(fy[ys, xs]))),
            depth_rank=float(np.median(z[ys, xs])) if z is not None else float("nan"),
            cells=len(members),
            area_frac=float(mask.mean())))
        if len(regions) >= max_regions:
            break

    regions.sort(key=lambda r: -r.cells)
    return regions


def purity(region: Region, semantic: np.ndarray) -> tuple[float, int]:
    """What fraction of a region is one semantic class, and which. For CHECKING only.

    A region that is 95% 'car' found a car without being told cars exist. A region that is 40% of
    five classes found a patch of image. This is the difference between segmentation and slicing,
    and it is not visible from looking at the boxes."""
    v = semantic[region.mask]
    if v.size == 0:
        return 0.0, -1
    ids, counts = np.unique(v, return_counts=True)
    k = int(np.argmax(counts))
    return float(counts[k] / v.size), int(ids[k])


#: A region smaller than this share of the frame is a fragment, not a thing. MEASURED, not chosen --
#: and the measurement is the whole story of this file.
#:
#: `segment` returns everything it finds, and over 184 regions the mean purity was 0.783 against a
#: shape-matched shuffled control of 0.814: WORSE THAN DROPPING THE SAME BLOB AT RANDOM. Split by size,
#: that aggregate inverts -- regions under ~2000 px lose badly and carry the count, while large ones
#: win, and at 30000+ px purity was 0.648 against a control of 0.329. The average was small fragments
#: outvoting real objects.
#:
#: The crossover was fitted on ep000-005 and CHECKED on ep056-065, which the fit never saw:
#:
#:      no floor     purity 0.808   shuffled 0.842   lift -0.034   52% win
#:      this floor   purity 0.884   shuffled 0.599   lift +0.285   89% win
#:
#: It got STRONGER held out, which is what says it is a property of the world (coherent motion at one
#: depth over a large area is an object) rather than a number fitted to one set of frames.
#:
#: Stored as a FRACTION OF FRAME AREA, because 11968 px is only meaningful at the 800x600 the episodes
#: were rendered at, and this has to survive a 640x480 webcam and a 2560x1440 screen.
THING_FLOOR = 11968 / (800 * 600)


def things(a: np.ndarray, b: np.ndarray, depth: np.ndarray | None = None, **kw) -> list:
    """The regions that are OBJECTS — segment, then drop the fragments.

    This is what everything downstream should call. Identity, permanence and naming all need a
    referent to attach to, and attaching them to a fragment is worse than attaching them to nothing:
    a fragment gets a name and a history and looks exactly like knowledge."""
    regions = segment(a, b, depth, **kw)
    area = float(a.shape[0] * a.shape[1]) or 1.0
    return [r for r in regions if float(r.mask.sum()) / area >= THING_FLOOR]


def frame_baseline(semantic: np.ndarray) -> float:
    """The share of this frame held by its single commonest class — the floor any purity must clear.

    WHY THIS EXISTS AND `shuffled_control` WAS NOT ENOUGH. The shuffled control is the right idea and
    it returns NaN for any region as large as the image, because there is nowhere else to put it. One
    such region poisons the mean, and the module's own check reported `nan` -- so the oracle this file
    was built with could not tell anyone whether it worked, and nobody read it. Measured just now:
    10 regions, purity 0.715, control nan.

    This baseline is ALWAYS defined and it is the honest one to beat: if a frame is 70% road, a region
    scoring 0.715 has found nothing at all. Cheap, and it needs no random placement."""
    v = semantic.reshape(-1)
    if v.size == 0:
        return 0.0
    _ids, counts = np.unique(v, return_counts=True)
    return float(counts.max() / v.size)


def shuffled_control(region: Region, semantic: np.ndarray, rng) -> float:
    """The same region, moved somewhere else at random. Its purity is what a region of this size and
    shape scores by accident in this image — the number the real purity has to beat.

    Without this a purity of 0.7 means nothing: a frame that is mostly road gives 0.7 to any blob
    dropped anywhere on it."""
    H, W = semantic.shape
    x0, y0, x1, y1 = region.box
    h, w = y1 - y0, x1 - x0
    if h >= H or w >= W:
        return float("nan")
    ny = int(rng.integers(0, H - h))
    nx = int(rng.integers(0, W - w))
    sub = region.mask[y0:y1, x0:x1]
    v = semantic[ny:ny + h, nx:nx + w][sub]
    if v.size == 0:
        return float("nan")
    _, counts = np.unique(v, return_counts=True)
    return float(counts.max() / v.size)
