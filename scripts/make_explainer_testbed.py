# -*- coding: utf-8 -*-
"""Explainer video with the answer key built in, at three difficulties.

    python scripts/make_explainer_testbed.py

Owner clarified that the videos they meant are informational — a knowledge channel, not live-action
footage. That changes what a boundary IS. In a driving clip a boundary is where the motion regime
changes; in an explainer it is where the EXPLANATION moves on, and those are different signals that
would be easy to conflate while testing only on one.

WHY GENERATED RATHER THAN DOWNLOADED. Real explainer video is what this is ultimately for, and
downloading it from YouTube is against their terms, so that is a decision for the owner rather than
something to do quietly. Generating it also buys the thing a downloaded clip cannot give: the exact
frame each explanation step begins on, with no annotation and no inference, and the ability to hold
everything constant while varying ONE property of the video.

THREE DIFFICULTIES, and the third is the one that matters:

  cut     hard slide changes. Trivially detectable — any pixel-difference measure finds these. Here
          as a floor: a segmenter that cannot do this is broken.

  build   elements appear one at a time WITHIN a topic, and the topic changes are the real
          boundaries. This is what explainers actually do, and it is a trap: the appearance of a new
          bullet is a large pixel change that is NOT a boundary, so anything scoring raw change
          fires constantly and scores worse than chance while looking busy.

  pan     the camera drifts across a large diagram continuously while topics change underneath.
          The confound is motion: smooth panning produces a large, steady residual throughout, which
          is exactly the failure divisive normalisation exists to remove. This is the direct test of
          whether that fix generalises off driving footage.

WHAT IT DOES NOT TEST. Everything the words carry. A knowledge video's causal content lives in
narration and in text, and no amount of pixel segmentation recovers "the compressor squeezes the
incoming air". This produces the UNITS; what is in them is a separate organ's problem and pretending
otherwise would be the more comfortable mistake.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path(r"D:\explainer_testbed")
H, W = 240, 320


def _panel(rng, h: int, w: int) -> np.ndarray:
    """A slide's background: a calm wash, the way an explainer's canvas is."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    base = 210 + 25 * np.sin(x / max(w / 3.0, 1) + rng.uniform(0, 6))
    return np.clip(base, 0, 255)


def _element(canvas: np.ndarray, rng, kind: str) -> None:
    """Draw one explanatory element in place — a box, an arrow, a line of text, a blob."""
    h, w = canvas.shape[:2]
    y0, x0 = int(rng.integers(10, max(11, h - 60))), int(rng.integers(10, max(11, w - 90)))
    hh, ww = int(rng.integers(18, 48)), int(rng.integers(40, 96))
    y1, x1 = min(h - 1, y0 + hh), min(w - 1, x0 + ww)
    v = float(rng.uniform(20, 110))
    if kind == "box":
        canvas[y0:y1, x0:x0 + 2] = v
        canvas[y0:y1, x1 - 2:x1] = v
        canvas[y0:y0 + 2, x0:x1] = v
        canvas[y1 - 2:y1, x0:x1] = v
    elif kind == "arrow":
        cy = (y0 + y1) // 2
        canvas[cy:cy + 2, x0:x1] = v
        for k in range(8):
            canvas[max(0, cy - k):cy + k + 2, max(x0, x1 - 8 + k):x1 - 7 + k] = v
    elif kind == "text":
        for r in range(3):
            ry = y0 + r * 8
            if ry + 4 < h:
                canvas[ry:ry + 4, x0:x0 + int(ww * rng.uniform(0.5, 1.0))] = v
    else:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        canvas -= 90 * np.exp(-(((yy - (y0 + y1) / 2) ** 2) / 120 + ((xx - (x0 + x1) / 2) ** 2) / 300))


def build_sequence(mode: str, *, topics: int = 12, seed: int = 0) -> tuple[np.ndarray, list[int], list[str]]:
    """Frames plus the frame index each topic begins on. The key is written, never inferred."""
    rng = np.random.default_rng(seed)
    frames: list[np.ndarray] = []
    bounds: list[int] = []
    labels: list[str] = []

    big_h, big_w = (H * 2, W * 3) if mode == "pan" else (H, W)
    for t in range(topics):
        if t:
            bounds.append(len(frames))
        hold = int(rng.integers(35, 90))
        canvas = _panel(rng, big_h, big_w)
        n_el = int(rng.integers(3, 7))
        kinds = [("box", "arrow", "text", "blob")[int(rng.integers(0, 4))] for _ in range(n_el)]

        if mode == "cut":
            for k in kinds:
                _element(canvas, rng, k)
            for _ in range(hold):
                frames.append(canvas.copy())
                labels.append(f"topic{t}")

        elif mode == "build":
            # elements arrive one at a time; each arrival is a big pixel change and NOT a boundary
            per = max(4, hold // max(n_el, 1))
            for i, k in enumerate(kinds):
                _element(canvas, rng, k)
                for _ in range(per):
                    frames.append(canvas.copy())
                    labels.append(f"topic{t}")

        else:                                   # pan
            for k in kinds:
                _element(canvas, rng, k)
            cy = float(rng.integers(0, max(1, big_h - H)))
            cx = float(rng.integers(0, max(1, big_w - W)))
            vy = float(rng.uniform(-1.1, 1.1))
            vx = float(rng.uniform(-1.6, 1.6))
            for _ in range(hold):
                cy = min(max(cy + vy, 0), big_h - H - 1)
                cx = min(max(cx + vx, 0), big_w - W - 1)
                frames.append(canvas[int(cy):int(cy) + H, int(cx):int(cx) + W].copy())
                labels.append(f"topic{t}")

    arr = np.stack(frames).astype(np.uint8)
    return np.repeat(arr[:, :, :, None], 3, axis=3), bounds, labels


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", type=int, default=14)
    ap.add_argument("--seeds", type=int, default=4)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for mode in ("cut", "build", "pan"):
        for seed in range(args.seeds):
            frames, bounds, labels = build_sequence(mode, topics=args.topics, seed=seed)
            d = OUT / f"{mode}_{seed}"
            d.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(d / "frames.npz", rgb=frames)
            (d / "meta.json").write_text(json.dumps(
                {"mode": mode, "seed": seed, "frames": len(frames), "boundaries": bounds,
                 "topics": args.topics,
                 "key": "recorded while generating; never inferred from the pixels"},
                indent=2), encoding="utf-8")
            index.append({"dir": d.name, "mode": mode, "frames": len(frames),
                          "boundaries": len(bounds)})
            print(f"  {mode}_{seed}: {len(frames)} frames, {len(bounds)} true boundaries")
    (OUT / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
