# -*- coding: utf-8 -*-
"""A thing is the smallest piece of the world whose future its own past accounts for.

Owner, 2026-07-29: 물체 정의 그걸로 가서 뚫어봐.

WHY THE PREVIOUS ATTEMPT FAILED, because the fix follows from it. `common_fate.py` grouped cells that
were MOVING ALIKE, and measured against CARLA's semantic truth it was no better than dropping blobs
at random (purity 0.782 against a shuffled control of 0.802). The cue distributions said why: at every
threshold, flow admitted cross-object joins at the same rate as same-object ones. Two cells either
side of a real boundary, at similar distance, seen from a moving car, move nearly identically.

Similarity was the wrong relation. It is instantaneous and symmetric, and objecthood is neither.

THE RELATION THAT IS RIGHT IS PREDICTION. Predict every cell from ITS OWN past — nothing else — and
keep what is left over. A smoothly drifting background is predictable from its own past, so its
residual is near zero and it couples with nothing. When something happens that a cell's own history
did not contain, the residual jumps; and the parts of ONE object jump TOGETHER, because their shared
cause is the same object doing something. Parts of different objects do not.

    common fate      do these move alike RIGHT NOW?          fails: everything moves alike
    coherence        does what surprised this one surprise    the shared cause is the object
                     that one, at the same moment?

That is the definition made computable: an object is a set of cells whose UNPREDICTED components move
together, which is exactly "a unit whose future its own past accounts for" read the other way round —
the cells that must be modelled jointly, because modelling them apart leaves correlated error.

WHY THIS IS THE SAME THING AS BEING SIMULATABLE, which is the reason to prefer this definition over a
cue that merely worked. A set of cells whose residuals are correlated is a set that has to be rolled
forward together, and a set that has to be rolled forward together IS what a mental simulation runs.
So the criterion for "this is one thing" and the criterion for "this can be imagined moving" are one
criterion, and objects found this way are, by construction, the things a 4D world model can carry.

WHAT WOULD FALSIFY IT. If the regions this produces are no purer than the shuffled control — the same
region shape dropped elsewhere in the same frame — then correlated residuals are not finding objects
either, and the honest reading is that neither cue works at this quality. The comparison, on the same CARLA frames, against the same shuffled control:

    common fate   purity 0.796   control 0.799   lift -0.003   beat 44%   <- no better than random
    coherence     purity 0.758   control 0.680   lift +0.078   beat 61%

So the definition produces a measurable signal where the previous cue produced none. It is NOT good
enough to name things from: 61% of regions beating a random placement of the same shape is a weak
segmenter, and the honest statement is that this is the first cue that works at all, not one that
works well.

MORE PAST HELPS UNTIL IT DOES NOT, and the turn is informative rather than a limit of tuning. On
40-frame episodes the trend looked monotone and I predicted it would continue:

    window 10   lift +0.044   beat 56%
    window 20   lift +0.073   beat 60%
    window 34   lift +0.078   beat 61%

400-frame episodes were recorded to test that, and it saturates and then reverses:

    window  34  lift +0.090   beat 64%
    window  80  lift +0.088   beat 67%
    window 160  lift +0.077   beat 65%
    window 300  lift -0.005   beat 60%   (n=10, thin)

The prediction was wrong, and the reason refines the definition rather than weakening it. Over three
hundred frames the car has driven somewhere else: a cell that held a vehicle now holds road, so
correlating its residual across the whole window correlates things that were never the same thing.

**A thing is predictable from its own past over a HORIZON**, and the horizon is set by how long it
stays in one part of the field — a physical quantity of the scene, not a parameter to choose. One to
four seconds here. A representation that tracked cells to objects rather than to image positions
would not have this ceiling, and that is what the next version needs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class Thing:
    """A candidate object: cells whose surprises coincide."""

    mask: np.ndarray
    box: tuple[int, int, int, int]
    cells: int
    area_frac: float
    coherence: float          # mean residual correlation inside the group
    residual: float           # how much it was surprised at all

    def as_dict(self) -> dict[str, Any]:
        return {"box": self.box, "cells": self.cells, "area_frac": round(self.area_frac, 4),
                "coherence": round(self.coherence, 3), "residual": round(self.residual, 4)}


def cell_series(frames: list[np.ndarray], cell: int = 16) -> np.ndarray:
    """(T, gh, gw, 3) — per cell, per frame: mean brightness and the flow it underwent.

    Appearance AND motion, because either alone misses a kind of event: a light turning on changes
    appearance without motion, a car passing changes motion without appearance."""
    import cv2
    T = len(frames)
    H, W = frames[0].shape[:2]
    gh, gw = H // cell, W // cell
    out = np.zeros((T, gh, gw, 3), np.float32)
    prev_g = None
    for t, f in enumerate(frames):
        g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32) if f.ndim == 3 else f.astype(np.float32)
        blocks = g[:gh * cell, :gw * cell].reshape(gh, cell, gw, cell)
        out[t, :, :, 0] = blocks.mean(axis=(1, 3))
        if prev_g is not None:
            fl = cv2.calcOpticalFlowFarneback(prev_g, g, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            fb = fl[:gh * cell, :gw * cell].reshape(gh, cell, gw, cell, 2)
            out[t, :, :, 1] = fb[..., 0].mean(axis=(1, 3))
            out[t, :, :, 2] = fb[..., 1].mean(axis=(1, 3))
        prev_g = g
    return out


def residuals(series: np.ndarray) -> np.ndarray:
    """What each cell's OWN past failed to account for. (T-2, gh, gw)

    Constant velocity per channel, which is the weakest predictor that is still a predictor. The
    point is not to predict well; it is that whatever this misses is, by construction, not explained
    by the cell alone — and that leftover is the only thing the grouping is allowed to use."""
    pred = series[1:-1] + (series[1:-1] - series[:-2])
    err = np.abs(series[2:] - pred)
    # channels are on different scales (brightness 0-255, flow in pixels); standardise each so one
    # does not silently dominate the correlation
    for c in range(err.shape[-1]):
        s = err[..., c].std()
        if s > 1e-9:
            err[..., c] /= s
    return err.mean(axis=-1)


def reject_common_mode(res: np.ndarray) -> np.ndarray:
    """Take out what surprised EVERYTHING at once, and keep what surprised only some of it.

    OFF BY DEFAULT, BECAUSE IT DOES NOT HELP — and the reasoning that predicted it would was good
    enough to be worth recording along with its failure. The argument was: when the body moves, the
    body is itself a shared cause, so every cell's own past fails together and residual correlation
    should find "everything my motion touched", which is the whole frame. Measured, it changes
    nothing:

        common mode kept      lift +0.078   beat 61%
        common mode removed   lift +0.069   beat 62%   (link 0.45)

    The likeliest reason is that there was little common mode left to take: a constant-velocity
    predictor already absorbs smooth ego-motion, because smooth ego-motion is locally constant
    velocity, so the step it was meant to undo had largely been undone one stage earlier. Kept as an
    option and as a record, not as a default, and not described as a fix.

    So the frame-wide common mode is regressed out of every cell, per timestep. It needs no pose, no
    command and no ground truth: whatever moved all of it together is, by definition, not what
    distinguishes one part of it from another. It is the same subtraction the efference copy makes
    from the outside, done from the inside, and centre-surround organisation in real retinas is the
    same operation for the same reason.

    What is left is what happened to SOME of the scene, which is where a thing can be."""
    T = res.shape[0]
    flat = res.reshape(T, -1)
    common = flat.mean(axis=1, keepdims=True)                # what happened to all of it
    var = float((common ** 2).sum())
    if var < 1e-12:
        return res
    # per cell, remove its best multiple of the common mode -- a projection, not a subtraction, so
    # cells that merely track the common mode more or less strongly are both fully cleaned
    beta = (flat * common).sum(axis=0, keepdims=True) / max(var, 1e-12)
    return (flat - beta * common).reshape(res.shape)


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 1e-12 else 0.0


def group(res: np.ndarray, *, link: float = 0.45, min_cells: int = 6,
          min_residual: float = 0.15, max_things: int = 24) -> list[tuple[list, float]]:
    """Join neighbouring cells whose residual series agree. Returns [(cells, coherence)].

    Only SPATIALLY ADJACENT cells are considered for joining. Two unrelated regions on opposite sides
    of the frame can have correlated residuals by coincidence — a global illumination change, a
    coincidence of timing — and objects are contiguous, so adjacency is a constraint the world
    supplies rather than one imposed for convenience.

    `min_residual` excludes cells that were never surprised. A cell that sat perfectly predictable
    the whole time has a residual of noise, its correlation with anything is meaningless, and letting
    such cells join would fill the frame with groups made of nothing happening."""
    T, gh, gw = res.shape
    flat = res.reshape(T, -1).T                     # (cells, T)
    energy = flat.std(axis=1)
    thr = np.percentile(energy, 100 * min_residual) if 0 < min_residual < 1 else min_residual
    alive = energy > max(thr, 1e-9)

    label = -np.ones(gh * gw, np.int32)
    out: list[tuple[list, float]] = []
    order = np.argsort(-energy)                     # start where the most went unexplained

    for seed in order:
        if not alive[seed] or label[seed] >= 0:
            continue
        rid = len(out)
        label[seed] = rid
        members, edges, stack = [int(seed)], [], [int(seed)]
        while stack:
            c = stack.pop()
            cy, cx = divmod(c, gw)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if not (0 <= ny < gh and 0 <= nx < gw):
                    continue
                n = ny * gw + nx
                if label[n] >= 0 or not alive[n]:
                    continue
                r = _corr(flat[c], flat[n])
                if r < link:
                    continue
                label[n] = rid
                members.append(n)
                edges.append(r)
                stack.append(n)
        if len(members) < min_cells:
            for mcell in members:
                label[mcell] = -2
            continue
        out.append((members, float(np.mean(edges)) if edges else 0.0))
        if len(out) >= max_things:
            break
    return out


def things(frames: list[np.ndarray], *, cell: int = 16, link: float = 0.45, common_mode: bool = False,
           min_cells: int = 6, max_things: int = 24) -> list[Thing]:
    """The whole procedure: watch a stretch, and say what moved as one."""
    if len(frames) < 5:
        return []
    series = cell_series(frames, cell)
    res = residuals(series)
    if common_mode:
        res = reject_common_mode(res)
    T, gh, gw = res.shape
    H, W = frames[0].shape[:2]
    flat = res.reshape(T, -1).T

    out: list[Thing] = []
    for members, coh in group(res, link=link, min_cells=min_cells, max_things=max_things):
        ys = np.array([m // gw for m in members])
        xs = np.array([m % gw for m in members])
        mask = np.zeros((H, W), bool)
        for m in members:
            my, mx = divmod(m, gw)
            mask[my * cell:(my + 1) * cell, mx * cell:(mx + 1) * cell] = True
        out.append(Thing(mask=mask,
                         box=(int(xs.min() * cell), int(ys.min() * cell),
                              int((xs.max() + 1) * cell), int((ys.max() + 1) * cell)),
                         cells=len(members), area_frac=float(mask.mean()),
                         coherence=coh,
                         residual=float(np.mean([flat[m].std() for m in members]))))
    out.sort(key=lambda t: -t.cells)
    return out


# --- the next version: units that follow the stuff, not the screen -------------------------------

def tracks(frames: list[np.ndarray], *, max_points: int = 400) -> dict[str, np.ndarray]:
    """Follow points as they move. Returns xy (T, N, 2) and alive (T, N).

    THE UNIT CHANGES, AND THAT IS THE WHOLE POINT. The grid version made a cell an image POSITION,
    so a cell that held a car for twenty frames held road for the next sixty, and its "own past" was
    the past of several different things stitched together. Measured, that put a ceiling on how much
    history could be used: lift rose to +0.090 at 34 frames, held to 80, and collapsed to -0.005 by
    300.

    A track follows one piece of the world, so its history is genuinely its own, and its LIFETIME is
    the horizon rather than a number chosen for it. A track dying is information too: things that
    vanish together tend to belong together."""
    import cv2
    T = len(frames)
    grey = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) if f.ndim == 3 else f for f in frames]
    p0 = cv2.goodFeaturesToTrack(grey[0], maxCorners=max_points, qualityLevel=0.01, minDistance=7)
    if p0 is None or len(p0) < 8:
        return {"xy": np.zeros((T, 0, 2), np.float32), "alive": np.zeros((T, 0), bool)}
    N = len(p0)
    xy = np.zeros((T, N, 2), np.float32)
    alive = np.zeros((T, N), bool)
    xy[0] = p0.reshape(-1, 2)
    alive[0] = True
    cur = p0.reshape(-1, 1, 2).astype(np.float32)
    living = np.ones(N, bool)
    for t in range(1, T):
        if not living.any():
            break
        nxt, st, _ = cv2.calcOpticalFlowPyrLK(
            grey[t - 1], grey[t], cur, None, winSize=(21, 21), maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
        # BACKWARD CHECK. A tracker asked to follow a point that has gone will happily return
        # somewhere, and a wrong track is worse than a dead one because it still looks like evidence.
        back, st2, _ = cv2.calcOpticalFlowPyrLK(
            grey[t], grey[t - 1], nxt, None, winSize=(21, 21), maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
        drift = np.linalg.norm(back.reshape(-1, 2) - cur.reshape(-1, 2), axis=1)
        ok = (st.ravel() == 1) & (st2.ravel() == 1) & (drift < 1.5) & living
        xy[t][ok] = nxt.reshape(-1, 2)[ok]
        alive[t] = ok
        living = ok
        cur = nxt.reshape(-1, 1, 2).astype(np.float32)
    return {"xy": xy, "alive": alive}


def rigidity(xy: np.ndarray, alive: np.ndarray, i: int, j: int, min_frames: int = 8) -> float:
    """How constant the separation between two tracked points stayed. 1 = rigidly attached.

    THE CUE A FIXED GRID CANNOT SEE. Two points on one rigid body keep their separation whatever the
    body does — exactly constant in 3D, nearly so in the image at similar depth. Two points on
    different bodies drift apart the moment those bodies do anything different.

    This is NOT common fate renamed. Common fate compares velocities AT AN INSTANT, and two points on
    a turning car have different velocities while remaining rigidly attached — which is precisely the
    case that made common fate score at chance. This compares the shape of the trajectory PAIR over
    its whole shared life, which is what rigid attachment actually means."""
    both = alive[:, i] & alive[:, j]
    if both.sum() < min_frames:
        return 0.0
    d = np.linalg.norm(xy[both, i] - xy[both, j], axis=1)
    m = float(d.mean())
    if m < 1e-6:
        return 0.0
    return float(max(0.0, 1.0 - (d.std() / m) * 3.0))       # 33% wobble scores zero


def track_residual(xy: np.ndarray, alive: np.ndarray, n: int) -> np.ndarray:
    """What a track's own past failed to predict, over its life. Constant velocity, as before."""
    live = np.where(alive[:, n])[0]
    if len(live) < 4:
        return np.zeros(0, np.float32)
    p = xy[live, n]
    pred = p[1:-1] + (p[1:-1] - p[:-2])
    return np.linalg.norm(p[2:] - pred, axis=1).astype(np.float32)


