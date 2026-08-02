# -*- coding: utf-8 -*-
"""Score the two object-discovery rules on Atari, against ground truth found in RAM by measurement.

    python scripts/atari_object_score.py

The object track was parked because CARLA street-view could not return a verdict: objects were
eleven pixels, 71% below the smallest unit a grouping could emit, and the only ground truth needed
semantic annotation. Atari cleared the pre-flight 4/4 -- 28px objects, six per frame, and RAM that
correlates 0.64 with where the motion is against a shuffled-time null of 0.11.

GROUND TRUTH IS DISCOVERED, NOT LOOKED UP. Ms. Pac-Man's RAM map is published, and using it would
make this a test of the internet's table rather than of anything here. Instead a byte pair is
accepted as an object's coordinates only if it BEHAVES like coordinates:

    in range        values stay inside the screen the whole rollout
    smooth          frame-to-frame steps are small; a counter or a score digit jumps
    grounded        the pixels at (x, y) are actually part of a moving blob, more often than the
                    same trajectory shifted in time would be

The third is the one that makes it ground truth rather than a plausible-looking series, and it comes
with its own control.

WHAT IS BEING SCORED. For each frame, each rule proposes regions. A region is CREDITED with an object
when it contains that object's RAM position, and the two failure modes are counted separately because
they are different mistakes: MISSED (no region contains the object) and MERGED (one region contains
two or more objects, so the rule found a blob where the world has two things).

THE CONTROL IS THE SAME SHAPE MOVED. Every region is re-scored after being dropped elsewhere in the
frame at random. A rule that credits objects no more often than its own shape does by accident has
found nothing, which is exactly what common fate did on CARLA (0.782 against a 0.802 control) and is
the outcome this is willing to report again.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path("data/atari/object_score.json")
W, H = 160, 210


def rollout(n: int = 600, seed: int = 0):
    import ale_py  # noqa: F401
    import gymnasium as gym
    env = gym.make("ALE/MsPacman-v5", obs_type="rgb", frameskip=4, repeat_action_probability=0.0)
    obs, _ = env.reset(seed=seed)
    rng = np.random.default_rng(seed)
    ale = env.unwrapped.ale
    frames, rams = [obs], [ale.getRAM().copy()]
    for _ in range(n - 1):
        obs, _r, term, trunc, _i = env.step(int(rng.integers(0, env.action_space.n)))
        frames.append(obs)
        rams.append(ale.getRAM().copy())
        if term or trunc:
            obs, _ = env.reset()
    env.close()
    return np.array(frames), np.array(rams, dtype=np.int16)


def moving_mask(frames: np.ndarray) -> np.ndarray:
    import cv2
    g = np.array([cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in frames]).astype(np.int16)
    return np.abs(g[1:] - g[:-1]) > 12


def find_coordinate_bytes(rams: np.ndarray, mv: np.ndarray, rng) -> list[tuple[int, int, float]]:
    """Byte pairs that BEHAVE like screen coordinates. Nothing is read from an offset table."""
    R = rams[1:]
    n_by = R.shape[1]
    cand_x = [b for b in range(n_by)
              if R[:, b].min() >= 0 and R[:, b].max() <= W + 8 and R[:, b].std() > 2
              and np.median(np.abs(np.diff(R[:, b]))) <= 6]
    cand_y = [b for b in range(n_by)
              if R[:, b].min() >= 0 and R[:, b].max() <= H + 8 and R[:, b].std() > 2
              and np.median(np.abs(np.diff(R[:, b]))) <= 6]

    def grounded(bx: int, by: int) -> float:
        xs = np.clip(R[:, bx], 0, W - 1)
        ys = np.clip(R[:, by], 0, H - 1)
        hit = np.mean([mv[t, ys[t], xs[t]] for t in range(len(R))])
        return float(hit)

    out = []
    for bx in cand_x:
        for by in cand_y:
            if bx == by:
                continue
            g = grounded(bx, by)
            if g < 0.05:
                continue
            # control: the SAME trajectory shifted in time — same statistics, wrong moment
            sh = []
            for _ in range(20):
                k = int(rng.integers(5, len(R) - 5))
                xs = np.clip(np.roll(R[:, bx], k), 0, W - 1)
                ys = np.clip(np.roll(R[:, by], k), 0, H - 1)
                sh.append(np.mean([mv[t, ys[t], xs[t]] for t in range(len(R))]))
            if g > np.percentile(sh, 95):
                out.append((bx, by, g))
    out.sort(key=lambda t: -t[2])
    # keep coordinate pairs that are not the same object twice
    kept: list[tuple[int, int, float]] = []
    for bx, by, g in out:
        if any(bx == kx or by == ky for kx, ky, _ in kept):
            continue
        kept.append((bx, by, g))
        if len(kept) >= 6:
            break
    return kept


def score_regions(regions, objs: list[tuple[int, int]], shape, rng) -> dict:
    """Credited / missed / merged, plus the same regions dropped elsewhere at random."""
    if not regions:
        return {"credited": 0, "missed": len(objs), "merged": 0, "control": 0.0, "n_regions": 0}
    Hh, Ww = shape
    credited = merged = 0
    covered = set()
    for r in regions:
        inside = [i for i, (x, y) in enumerate(objs)
                  if 0 <= y < Hh and 0 <= x < Ww and r.mask[y, x]]
        if len(inside) == 1:
            credited += 1
            covered.add(inside[0])
        elif len(inside) > 1:
            merged += 1
            covered.update(inside)
    ctrl = 0
    for r in regions:
        ys, xs = np.where(r.mask)
        if not len(ys):
            continue
        dy = int(rng.integers(-Hh // 3, Hh // 3))
        dx = int(rng.integers(-Ww // 3, Ww // 3))
        m = np.zeros_like(r.mask)
        yy, xx = np.clip(ys + dy, 0, Hh - 1), np.clip(xs + dx, 0, Ww - 1)
        m[yy, xx] = True
        if sum(1 for x, y in objs if 0 <= y < Hh and 0 <= x < Ww and m[y, x]) == 1:
            ctrl += 1
    return {"credited": credited, "missed": len(objs) - len(covered), "merged": merged,
            "control": ctrl, "n_regions": len(regions)}


def main() -> None:
    from packages.perception.coherence import things, things_tracked

    frames, rams = rollout()
    mv = moving_mask(frames)
    rng = np.random.default_rng(0)
    coords = find_coordinate_bytes(rams, mv, rng)
    print(f"RAM byte pairs that BEHAVE like coordinates (no offset table used): {len(coords)}")
    for bx, by, g in coords:
        print(f"  bytes ({bx:>3}, {by:>3})   on a moving pixel {g:.1%} of frames")
    if not coords:
        sys.exit("no coordinate-like byte pair survived the grounding control — cannot score")

    WIN = 40
    tot = {"coherence": [], "tracked": []}
    for start in range(0, min(len(frames) - WIN, 400), WIN):
        win = list(frames[start:start + WIN])
        mid = start + WIN // 2
        objs = [(int(np.clip(rams[mid, bx], 0, W - 1)), int(np.clip(rams[mid, by], 0, H - 1)))
                for bx, by, _ in coords]
        for name, fn in (("coherence", lambda w: things(w, cell=7, link=0.45, min_cells=2)),
                         ("tracked", lambda w: things_tracked(w, cell=7, min_size=3,
                                                              neighbourhood=0.15, link=0.55))):
            regs = [r for r in fn(win) if 0.0002 < r.area_frac < 0.4]
            tot[name].append(score_regions(regs, objs, (H, W), rng))

    print(f"\n{len(tot['coherence'])} windows of {WIN} frames, {len(coords)} objects each\n")
    print(f"{'rule':14}{'credited':>10}{'control':>9}{'lift':>8}{'missed':>9}{'merged':>9}{'regions':>9}")
    result = {}
    for name, rows in tot.items():
        c = sum(r["credited"] for r in rows)
        k = sum(r["control"] for r in rows)
        m = sum(r["missed"] for r in rows)
        g = sum(r["merged"] for r in rows)
        n = sum(r["n_regions"] for r in rows)
        print(f"{name:14}{c:>10}{k:>9}{c - k:>+8}{m:>9}{g:>9}{n:>9}")
        result[name] = {"credited": c, "control": k, "lift": c - k, "missed": m,
                        "merged": g, "regions": n}

    best = max(result, key=lambda k_: result[k_]["lift"])
    print(f"\n-> {best} leads on lift over its own shifted-shape control ({result[best]['lift']:+d})")
    print("   CARLA for comparison: purity 0.782 against a 0.802 control — no lift at all")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"game": "ALE/MsPacman-v5", "windows": len(tot["coherence"]),
                               "coordinate_bytes": [[int(a), int(b), float(g)] for a, b, g in coords],
                               "scores": result}, indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
