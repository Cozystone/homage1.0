# -*- coding: utf-8 -*-
"""Predict the turn, using a maze nobody supplied. Registered target: beat 2.194 px AT TURNS.

    python scripts/atari_turn_prediction.py

The previous rung measured where prediction breaks. Constant velocity solves corridors outright —
median error 0.000 px — and is 4.5x worse at a junction (2.194 against 0.489 overall). At a junction
`stay` even beats it (1.577), because extrapolating a velocity that is about to rotate overshoots
further than assuming none.

That gap is the whole of what a world model has to earn, and the target was registered before this
was built: **beat 2.194 px at turns**. Corridor performance does not count. Constant velocity already
has corridors, and crediting it there is precisely the mistake the previous rung was arranged to
prevent.

THE MAZE IS NOT SUPPLIED. 75% of the screen never held a sprite across a rollout, so a wall is simply
somewhere nothing has ever been. That map comes from the same background subtraction already in use,
and nothing about Ms. Pac-Man's layout is written down anywhere here.

THE PREDICTOR HAS NO FREE PARAMETER, which matters because a tunable one could be fitted to the
target after seeing it:

    if the cell straight ahead is traversable   -> keep going (constant velocity)
    else                                        -> take the legal direction closest to the current
                                                   heading; ties go to neither, so it predicts stay

Most turns in this game happen because straight ahead is a wall, so a map alone should account for a
large part of the gap without anything being learned about ghosts specifically.

TWO CONTROLS, because a wall map that helps might be helping for the wrong reason:

    shuffled map   the same number of traversable cells, scattered at random. If that scores as well,
                   the gain came from the RULE (occasionally predicting a turn) and not from knowing
                   WHERE the walls are.
    stay           the incumbent champion at turns, which anything claiming to model the maze must
                   also beat -- beating only constant velocity would be beating the weaker rival.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.atari_predict_ghosts import collect   # noqa: E402

OUT = Path("data/atari/turn_prediction.json")
TARGET = 2.194          # registered before this file existed: constant velocity's error at turns
STAY_AT_TURN = 1.577    # and the stronger incumbent it must also beat

DIRS = np.array([(1, 0), (-1, 0), (0, 1), (0, -1),
                 (1, 1), (1, -1), (-1, 1), (-1, -1)], dtype=float)


def traversable_map(ever: np.ndarray, grow: int = 3) -> np.ndarray:
    """Where a sprite has ever been, thickened. Thickened because a blob CENTROID traces a thinner
    path than the sprite occupies, so the raw mask under-reports the corridor by a few pixels and a
    predictor would then call legal moves illegal."""
    import cv2
    k = np.ones((grow * 2 + 1, grow * 2 + 1), np.uint8)
    return cv2.dilate(ever.astype(np.uint8), k).astype(bool)


def legal(tm: np.ndarray, p: np.ndarray, step: float) -> list[np.ndarray]:
    """Unit directions from p whose next cell is traversable."""
    out = []
    H, W = tm.shape
    for d in DIRS:
        n = d / np.linalg.norm(d)
        q = p + n * step
        x, y = int(round(q[0])), int(round(q[1]))
        if 0 <= y < H and 0 <= x < W and tm[y, x]:
            out.append(n)
    return out


def wall_aware(hist: np.ndarray, tm: np.ndarray) -> np.ndarray:
    """No free parameter. Straight on if the way is open; otherwise the smallest legal turn."""
    p1, p0 = hist[-1], hist[-2]
    v = p1 - p0
    sp = float(np.linalg.norm(v))
    if sp < 0.5:
        return p1
    H, W = tm.shape
    ahead = p1 + v
    ax, ay = int(round(ahead[0])), int(round(ahead[1]))
    if 0 <= ay < H and 0 <= ax < W and tm[ay, ax]:
        return ahead
    opts = legal(tm, p1, sp)
    if not opts:
        return p1
    heading = v / sp
    dots = [float(o @ heading) for o in opts]
    best = max(dots)
    winners = [o for o, d in zip(opts, dots) if d >= best - 1e-9]
    if len(winners) != 1:
        return p1                       # a tie is not an answer; predict no motion
    return p1 + winners[0] * sp


def main() -> None:
    tracks, ever = collect()
    usable = {t: np.array(v) for t, v in tracks.items() if len(v) >= 12}
    tm = traversable_map(ever)
    print(f"tracks {len(usable)}   traversable after thickening: {tm.mean():.1%} of the screen")

    rng = np.random.default_rng(0)
    shuf = np.zeros_like(tm).ravel()
    shuf[:tm.sum()] = True
    rng.shuffle(shuf)
    shuf = shuf.reshape(tm.shape)

    err = {k: [] for k in ("constant_velocity", "stay", "wall_aware", "shuffled_map")}
    n_turn = 0
    for v in usable.values():
        for i in range(3, len(v) - 1):
            hist, truth = v[:i + 1], v[i + 1]
            pv = v[i] - v[i - 1]
            nv = truth - v[i]
            if float(np.linalg.norm(nv - pv)) <= 1.0:
                continue                       # not a turn; the registered target is turns only
            n_turn += 1
            err["constant_velocity"].append(float(np.linalg.norm((v[i] + pv) - truth)))
            err["stay"].append(float(np.linalg.norm(v[i] - truth)))
            err["wall_aware"].append(float(np.linalg.norm(wall_aware(hist, tm) - truth)))
            err["shuffled_map"].append(float(np.linalg.norm(wall_aware(hist, shuf) - truth)))

    print(f"\n{n_turn} turns evaluated. Registered target: beat {TARGET} px (constant velocity),")
    print(f"and beat {STAY_AT_TURN} px (stay), which is the stronger incumbent.\n")
    print(f"{'predictor':20}{'mean err at turns':>20}{'vs target':>12}")
    res = {}
    for k, v_ in err.items():
        m = float(np.mean(v_)) if v_ else float("nan")
        res[k] = m
        print(f"{k:20}{m:>20.3f}{TARGET - m:>+12.3f}")

    wa = res["wall_aware"]
    beats_cv = wa < TARGET
    beats_stay = wa < STAY_AT_TURN
    map_matters = wa < res["shuffled_map"]
    print(f"\n-> beats constant velocity ({TARGET}): {beats_cv}")
    print(f"-> beats stay ({STAY_AT_TURN}):            {beats_stay}")
    print(f"-> and the MAP is doing it, not the rule: {map_matters} "
          f"(shuffled map {res['shuffled_map']:.3f})")
    verdict = ("PASSES — a maze read off the pixels predicts turns better than either incumbent"
               if (beats_cv and beats_stay and map_matters) else
               "FAILS the registered target")
    print(f"\n{verdict}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"turns": n_turn, "target_cv": TARGET, "target_stay": STAY_AT_TURN,
                               "errors": res, "beats_cv": bool(beats_cv),
                               "beats_stay": bool(beats_stay), "map_matters": bool(map_matters),
                               "verdict": verdict}, indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
