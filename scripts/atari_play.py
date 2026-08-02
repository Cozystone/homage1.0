# -*- coding: utf-8 -*-
"""Put it in the game. Give it a score to reach. Watch how it gets there.

    python scripts/atari_play.py

Owner: 본 게임에 바로 투입해야지 뭘 자꾸 만들고 있어. 그냥 점수 일정치에 도달하라고만 하고 스스로
어떻게 문제를 해결하는지 봐야지.

Fair. The last several rungs were instruments for watching, not the thing being watched, and each one
found a defect in itself rather than telling us anything about ATANOR. So: the game, a score target,
and nothing else specified.

WHAT IS AND IS NOT GIVEN. Given: the screen, nine buttons, and the score. NOT given: which button
does what, which sprite is the body, where the walls are, what a ghost is, or that dying is bad. The
target is set from the random baseline measured in the same run, so it is a number the game produces
rather than one I picked.

HOW IT LEARNS, and this is the only design decision, so it is stated plainly. The screen is reduced
to the retina code already used everywhere in this project, and the agent remembers what each action
paid the last times the screen looked like this. Nearest-neighbour over remembered situations; no
gradients, no training, no network. "When it looked like this before, this button paid that much."

That is memory, not a policy anyone wrote, and it is the weakest thing that can improve at all — so
if the score rises, the rise is attributable to remembering consequences rather than to a clever
controller I supplied.

THE MAP IS NOT BUILT. It is recorded. Every place the agent has been is kept, and the question at the
end is whether playing for score revealed more of the maze than random play did — which is the
circularity from the previous rung, tested rather than argued: mapping needs traversal, traversal
needs a reason to move, and score is the reason.

THREE ARMS AND A REPLAY, because a score by itself cannot tell learning from luck:
    random    the floor, and the source of the target
    learner   nearest-neighbour value over retina codes
    replay    the learner's own action sequence, into differently seeded games
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.atari_find_body import measured_warmup   # noqa: E402

OUT = Path("data/atari/play.json")
GAME = "ALE/MsPacman-v5"


def make():
    import ale_py  # noqa: F401
    import gymnasium as gym
    return gym.make(GAME, obs_type="rgb", frameskip=4, repeat_action_probability=0.0)


class Memory:
    """What each button paid, the last times the screen looked like this.

    A situation is the retina code. `recall` finds the nearest remembered situations and returns the
    mean payoff per action among them; `learn` stores what actually happened. Nothing is fitted."""

    def __init__(self, n_actions: int, k: int = 12, cap: int = 4000):
        self.n = n_actions
        self.k = k
        self.cap = cap
        self.codes: list[np.ndarray] = []
        self.acts: list[int] = []
        self.pays: list[float] = []

    def recall(self, code: np.ndarray) -> np.ndarray:
        if len(self.codes) < self.k * self.n:
            return np.full(self.n, np.nan)
        C = np.array(self.codes)
        d = np.abs(C - code).mean(axis=1)
        near = np.argsort(d)[: self.k * self.n]
        out = np.full(self.n, np.nan)
        for a in range(self.n):
            v = [self.pays[i] for i in near if self.acts[i] == a]
            if v:
                out[a] = float(np.mean(v))
        return out

    def learn(self, code: np.ndarray, a: int, pay: float) -> None:
        self.codes.append(code)
        self.acts.append(a)
        self.pays.append(pay)
        if len(self.codes) > self.cap:
            self.codes.pop(0)
            self.acts.pop(0)
            self.pays.pop(0)


def episode(mode: str, steps: int, warm: int, seed: int, mem=None, actions=None):
    """One run. Returns score, the action sequence, and everywhere the screen was."""
    from packages.perception.attention import frame_signature

    env = make()
    obs, _ = env.reset(seed=seed)
    for _ in range(max(1, warm // 4)):
        obs, *_ = env.step(0)
    n_a = env.action_space.n
    rng = np.random.default_rng(seed)
    score = 0.0
    chosen: list[int] = []
    visited: set = set()
    code = frame_signature(obs)

    for t in range(steps):
        if actions is not None:
            a = actions[t % len(actions)]
        elif mode == "random" or mem is None:
            a = int(rng.integers(0, n_a))
        else:
            q = mem.recall(code)
            if np.all(np.isnan(q)) or rng.random() < 0.15:
                a = int(rng.integers(0, n_a))          # try the untried; the only exploration term
            else:
                q = np.where(np.isnan(q), np.nanmin(q) - 1e-6, q)
                a = int(np.argmax(q))
        pay = 0.0
        for _ in range(3):
            obs, r, term, trunc, _i = env.step(a)
            pay += float(r)
            if term or trunc:
                obs, _ = env.reset()
                for _ in range(max(1, warm // 4)):
                    obs, *_ = env.step(0)
        score += pay
        nxt = frame_signature(obs)
        if mem is not None and actions is None and mode == "learner":
            mem.learn(code, a, pay)
        code = nxt
        chosen.append(a)
        visited.add(tuple(np.round(code * 24).astype(np.int8)))   # coarse record of where it has been
    env.close()
    return {"score": score, "actions": chosen, "places": len(visited)}


def main() -> None:
    env = make()
    warm = measured_warmup(env, env.action_space.n)
    n_a = env.action_space.n
    env.close()
    print(f"{GAME}: {n_a} buttons. Given: the screen, the buttons, the score.")
    print(f"NOT given: what any button does, which sprite is the body, where the walls are.\n")

    STEPS, N = 400, 5
    rnd = [episode("random", STEPS, warm, seed=200 + s) for s in range(N)]
    base = float(np.mean([e["score"] for e in rnd]))
    target = base * 1.5
    print(f"random baseline over {N} episodes: {base:.1f}   "
          f"(scores {[int(e['score']) for e in rnd]})")
    print(f"TARGET, set from the game and not by me: {target:.1f}  (1.5x random)\n")

    mem = Memory(n_a)
    curve, places = [], []
    for ep in range(12):
        out = episode("learner", STEPS, warm, seed=300 + ep, mem=mem)
        curve.append(out["score"])
        places.append(out["places"])
        print(f"  episode {ep:>2}  score {out['score']:>7.1f}   memory {len(mem.codes):>5}   "
              f"places {out['places']:>4}")

    first, last = float(np.mean(curve[:4])), float(np.mean(curve[-4:]))
    rep_actions = episode("learner", STEPS, warm, seed=999, mem=mem)["actions"]
    rep = [episode("replay", STEPS, warm, seed=700 + s, actions=rep_actions)["score"]
           for s in range(N)]

    print(f"\nfirst 4 episodes {first:.1f}  ->  last 4 {last:.1f}")
    print(f"replay of its own sequence into fresh games: {np.mean(rep):.1f}")
    print(f"places seen: random {np.mean([e['places'] for e in rnd]):.0f}  "
          f"learner first {places[0]}  last {places[-1]}")

    reached = last >= target
    improved = last > first
    not_luck = last > float(np.mean(rep))
    print(f"\n-> reached the target ({target:.1f}): {reached}")
    print(f"-> improved over its own start: {improved}  ({first:.1f} -> {last:.1f})")
    print(f"-> and not just a lucky sequence: {not_luck}  (replay {np.mean(rep):.1f})")
    print(f"-> the map grew as a by-product: "
          f"{places[-1] > np.mean([e['places'] for e in rnd])}  "
          f"({np.mean([e['places'] for e in rnd]):.0f} random vs {places[-1]} at the end)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"baseline": base, "target": target, "curve": curve,
                               "first4": first, "last4": last, "replay": rep,
                               "places_random": float(np.mean([e["places"] for e in rnd])),
                               "places_curve": places,
                               "reached": bool(reached), "improved": bool(improved),
                               "not_luck": bool(not_luck)}, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