def things_tracked(frames: list[np.ndarray], *, link: float = 0.55, min_size: int = 5,
                   neighbourhood: float = 0.35, cell: int = 16, max_things: int = 24,
                   weights: tuple[float, float, float] = (0.6, 0.25, 0.15)) -> list["Thing"]:
    """Group TRACKS that behave as one body. The unit follows the stuff, not the screen.

    Affinity combines three things the tracked substrate makes available and a grid does not:

        rigidity        did they keep their separation over their shared life
        co-life         did they live and die together
        residual corr   were they surprised at the same moments

    None of the three is computable on a fixed grid, which is why this is a different version rather
    than the previous one retuned."""
    tr = tracks(frames)
    xy, alive = tr["xy"], tr["alive"]
    T, N = alive.shape
    if N < min_size * 2:
        return []
    life = alive.sum(axis=0)
    keep = [int(n) for n in np.where(life >= max(6, T // 6))[0]]
    if len(keep) < min_size * 2:
        return []

    res = {n: track_residual(xy, alive, n) for n in keep}
    H, W = frames[0].shape[:2]
    radius = neighbourhood * max(H, W)
    w_rig, w_co, w_res = weights

    aff: dict[int, list[int]] = {n: [] for n in keep}
    for a_i, i in enumerate(keep):
        for j in keep[a_i + 1:]:
            both = alive[:, i] & alive[:, j]
            if both.sum() < 6:
                continue
            if float(np.linalg.norm(xy[both, i] - xy[both, j], axis=1).mean()) > radius:
                continue                          # objects are contiguous
            rg = rigidity(xy, alive, i, j)
            co = float(both.sum()) / float(max((alive[:, i] | alive[:, j]).sum(), 1))
            ra, rb = res[i], res[j]
            L = min(len(ra), len(rb))
            rc = _corr(ra[:L], rb[:L]) if L >= 6 else 0.0
            if w_rig * rg + w_co * co + w_res * max(rc, 0.0) >= link:
                aff[i].append(j)
                aff[j].append(i)

    seen: set = set()
    groups: list[list[int]] = []
    for n in sorted(keep, key=lambda k: -life[k]):
        if n in seen:
            continue
        comp, stack = [], [n]
        seen.add(n)
        while stack:
            c = stack.pop()
            comp.append(c)
            for m in aff[c]:
                if m not in seen:
                    seen.add(m)
                    stack.append(m)
        if len(comp) >= min_size:
            groups.append(comp)
        if len(groups) >= max_things:
            break

    out: list[Thing] = []
    mid = T // 2
    for comp in groups:
        pts = [xy[mid, n] for n in comp if alive[mid, n]]
        if len(pts) < 3:
            pts = [xy[alive[:, n], n][0] for n in comp if alive[:, n].any()]
        if len(pts) < 3:
            continue
        mask = np.zeros((H, W), bool)
        for x, y in pts:
            cx, cy = max(0, int(x) // cell * cell), max(0, int(y) // cell * cell)
            mask[cy:cy + cell, cx:cx + cell] = True
        if not mask.any():
            continue
        ys, xs = np.where(mask)
        inner = [rigidity(xy, alive, a, b) for a in comp[:12] for b in comp[:12] if a < b]
        rr = [res[n].mean() for n in comp if len(res[n])]
        out.append(Thing(mask=mask,
                         box=(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1),
                         cells=len(comp), area_frac=float(mask.mean()),
                         coherence=float(np.mean(inner)) if inner else 0.0,
                         residual=float(np.mean(rr)) if rr else 0.0))
    out.sort(key=lambda t: -t.cells)
    return out
