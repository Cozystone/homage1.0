# -*- coding: utf-8 -*-
"""Predict where the other things will be. Object-hood run forward.

    python scripts/atari_predict_ghosts.py

Owner: 4D 월드모델이라도 꼭 3D만 예측가능한건 아니잖아. 2D 게임을 띄운 3D 컴퓨터를 상상할수도 있고.

Right, and the narrower statement is the useful one: what a 4D world model contributes is not physics,
it is PREDICTION OVER SPACETIME. A maze on a screen is a world with a time axis. The physics does not
carry over -- no momentum, no continuous dynamics -- and the machinery does.

AND IT IS THE SAME QUESTION AS OBJECTHOOD. Today's definition was "a thing is the smallest unit whose
future its own past accounts for". Measuring how well a track predicts its own next position IS that
criterion, evaluated forward instead of used to group. So this is not a new organ; it is the same
statement asked in the tense a world model needs.

WHAT WOULD BE CHEATING. Ms. Pac-Man ghosts move at constant speed along corridors, so constant
velocity will already be very good and it would be easy to report that as success. The question is
therefore not "can anything predict them" but WHERE constant velocity fails and whether anything does
better THERE. A ghost's trajectory is only interesting at a junction, and a predictor that matches
the baseline overall while failing at every turn has learned the corridor, not the ghost.

THE PRE-FLIGHT RUNS FIRST, as it now always does:
    D  are there enough tracks, long enough, to fit and test on
    R  is the displacement being predicted larger than the measurement noise on it
    X  does the instrument separate a good predictor from a bad one -- checked by handing it a
       deliberately bad one and requiring it to lose
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.atari_babble import blobs, match, sprite_mask                # noqa: E402
from scripts.atari_find_body import measured_warmup                       # noqa: E402

OUT = Path("data/atari/ghost_prediction.json")
GAME = "ALE/MsPacman-v5"


def collect(steps: int = 1200, seed: int = 0):
    """Blob tracks and the wall map, both from pixels."""
    import ale_py  # noqa: F401
    import gymnasium as gym

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

    tracks: dict[int, list[tuple[float, float]]] = defaultdict(list)
    ever_moved = np.zeros(bg.shape[:2], bool)
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
        ever_moved |= m
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
    # THE MAZE, learned rather than given: a wall is where nothing ever appeared.
    return tracks, ever_moved


def predictors(hist: np.ndarray) -> dict[str, np.ndarray]:
    """Each takes the track's own past and returns the next position. Own past only."""
    p1, p0 = hist[-1], hist[-2]
    v = p1 - p0
    out = {"stay": p1, "constant_velocity": p1 + v}
    if len(hist) >= 3:
        a = (hist[-1] - hist[-2]) - (hist[-2] - hist[-3])
        out["constant_accel"] = p1 + v + a
    out["reversed"] = p1 - v                 # the DELIBERATELY BAD one; must lose
    return out


def main() -> None:
    tracks, ever = collect()
    usable = {t: np.array(v) for t, v in tracks.items() if len(v) >= 12}
    lens = [len(v) for v in usable.values()]
    print(f"tracks: {len(usable)} with >=12 samples   median length {np.median(lens):.0f}")

    steps = []
    for v in usable.values():
        d = np.linalg.norm(np.diff(v, axis=0), axis=1)
        steps += list(d[d > 0])
    S = np.array(steps) if steps else np.array([0.0])
    print(f"D  displacements to predict: {len(S)}   median {np.median(S):.2f} px")
    print(f"R  vs blob-centroid noise (~0.5 px): {np.median(S) / 0.5:.1f}x")
    print(f"   walls learned from pixels: {100 * (1 - ever.mean()):.0f}% of the screen never held a sprite")
    if len(usable) < 8 or np.median(S) < 1.0:
        sys.exit("pre-flight fails: too few tracks or displacements at the noise floor")

    err: dict[str, list] = defaultdict(list)
    at_turn: dict[str, list] = defaultdict(list)
    for v in usable.values():
        for i in range(3, len(v) - 1):
            hist, truth = v[:i + 1], v[i + 1]
            prev_v = v[i] - v[i - 1]
            next_v = truth - v[i]
            turning = float(np.linalg.norm(next_v - prev_v)) > 1.0
            for name, pred in predictors(hist).items():
                e = float(np.linalg.norm(pred - truth))
                err[name].append(e)
                if turning:
                    at_turn[name].append(e)

    print(f"\n{len(err['stay'])} predictions, {len(at_turn['stay'])} of them at a turn\n")
    print(f"{'predictor':22}{'mean err':>10}{'median':>9}{'at a turn':>12}")
    rows = {}
    for name in ("stay", "constant_velocity", "constant_accel", "reversed"):
        if name not in err:
            continue
        e = np.array(err[name])
        tt = np.array(at_turn[name]) if at_turn[name] else np.array([np.nan])
        rows[name] = {"mean": float(e.mean()), "median": float(np.median(e)),
                      "at_turn": float(np.nanmean(tt))}
        print(f"{name:22}{e.mean():>10.3f}{np.median(e):>9.3f}{np.nanmean(tt):>12.3f}")

    cv, bad = rows["constant_velocity"]["mean"], rows["reversed"]["mean"]
    print(f"\nX  the instrument separates good from bad: constant_velocity {cv:.3f} vs "
          f"reversed {bad:.3f} -> {'YES' if cv < bad * 0.7 else 'NO — it cannot tell them apart'}")

    best_flat = min(rows, key=lambda k: rows[k]["mean"])
    best_turn = min((k for k in rows if k != "reversed"), key=lambda k: rows[k]["at_turn"])
    print(f"\n-> overall the best of these is `{best_flat}`")
    print(f"-> AT A TURN the best is `{best_turn}` at {rows[best_turn]['at_turn']:.3f} px, "
          f"against {rows['constant_velocity']['at_turn']:.3f} for constant velocity")
    gap = rows["constant_velocity"]["at_turn"] / max(rows["constant_velocity"]["mean"], 1e-9)
    print(f"   constant velocity is {gap:.1f}x worse at a turn than overall — that gap is the whole "
          f"of what a world model would have to earn")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"game": GAME, "tracks": len(usable),
                               "median_track_len": float(np.median(lens)),
                               "median_step_px": float(np.median(S)),
                               "wall_fraction": float(1 - ever.mean()),
                               "predictions": len(err["stay"]),
                               "turns": len(at_turn["stay"]),
                               "predictors": rows,
                               "turn_penalty_x": float(gap)}, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
