# -*- coding: utf-8 -*-
"""Rung A — one instruction, no reward, no handler. Can a preference over predicted futures avoid death?

    python scripts/schema_executor_pacman.py

TODAY'S HARDEST MEASURED FACT: across 16 deaths, the reward on the step a life is lost is +0.00, on the
five steps before it +0.00, against +3.09 on an ordinary step. Death is not merely unrewarded, it is
INDISTINGUISHABLE FROM A DULL PATCH. No learner that stores immediate reward can avoid it, at any level
of intelligence, and the measured consequence was that the agent dies MORE than random (12.4 against
11.0 per thousand steps) while eating more.

THE IDEOMOTOR CLAIM SAYS THIS IS THE WRONG WAY ROUND. Actions are coded by their effects: you select by
imagining the outcome, not by recalling a payoff. A preference over PREDICTED futures needs no reward
signal at all, so a consequence the environment never pays for is still visible.

    instruction   ->  Proximity(me, ghost, polarity = -1)
    executor      ->  for each button, roll the world forward, score the predicted scene, take the best

`choose()` in packages/image_schema/basis.py is that loop and it contains no verb, no game, and no
reward. Swapping the polarity turns avoidance into pursuit with no other change, which is the whole
argument for a schema basis compressed into one integer.

WHAT IS SUPPLIED AND WHAT IS NOT.
    supplied      where the body and the ghosts are (RAM, verified at r=1.000). Body-finding failed
                  four ways today and is a SEPARATE problem; this rung tests the executor, and mixing
                  the two would leave any result unattributable.
    NOT supplied  what any button does. The action->displacement map is LEARNED online from the agent's
                  own observations, which today's audit showed is present in the data (nine actions'
                  mean displacements spread 3.11 px against a shuffled-action null of 0.74, p=0.0050).
    NOT supplied  that ghosts are dangerous, that death is bad, or any reward shaping. Nothing in the
                  loop reads the score.

THE CONTROL THAT MAKES THE RESULT MEAN ANYTHING: the same executor with polarity +1 — an instruction to
CHASE the ghosts. If avoid and chase produce the same death rate, the executor is not doing anything and
a lower number would be luck. Registered before running:

    1  avoid dies LESS than random          (random measured in the same run; today's figure was 11.0)
    2  avoid dies less than chase           the polarity discriminator; without this, claim nothing
    3  reported per episode with a test, not as two means side by side
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.image_schema import MetricScene, Proximity, choose         # noqa: E402
from scripts.atari_find_body import measured_warmup                      # noqa: E402
from scripts.atari_play import make                                      # noqa: E402
from scripts.atari_taught import (RAM_BODY, RAM_GHOSTS, fit_ram_to_screen,   # noqa: E402
                                  screen_xy)

OUT = Path("data/language/schema_executor_pacman.json")
OUT_N = Path("data/language/schema_executor_pacman_n.json")
RAM_LIVES = 123
HORIZON = 4          # how far ahead the world is rolled, in agent steps


class ActionMap:
    """What each button does to the body. LEARNED from watching, never told."""

    def __init__(self, n: int):
        self.sum = np.zeros((n, 2))
        self.cnt = np.zeros(n)

    def learn(self, a: int, d) -> None:
        if abs(d[0]) > 0.1 or abs(d[1]) > 0.1:
            self.sum[a] += d
            self.cnt[a] += 1

    def ready(self) -> bool:
        return bool((self.cnt >= 5).sum() >= 4)

    def delta(self, a: int):
        return self.sum[a] / self.cnt[a] if self.cnt[a] else np.zeros(2)


def scene_of(pos: dict) -> MetricScene:
    return MetricScene(pos=pos, radius=8.0)


def make_rollout(amap: ActionMap, vel: dict, names: list):
    """predicted scene = body moved by what the button has been observed to do, others by their velocity.

    The ghost model is constant velocity, which today's measurement put at 2.194 px error at a turn and
    0.000 in a corridor. It is a poor model of a junction and an exact one everywhere else, and it is
    the model the agent actually has."""
    def rollout(scene: MetricScene, a: int) -> MetricScene:
        nxt = {}
        for k in names:
            p = scene._pos.get(k)
            if p is None:
                continue
            if k == "me":
                d = amap.delta(a) * HORIZON
            else:
                d = np.array(vel.get(k, (0.0, 0.0))) * HORIZON
            nxt[k] = (p[0] + d[0], p[1] + d[1])
        return scene_of(nxt)
    return rollout


def episode(mode: str, warm: int, seed: int, fit, cap: int = 3000):
    """One episode to game over. `mode` is random, avoid, or chase — the last two differ by polarity."""
    env = make()
    obs, _ = env.reset(seed=seed)
    for _ in range(max(1, warm // 4)):
        obs, *_ = env.step(0)
    n_a = env.action_space.n
    rng = np.random.default_rng(seed)
    amap = ActionMap(n_a)

    ram = env.unwrapped.ale.getRAM()
    names = ["me"] + [f"ghost{i}" for i in range(len(RAM_GHOSTS))]
    prev = {"me": tuple(screen_xy(ram, fit, RAM_BODY))}
    for i, g in enumerate(RAM_GHOSTS):
        prev[f"ghost{i}"] = tuple(screen_xy(ram, fit, g))
    vel = {k: (0.0, 0.0) for k in names}

    lives = int(ram[RAM_LIVES])
    score, steps, deaths, guided = 0.0, 0, 0, 0
    for _t in range(cap):
        scene = scene_of(prev)
        if mode == "random" or not amap.ready():
            a = int(rng.integers(0, n_a))
        else:
            # THE ONLY PLACE AN INSTRUCTION ENTERS. One schema; polarity is the instruction.
            pol = -1 if mode == "avoid" else 1
            near = min((k for k in names if k != "me"),
                       key=lambda k: scene.distance("me", k) or 1e9)
            pick, _v = choose(list(range(n_a)), make_rollout(amap, vel, names),
                              [Proximity("me", near, polarity=pol)], scene)
            if pick is None:
                a = int(rng.integers(0, n_a))
            else:
                a, guided = int(pick), guided + 1

        done = False
        for _ in range(3):
            obs, r, term, trunc, _i = env.step(a)
            score += float(r)
            if term or trunc:
                done = True
                break
        steps += 1

        ram = env.unwrapped.ale.getRAM()
        cur = {"me": tuple(screen_xy(ram, fit, RAM_BODY))}
        for i, g in enumerate(RAM_GHOSTS):
            cur[f"ghost{i}"] = tuple(screen_xy(ram, fit, g))
        d_me = np.array(cur["me"]) - np.array(prev["me"])
        if np.hypot(*d_me) < 40:                      # ignore the teleport on respawn
            amap.learn(a, d_me)
        for k in names:
            dv = np.array(cur[k]) - np.array(prev[k])
            vel[k] = tuple(dv) if np.hypot(*dv) < 40 else (0.0, 0.0)
        prev = cur

        nl = int(ram[RAM_LIVES])
        if nl < lives:
            deaths += 1
        lives = nl
        if done:
            break
    env.close()
    return {"score": score, "steps": steps, "deaths": deaths,
            "per1000": 1000.0 * deaths / max(steps, 1), "guided": guided}


def main() -> None:
    env = make()
    warm = measured_warmup(env, env.action_space.n)
    fit, agree = fit_ram_to_screen(env, warm)
    env.close()
    print(f"oracle verified: r_x {agree['r_x']:.3f} r_y {agree['r_y']:.3f}, "
          f"residual {agree['residual_px']:.2f} px")
    print("supplied: positions. NOT supplied: what any button does, that ghosts hurt, any reward.\n")

    N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    res = {}
    for mode in ("random", "avoid", "chase"):
        runs = [episode(mode, warm, 800 + s, fit) for s in range(N)]
        res[mode] = runs
        d = np.array([r["per1000"] for r in runs])
        print(f"  {mode:8} deaths/1000 steps {d.mean():>6.2f} +- {d.std(ddof=1):>5.2f}   "
              f"score {np.mean([r['score'] for r in runs]):>6.0f}   "
              f"steps {np.mean([r['steps'] for r in runs]):>5.0f}   "
              f"schema chose {np.mean([r['guided'] for r in runs]):>5.0f}x")

    from scipy.stats import mannwhitneyu
    A = np.array([r["per1000"] for r in res["avoid"]])
    R = np.array([r["per1000"] for r in res["random"]])
    C = np.array([r["per1000"] for r in res["chase"]])
    _u, p_vs_rand = mannwhitneyu(A, R, alternative="less")
    _u2, p_vs_chase = mannwhitneyu(A, C, alternative="less")

    print(f"\n-> 1. avoid dies less than random: {A.mean():.2f} vs {R.mean():.2f}, "
          f"p = {p_vs_rand:.4f}   {'REAL' if p_vs_rand < 0.05 else 'not established'}")
    print(f"-> 2. avoid dies less than chase : {A.mean():.2f} vs {C.mean():.2f}, "
          f"p = {p_vs_chase:.4f}   {'REAL' if p_vs_chase < 0.05 else 'not established'}")
    print("\nWHAT THE PAIR MEANS")
    if p_vs_chase < 0.05 and p_vs_rand < 0.05:
        print("  A preference over predicted futures avoids a consequence the environment never pays")
        print("  for. No reward, no handler, and the instruction is ONE INTEGER of difference.")
    elif p_vs_chase >= 0.05:
        print("  The polarity control FAILED: chasing and avoiding die at the same rate, so the")
        print("  executor is not steering and any gain against random is not attributable to it.")
    else:
        print("  Avoid separates from chase but not from random: the schema changes behaviour without")
        print("  yet making it better, so the predictor rather than the instruction is the limit.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tgt = OUT if N == 8 else OUT_N
    tgt.write_text(json.dumps({"oracle": agree, "n": N, "runs": res,
                               "p_vs_random": float(p_vs_rand),
                               "p_vs_chase": float(p_vs_chase)}, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
