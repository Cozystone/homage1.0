# -*- coding: utf-8 -*-
"""Score permanence on THE CROSSING ITSELF — not on an average that buries it.

The first version of this scored the overall keep-rate with a blind stretch somewhere inside it, and
reported 0.910 with no gap against 0.909 with a six-frame gap. That difference is not small, it is
ABSENT: 48 blind frames diluted into 5,500 bindings cannot move a mean, so the number was measuring
everything except the thing it was built to measure.

So this scores only the re-binding ACROSS the gap, and runs three arms that differ in one thing each,
because "it works" is not a claim until the alternatives are on the same page:

    none      belief expires immediately -- the floor. Anything that vanishes comes back a stranger.
    static    belief persists, predicting the thing stayed where it was last seen.
    coast     belief persists, carrying its motion through the blind stretch (owner's design).

static vs coast is the whole of the owner's simulation idea, isolated: same memory, same appearance
model, same binding rule, differing only in whether a hidden thing is thought to MOVE.

The truth across the gap is free because we cut the gap ourselves.

Run:  python scripts/score_object_permanence.py --gap 6 --episodes 12
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.perception import common_fate as CF                       # noqa: E402
from packages.perception.object_permanence import (Permanence,          # noqa: E402
                                                   appearance, centroid)

EPISODES = r"D:\carla\episodes"
LEAD, TAIL = 8, 3          # frames watched before the gap, and after it


def _truth(mask, semantic) -> int:
    v = semantic[mask]
    if v.size == 0:
        return -1
    ids, counts = np.unique(v, return_counts=True)
    return int(ids[int(np.argmax(counts))])


def _frame(fs, t):
    a, b = np.load(fs[t]), np.load(fs[t + 1])
    rgb, sem, dm = a["rgb"], a["semantic"], a["depth_m"].astype("float32")
    regs = CF.things(rgb, b["rgb"], dm)
    # the distance TO A LUMP is the median over its mask, not the depth at its centre of mass: an
    # irregular region has its centroid in a hole, and the hole shows whatever is behind.
    zs = []
    for r in regs:
        v = dm[r.mask]
        v = v[np.isfinite(v) & (v > 0.5) & (v <= 200.0)]
        zs.append(float(np.median(v)) if v.size else None)
    return ([(centroid(r.mask), appearance(rgb, r.mask)) for r in regs],
            [_truth(r.mask, sem) for r in regs], rgb.shape[:2], a["pose"], dm, zs)


def crossing(fs, gap: int, mode: str, look_weight: float = 0.5) -> tuple[int, int, int]:
    """Watch, go blind, look again. Returns (right, wrong, lost) for the first frame after the gap.

    `look_weight` matters more than it looks. At the default 0.5 all four arms scored within noise of
    each other, because APPEARANCE was carrying the binding and the arms differ only in where they
    think a hidden thing went -- three different predictions feeding a decision that was not
    listening to any of them. Set it to 0 and position is the only signal, which is the only setting
    where the arms are actually being compared."""
    p = Permanence(gap_tolerance=0 if mode == "none" else gap + 4, look_weight=look_weight)
    start = max(0, len(fs) // 3 - LEAD)
    truth_of: dict = {}
    world = (mode == "world")
    for t in range(start, start + LEAD):
        dets, truths, shape, pose, dm, zs = _frame(fs, t)
        out = p.observe(dets, t, shape=shape, pose=pose if world else None,
                        depths=zs if world else None)
        for i, tid in out["bound"].items():
            truth_of[tid] = truths[i]
        for i in out["new"]:
            truth_of[max(p.tracks)] = truths[i]
    if mode == "static":
        for tr in p.tracks.values():
            tr.vel = (0.0, 0.0)                      # believe it stayed put
    believed = dict(truth_of)
    t_back = start + LEAD + gap                      # the gap frames are simply never loaded
    if t_back + TAIL + 1 >= len(fs):
        return (0, 0, 0)
    dets, truths, shape, pose, dm, zs = _frame(fs, t_back)
    out = p.observe(dets, t_back, shape=shape, pose=pose if world else None,
                    depths=zs if world else None)
    right = wrong = lost = 0
    for i, tid in out["bound"].items():
        if believed.get(tid) == truths[i]:
            right += 1
        else:
            wrong += 1
    for i in out["new"]:
        if truths[i] in set(believed.values()):
            lost += 1                                # it was there before; we failed to know it
    return (right, wrong, lost)


def run(gap: int, n_eps: int, start_ep: int, look_weight: float = 0.5) -> None:
    eps = sorted(e for e in os.listdir(EPISODES) if e.startswith("ep"))[start_ep:start_ep + n_eps]
    print("gap %d frames | %d episodes from %s | look_weight %.2f"
          % (gap, len(eps), eps[0] if eps else "-", look_weight))
    print("%-7s %7s %7s %7s   %s" % ("mode", "right", "wrong", "lost", "re-bound correctly"))
    for mode in ("none", "static", "coast", "world"):
        R = W = L = 0
        for ep in eps:
            fs = sorted(glob.glob(os.path.join(EPISODES, ep, "*.npz")))
            if len(fs) < LEAD + gap + TAIL + 4:
                continue
            r, w, ll = crossing(fs, gap, mode, look_weight)
            R += r
            W += w
            L += ll
        tot = R + W + L
        print("%-7s %7d %7d %7d   %.3f" % (mode, R, W, L, (R / tot) if tot else 0.0))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=int, default=6)
    ap.add_argument("--episodes", type=int, default=12)
    ap.add_argument("--start", type=int, default=40)
    ap.add_argument("--look-weight", type=float, default=0.5)
    a = ap.parse_args()
    run(a.gap, a.episodes, a.start, a.look_weight)
