# -*- coding: utf-8 -*-
"""A walkable map read off the pellets, and the turn prediction redone against it.

    python scripts/atari_pellet_map.py

The previous rung failed and named its own cause: `wall_aware` dilated a blob-centroid path by 3px to
recover the corridor, which pushed traversable area from 25% to 42% of the screen, so the way ahead
was nearly always open and the predictor was constant velocity wearing a maze. Lowering the dilation
would have passed the target and would have been fitting a parameter to the thing it must clear.

PELLETS ARE THE RIGHT SIGNAL AND THEY WERE ALREADY IN THE DATA. A pellet sits exactly where the game
permits travel, is small, is stationary, and DISAPPEARS PERMANENTLY when eaten. That last property is
what identifies them without anyone saying what a pellet is: a thing that was there, went, and never
came back. Ghosts return, Pac-Man returns, the fruit returns; a pellet does not.

So the map is: the places something vanished from for good.

THE ONE FREE PARAMETER IS DERIVED, NOT PICKED. Pellets are spaced along a corridor, so linking
neighbouring ones needs a radius — and that radius is MEASURED as half the median nearest-neighbour
spacing between pellets. Adjacent pellets then join and nothing else does. Choosing 3 was what broke
the last rung; this number is read from the pellets themselves.

THE TARGET IS UNCHANGED AND WAS REGISTERED TWO RUNGS AGO: beat 2.194 px at turns (constant velocity)
and 1.577 px (stay, the stronger incumbent). Corridors do not count.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.atari_babble import blobs, match, sprite_mask     # noqa: E402
from scripts.atari_find_body import measured_warmup            # noqa: E402
from scripts.atari_turn_prediction import STAY_AT_TURN, TARGET, wall_aware   # noqa: E402

OUT = Path("data/atari/pellet_map.json")
GAME = "ALE/MsPacman-v5"


def gather(steps: int = 1400, seed: int = 0):
    """Frames, tracks, and the per-pixel record of what was present when."""
    import ale_py  # noqa: F401
    import gymnasium as gym
    from collections import defaultdict

    env = gym.make(GAME, obs_type="rgb", frameskip=1, repeat_action_probability=0.0)
    n_a = env.action_space.n
    warm = measured_warmup(env, n_a)
    env.reset(seed=seed)
    for _ in range(warm):
        env.step(0)
    rng = np.random.default_rng(seed)
    buf = []
    obs = env.unwrapped.ale.getScreenRGB()
    for _ in range(150):
        obs, *_ = env.step(int(rng.integers(0, n_a)))
        buf.append(obs)
    bg = np.median(np.array(buf, dtype=np.int16), axis=0)

    masks = []
    raw = []
    tracks: dict[int, list] = defaultdict(list)
    prev = blobs(sprite_mask(obs, bg))
    ids = list(range(len(prev)))
    nxt = len(prev)
    for _t in range(steps):
        a = int(rng.integers(0, n_a))
        for _ in range(2):
            obs, _r, term, trunc, _i = env.step(a)
            if term or trunc:
                obs, _ = env.reset()
                for _ in range(warm):
                    obs, *_ = env.step(0)
        m = sprite_mask(obs, bg)
        masks.append(m)
        raw.append(obs.copy())
        cur = blobs(m)
        new_ids: list = [None] * len(cur)
        for i0, i1, _dx, _dy in match(prev, cur, max_jump=10.0):
            new_ids[i1] = ids[i0]
        for k in range(len(cur)):
            if new_ids[k] is None:
                new_ids[k] = nxt
                nxt += 1
            tracks[new_ids[k]].append((cur[k][0], cur[k][1]))
        prev, ids = cur, new_ids
    env.close()
    return np.array(masks), tracks, np.array(raw, dtype=np.int16)


def pellets_from(raw: np.ndarray, tail: int = 150) -> np.ndarray:
    """Places something was, and then permanently was not — read from RAW FRAMES, not the mask.

    THE FIRST VERSION LOOKED FOR PELLETS INSIDE BACKGROUND SUBTRACTION, which removes them by
    construction: a pellet is stationary, so it sits in the rollout median and is subtracted away. It
    found 74 pixels, the map covered 0.7% of the screen, and the predictor degenerated to `stay` with
    noise (1.601 against stay's 1.567). Same error as the morning's "the background median included
    the body", committed again in the afternoon.

    A pellet is still defined by BEHAVIOUR and not by looks: bright early, gone late, never back.
    Everything else on this screen comes back. Only the source changed."""
    early = raw[:tail].mean(axis=0)
    late = raw[-tail:].mean(axis=0)
    vanished = (np.abs(early - late).sum(axis=2) > 60) & (early.sum(axis=2) > late.sum(axis=2))
    return vanished


def walkable_from_pellets(pel: np.ndarray) -> tuple[np.ndarray, float]:
    """Link neighbouring pellets, with the radius MEASURED as half their typical spacing."""
    import cv2
    ys, xs = np.where(pel)
    if len(ys) < 20:
        return pel.copy(), 0.0
    pts = np.stack([xs, ys], 1).astype(float)
    sample = pts[np.random.default_rng(0).choice(len(pts), min(400, len(pts)), replace=False)]
    d = np.linalg.norm(sample[:, None, :] - sample[None, :, :], axis=2)
    np.fill_diagonal(d, np.inf)
    spacing = float(np.median(d.min(axis=1)))
    r = max(1, int(round(spacing / 2)))
    k = np.ones((r * 2 + 1, r * 2 + 1), np.uint8)
    return cv2.dilate(pel.astype(np.uint8), k).astype(bool), spacing


def main() -> None:
    masks, tracks, raw = gather()
    pel = pellets_from(raw)
    walk, spacing = walkable_from_pellets(pel)
    print(f"pellets found by behaviour (present early, gone late, never back): {int(pel.sum())} px")
    print(f"their median nearest-neighbour spacing: {spacing:.1f} px "
          f"-> linking radius {max(1, int(round(spacing / 2)))} px, DERIVED not chosen")
    print(f"walkable map: {walk.mean():.1%} of the screen "
          f"(the failed rung's centroid+3px map was 42.3%)")

    usable = {t: np.array(v) for t, v in tracks.items() if len(v) >= 12}
    err = {k: [] for k in ("constant_velocity", "stay", "pellet_map")}
    n = 0
    for v in usable.values():
        for i in range(3, len(v) - 1):
            hist, truth = v[:i + 1], v[i + 1]
            pv = v[i] - v[i - 1]
            if float(np.linalg.norm((truth - v[i]) - pv)) <= 1.0:
                continue
            n += 1
            err["constant_velocity"].append(float(np.linalg.norm((v[i] + pv) - truth)))
            err["stay"].append(float(np.linalg.norm(v[i] - truth)))
            err["pellet_map"].append(float(np.linalg.norm(wall_aware(hist, walk) - truth)))

    print(f"\n{n} turns. Target registered two rungs ago: beat {TARGET} (constant velocity) "
          f"and {STAY_AT_TURN} (stay).\n")
    print(f"{'predictor':20}{'mean err at turns':>20}")
    res = {}
    for k, v_ in err.items():
        m = float(np.mean(v_)) if v_ else float("nan")
        res[k] = m
        print(f"{k:20}{m:>20.3f}")

    pm = res["pellet_map"]
    beats_cv, beats_stay = pm < TARGET, pm < STAY_AT_TURN
    print(f"\n-> beats constant velocity ({TARGET}): {beats_cv}")
    print(f"-> beats stay ({STAY_AT_TURN}):            {beats_stay}")
    verdict = ("PASSES — a map read off the pellets predicts turns better than both incumbents"
               if beats_cv and beats_stay else "FAILS the registered target")
    print(f"\n{verdict}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"pellet_px": int(pel.sum()), "spacing": spacing,
                               "walkable_fraction": float(walk.mean()),
                               "turns": n, "errors": res,
                               "beats_cv": bool(beats_cv), "beats_stay": bool(beats_stay),
                               "verdict": verdict}, indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
