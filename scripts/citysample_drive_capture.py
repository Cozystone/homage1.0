# -*- coding: utf-8 -*-
"""Record what ATANOR sees while it moves through City Sample.

    python scripts/citysample_drive_capture.py --seconds 60

THE POINT IS LEARNING, NOT A TEST. City Sample has no depth ground truth — it is a rendered game
window and nothing hands out metres. So this cannot be, and is not trying to be, a labelled
benchmark. What a moving body DOES have is its own motion, and that is enough: predict depth for
frame t and the ego-motion from t to t+1, warp t into t+1, and score the photometric error. The
supervision is the next frame. No labels, no simulator cooperation, and the same signal a humanoid
would have walking down a real street.

So this script captures the raw material for that: consecutive frames, in order, with timestamps,
through `packages.eye` — the SAME door a screen, a camera or a CARLA episode comes through. That
sameness is the point rather than a convenience. If City Sample frames arrived by a private path,
"does what it learned in CARLA apply here" would be confounded before any model saw a pixel.

WHAT IS STORED AND WHY. Frames are downscaled to 640x480: the depth net takes 320x240, so anything
larger is storage spent on detail the learner will throw away, and at ~30 fps full-resolution frames
fill a disk in minutes. Timestamps are kept per frame because the interval between two frames is
what turns a pile of pictures into motion — without it the pairs are unordered and the photometric
objective has nothing to warp along.

Frames where the eye reports `fresh=False` are DROPPED. A repeated cached frame has zero baseline,
so a depth-from-motion objective would see "no motion" and learn that everything is infinitely far.
That is the failure this flag was added to prevent, and it is the reason it is checked here.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.eye import WindowSource, open_eye   # noqa: E402

OUT = Path(r"D:\citysample_drive")


def _downscale(rgb: np.ndarray, w: int = 640, h: int = 480) -> np.ndarray:
    ys = (np.arange(h) * (rgb.shape[0] / h)).astype(np.int32)
    xs = (np.arange(w) * (rgb.shape[1] / w)).astype(np.int32)
    return np.ascontiguousarray(rgb[ys][:, xs])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--window", default="CitySample")
    ap.add_argument("--every", type=int, default=2, help="keep 1 of N fresh frames")
    ap.add_argument("--tag", default="drive")
    args = ap.parse_args()

    src = WindowSource(title_contains=args.window)
    ok, why = src.available()
    if not ok:
        sys.exit(f"window {args.window!r} not available: {why}")

    run = OUT / f"{args.tag}_{time.strftime('%H%M%S')}"
    run.mkdir(parents=True, exist_ok=True)
    eye = open_eye(src, gate=False)          # the gate decides what to RECOGNISE; here we want all
                                             # fresh frames, because motion is the training signal
    kept, seen, stale = 0, 0, 0
    times: list[float] = []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < args.seconds:
        look = eye.look()
        seen += 1
        if not look.frame.meta.get("fresh"):
            stale += 1
            continue                          # a repeat has no baseline; see the module docstring
        if kept % 1 == 0 and seen % args.every == 0:
            np.savez_compressed(run / f"{kept:05d}.npz",
                                rgb=_downscale(look.frame.rgb),
                                t_mono=np.float64(look.frame.t_mono))
            times.append(look.frame.t_mono)
            kept += 1

    dt = time.perf_counter() - t0
    gaps = np.diff(times) if len(times) > 1 else np.array([0.0])
    meta = {"tag": args.tag, "window": args.window, "seconds": round(dt, 2),
            "looks": seen, "kept": kept, "stale_dropped": stale,
            "fresh_fps": round((seen - stale) / dt, 2),
            "kept_fps": round(kept / dt, 2),
            "gap_ms": {"median": round(float(np.median(gaps)) * 1000, 1),
                       "p90": round(float(np.percentile(gaps, 90)) * 1000, 1),
                       "max": round(float(gaps.max()) * 1000, 1)},
            "size": [640, 480]}
    (run / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))
    print("wrote", run)
    eye.close()


if __name__ == "__main__":
    main()
