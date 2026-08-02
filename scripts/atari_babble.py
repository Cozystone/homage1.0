# -*- coding: utf-8 -*-
"""ATANOR finds out what its buttons do in a game nobody explained to it. Pixels only.

    python scripts/atari_babble.py

The same procedure `packages/hand/babble.py` ran on a City Sample body, on a different body. Nothing
is told that action 2 is UP or that there is an up. Nine actions are pressed, the screen is watched,
and the pair is kept. ALE knows the true meanings and is used ONLY to score afterwards — the schema
is built without them, which is the whole point and is checkable because the answer exists.

WHY THIS BODY IS HARDER THAN THE LAST ONE, and worth doing because of it:

  THE VIEW DOES NOT MOVE. In City Sample the camera was the body, so every command produced global
  optical flow and the flow WAS the consequence. Here the maze is fixed and only a sprite moves, so
  the consequence is a few pixels changing in one place. A body schema read off global flow will read
  nothing at all.

  THE BODY IS ONE THING AMONG MANY. Four ghosts move on their own, under no command. So the
  consequence of an action has to be separated from what the world was doing anyway — which is what
  the still-baseline was for on the last body, and matters far more here.

  ACTIONS ARE INSTANTANEOUS AND THE WORLD HAS MOMENTUM. Ms. Pac-Man keeps travelling in the last
  commanded direction, so pressing LEFT while already moving left changes nothing visible. An
  effect measured on a single frame pair will be missing for exactly the actions that are working.

WHAT IS MEASURED. For each action, where the CONTROLLED thing went — found without being told which
sprite is the body, by taking the sprite blob whose displacement is most consistent across repeats of
the same action. A blob that moves the same way every time that button is held is the one the button
controls; the ghosts do not care which button was pressed.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path("data/atari/body_schema.json")
GAME = "ALE/MsPacman-v5"
W, H = 160, 210


def sprite_mask(frame: np.ndarray, bg: np.ndarray) -> np.ndarray:
    return (np.abs(frame.astype(np.int16) - bg).sum(axis=2) > 40)


def blobs(mask: np.ndarray, min_px: int = 10) -> list[tuple[float, float, int]]:
    import cv2
    n, _lab, st, cen = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    return [(float(cen[k][0]), float(cen[k][1]), int(st[k, cv2.CC_STAT_AREA]))
            for k in range(1, n) if st[k, cv2.CC_STAT_AREA] >= min_px]


def match(a: list, b: list, max_jump: float = 14.0) -> list[tuple[int, int, float, float]]:
    """Nearest-neighbour correspondence between two frames' blobs. Crude and enough: a sprite moves a
    few pixels per step, so the nearest blob is the same blob unless two collide."""
    out = []
    used = set()
    for i, (x0, y0, _s0) in enumerate(a):
        best, bj = None, None
        for j, (x1, y1, _s1) in enumerate(b):
            if j in used:
                continue
            d = float(np.hypot(x1 - x0, y1 - y0))
            if d <= max_jump and (best is None or d < best):
                best, bj = d, j
        if bj is not None:
            used.add(bj)
            out.append((i, bj, b[bj][0] - x0, b[bj][1] - y0))
    return out


def main() -> None:
    import ale_py  # noqa: F401
    import gymnasium as gym

    env = gym.make(GAME, obs_type="rgb", frameskip=1, repeat_action_probability=0.0)
    n_actions = env.action_space.n
    truth = env.unwrapped.get_action_meanings()          # NOT given to the schema; scoring only

    # PRE-FLIGHT INSIDE THE SCRIPT, because the first run of this file babbled through the READY
    # period where Ms. Pac-Man ignores input entirely and scored 0/8. Measured: with 0 or 100 warmup
    # frames all nine actions leave the machine in ONE identical RAM state; control appears around
    # 400. A body schema built while the body cannot move records that the body cannot move.
    obs, _ = env.reset(seed=0)
    warm_frames = 0
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
            warm_frames = probe
            break
    if not warm_frames:
        sys.exit("the actions never diverge — this body cannot be babbled and nothing is built")
    print(f"control begins after {warm_frames} warmup frames "
          f"(measured: the actions stop landing in one state)")

    obs, _ = env.reset(seed=0)
    for _ in range(warm_frames):
        obs, *_ = env.step(0)
    # BACKGROUND FROM A MOVING BODY. Taking the median while the body sits still puts the body IN the
    # background and subtracts it away, which is what happened on the first run.
    warm = []
    rngw = np.random.default_rng(1)
    for _ in range(200):
        obs, *_ = env.step(int(rngw.integers(0, n_actions)))
        warm.append(obs)
    bg = np.median(np.array(warm, dtype=np.int16), axis=0)

    HOLD = 6          # frames per trial: momentum means one frame shows nothing
    REPEATS = 30      # interleaved; more repeats because only moving blobs now count
    moves: dict[int, list[tuple[float, float]]] = defaultdict(list)
    still: list[tuple[float, float]] = []

    for rep in range(REPEATS):
        for a in range(n_actions):
            before = env.render() if False else None
            obs0 = obs
            for _ in range(HOLD):
                obs, _r, term, trunc, _i = env.step(a)
                if term or trunc:
                    obs, _ = env.reset()
            m0, m1 = sprite_mask(obs0, bg), sprite_mask(obs, bg)
            b0, b1 = blobs(m0), blobs(m1)
            # ONLY BLOBS THAT MOVED. The sprite mask holds ~200 static pellets — they differ from
            # the rollout median because they get eaten, so background subtraction calls them
            # sprites — and each matches itself at displacement zero. Two runs reported "the world
            # moves 0.00px uncommanded" in a game with four ghosts in it, because the median was
            # reading pellets. A statistic taken over a population the thing of interest is a
            # minority of is not a statistic about the thing of interest.
            for _i0, _i1, dx, dy in match(b0, b1):
                if abs(dx) > 0.5 or abs(dy) > 0.5:
                    moves[a].append((dx, dy))
        # what the world does when nothing is commanded: NOOP is action 0, but the ghosts still move
        obs0 = obs
        for _ in range(HOLD):
            obs, _r, term, trunc, _i = env.step(0)
            if term or trunc:
                obs, _ = env.reset()
        for _i0, _i1, dx, dy in match(blobs(sprite_mask(obs0, bg)), blobs(sprite_mask(obs, bg))):
            if abs(dx) > 0.5 or abs(dy) > 0.5:
                still.append((dx, dy))
    env.close()

    S = np.array(still) if still else np.zeros((1, 2))
    print(f"{GAME}: {n_actions} actions, {REPEATS} interleaved repeats of {HOLD} frames\n")
    print(f"what the world does uncommanded: median |d| = {np.median(np.hypot(S[:, 0], S[:, 1])):.2f} px "
          f"over {len(S)} blob movements\n")

    # THE CONTROLLED BLOB: for each action, the displacement that RECURS. A ghost's motion is
    # unrelated to which button was pressed, so it averages toward the uncommanded baseline; the
    # body's motion does not.
    schema = {}
    print(f"{'action':>7}{'n':>6}{'dx':>8}{'dy':>8}{'|d|':>8}{'consistency':>13}   what ATANOR concluded")
    for a in range(n_actions):
        V = np.array(moves[a]) if moves[a] else np.zeros((0, 2))
        if len(V) < 8:
            print(f"{a:>7}{len(V):>6}{'-':>8}{'-':>8}{'-':>8}{'-':>13}   too few observations")
            continue
        # THE MODAL DIRECTION, not the median over everything that moved. Five blobs move on a
        # given trial -- the body and four ghosts -- and only one of them is answering the button.
        # The docstring said to take "the blob whose displacement is most consistent across repeats"
        # and the first three versions of this code pooled all of them instead, so the body's signal
        # was averaged against four independent walkers. A ghost's direction is unrelated to which
        # button was pressed, so it spreads across the eight compass cells; the body's repeats land
        # in one. So the cell with the most mass IS the body's answer, and the fraction of mass in it
        # is how sure the answer is.
        cells = {}
        for vx, vy in V:
            key = (int(np.sign(vx)) if abs(vx) > 0.5 else 0,
                   int(np.sign(vy)) if abs(vy) > 0.5 else 0)
            if key == (0, 0):
                continue
            cells.setdefault(key, []).append((vx, vy))
        if not cells:
            schema[a] = {"effect": "no effect above the world's own motion", "n": int(len(V))}
            print(f"{a:>7}{len(V):>6}{0:>8.2f}{0:>8.2f}{0:>8.2f}{'-':>13}   nothing above the world")
            continue
        key = max(cells, key=lambda k_: len(cells[k_]))
        Vk = np.array(cells[key])
        consistency = len(Vk) / sum(len(v) for v in cells.values())
        dx, dy = float(np.median(Vk[:, 0])), float(np.median(Vk[:, 1]))
        parts = []
        if abs(dx) > 0.6:
            parts.append("moves_right" if dx > 0 else "moves_left")
        if abs(dy) > 0.6:
            parts.append("moves_down" if dy > 0 else "moves_up")
        eff = " + ".join(parts) or "moves, direction unclear"
        schema[a] = {"effect": eff, "dx": round(dx, 2), "dy": round(dy, 2),
                     "consistency": round(consistency, 3), "n": int(len(Vk))}
        print(f"{a:>7}{len(Vk):>6}{dx:>8.2f}{dy:>8.2f}{np.hypot(dx, dy):>8.2f}"
              f"{consistency:>13.3f}   {eff}")

    # SCORING ONLY. The schema above was built without these.
    print(f"\n=== scored against ALE's own action meanings (never shown to the schema) ===")
    hit = tot = 0
    for a, name in enumerate(truth):
        got = schema.get(a, {}).get("effect", "")
        exp = {"UP": "moves_up", "DOWN": "moves_down", "LEFT": "moves_left", "RIGHT": "moves_right"}
        want = [v for k, v in exp.items() if k in name]
        if not want:
            print(f"  {a:>2} {name:<12} -> {got}")
            continue
        ok = all(w in got for w in want)
        hit += ok
        tot += 1
        print(f"  {a:>2} {name:<12} -> {got:<34} {'OK' if ok else 'x'}")
    print(f"\n  directional actions recovered: {hit}/{tot}   (chance for one axis-sign is 1/4)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"game": GAME, "actions": int(n_actions), "hold": HOLD,
                               "repeats": REPEATS, "schema": schema,
                               "scored_against": list(truth),
                               "directional_recovered": [hit, tot]},
                              indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
