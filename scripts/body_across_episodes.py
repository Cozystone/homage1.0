# -*- coding: utf-8 -*-
"""Eighth attempt at the body: carry the evidence across episodes, because the body outlives the reset.

    python scripts/body_across_episodes.py

The seventh attempt closed on a specific number rather than a shrug. The intention-with-momentum
criterion reaches 74.0% on-body given a 300-step rollout and only 42.9% given 150, and an episode is
~148 steps. So the criterion is not wrong, it is STARVED -- and it is starved by an accident of
bookkeeping:

    the game resets; the body's identity does not. Only the tracker forgets.

WHAT CAN CARRY IDENTITY THROUGH A RESET. Not a track id -- those are created fresh. Not a position --
everything teleports. It has to be something OBSERVABLE that survives, and on a screen that means
APPEARANCE: the colour and size of the thing. So command-evidence accumulates against an appearance
bucket instead of a track, and a new episode's tracks inherit whatever that appearance has already
earned.

This is not a trick for this game. A body is the thing whose appearance persists while everything else
about the scene is replaced, and evidence about it should persist with it.

WHAT IS AND IS NOT SUPPLIED. Pixels only: the appearance descriptor is mean colour plus size, read off
the frame. Nothing says which colour is the body, how many bodies there are, or that yellow matters --
the buckets are discovered by clustering what appears, and the command statistic chooses among them.
The RAM oracle SCORES and never decides, and it is pre-flighted before it scores.

REGISTERED BEFORE RUNNING, against the seventh attempt's measured figures:
    1  within a 148-step episode, on-body% rises with the number of PRIOR episodes of evidence -- the
       whole claim is that carrying evidence removes the per-episode budget
    2  it exceeds 42.9%, which is what one episode's worth of evidence bought
    3  and approaches 74.0%, the 300-step figure, without any single rollout being that long
    4  against choosing an appearance bucket at random, measured in the same run
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception.self_criterion import intention_momentum                # noqa: E402
from packages.perception.sprite_tracker import SpriteTracker                     # noqa: E402
from scripts.atari_babble import blobs, sprite_mask                              # noqa: E402
from scripts.atari_find_body import measured_warmup                              # noqa: E402
from scripts.atari_play import make                                             # noqa: E402
from scripts.atari_taught import RAM_BODY, fit_ram_to_screen, screen_xy         # noqa: E402

OUT = Path("data/atari/body_across_episodes.json")
EP_STEPS = 148            # what an episode actually lasts, measured
SEVENTH = {"one_episode": 0.429, "three_hundred_steps": 0.740}


def appearance(frame: np.ndarray, blob, r: int = 4) -> tuple:
    """A descriptor that survives a reset: coarse mean colour plus coarse size. Pixels only.

    Quantised deliberately. A continuous descriptor would give every sprite its own bucket on every
    frame and carry nothing; the point is that the SAME thing lands in the SAME bucket next episode."""
    x, y, size = int(blob[0]), int(blob[1]), blob[2]
    H, W = frame.shape[:2]
    patch = frame[max(0, y - r):min(H, y + r), max(0, x - r):min(W, x + r)]
    if patch.size == 0:
        return (0, 0, 0, 0)
    c = patch.reshape(-1, 3).mean(axis=0)
    return (int(c[0]) // 32, int(c[1]) // 32, int(c[2]) // 32, int(np.log2(max(size, 1))))


def run_episode(env, warm, rng, n_a, fit, memory: dict, steps: int):
    """One episode. Evidence goes into `memory`, keyed by APPEARANCE, and is never cleared."""
    obs, _ = env.reset()
    for _ in range(warm):
        obs, *_ = env.step(0)
    buf = []
    for _ in range(40):
        obs, *_ = env.step(int(rng.integers(0, n_a)))
        buf.append(obs)
    bg = np.median(np.array(buf, dtype=np.int16), axis=0)

    tr = SpriteTracker(max_jump=22.0)
    look: dict = {}          # track id -> appearance bucket, decided on first sight
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
                j = int(np.argmin([np.hypot(b[0] - k.pos[0], b[1] - k.pos[1]) for b in bl])) if bl else None
                look[k.id] = appearance(obs, bl[j]) if j is not None else (0, 0, 0, 0)
            d = k.pos - before.get(k.id, k.pos)
            if abs(d[0]) > 0.5 or abs(d[1]) > 0.5:
                memory.setdefault(look[k.id], []).append((a, float(d[0]), float(d[1])))
            hist[look[k.id]][t] = k.pos.copy()
        truth.append(screen_xy(env.unwrapped.ale.getRAM(), fit, RAM_BODY))
    return hist, np.array(truth)


def on_body(track_hist: dict, truth: np.ndarray) -> float:
    if not track_hist:
        return 0.0
    ts = sorted(track_hist)
    P = np.array([track_hist[t] for t in ts])
    T = truth[ts]
    return float((np.hypot(P[:, 0] - T[:, 0], P[:, 1] - T[:, 1]) < 8.0).mean())


def main() -> None:
    env = make()
    warm = measured_warmup(env, env.action_space.n)
    fit, agree = fit_ram_to_screen(env, warm, seed=3)
    n_a = env.action_space.n
    env.close()
    if not (agree["r_x"] > 0.9 and agree["r_y"] > 0.9):
        sys.exit("the oracle failed its own check; a pixel score against it would mean nothing")
    print(f"oracle verified r_x {agree['r_x']:.3f}; it SCORES and never decides")
    print(f"episodes are {EP_STEPS} steps. Seventh attempt: {SEVENTH['one_episode']:.1%} with one "
          f"episode of evidence, {SEVENTH['three_hundred_steps']:.1%} with 300 steps.\n")

    env = make()
    rng = np.random.default_rng(3)
    memory: dict = {}
    rows = []
    for ep in range(8):
        hist, truth = run_episode(env, warm, rng, n_a, fit, memory, EP_STEPS)
        scored = [(b, intention_momentum(ev)) for b, ev in memory.items() if len(ev) >= 12]
        if not scored:
            rows.append({"episode": ep, "chosen": None, "buckets": len(memory)})
            print(f"  episode {ep}: no appearance bucket has 12 samples yet "
                  f"({len(memory)} buckets seen)")
            continue
        best = max(scored, key=lambda x: x[1])[0]
        per = {b: on_body(hist.get(b, {}), truth) for b, _s in scored}
        chosen = per.get(best, 0.0)
        chance = float(np.mean(list(per.values()))) if per else 0.0
        rows.append({"episode": ep, "chosen_on_body": chosen, "chance": chance,
                     "buckets": len(memory), "scoreable": len(scored),
                     "evidence_on_chosen": len(memory[best]),
                     "best_available": max(per.values()) if per else 0.0})
        print(f"  episode {ep}: chosen bucket on the body {chosen:>6.1%}   "
              f"chance {chance:>6.1%}   best available {max(per.values()):>6.1%}   "
              f"evidence carried {len(memory[best]):>4}")
    env.close()

    ok = [r for r in rows if r.get("chosen_on_body") is not None]
    late = [r["chosen_on_body"] for r in ok[-4:]]
    early = [r["chosen_on_body"] for r in ok[:2]]
    print(f"\n-> 1. rises with prior episodes: {bool(late and early) and np.mean(late) > np.mean(early)}"
          f"  (first two {np.mean(early):.1%} -> last four {np.mean(late):.1%})")
    print(f"-> 2. beats one episode's worth ({SEVENTH['one_episode']:.1%}): "
          f"{bool(late) and np.mean(late) > SEVENTH['one_episode']}")
    print(f"-> 3. approaches the 300-step figure ({SEVENTH['three_hundred_steps']:.1%}): "
          f"{bool(late) and np.mean(late) > 0.9 * SEVENTH['three_hundred_steps']}")
    ch = [r["chance"] for r in ok[-4:]]
    print(f"-> 4. beats picking an appearance bucket at random: "
          f"{bool(late) and np.mean(late) > np.mean(ch)}  ({np.mean(ch):.1%})")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"oracle": agree, "episode_steps": EP_STEPS,
                               "seventh_attempt": SEVENTH, "rows": rows}, indent=2),
                   encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
