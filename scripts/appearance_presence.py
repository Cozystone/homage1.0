# -*- coding: utf-8 -*-
"""Why the body's appearance bucket is absent 62% of the time, and which descriptor fixes it.

    python scripts/appearance_presence.py

Keying command-evidence by appearance rather than by track id removed the fragmentation that starved the
criterion -- 66 track ids collapse into one bucket. But wired into the executor it steered on 1.3% of
steps, and the gate counts named the reason: THE CHOSEN BUCKET HAS NO LIVE TRACK ON 62% OF STEPS.

That also forces a correction I have already committed: the 86.7% I reported is on-body GIVEN the bucket
was instantiated, and instantiation is only about 38%. Unconditionally it is near 0.33. This file makes
the unconditional figure the headline, because that is the number the executor actually experiences.

TWO HYPOTHESES, and they are about the descriptor rather than about the tracker or the criterion:

    the mean mixes in the background   an 8x8 patch around a sprite contains maze, pellets and dark
                                      space, and as the sprite travels the MEAN shifts across the /32
                                      quantisation boundary. The DOMINANT colour of the patch is the
                                      sprite's own and should not move.
    exact keys are brittle by design   two frames of one animating sprite land in two buckets whenever
                                      any channel crosses a boundary. Matching to the NEAREST existing
                                      bucket cannot have that failure at all.

MEASURED PER VARIANT, with the honest metric last:
    buckets            fewer is more stable, but merging the body with a ghost would also look like this
    presence           fraction of frames the chosen bucket has a live track -- the thing that broke
    on-body | present  what I reported before, kept so the two can be compared
    ON-BODY OVERALL    presence x accuracy. This is what the executor sees and what must improve.
    chance             the same figure for a bucket chosen at random, measured in the same run
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception.self_criterion import intention_momentum              # noqa: E402
from packages.perception.sprite_tracker import SpriteTracker                   # noqa: E402
from scripts.atari_babble import blobs, sprite_mask                            # noqa: E402
from scripts.atari_find_body import measured_warmup                            # noqa: E402
from scripts.atari_play import make                                           # noqa: E402
from scripts.atari_taught import RAM_BODY, fit_ram_to_screen, screen_xy       # noqa: E402

OUT = Path("data/atari/appearance_presence.json")


def _patch(frame, blob, r: int = 4):
    x, y = int(blob[0]), int(blob[1])
    H, W = frame.shape[:2]
    p = frame[max(0, y - r):min(H, y + r), max(0, x - r):min(W, x + r)]
    return p.reshape(-1, 3) if p.size else np.zeros((1, 3), frame.dtype)


def d_mean(frame, blob):
    """The current descriptor: mean colour, quantised. The one that scatters."""
    c = _patch(frame, blob).mean(axis=0)
    return np.array([c[0] // 32, c[1] // 32, c[2] // 32, np.log2(max(blob[2], 1))], np.float32)


def d_dominant(frame, blob):
    """The most common colour in the patch, not the average of sprite and background."""
    px = _patch(frame, blob)
    q = (px.astype(np.int32) // 32)
    keys = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
    k = collections.Counter(keys.tolist()).most_common(1)[0][0]
    return np.array([k // 64, (k // 8) % 8, k % 8, np.log2(max(blob[2], 1))], np.float32)


def d_hue(frame, blob):
    """Hue of the dominant colour, which brightness changes do not move."""
    px = _patch(frame, blob).astype(np.float32)
    q = (px // 32).astype(np.int32)
    keys = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
    k = collections.Counter(keys.tolist()).most_common(1)[0][0]
    r, g, b = (k // 64) * 32.0, ((k // 8) % 8) * 32.0, (k % 8) * 32.0
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 1e-6:
        h = 0.0
    elif mx == r:
        h = (60 * (g - b) / (mx - mn)) % 360
    elif mx == g:
        h = 60 * (2 + (b - r) / (mx - mn))
    else:
        h = 60 * (4 + (r - g) / (mx - mn))
    return np.array([h // 30, (mx - mn) // 64, np.log2(max(blob[2], 1))], np.float32)


class Buckets:
    """Exact keys, or nearest-match within a radius DERIVED from the descriptors themselves."""

    def __init__(self, nearest: bool):
        self.nearest = nearest
        self.keys: list = []
        self.radius = None

    def calibrate(self, samples) -> None:
        """Half the median nearest-neighbour distance among distinct descriptors. Derived, not chosen."""
        if not self.nearest or len(samples) < 8:
            self.radius = 0.0
            return
        S = np.unique(np.array(samples, np.float32), axis=0)
        if len(S) < 3:
            self.radius = 0.0
            return
        D = np.linalg.norm(S[:, None, :] - S[None, :, :], axis=2)
        np.fill_diagonal(D, np.inf)
        self.radius = float(np.median(D.min(axis=1)) / 2.0)

    def key(self, v) -> int:
        v = np.asarray(v, np.float32)
        if not self.nearest:
            t = tuple(v.tolist())
            if t not in self.keys:
                self.keys.append(t)
            return self.keys.index(t)
        if self.keys:
            K = np.array(self.keys, np.float32)
            d = np.linalg.norm(K - v, axis=1)
            j = int(np.argmin(d))
            if d[j] <= (self.radius or 0.0):
                return j
        self.keys.append(tuple(v.tolist()))
        return len(self.keys) - 1


def run(desc, nearest: bool, steps: int = 600, seed: int = 3):
    env = make()
    warm = measured_warmup(env, env.action_space.n)
    fit, agree = fit_ram_to_screen(env, warm, seed=seed)
    n_a = env.action_space.n
    env.close()
    env = make()
    obs, _ = env.reset(seed=seed)
    for _ in range(warm):
        obs, *_ = env.step(0)
    rng = np.random.default_rng(seed)
    buf = []
    for _ in range(40):
        obs, *_ = env.step(int(rng.integers(0, n_a)))
        buf.append(obs)
    bg = np.median(np.array(buf, dtype=np.int16), axis=0)

    B = Buckets(nearest)
    if nearest:                                  # a short calibration pass, then the radius is fixed
        samp = []
        for _ in range(30):
            obs, *_ = env.step(int(rng.integers(0, n_a)))
            for b in blobs(sprite_mask(obs, bg)):
                samp.append(desc(obs, b))
        B.calibrate(samp)

    tr = SpriteTracker(max_jump=22.0)
    look: dict = {}
    mem: dict = collections.defaultdict(list)
    present: dict = collections.defaultdict(set)
    hist: dict = collections.defaultdict(dict)
    truth = []
    for t in range(steps):
        a = int(rng.integers(0, n_a))
        for _ in range(3):
            obs, _r, term, trunc, _i = env.step(a)
            if term or trunc:
                obs, _ = env.reset()
                for _ in range(warm):
                    obs, *_ = env.step(0)
        bl = blobs(sprite_mask(obs, bg))
        before = {k.id: k.pos.copy() for k in tr.tracks}
        tr.step(bl, action=a, moving_only=False)
        for k in tr.tracks:
            if k.id not in look:
                j = (int(np.argmin([np.hypot(b[0] - k.pos[0], b[1] - k.pos[1]) for b in bl]))
                     if bl else None)
                look[k.id] = B.key(desc(obs, bl[j])) if j is not None else -1
            d = k.pos - before.get(k.id, k.pos)
            if abs(d[0]) > 0.5 or abs(d[1]) > 0.5:
                mem[look[k.id]].append((a, float(d[0]), float(d[1])))
            present[look[k.id]].add(t)
            hist[look[k.id]][t] = k.pos.copy()
        truth.append(screen_xy(env.unwrapped.ale.getRAM(), fit, RAM_BODY))
    env.close()

    T = np.array(truth)
    scored = [(b, intention_momentum(ev)) for b, ev in mem.items() if len(ev) >= 12]
    if not scored:
        return None
    chosen = max(scored, key=lambda x: x[1])[0]

    def stats(b):
        ts = sorted(hist.get(b, {}))
        if not ts:
            return 0.0, 0.0, 0.0
        P = np.array([hist[b][t] for t in ts])
        hit = np.hypot(P[:, 0] - T[ts, 0], P[:, 1] - T[ts, 1]) < 8.0
        pres = len(ts) / steps
        return pres, float(hit.mean()), pres * float(hit.mean())

    pres, cond, overall = stats(chosen)
    alls = [stats(b) for b, _s in scored]
    return {"buckets": len(B.keys), "radius": B.radius, "scoreable": len(scored),
            "presence": pres, "on_body_given_present": cond, "on_body_overall": overall,
            "chance_overall": float(np.mean([x[2] for x in alls]))}


def main() -> None:
    variants = [("mean RGB, exact key (current)", d_mean, False),
                ("dominant colour, exact key", d_dominant, False),
                ("hue of dominant, exact key", d_hue, False),
                ("dominant colour, NEAREST match", d_dominant, True),
                ("hue of dominant, NEAREST match", d_hue, True)]
    print(f"{'descriptor':<34}{'buckets':>9}{'presence':>10}{'|present':>10}"
          f"{'OVERALL':>9}{'chance':>8}")
    rows = {}
    for name, desc, near in variants:
        r = run(desc, near)
        if r is None:
            print(f"{name:<34}{'no bucket reached 12 samples':>46}")
            continue
        rows[name] = r
        print(f"{name:<34}{r['buckets']:>9}{r['presence']:>9.1%}"
              f"{r['on_body_given_present']:>10.1%}{r['on_body_overall']:>9.1%}"
              f"{r['chance_overall']:>8.1%}", flush=True)

    if rows:
        best = max(rows, key=lambda k: rows[k]["on_body_overall"])
        cur = rows.get("mean RGB, exact key (current)")
        print(f"\n-> best unconditional on-body: {best} at {rows[best]['on_body_overall']:.1%}")
        if cur:
            print(f"-> against the current descriptor's {cur['on_body_overall']:.1%} "
                  f"(presence {cur['presence']:.1%} x accuracy {cur['on_body_given_present']:.1%})")
        print(f"-> and against a bucket chosen at random: {rows[best]['chance_overall']:.1%}")
        print("\n   The executor needed ~100% and got no steering at 57%. The unconditional figure is")
        print("   what it experiences, so that is the one to move.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
