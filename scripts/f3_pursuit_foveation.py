# -*- coding: utf-8 -*-
"""F3: make our cost sublinear in frame size, the way an eye does -- coarse periphery, fine fovea, pursuit.

    python scripts/f3_pursuit_foveation.py

F1 turned this into the load-bearing rung. OWLv2 resizes to a fixed resolution, so its cost is CONSTANT in
frame size (0.98x for 16x the pixels) while ours is linear (11.62x). The gap therefore closes as frames
grow -- 356x at 160x210, 121x at 640x840 -- and extrapolates to parity somewhere above 4K. Our efficiency
advantage survives at scale only if our cost stops being linear in pixels.

Human vision solved this and the solution is not compression, it is ALLOCATION:

    a coarse periphery ACQUIRES -- low resolution over the whole field, enough to notice that something
      moved, and cheap because it is subsampled
    a fine fovea CONFIRMS -- full resolution over about one degree, which is a tiny fraction of the field
    pursuit MAINTAINS -- once the fovea is on a moving thing it stays on it, and a saccade is only needed
      when acquisition beats pursuit

That decomposition is what makes the cost roughly independent of how big the field is: the fovea's area is
fixed, and only the cheap periphery scales.

REGISTERED, measured across three frame sizes so the scaling claim is a slope and not a point:
    1  cost grows SUBLINEARLY in pixels -- ours is 11.62x for 16x area today, and the fovea must beat that
    2  accuracy holds -- on-body via the same tracker and criterion, against the full-resolution chain
    3  and against a control whose fovea is placed at RANDOM, because a fixed-size window that happens to
       cover a small screen would score well for reasons that have nothing to do with pursuit
"""
from __future__ import annotations

import collections
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception.self_criterion import intention_momentum         # noqa: E402
from packages.perception.sprite_tracker import SpriteTracker              # noqa: E402
from scripts.atari_babble import blobs, sprite_mask                       # noqa: E402
from scripts.wire_learned_mask import frames_of                           # noqa: E402

OUT = Path("data/atari/f3_pursuit_foveation.json")
FOVEA = 64            # side of the full-resolution window, in pixels, FIXED regardless of frame size
PERIPHERY_STRIDE = 4  # the coarse field: every 4th pixel


def upscale(a, k):
    return np.repeat(np.repeat(a, k, axis=0), k, axis=1) if k > 1 else a


class PursuitEye:
    """Coarse periphery acquires, fixed-size fovea confirms, pursuit keeps it there.

    `px` counts the pixels actually READ, which is the quantity that must stop scaling. The periphery is
    subsampled so its cost is (area / stride^2); the fovea is a constant."""

    def __init__(self, bg, random_gaze: bool = False, seed: int = 0):
        self.bg = bg
        self.gaze = None
        self.px = 0
        self.random = random_gaze
        self.rng = np.random.default_rng(seed)

    def __call__(self, frame):
        H, W = frame.shape[:2]
        s = PERIPHERY_STRIDE
        # --- periphery: coarse, whole field, cheap
        small = frame[::s, ::s]
        bgs = self.bg[::s, ::s]
        self.px += small.shape[0] * small.shape[1]
        coarse = np.abs(small.astype(np.int16) - bgs).sum(axis=2) > 40
        if self.random or self.gaze is None:
            if self.random:
                self.gaze = (float(self.rng.integers(0, W)), float(self.rng.integers(0, H)))
            else:
                ys, xs = np.where(coarse)
                self.gaze = ((float(xs.mean()) * s, float(ys.mean()) * s) if len(ys)
                             else (W / 2.0, H / 2.0))
        # --- fovea: full resolution, FIXED area, centred on the gaze
        r = FOVEA // 2
        cx, cy = int(self.gaze[0]), int(self.gaze[1])
        x0, y0 = max(0, min(cx - r, W - FOVEA)), max(0, min(cy - r, H - FOVEA))
        win = frame[y0:y0 + FOVEA, x0:x0 + FOVEA]
        self.px += win.shape[0] * win.shape[1]
        fine = sprite_mask(win, self.bg[y0:y0 + FOVEA, x0:x0 + FOVEA])
        mask = np.zeros((H, W), bool)
        mask[y0:y0 + win.shape[0], x0:x0 + win.shape[1]] = fine
        # coarse detections outside the fovea, upsampled -- the periphery still reports, roughly
        per = np.repeat(np.repeat(coarse, s, axis=0), s, axis=1)[:H, :W]
        per[y0:y0 + FOVEA, x0:x0 + FOVEA] = False
        mask |= per
        # --- pursuit: follow the biggest thing the FOVEA found; else re-acquire next frame
        bl = blobs(fine)
        if bl and not self.random:
            b = max(bl, key=lambda z: z[2])
            self.gaze = (x0 + b[0], y0 + b[1])
        elif not self.random:
            self.gaze = None
        return mask


