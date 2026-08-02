# -*- coding: utf-8 -*-
"""F3, done properly: a genuinely large field with ONE live region, and a fovea that has to find it.

    python scripts/f3_large_field_foveation.py

The first F3 was invalid and I said so: upscaling by pixel repeat broke the chain WITHOUT any foveation --
the full-resolution baseline fell from 68% to 36.7% to 15.0% to 0.0% as the frame grew -- because repeated
pixels make blocky sprites and change the blob statistics the tracker depends on. The large-frame arms
measured my upscaling artefact.

City Sample would have been the honest large frame and it is not available: `UnrealEditor.exe` is running
with 2.1 GB resident and NO titled window to capture.

SO THE DEFECT IS FIXED RATHER THAN WORKED AROUND. The live frame is kept at NATIVE resolution and PLACED
at a random position in a large canvas whose remaining area is filled with static clutter drawn from other
frames of the same stream. Sprites stay sharp, the statistics stay familiar, and the field is genuinely
large with exactly one region that matters -- which is the human task, and the only condition under which
a fovea has anything to do.

    canvas 4x and 16x the native area, with one 160x210 live region placed at random each episode
    the clutter is real frames from the same rollout, so it is not a blank margin that foveation could
      exploit for free

REGISTERED:
    1  the FULL-RESOLUTION baseline must hold as the canvas grows. If it collapses again the harness is
       still broken and no foveation number from it means anything -- this is the check the first attempt
       lacked.
    2  cost sublinear: pixels read must grow far slower than the area
    3  accuracy within 5 points of full resolution, and NOT by both being zero -- a vacuous pass is
       explicitly refused this time, having happened three times already this session
    4  pursuit beats a random-gaze control at the same pixel budget
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

OUT = Path("data/atari/f3_large_field.json")
FOVEA = 96
STRIDE = 4


def build_field(frames, clutter, scale: int, seed: int):
    """One live region at native resolution, placed at random in a large canvas of static clutter."""
    h, w = frames[0].shape[:2]
    H, W = h * scale, w * scale
    rng = np.random.default_rng(seed)
    canvas = np.zeros((H, W, 3), np.uint8)
    for y in range(0, H, h):
        for x in range(0, W, w):
            c = clutter[int(rng.integers(0, len(clutter)))]
            canvas[y:min(H, y + h), x:min(W, x + w)] = c[:min(h, H - y), :min(w, W - x)]
    oy = int(rng.integers(0, max(1, H - h)))
    ox = int(rng.integers(0, max(1, W - w)))
    out = []
    for f in frames:
        c = canvas.copy()
        c[oy:oy + h, ox:ox + w] = f
        out.append(c)
    return out, (ox, oy), (H, W)


class Eye:
    """Coarse periphery acquires, fixed fovea confirms, pursuit maintains. `px` is pixels READ."""

    def __init__(self, bg, random_gaze=False, seed=0):
        self.bg = bg
        self.gaze = None
        self.px = 0
        self.random = random_gaze
        self.rng = np.random.default_rng(seed)
        self.prev_small = None

    def __call__(self, frame):
        H, W = frame.shape[:2]
        s = STRIDE
        small = frame[::s, ::s]
        self.px += small.shape[0] * small.shape[1]
        # ACQUISITION IS BY MOTION, NOT BY DIFFERENCE FROM BACKGROUND. The first version used
        # background subtraction in the periphery, so every static sprite in the clutter registered
        # permanently -- hundreds of them -- and the fovea was dragged to whichever was largest. A real
        # large scene is mostly static structure, so an acquisition signal that fires on structure
        # cannot work at scale. Frame-to-frame change fires only on what moves, which is the same
        # lesson the motion-aware consumers rung established downstream.
        if self.prev_small is None:
            coarse = np.zeros(small.shape[:2], bool)
        else:
            coarse = np.abs(small.astype(np.int16) - self.prev_small).sum(axis=2) > 40
        self.prev_small = small.astype(np.int16)
        if self.random:
            self.gaze = (float(self.rng.integers(0, W)), float(self.rng.integers(0, H)))
        elif self.gaze is None:
            ys, xs = np.where(coarse)
            self.gaze = ((float(xs.mean()) * s, float(ys.mean()) * s) if len(ys)
                         else (W / 2.0, H / 2.0))
        r = FOVEA // 2
        x0 = max(0, min(int(self.gaze[0]) - r, W - FOVEA))
        y0 = max(0, min(int(self.gaze[1]) - r, H - FOVEA))
        win = frame[y0:y0 + FOVEA, x0:x0 + FOVEA]
        self.px += win.shape[0] * win.shape[1]
        fine = sprite_mask(win, self.bg[y0:y0 + FOVEA, x0:x0 + FOVEA])
        mask = np.zeros((H, W), bool)
        mask[y0:y0 + win.shape[0], x0:x0 + win.shape[1]] = fine
        bl = blobs(fine)
        if bl and not self.random:
            b = max(bl, key=lambda z: z[2])
            self.gaze = (x0 + b[0], y0 + b[1])
        elif not self.random:
            self.gaze = None            # lost it: re-acquire from the periphery next frame
        return mask


def chain(mask_of, frames, acts, truth, off):
    tr = SpriteTracker(max_jump=22.0)
    per_frame = []
    t0 = time.perf_counter()
    for t, f in enumerate(frames):
        bl = blobs(mask_of(f))
        before = {k.id: k.pos.copy() for k in tr.tracks}
        tr.step(bl, action=acts[t], moving_only=False)
        per_frame.append([(k.id, k.pos.copy(), k.pos - before.get(k.id, k.pos)) for k in tr.tracks])
    ms = 1000.0 * (time.perf_counter() - t0) / len(frames)
    mem, hist = collections.defaultdict(list), collections.defaultdict(dict)
    for t, rows in enumerate(per_frame):
        for tid, pos, d in rows:
            if abs(d[0]) > 0.5 or abs(d[1]) > 0.5:
                mem[tid].append((acts[t], float(d[0]), float(d[1])))
            hist[tid][t] = pos
    scored = [(k, intention_momentum(v)) for k, v in mem.items() if len(v) >= 12]
    if not scored:
        return {"ms": ms, "on_body": 0.0, "presence": 0.0}
    best = max(scored, key=lambda x: x[1])[0]
    ts = sorted(hist[best])
    P = np.array([hist[best][t] for t in ts])
    T = truth[ts] + np.array(off, float)
    hit = np.hypot(P[:, 0] - T[:, 0], P[:, 1] - T[:, 1]) < 8.0
    pres = len(ts) / len(frames)
    return {"ms": ms, "presence": pres, "acc_given_present": float(hit.mean()),
            "on_body": pres * float(hit.mean())}


def main() -> None:
    base, bg0, acts, truth, agree = frames_of(240, seed=3)
    clutter, _b, _a, _t, _g = frames_of(40, seed=17)
    print(f"oracle verified r_x {agree['r_x']:.3f}; fovea FIXED at {FOVEA}x{FOVEA}, "
          f"periphery subsampled by {STRIDE}")
    print("live region kept at NATIVE resolution and placed at random in a field of real clutter\n")

    print(f"{'canvas':<14}{'policy':<26}{'px read':>10}{'ms':>8}{'presence':>10}{'ON-BODY':>9}")
    res = {}
    for scale in (1, 2, 4):
        frames, off, (H, W) = build_field(base[:120], clutter, scale, seed=5)
        bg = np.zeros((H, W, 3), np.int16)
        for y in range(0, H, bg0.shape[0]):
            for x in range(0, W, bg0.shape[1]):
                bg[y:min(H, y + bg0.shape[0]), x:min(W, x + bg0.shape[1])] = \
                    bg0[:min(bg0.shape[0], H - y), :min(bg0.shape[1], W - x)]
        bg[off[1]:off[1] + bg0.shape[0], off[0]:off[0] + bg0.shape[1]] = bg0
        tag = f"{W}x{H}"
        full = chain(lambda f: sprite_mask(f, bg), frames, acts, truth, off)
        full["px"] = float(W * H)
        e = Eye(bg)
        fov = chain(e, frames, acts, truth, off)
        fov["px"] = e.px / len(frames)
        c = Eye(bg, random_gaze=True)
        ctl = chain(c, frames, acts, truth, off)
        ctl["px"] = c.px / len(frames)
        for nm, r in (("full resolution", full), ("PURSUIT FOVEATION", fov),
                      ("random gaze (control)", ctl)):
            res[f"{tag}|{nm}"] = r
            print(f"{tag:<14}{nm:<26}{r['px']:>10.0f}{r['ms']:>8.2f}"
                  f"{r.get('presence', 0):>9.1%}{r['on_body']:>9.1%}", flush=True)
        print(flush=True)

    tags = sorted({k.split('|')[0] for k in res}, key=lambda t: int(t.split('x')[0]))
    small, big = tags[0], tags[-1]
    g = lambda t, n, k: res[f"{t}|{n}"][k]      # noqa: E731
    area = g(big, "full resolution", "px") / g(small, "full resolution", "px")
    fovg = g(big, "PURSUIT FOVEATION", "px") / g(small, "PURSUIT FOVEATION", "px")
    base_ok = g(big, "full resolution", "on_body") > 0.15
    print(f"-> 1. the full-resolution baseline HOLDS as the canvas grows: {base_ok}  "
          f"({g(small, 'full resolution', 'on_body'):.1%} -> "
          f"{g(big, 'full resolution', 'on_body'):.1%})")
    if not base_ok:
        print("      the harness is still broken; nothing below can be read.")
    print(f"-> 2. cost sublinear: area {area:.0f}x, pixels read {fovg:.1f}x  "
          f"{fovg < area / 2}")
    fov_b, full_b = g(big, "PURSUIT FOVEATION", "on_body"), g(big, "full resolution", "on_body")
    vacuous = fov_b < 0.02 and full_b < 0.02
    print(f"-> 3. accuracy within 5 points, NOT vacuously: "
          f"{(fov_b >= full_b - 0.05) and not vacuous}  "
          f"({full_b:.1%} -> {fov_b:.1%}{'  [VACUOUS -- refused]' if vacuous else ''})")
    print(f"-> 4. pursuit beats random gaze: "
          f"{fov_b > g(big, 'random gaze (control)', 'on_body') + 0.05}  "
          f"({g(big, 'random gaze (control)', 'on_body'):.1%})")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"fovea": FOVEA, "stride": STRIDE, "results": res,
                               "area_growth": area, "px_growth_foveated": fovg,
                               "baseline_holds": bool(base_ok)}, indent=2, default=str),
                   encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
