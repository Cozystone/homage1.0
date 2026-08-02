# -*- coding: utf-8 -*-
"""Which of the moving things is ME? Found by asking which one answers the button.

    python scripts/atari_find_body.py

The babble scored 2/8 and the obstacle was named rather than guessed: five blobs move on any trial —
the body and four ghosts — and averaging over them buries the body's signal in four independent
walkers. Even NOOP came out as a direction.

THE BODY IS THE BLOB WHOSE MOTION THE COMMAND PREDICTS. A ghost walks its own walk whatever was
pressed, so knowing the action tells you nothing about where it went. The body's displacement is a
function of the action. That is a measurable quantity per track — how much the command reduces
uncertainty about the displacement — and it needs no one to say which sprite is Pac-Man.

It is also the efference-copy question in a new body. In City Sample the camera WAS the body, so
every command moved the whole image and the question never arose. A body that is one object among
many in a fixed world has to find itself first, and that is the case a humanoid will be in.

THE CONTROL IS THE OTHER BLOBS. The winning track has to beat the ghosts, not a threshold — if the
body's command-prediction score is no better than a ghost's, nothing has been identified. And the
whole screen is read: background subtraction is a temporal contrast applied to every pixel, not a
crop or a region anyone chose.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.atari_babble import blobs, match, sprite_mask   # noqa: E402

OUT = Path("data/atari/body_identity.json")
GAME = "ALE/MsPacman-v5"


def measured_warmup(env, n_actions: int) -> int:
    """Frames of NOOP before the machine answers a button at all. Measured, never assumed."""
    for probe in range(0, 1400, 100):
        states = set()
        for a in range(n_actions):
            env.reset(seed=0)
            for _ in range(probe):
                env.step(0)
            for _ in range(30):
                env.step(a)
            states.add(env.unwrapped.ale.getRAM().tobytes())
        if len(states) >= max(4, n_actions // 3):
            return probe
    return 0


def command_prediction(rows: list[tuple[int, float, float]]) -> float:
    """How much knowing the action narrows the blob's displacement direction. 0 = not at all.

    The direction is binned to eight compass cells. Without the command, the distribution over cells
    has some spread; conditioned on the command it should collapse for the body and not budge for a
    ghost. The score is the drop in normalised entropy, which is bounded in [0, 1] and comparable
    across tracks with different amounts of data."""
    def ent(cells: list[tuple[int, int]]) -> float:
        if not cells:
            return 0.0
        _u, c = np.unique(np.array(cells), axis=0, return_counts=True)
        p = c / c.sum()
        h = -(p * np.log(p + 1e-12)).sum()
        return float(h / np.log(8))                     # eight compass cells is the ceiling

    cell = lambda dx, dy: (int(np.sign(dx)) if abs(dx) > 0.5 else 0,
                           int(np.sign(dy)) if abs(dy) > 0.5 else 0)
    allc = [cell(dx, dy) for _a, dx, dy in rows]
    allc = [c for c in allc if c != (0, 0)]
    if len(allc) < 12:
        return 0.0
    h_all = ent(allc)
    by_a: dict[int, list] = defaultdict(list)
    for a, dx, dy in rows:
        c = cell(dx, dy)
        if c != (0, 0):
            by_a[a].append(c)
    tot = sum(len(v) for v in by_a.values())
    h_cond = sum(len(v) / tot * ent(v) for v in by_a.values() if v)
    return float(max(0.0, h_all - h_cond))


def main() -> None:
    import ale_py  # noqa: F401
    import gymnasium as gym

    env = gym.make(GAME, obs_type="rgb", frameskip=1, repeat_action_probability=0.0)
    n_actions = env.action_space.n
    truth = env.unwrapped.get_action_meanings()
    warm = measured_warmup(env, n_actions)
    print(f"control begins after {warm} warmup frames (measured)\n")

    env.reset(seed=0)
    for _ in range(warm):
        env.step(0)
    rng = np.random.default_rng(0)
    bgbuf = []
    obs = env.unwrapped.ale.getScreenRGB()
    for _ in range(200):
        obs, *_ = env.step(int(rng.integers(0, n_actions)))
        bgbuf.append(obs)
    bg = np.median(np.array(bgbuf, dtype=np.int16), axis=0)

    # Track blobs across a long run, recording (action, displacement) per track.
    HOLD = 6
    tracks: dict[int, list[tuple[int, float, float]]] = defaultdict(list)
    prev = blobs(sprite_mask(obs, bg))
    ids = list(range(len(prev)))
    next_id = len(prev)
    for step in range(700):
        a = int(rng.integers(0, n_actions))
        for _ in range(HOLD):
            obs, _r, term, trunc, _i = env.step(a)
            if term or trunc:
                obs, _ = env.reset()
                for _ in range(warm):
                    obs, *_ = env.step(0)
        cur = blobs(sprite_mask(obs, bg))
        new_ids = [None] * len(cur)
        for i0, i1, dx, dy in match(prev, cur):
            new_ids[i1] = ids[i0]
            if abs(dx) > 0.5 or abs(dy) > 0.5:
                tracks[ids[i0]].append((a, dx, dy))
        for k in range(len(cur)):
            if new_ids[k] is None:
                new_ids[k] = next_id
                next_id += 1
        prev, ids = cur, new_ids
    env.close()

    # THE SHUFFLED-ACTION NULL, per track. Conditional entropy with two or three samples per action
    # is biased toward zero for EVERY track, so a ghost scores as "predicted" too — which is exactly
    # what the first run showed: 32 tracks all between 0.22 and 0.39 and the winner beating the
    # runner-up by 0.008. Comparing tracks to each other cannot see that bias because they all carry
    # it. Shuffling the action labels inside a track keeps its sample size and destroys any real
    # dependence, so the excess over that shuffle is the part that is not bias.
    rngn = np.random.default_rng(0)
    scored = []
    for tr, rows in tracks.items():
        if len(rows) < 20:
            continue
        real = command_prediction(rows)
        acts = [a for a, _dx, _dy in rows]
        null = []
        for _ in range(60):
            sh = list(acts)
            rngn.shuffle(sh)
            null.append(command_prediction([(sh[i], rows[i][1], rows[i][2])
                                            for i in range(len(rows))]))
        null = np.array(null)
        scored.append((tr, float(real - null.mean()), len(rows), real, float(null.mean())))
    scored = [(a, b, c) for a, b, c, _r, _n in
              sorted(scored, key=lambda r: -r[1])] if scored else []
    scored.sort(key=lambda r: -r[1])
    if len(scored) < 3:
        sys.exit(f"only {len(scored)} tracks survived — nothing to compare")

    print(f"{len(scored)} tracks with >=20 movements. How much does the command predict each?\n")
    print(f"{'rank':>5}{'track':>7}{'n':>6}{'excess over shuffle':>21}")
    for r, (t, s, n) in enumerate(scored[:8]):
        print(f"{r:>5}{t:>7}{n:>6}{s:>18.4f}")

    body, best, nb = scored[0]
    others = np.array([s for _t, s, _n in scored[1:]])
    print(f"\nbody candidate: track {body}   score {best:.4f}")
    print(f"the rest       : mean {others.mean():.4f}   max {others.max():.4f}")
    identified = best > others.max() * 1.5 and best > 0.05
    print(f"-> {'IDENTIFIED' if identified else 'NOT identified'}: the winner "
          f"{'beats' if identified else 'does not beat'} every other track by 1.5x")

    schema = {}
    if identified:
        rows = tracks[body]
        print(f"\n=== what that one blob does per action (the body schema, from pixels only) ===")
        hit = tot = 0
        for a in range(n_actions):
            V = np.array([(dx, dy) for aa, dx, dy in rows if aa == a])
            if len(V) < 3:
                continue
            dx, dy = float(np.median(V[:, 0])), float(np.median(V[:, 1]))
            parts = []
            if abs(dx) > 0.5:
                parts.append("moves_right" if dx > 0 else "moves_left")
            if abs(dy) > 0.5:
                parts.append("moves_down" if dy > 0 else "moves_up")
            eff = " + ".join(parts) or "no clear effect"
            schema[a] = {"effect": eff, "dx": round(dx, 2), "dy": round(dy, 2), "n": int(len(V))}
            exp = {"UP": "moves_up", "DOWN": "moves_down",
                   "LEFT": "moves_left", "RIGHT": "moves_right"}
            want = [v for k, v in exp.items() if k in truth[a]]
            ok = bool(want) and all(w in eff for w in want)
            if want:
                hit += ok
                tot += 1
            print(f"  {a:>2} {truth[a]:<12} -> {eff:<28} n={len(V):<4} {'OK' if ok else ('x' if want else '')}")
        print(f"\n  directional actions recovered: {hit}/{tot}   (babble without body identity: 2/8)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"game": GAME, "warmup": warm, "tracks_scored": len(scored),
                               "body_track": int(body), "body_score": round(best, 5),
                               "others_mean": round(float(others.mean()), 5),
                               "others_max": round(float(others.max()), 5),
                               "identified": bool(identified), "schema": schema},
                              indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