def chain(mask_of, frames, acts, truth, scale):
    tr = SpriteTracker(max_jump=22.0 * scale)
    per_frame = []
    t0 = time.perf_counter()
    for t, f in enumerate(frames):
        bl = blobs(mask_of(f))
        before = {k.id: k.pos.copy() for k in tr.tracks}
        tr.step(bl, action=acts[t], moving_only=False)
        per_frame.append([(k.id, k.pos.copy(), k.pos - before.get(k.id, k.pos)) for k in tr.tracks])
    ms = 1000.0 * (time.perf_counter() - t0) / len(frames)

    mem = collections.defaultdict(list)
    hist = collections.defaultdict(dict)
    for t, rows in enumerate(per_frame):
        for tid, pos, d in rows:
            if abs(d[0]) > 0.5 or abs(d[1]) > 0.5:
                mem[tid].append((acts[t], float(d[0]), float(d[1])))
            hist[tid][t] = pos
    scored = [(k, intention_momentum(v)) for k, v in mem.items() if len(v) >= 12]
    if not scored:
        return {"ms": ms, "on_body": 0.0, "note": "no track reached 12 samples"}
    best = max(scored, key=lambda x: x[1])[0]
    ts = sorted(hist[best])
    P = np.array([hist[best][t] for t in ts])
    T = truth[ts] * scale
    hit = np.hypot(P[:, 0] - T[:, 0], P[:, 1] - T[:, 1]) < 8.0 * scale
    pres = len(ts) / len(frames)
    return {"ms": ms, "presence": pres, "acc_given_present": float(hit.mean()),
            "on_body": pres * float(hit.mean())}


def main() -> None:
    base, bg0, acts, truth, agree = frames_of(300, seed=3)
    print(f"oracle verified r_x {agree['r_x']:.3f}; fovea is a FIXED {FOVEA}x{FOVEA} window, "
          f"periphery subsampled by {PERIPHERY_STRIDE}\n")

    print(f"{'frame':<14}{'policy':<26}{'px read':>10}{'ms':>9}{'presence':>10}{'ON-BODY':>9}")
    res = {}
    for k in (1, 2, 4):
        frames = [upscale(f, k) for f in base[:120]]
        bg = upscale(bg0.astype(np.int16), k)
        H, W = frames[0].shape[:2]
        tag = f"{W}x{H}"

        full = chain(lambda f: sprite_mask(f, bg), frames, acts, truth, k)
        full["px"] = W * H
        eye = PursuitEye(bg)
        fov = chain(eye, frames, acts, truth, k)
        fov["px"] = eye.px / len(frames)
        ctl_eye = PursuitEye(bg, random_gaze=True)
        ctl = chain(ctl_eye, frames, acts, truth, k)
        ctl["px"] = ctl_eye.px / len(frames)

        for name, r in (("full resolution", full), ("PURSUIT FOVEATION", fov),
                        ("random gaze (control)", ctl)):
            res[f"{tag}|{name}"] = r
            print(f"{tag:<14}{name:<26}{r['px']:>10.0f}{r['ms']:>9.2f}"
                  f"{r.get('presence', 0):>9.1%}{r['on_body']:>9.1%}", flush=True)
        print(flush=True)

    def g(tag, name, key):
        return res[f"{tag}|{name}"][key]

    small, big = "160x210", "640x840"
    full_growth = g(big, "full resolution", "px") / g(small, "full resolution", "px")
    fov_growth = g(big, "PURSUIT FOVEATION", "px") / g(small, "PURSUIT FOVEATION", "px")
    print(f"-> 1. pixels read for 16x the area:  full {full_growth:.1f}x   "
          f"FOVEATED {fov_growth:.1f}x   sublinear: {fov_growth < full_growth / 2}")
    held = g(big, "PURSUIT FOVEATION", "on_body") >= g(big, "full resolution", "on_body") - 0.05
    print(f"-> 2. accuracy holds at {big}: {held}  "
          f"({g(big, 'full resolution', 'on_body'):.1%} -> "
          f"{g(big, 'PURSUIT FOVEATION', 'on_body'):.1%})")
    beats = (g(big, "PURSUIT FOVEATION", "on_body")
             > g(big, "random gaze (control)", "on_body") + 0.05)
    print(f"-> 3. pursuit beats random gaze: {beats}  "
          f"({g(big, 'random gaze (control)', 'on_body'):.1%})")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"fovea": FOVEA, "stride": PERIPHERY_STRIDE, "results": res,
                               "px_growth_full": full_growth, "px_growth_foveated": fov_growth},
                              indent=2, default=str), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
