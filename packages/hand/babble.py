# -*- coding: utf-8 -*-
"""Learn what a body does by moving it and watching — no one says which key is which.

THE RULE THIS ORGAN EXISTS TO KEEP. Nothing here is told that `w` is forward. It is not told that
there IS a forward. It presses a key, looks at what the image did, and keeps the pair. The mapping
from motor command to visual consequence is DISCOVERED, and if the game were rebound tomorrow, or
the body swapped for a different one, the same procedure would find the new mapping without a line
changing. Writing `w -> forward` in a table would be faster today and would be supplying the answer,
which is the thing this project keeps refusing to do.

This is the same procedure `Track E M1` already passed on a robot arm — babble, observe, fit forward
kinematics — moved to a different body. That it is the same procedure is the interesting part: a
body schema for a limb and a body schema for a city avatar should not be two mechanisms.

HOW THE CONSEQUENCE IS MEASURED. Two frames, coarse block matching on a downsampled grey image, and
three numbers read off the resulting flow field:

    dx, dy    how far the image slid, in pixels     -> turning and strafing
    div       how much it expanded from the centre  -> moving along the view axis

Expansion is the one that separates walking from turning, and it is why flow is measured as a FIELD
rather than as a single global shift. Walking forward and turning both move most pixels sideways;
only walking makes them spread outward from the focus of expansion. A global-shift estimator would
call those the same thing and the body schema would fuse two different acts.

WHAT COUNTS AS AN EFFECT IS MEASURED, NOT ASSUMED. Before any key is tried, the world is watched
doing nothing for a moment, and the flow of that stillness is recorded. A key's effect has to stand
out against THAT, not against zero — a city has traffic, pedestrians and moving light, so "the image
changed" is not evidence that the body did anything.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

LEDGER = Path(r"D:\citysample_drive\body_schema.jsonl")


# --- reading the consequence ---------------------------------------------------------------------

def _grey(rgb: np.ndarray, w: int = 96, h: int = 72) -> np.ndarray:
    """Downsample by AREA AVERAGE, not by picking every Nth pixel.

    Nearest-neighbour subsampling was the first version and it aliases: sampling a 320-wide image at
    stride 3.3 throws away everything between the samples, so a shift that does not land on the
    stride is unrecoverable. On real frames — smooth, spatially correlated — it happened to work,
    and the live babbling run gave consistent readings across three repeats. On a test image of
    white noise it collapsed entirely, and the test failing was the first honest signal that the
    measurement rests on the input being smooth rather than on the method being sound.

    Area averaging keeps the information between samples, which is what makes a sub-stride shift
    still visible."""
    g = rgb.mean(axis=2).astype(np.float32)
    try:
        import cv2
        return cv2.resize(g, (w, h), interpolation=cv2.INTER_AREA)
    except Exception:
        H, W = g.shape
        by, bx = max(1, H // h), max(1, W // w)
        g = g[:by * h, :bx * w].reshape(h, by, w, bx).mean(axis=(1, 3))
        return g.astype(np.float32)


def _block_flow(a: np.ndarray, b: np.ndarray, blocks: int = 6, search: int = 6) -> np.ndarray:
    """Per-block (dx, dy) by exhaustive small search. Crude and dependency-free on purpose.

    A proper optical flow would be better and would also be another thing to install, tune and
    trust. For deciding "did this key turn me or move me", block matching on a 96x72 image is
    enough, and its failure mode is honest: on a textureless wall it returns near-zero everywhere,
    which is correctly reported as "no measurable effect" rather than as a confident wrong answer."""
    H, W = a.shape
    bh, bw = H // blocks, W // blocks
    out = np.zeros((blocks, blocks, 2), np.float32)
    for by in range(blocks):
        for bx in range(blocks):
            y0, x0 = by * bh, bx * bw
            patch = a[y0:y0 + bh, x0:x0 + bw]
            best, bd = 1e18, (0, 0)
            for dy in range(-search, search + 1):
                for dx in range(-search, search + 1):
                    yy, xx = y0 + dy, x0 + dx
                    if yy < 0 or xx < 0 or yy + bh > H or xx + bw > W:
                        continue
                    d = float(np.abs(b[yy:yy + bh, xx:xx + bw] - patch).mean())
                    if d < best:
                        best, bd = d, (dx, dy)
            out[by, bx] = bd
    return out


def flow_signature(a_rgb: np.ndarray, b_rgb: np.ndarray) -> dict[str, float]:
    """(dx, dy, div, mag) — what the image did between two frames."""
    a, b = _grey(a_rgb), _grey(b_rgb)
    f = _block_flow(a, b)
    dx, dy = float(f[..., 0].mean()), float(f[..., 1].mean())
    n = f.shape[0]
    gy, gx = np.mgrid[0:n, 0:n].astype(np.float32)
    cx = cy = (n - 1) / 2.0
    rx, ry = gx - cx, gy - cy
    norm = np.sqrt(rx ** 2 + ry ** 2) + 1e-6
    # divergence: how much the flow points AWAY from the centre. Positive = expansion = closing in.
    div = float(((f[..., 0] * rx + f[..., 1] * ry) / norm).mean())
    mag = float(np.sqrt(f[..., 0] ** 2 + f[..., 1] ** 2).mean())
    return {"dx": round(dx, 3), "dy": round(dy, 3), "div": round(div, 3), "mag": round(mag, 3)}


# --- the babbling session -------------------------------------------------------------------------

@dataclass
class BodySchema:
    """What pressing each thing does, as observed."""

    still: dict[str, float] = field(default_factory=dict)      # the world moving on its own
    effects: dict[str, list[dict[str, float]]] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {"still_baseline": self.still, "moves": {}}
        base = float(self.still.get("mag", 0.0))
        for k, rows in sorted(self.effects.items()):
            if not rows:
                continue
            arr = {c: float(np.median([r[c] for r in rows])) for c in ("dx", "dy", "div", "mag")}
            # Effect size against the world's own motion. When the world was genuinely still the
            # ratio is UNDEFINED, not enormous: dividing by a 1e-3 floor produced readings like
            # "2130x still", which is a division artefact wearing the costume of a measurement.
            # A zero baseline is good news — it means the scene was quiet — and it is said plainly.
            arr["over_still"] = round(arr["mag"] / base, 2) if base > 1e-3 else None
            arr["n"] = len(rows)
            # Agreement across repeats. Two trials of the same key that disagree are not a weaker
            # version of a result, they are a different result, and the median hides that.
            mags = [r["mag"] for r in rows]
            arr["spread"] = round(float(np.std(mags)), 3)
            out["moves"][k] = {c: round(v, 3) if isinstance(v, float) else v for c, v in arr.items()}
        return out

    def describe(self) -> list[str]:
        """Name what was found, in the language of consequences rather than of key labels.

        The names are descriptions of measured flow, not assumptions about what the key 'is'. A move
        that expands the image is called `closes_in` because that is what was seen; whether the body
        walked, rolled or flew is not something this organ can know, and it does not need to."""
        s = self.summary()
        lines = []
        # THE FLOOR. When the world is still there is no ratio, so the bar becomes an absolute one
        # on measured flow. 0.5 px of median block motion on a 96x72 grid is well above what area-
        # averaged frames of a quiet scene produce (measured: 0.0), and well below any real move
        # (measured: 1.4-3.2).
        for k, v in s["moves"].items():
            ratio, mag = v.get("over_still"), v["mag"]
            weak = (ratio is not None and ratio < 1.5) or (ratio is None and mag < 0.5)
            if weak:
                how = f"{ratio}x still" if ratio is not None else f"mag {mag}, still was 0"
                lines.append(f"{k}: no effect above the world's own motion ({how})")
                continue
            parts = []
            if abs(v["div"]) > 0.4:
                parts.append("closes_in" if v["div"] > 0 else "backs_off")
            if abs(v["dx"]) > 0.4:
                parts.append("view_slides_right" if v["dx"] > 0 else "view_slides_left")
            if abs(v["dy"]) > 0.4:
                parts.append("view_slides_down" if v["dy"] > 0 else "view_slides_up")
            conf = "consistent" if v["spread"] < 0.4 * max(v["mag"], 1e-6) else "VARIABLE across repeats"
            lines.append(f"{k}: {' + '.join(parts) or 'moves, direction unclear'} "
                         f"(mag {v['mag']}, spread {v['spread']}, {conf})")
        return lines


def babble(eye, hand, moves, *, repeats: int = 3, settle: float = 0.25) -> BodySchema:
    """Try each move, watch what happens, keep the pair.

    `moves` is a list of `Move`. What is NOT passed in is any claim about what they do."""
    from .effector import Move  # noqa: F401  (documents the expected type)

    schema = BodySchema()

    # What does the world do when the body does nothing? Measured first, because everything after is
    # scored against it.
    # Several samples, because one pair of a quiet scene can miss a passing car and then every
    # effect below is scored against a baseline that happened to be taken in a lull.
    stills = []
    for _ in range(4):
        a = eye.look().frame.rgb.copy()
        time.sleep(settle)
        b = eye.look().frame.rgb.copy()
        stills.append(flow_signature(a, b))
    schema.still = {c: round(float(np.median([s[c] for s in stills])), 3)
                    for c in ("dx", "dy", "div", "mag")}

    # INTERLEAVED, not blocked. Three consecutive presses of the same key leave the body somewhere
    # new each time -- further down a street, facing a wall -- so the second and third trials start
    # from a different world than the first and are not repeats of the same experiment. Running one
    # of every move, then another of every move, spreads that drift across all of them instead of
    # loading it onto whichever key went last. The first blocked run had `w` and `lshift+w`
    # disagreeing about their own direction, which is what that flaw looks like from the outside.
    for mv in moves:
        schema.effects.setdefault(mv.label or "+".join(mv.keys) or f"mouse{mv.mouse_dx},{mv.mouse_dy}", [])
    for _round in range(repeats):
        for mv in moves:
            key = mv.label or "+".join(mv.keys) or f"mouse{mv.mouse_dx},{mv.mouse_dy}"
            before = eye.look().frame.rgb.copy()
            res = hand.do(mv)
            if not res.get("ok"):
                schema.effects[key].append({"dx": 0.0, "dy": 0.0, "div": 0.0, "mag": 0.0,
                                            "refused": res.get("refused", "?")})
                continue
            time.sleep(settle)
            after = eye.look().frame.rgb.copy()
            schema.effects[key].append(flow_signature(before, after))
    hand.release_all()

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                             **schema.summary()}, ensure_ascii=False) + "\n")
    return schema
