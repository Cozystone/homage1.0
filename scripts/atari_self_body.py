# -*- coding: utf-8 -*-
"""Find the body without being told, by accumulating over space instead of over identities.

    python scripts/atari_self_body.py

THE DIAGNOSIS NAMED THE REPAIR. With the oracle in hand, the previous rung separated three
explanations for the wandering body estimate and the numbers picked one outright:

    detection     the body is inside a blob in 100.0% of frames, nearest at 0.54 px   -> not this
    the statistic the true body's track ranked 1st of 42 under command_prediction     -> not this
    fragmentation the id holding the body survived 7 frames against the 12 samples the
                  statistic needs, and 66 distinct ids held it across 700 frames      -> THIS

So the statistic I wrote off at 1.48 against a 1.5 bar was never the problem. It was starved: the
evidence was thrown away and restarted before enough of it existed to weigh.

THE REPAIR, WHICH USES NOTHING SUPERVISED. Track identity dies because matching refuses a jump it
cannot justify — correct for tracking, fatal for accumulation. A CHAIN does not refuse: seed at some
blob and, every frame, continue to the nearest blob, whatever it is. A chain can be wrong, and it
cannot die, so evidence accumulates for as long as the game runs. Wrongness is then a matter for the
statistic rather than for the plumbing, which is where it belongs.

    ids     42 tracks, median 7 frames of evidence each
    chains  one per seed, 700 frames of evidence each, no identity assumed anywhere

WHAT IS SUPERVISED HERE AND WHAT IS NOT. The chains and the choice among them use only pixels, the
buttons pressed, and nothing else. The oracle appears exactly once, AFTER the choice is made, to say
in pixels how often the choice was right. Nothing is fitted to it. If any threshold below were tuned
against it this rung would be worthless, so there are none: the winner is the argmax and that is all.

THEN IT GOES BACK INTO THE GAME, against three numbers already registered and committed:
    1139   the body estimated by track ids, 3.9 switches an episode
    1458   the whole-screen state, no body at all
    1798   the body SUPPLIED from RAM — the ceiling, and 658 of it is what this has to win back
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.atari_babble import blobs, sprite_mask                        # noqa: E402
from scripts.atari_find_body import command_prediction, measured_warmup    # noqa: E402
from scripts.atari_play import Memory, make                                # noqa: E402
from scripts.atari_play_egocentric import local_code                       # noqa: E402
from scripts.atari_taught import RAM_BODY, fit_ram_to_screen, screen_xy    # noqa: E402

OUT = Path("data/atari/self_body.json")
EGO_MEAN, WHOLE_MEAN, TAUGHT_MEAN = 1139.0, 1458.0, 1798.0


class Chains:
    """Several hypotheses about which moving thing is me, each one a nearest-blob continuation.

    No identity is claimed and none is needed. Every frame each chain steps to whatever blob is
    closest to where it was; the statistic decides afterwards which chain was worth following."""

    def __init__(self, seeds: list, n_max: int = 10):
        self.pos = [np.array(s[:2], float) for s in seeds[:n_max]]
        self.ev: list[list] = [[] for _ in self.pos]

    def step(self, cur: list, action: int) -> None:
        if not cur:
            return
        P = np.array([c[:2] for c in cur], float)
        for i, p in enumerate(self.pos):
            j = int(np.argmin(np.hypot(P[:, 0] - p[0], P[:, 1] - p[1])))
            d = P[j] - p
            if abs(d[0]) > 0.5 or abs(d[1]) > 0.5:
                self.ev[i].append((action, float(d[0]), float(d[1])))
            self.pos[i] = P[j]

    def best(self) -> int | None:
        """The chain whose displacements the button presses predict best. Argmax, no threshold."""
        s = [command_prediction(e) if len(e) >= 12 else -1.0 for e in self.ev]
        return int(np.argmax(s)) if max(s) > 0 else None

    def scores(self) -> list:
        return [command_prediction(e) if len(e) >= 12 else float("nan") for e in self.ev]


def measure(steps: int = 700, seed: int = 3):
    """Run the chains unsupervised, then ask the oracle — once, afterwards — how right they were."""
    env = make()
    warm = measured_warmup(env, env.action_space.n)
    fit, agree = fit_ram_to_screen(env, warm, seed=seed)
    env.close()
    if not (agree["r_x"] > 0.9 and agree["r_y"] > 0.9):
        sys.exit("the oracle failed its own check; a pixel score against it would mean nothing")

    env = make()
    obs, _ = env.reset(seed=seed)
    for _ in range(warm):
        obs, *_ = env.step(0)
    rng = np.random.default_rng(seed)
    n_a = env.action_space.n
    buf = []
    for _ in range(40):
        obs, *_ = env.step(int(rng.integers(0, n_a)))
        buf.append(obs)
    bg = np.median(np.array(buf, dtype=np.int16), axis=0)

    ch = Chains(blobs(sprite_mask(obs, bg)))
    hist, truths = [], []
    for _t in range(steps):
        a = int(rng.integers(0, n_a))
        for _ in range(3):
            obs, _r, term, trunc, _i = env.step(a)
            if term or trunc:
                obs, _ = env.reset()
                for _ in range(warm):
                    obs, *_ = env.step(0)
        ch.step(blobs(sprite_mask(obs, bg)), a)
        hist.append([p.copy() for p in ch.pos])
        truths.append(screen_xy(env.unwrapped.ale.getRAM(), fit, RAM_BODY))
    env.close()

    b = ch.best()
    T = np.array(truths)
    per = []
    for i in range(len(ch.pos)):
        P = np.array([h[i] for h in hist])
        per.append(float(np.mean(np.hypot(P[:, 0] - T[:, 0], P[:, 1] - T[:, 1]) < 8.0)))
    return ch, b, per, agree


def episode(steps: int, warm: int, seed: int, mem=None):
    """Play with the body found by chains DURING the episode. Nothing supplied, nothing carried in."""
    env = make()
    obs, _ = env.reset(seed=seed)
    for _ in range(max(1, warm // 4)):
        obs, *_ = env.step(0)
    n_a = env.action_space.n
    rng = np.random.default_rng(seed)
    buf = []
    for _ in range(40):
        obs, *_ = env.step(int(rng.integers(0, n_a)))
        buf.append(obs)
    bg = np.median(np.array(buf, dtype=np.int16), axis=0)

    ch = Chains(blobs(sprite_mask(obs, bg)))
    body = np.array([obs.shape[1] / 2, obs.shape[0] / 2])
    score, switches, last = 0.0, 0, None
    for t in range(steps):
        code = local_code(obs, body)
        if mem is None:
            a = int(rng.integers(0, n_a))
        else:
            q = mem.recall(code)
            if np.all(np.isnan(q)) or rng.random() < 0.15:
                a = int(rng.integers(0, n_a))
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
        if mem is not None:
            mem.learn(code, a, pay)

        ch.step(blobs(sprite_mask(obs, bg)), a)
        if t % 25 == 24:
            b = ch.best()
            if b is not None:
                if last is not None and b != last:
                    switches += 1
                last = b
        if last is not None:
            body = ch.pos[last]
    env.close()
    return {"score": score, "switches": switches}


def main() -> None:
    ch, b, per, agree = measure()
    s = ch.scores()
    print(f"oracle verified: r_x {agree['r_x']:.3f} r_y {agree['r_y']:.3f}, "
          f"residual {agree['residual_px']:.2f} px\n")
    print(f"{len(ch.pos)} chains, each with {len(ch.ev[0])} frames of evidence "
          f"(track ids gave a median of 7)\n")
    print(f"{'chain':8}{'command prediction':>22}{'frames within 8px of the body':>32}")
    for i in range(len(ch.pos)):
        mark = "  <- chosen, unsupervised" if i == b else ""
        print(f"{i:<8}{s[i]:>22.4f}{per[i]:>31.1%}{mark}")

    chosen = per[b] if b is not None else 0.0
    others = [per[i] for i in range(len(per)) if i != b]
    print(f"\n-> the chain the statistic picked is on the body {chosen:.1%} of frames")
    print(f"   the rest average {np.mean(others):.1%}; picking at random would give {np.mean(per):.1%}")
    print(f"-> the statistic picked the BEST available chain: "
          f"{b == int(np.argmax(per))} (best was {int(np.argmax(per))} at {max(per):.1%})")

    env = make()
    warm = measured_warmup(env, env.action_space.n)
    n_a = env.action_space.n
    env.close()
    print("\nBack into the game with that body. Nothing supplied.\n")
    STEPS, EP = 400, 12
    rnd = [episode(STEPS, warm, 400 + i)["score"] for i in range(6)]
    print(f"random baseline: {np.mean(rnd):.0f}   {[int(x) for x in rnd]}\n")

    mem = Memory(n_a)
    curve, sw = [], []
    for ep in range(EP):
        o = episode(STEPS, warm, 600 + ep, mem=mem)
        curve.append(o["score"])
        sw.append(o["switches"])
        print(f"  episode {ep:>2}  score {o['score']:>7.0f}   chain switched {o['switches']:>2}x")

    c = np.array(curve)
    from scipy.stats import linregress, mannwhitneyu, spearmanr
    _u, p_r = mannwhitneyu(c, rnd, alternative="greater")
    sl = linregress(np.arange(len(c)), c)
    rho, p_s = spearmanr(np.arange(len(c)), c)

    print(f"\n{'state':16}{'body':>14}{'mean':>8}{'vs random':>12}{'improves':>14}")
    print(f"{'whole-screen':16}{'none':>14}{WHOLE_MEAN:>8.0f}{'p=0.0001':>12}{'p=0.28':>14}")
    print(f"{'egocentric':16}{'track ids':>14}{EGO_MEAN:>8.0f}{'p=0.1578':>12}{'p=0.05':>14}")
    print(f"{'egocentric':16}{'CHAINS':>14}{c.mean():>8.0f}"
          f"{'p=' + format(p_r, '.4f'):>12}{'rho=' + format(rho, '+.2f'):>14}")
    print(f"{'egocentric':16}{'SUPPLIED':>14}{TAUGHT_MEAN:>8.0f}{'p=0.0014':>12}{'rho=+0.74':>14}")

    gap = TAUGHT_MEAN - EGO_MEAN
    won = c.mean() - EGO_MEAN
    print(f"\n-> of the {gap:.0f} points a supplied body was worth, chains win back {won:+.0f} "
          f"({won / gap:.0%})")
    print(f"-> chain switched {np.mean(sw):.1f}x per episode against 3.9 for track ids")
    print(f"-> improves with practice: slope p={sl.pvalue:.4f}, Spearman p={p_s:.4f}  "
          f"{'YES' if p_s < 0.05 else 'not established'}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"oracle": agree, "chain_scores": [float(x) for x in s],
                               "chain_on_body": per, "chosen": b, "chosen_on_body": float(chosen),
                               "curve": curve, "switches": sw, "mean": float(c.mean()),
                               "p_vs_random": float(p_r), "slope_p": float(sl.pvalue),
                               "spearman_rho": float(rho), "spearman_p": float(p_s),
                               "recovered_frac": float(won / gap)}, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
