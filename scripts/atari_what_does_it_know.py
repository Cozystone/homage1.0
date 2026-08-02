# -*- coding: utf-8 -*-
"""Is the score low because it is stupid, or because of what I measured and what I gave it to learn with?

    python scripts/atari_what_does_it_know.py

Owner: 점수대가 너무 낮은데 atanor 지능이 딸리는건가? 규칙은 제대로 알아?

Fair question, and it splits into three that have separate answers, so it gets measured rather than
argued. Before any of them: MY NUMBER IS NOT AN EPISODE SCORE. Every run so far was 400 agent steps --
about 4,800 game frames -- and on death it RESET AND KEPT PLAYING, accumulating across restarts. That
is points per eighty seconds with free lives, and it cannot be compared to a published Ms. Pac-Man
figure, which is one episode to game over. Both are measured here so the difference is visible instead
of assumed.

PART A  what the number actually is
        the same agents played to game over, no step cap, no restart, lives counted

PART B  does it know the rules -- three propositions, each with its own test and its own control
        buttons  is the map from button to direction even present in the data, and does the memory
                 hold it? Measured as the spread of the body's mean displacement across the nine
                 actions, against a shuffled-action null.
        ghosts   does it die less than random? deaths per thousand steps.
        pellets  does it eat more than random? Ms. Pac-Man pays exactly 10 for a pellet, so a
                 reward of 10 is a pellet and no vision is needed to count them.

PART C  is the learner the limit
        the learner is a 4,000-slot nearest-neighbour table with no gradients and no network. I chose
        the weakest thing that can improve at all, on purpose, so that a rise would be attributable to
        remembering consequences rather than to a controller I supplied. That choice has a price and
        this part measures it: the same states, the same games, with the memory made larger.

PRE-FLIGHT: the lives counter is verified before it is used to count deaths. An unchecked RAM byte is
how this session lost an afternoon already.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception.attention import frame_signature                 # noqa: E402
from scripts.atari_find_body import measured_warmup                       # noqa: E402
from scripts.atari_play import Memory, make                               # noqa: E402
from scripts.atari_play_egocentric import local_code                      # noqa: E402
from scripts.atari_taught import RAM_BODY, fit_ram_to_screen, screen_xy   # noqa: E402

OUT = Path("data/atari/what_does_it_know.json")
RAM_LIVES = 123
# Published reference points for Ms. Pac-Man, one episode to game over (Mnih et al. 2015 protocol).
REF = {"random": 307.3, "DQN": 2311.0, "human": 15693.0}


def check_lives(env, warm: int, seed: int = 0) -> dict:
    """Pre-flight: does byte 123 behave like a life counter — bounded, and falling on death?"""
    rng = np.random.default_rng(seed)
    env.reset(seed=seed)
    for _ in range(warm):
        env.step(0)
    seen, drops, rises = [], 0, 0
    prev = int(env.unwrapped.ale.getRAM()[RAM_LIVES])
    for _ in range(1500):
        _o, _r, term, trunc, _i = env.step(int(rng.integers(0, env.action_space.n)))
        v = int(env.unwrapped.ale.getRAM()[RAM_LIVES])
        seen.append(v)
        if v < prev:
            drops += 1
        if v > prev:
            rises += 1
        prev = v
        if term or trunc:
            break
    u = sorted(set(seen))
    return {"values": u, "drops": drops, "rises": rises,
             "ok": len(u) <= 6 and max(u) <= 5 and drops >= 1}


def act(mem, code, rng, n_a):
    if mem is None:
        return int(rng.integers(0, n_a))
    q = mem.recall(code)
    if np.all(np.isnan(q)) or rng.random() < 0.15:
        return int(rng.integers(0, n_a))
    q = np.where(np.isnan(q), np.nanmin(q) - 1e-6, q)
    return int(np.argmax(q))


def full_episode(state: str, warm: int, seed: int, mem=None, fit=None, cap: int = 3000):
    """To game over. No restart, no step cap that the agent can reach in practice."""
    env = make()
    obs, _ = env.reset(seed=seed)
    for _ in range(max(1, warm // 4)):
        obs, *_ = env.step(0)
    n_a = env.action_space.n
    rng = np.random.default_rng(seed)
    score, steps, pellets, deaths = 0.0, 0, 0, 0
    lives = int(env.unwrapped.ale.getRAM()[RAM_LIVES])
    for _t in range(cap):
        ram = env.unwrapped.ale.getRAM()
        if state == "whole":
            code = frame_signature(obs)
        else:
            code = local_code(obs, screen_xy(ram, fit, RAM_BODY))
        a = act(mem, code, rng, n_a)
        pay, done = 0.0, False
        for _ in range(3):
            obs, r, term, trunc, _i = env.step(a)
            pay += float(r)
            if float(r) == 10.0:
                pellets += 1
            if term or trunc:
                done = True
                break
        score += pay
        steps += 1
        nl = int(env.unwrapped.ale.getRAM()[RAM_LIVES])
        if nl < lives:
            deaths += 1
        lives = nl
        if mem is not None:
            mem.learn(code, a, pay)
        if done:
            break
    env.close()
    return {"score": score, "steps": steps, "pellets": pellets, "deaths": deaths,
            "capped": steps >= cap}


def button_map(warm: int, fit, seed: int = 5, steps: int = 900):
    """Is the button-to-direction map present in the pixels at all? Spread across actions vs a null."""
    env = make()
    obs, _ = env.reset(seed=seed)
    for _ in range(warm):
        obs, *_ = env.step(0)
    n_a = env.action_space.n
    rng = np.random.default_rng(seed)
    rows = []
    p = screen_xy(env.unwrapped.ale.getRAM(), fit, RAM_BODY)
    for _ in range(steps):
        a = int(rng.integers(0, n_a))
        for _ in range(3):
            obs, _r, term, trunc, _i = env.step(a)
            if term or trunc:
                obs, _ = env.reset()
                for _ in range(warm):
                    obs, *_ = env.step(0)
        q = screen_xy(env.unwrapped.ale.getRAM(), fit, RAM_BODY)
        d = q - p
        if np.hypot(*d) < 60:
            rows.append((a, d[0], d[1]))
        p = q
    env.close()
    A = np.array([r[0] for r in rows])
    D = np.array([[r[1], r[2]] for r in rows])

    def spread(labels):
        m = np.array([D[labels == a].mean(axis=0) for a in range(n_a) if (labels == a).sum() >= 8])
        return float(np.linalg.norm(m - m.mean(axis=0), axis=1).mean())

    real = spread(A)
    null = [spread(rng.permutation(A)) for _ in range(200)]
    return {"n": len(rows), "spread_px": real, "null_mean": float(np.mean(null)),
            "null_p95": float(np.percentile(null, 95)),
            "p": float((np.sum(np.array(null) >= real) + 1) / 201)}


def main() -> None:
    env = make()
    warm = measured_warmup(env, env.action_space.n)
    lv = check_lives(env, warm)
    fit, agree = fit_ram_to_screen(env, warm)
    n_a = env.action_space.n
    env.close()
    print(f"PRE-FLIGHT  lives byte takes values {lv['values']}, fell {lv['drops']}x, "
          f"rose {lv['rises']}x -> {'usable' if lv['ok'] else 'NOT usable'}")
    print(f"            oracle r_x {agree['r_x']:.3f} r_y {agree['r_y']:.3f}\n")
    if not lv["ok"]:
        sys.exit("the lives byte is not a life counter; deaths cannot be counted from it")

    print("PART B (i) — ARE THE RULES EVEN LEGIBLE? Does a button determine which way the body goes?")
    bm = button_map(warm, fit)
    print(f"  across {bm['n']} moves the nine actions' mean displacements spread {bm['spread_px']:.2f} px")
    print(f"  shuffling which button was pressed gives {bm['null_mean']:.2f} px "
          f"(95th pct {bm['null_p95']:.2f}),  p = {bm['p']:.4f}")
    print(f"  -> the button-to-direction rule IS{'' if bm['p'] < 0.05 else ' NOT'} present in the data "
          f"the agent sees\n")

    print("PART A — WHAT THE NUMBER ACTUALLY IS. Same agents, played to game over instead of 400 steps.\n")
    rows = {}
    for name, state, train in (("random", "ego", False), ("whole-screen", "whole", True),
                               ("egocentric, supplied body", "ego", True)):
        mem = Memory(n_a) if train else None
        if train:                       # a short warm-up so the table is not empty on the scored run
            for s in range(6):
                full_episode(state, warm, 700 + s, mem=mem, fit=fit, cap=400)
        runs = [full_episode(state, warm, 800 + s, mem=mem, fit=fit) for s in range(5)]
        rows[name] = {k: float(np.mean([r[k] for r in runs])) for k in
                      ("score", "steps", "pellets", "deaths")}
        rows[name]["scores"] = [r["score"] for r in runs]
        rows[name]["capped"] = sum(r["capped"] for r in runs)
        r = rows[name]
        print(f"  {name:28} score {r['score']:>7.0f}   lasted {r['steps']:>5.0f} steps   "
              f"pellets {r['pellets']:>5.1f}   deaths {r['deaths']:.1f}")

    print(f"\n  published, one episode to game over: random {REF['random']:.0f}, "
          f"DQN {REF['DQN']:.0f}, human {REF['human']:.0f}")
    best = max(rows, key=lambda k: rows[k]["score"])
    print(f"  best here: {best} at {rows[best]['score']:.0f}")

    print("\nPART B (ii) — DOES IT KNOW GHOSTS HURT AND PELLETS PAY? Per thousand steps, vs random.")
    R = rows["random"]
    for name in ("whole-screen", "egocentric, supplied body"):
        r = rows[name]
        dr = 1000 * r["deaths"] / max(r["steps"], 1)
        pr = 1000 * r["pellets"] / max(r["steps"], 1)
        d0 = 1000 * R["deaths"] / max(R["steps"], 1)
        p0 = 1000 * R["pellets"] / max(R["steps"], 1)
        print(f"  {name:28} deaths {dr:>6.1f} (random {d0:.1f})   "
              f"pellets {pr:>6.1f} (random {p0:.1f})")
        print(f"  {'':28} -> dies {'LESS' if dr < d0 else 'MORE'} than random, "
              f"eats {'MORE' if pr > p0 else 'LESS'}")

    print("\nPART C — IS THE LEARNER THE LIMIT? Same state, same games, a bigger memory.")
    cap_rows = {}
    for cap in (4000, 20000):
        mem = Memory(n_a, cap=cap)
        for s in range(6):
            full_episode("ego", warm, 700 + s, mem=mem, fit=fit, cap=400)
        runs = [full_episode("ego", warm, 800 + s, mem=mem, fit=fit) for s in range(5)]
        cap_rows[cap] = float(np.mean([r["score"] for r in runs]))
        print(f"  memory {cap:>6} slots   score {cap_rows[cap]:>7.0f}")
    print(f"  -> a 5x table is worth {cap_rows[20000] - cap_rows[4000]:+.0f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"lives_check": lv, "oracle": agree, "button_map": bm,
                               "full_episodes": rows, "memory_size": cap_rows,
                               "reference": REF}, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
