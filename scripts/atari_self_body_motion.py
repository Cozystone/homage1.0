# -*- coding: utf-8 -*-
"""Continue toward what MOVES, not toward what is near. One variable changed, paired against the old.

    python scripts/atari_self_body_motion.py

THE PREVIOUS RUNG FAILED AND MEASURED ITS OWN CAUSE. Chains -- seed at a blob, step every frame to the
nearest one -- were meant to accumulate evidence where track ids could not. The chosen chain landed on
the body 0.6% of frames against 4.1% for picking one at random, and each chain gathered 36 frames of
motion evidence out of 700, meaning the chains sat still 95% of the time.

Nearest-blob continuation is a STATIC-BLOB SINK. The body outruns the chain; the nearest blob on the
next frame is the stationary neighbour it left behind. Seven of nine chains sank. The two that did not
are the ones that scored 16.6% and 18.0%.

THE ONE CHANGE: a chain may only continue to a blob that MOVED this frame. Same 0.5 px threshold
already used everywhere in this line, so no new free parameter, and nothing else differs -- same
seeds, same blobs, same statistic, same window, same learner. If the statistic now ranks the body
first it is because the candidates stopped being furniture.

THE COMPARISON IS PAIRED THIS TIME, which the last one was not. Both continuations run inside the SAME
rollout on the SAME blobs, and both play the SAME twelve episode seeds. Last rung's 1362 against 1139
came from different runs and no test was possible; a difference here is a difference on matched games.

REGISTERED BEFORE RUNNING, and all four have to be read out whichever way they fall:
    1  the chosen chain is on the body more often than chance -- the last version got 0.6% vs 4.1%
    2  the statistic picks the best chain available to it -- last time it picked 3 when 4 was best
    3  evidence per chain rises well above the starved 36 frames
    4  in the game: against 1139 estimated, 1458 whole-screen, and the 1798 supplied ceiling
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.atari_babble import blobs, match, sprite_mask                 # noqa: E402
from scripts.atari_find_body import command_prediction, measured_warmup    # noqa: E402
from scripts.atari_play import Memory, make                                # noqa: E402
from scripts.atari_play_egocentric import local_code                       # noqa: E402
from scripts.atari_taught import RAM_BODY, fit_ram_to_screen, screen_xy    # noqa: E402

OUT = Path("data/atari/self_body_motion.json")
EGO_MEAN, WHOLE_MEAN, TAUGHT_MEAN = 1139.0, 1458.0, 1798.0
CHANCE_ON_BODY, OLD_CHOSEN_ON_BODY = 0.041, 0.006


class Chains:
    """Hypotheses about which moving thing is me. `motion` decides what a chain may continue to.

    motion=False   the nearest blob, whatever it is           -- the sink, kept as the control
    motion=True    the nearest blob THAT MOVED this frame     -- the repair
    A chain that finds no moving candidate holds still rather than falling onto furniture."""

    def __init__(self, seeds: list, motion: bool, n_max: int = 10):
        self.motion = motion
        self.pos = [np.array(s[:2], float) for s in seeds[:n_max]]
        self.ev: list[list] = [[] for _ in self.pos]
        self.held = 0

    def step(self, prev: list, cur: list, action: int) -> None:
        if not cur:
            return
        if self.motion:
            keep = [i1 for _i0, i1, dx, dy in match(prev, cur, max_jump=12.0)
                    if abs(dx) > 0.5 or abs(dy) > 0.5]
            if not keep:
                self.held += 1
                return
            cand = [cur[i] for i in keep]
        else:
            cand = cur
        P = np.array([c[:2] for c in cand], float)
        for i, p in enumerate(self.pos):
            j = int(np.argmin(np.hypot(P[:, 0] - p[0], P[:, 1] - p[1])))
            d = P[j] - p
            if abs(d[0]) > 0.5 or abs(d[1]) > 0.5:
                self.ev[i].append((action, float(d[0]), float(d[1])))
            self.pos[i] = P[j]

    def best(self):
        s = [command_prediction(e) if len(e) >= 12 else -1.0 for e in self.ev]
        return int(np.argmax(s)) if max(s) > 0 else None

    def scores(self):
        return [command_prediction(e) if len(e) >= 12 else float("nan") for e in self.ev]


def measure(steps: int = 700, seed: int = 3):
    """Both continuations, same rollout, same blobs. The oracle speaks once, at the end."""
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
    n_a = env.action_space.n
    rng = np.random.default_rng(seed)
    buf = []
    for _ in range(40):
        obs, *_ = env.step(int(rng.integers(0, n_a)))
        buf.append(obs)
    bg = np.median(np.array(buf, dtype=np.int16), axis=0)

    prev = blobs(sprite_mask(obs, bg))
    arms = {"nearest": Chains(prev, motion=False), "moving": Chains(prev, motion=True)}
    hist = {k: [] for k in arms}
    truths = []
    for _t in range(steps):
        a = int(rng.integers(0, n_a))
        for _ in range(3):
            obs, _r, term, trunc, _i = env.step(a)
            if term or trunc:
                obs, _ = env.reset()
                for _ in range(warm):
                    obs, *_ = env.step(0)
        cur = blobs(sprite_mask(obs, bg))
        for k, ch in arms.items():
            ch.step(prev, cur, a)
            hist[k].append([p.copy() for p in ch.pos])
        prev = cur
        truths.append(screen_xy(env.unwrapped.ale.getRAM(), fit, RAM_BODY))
    env.close()

    T = np.array(truths)
    out = {}
    for k, ch in arms.items():
        per = []
        for i in range(len(ch.pos)):
            P = np.array([h[i] for h in hist[k]])
            per.append(float(np.mean(np.hypot(P[:, 0] - T[:, 0], P[:, 1] - T[:, 1]) < 8.0)))
        out[k] = {"chain": ch, "on_body": per, "best": ch.best(),
                  "evidence": [len(e) for e in ch.ev], "held": ch.held}
    return out, agree


def episode(steps: int, warm: int, seed: int, motion: bool, mem=None):
    """Play with the body the chains found during this very episode. Nothing supplied."""
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

    prev = blobs(sprite_mask(obs, bg))
    ch = Chains(prev, motion=motion)
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
        cur = blobs(sprite_mask(obs, bg))
        ch.step(prev, cur, a)
        prev = cur
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
    res, agree = measure()
    print(f"oracle verified: r_x {agree['r_x']:.3f} r_y {agree['r_y']:.3f}, "
          f"residual {agree['residual_px']:.2f} px\n")
    print(f"{'continuation':14}{'evidence/chain':>16}{'chosen chain':>14}"
          f"{'on the body':>14}{'best chain':>13}{'picked best':>13}")
    for k in ("nearest", "moving"):
        r = res[k]
        b = r["best"]
        on = r["on_body"][b] if b is not None else float("nan")
        bi = int(np.argmax(r["on_body"]))
        print(f"{k:14}{np.mean(r['evidence']):>16.0f}{str(b):>14}{on:>13.1%}"
              f"{format(r['on_body'][bi], '.1%') + ' (#' + str(bi) + ')':>13}"
              f"{str(b == bi):>13}")
    print(f"\n   chance, if a chain were picked at random: "
          f"nearest {np.mean(res['nearest']['on_body']):.1%}, "
          f"moving {np.mean(res['moving']['on_body']):.1%}")
    print(f"   the moving arm held still on {res['moving']['held']} of 700 frames "
          f"(no candidate had moved)")

    mv = res["moving"]
    chosen = mv["on_body"][mv["best"]] if mv["best"] is not None else 0.0
    print(f"\n-> 1. beats chance: {chosen > np.mean(mv['on_body'])}  "
          f"({chosen:.1%} vs {np.mean(mv['on_body']):.1%}; the old version got "
          f"{OLD_CHOSEN_ON_BODY:.1%} vs {CHANCE_ON_BODY:.1%})")
    print(f"-> 2. statistic picked the best chain: "
          f"{mv['best'] == int(np.argmax(mv['on_body']))}")
    print(f"-> 3. evidence per chain: {np.mean(mv['evidence']):.0f} frames "
          f"(the starved version had 36)")

    env = make()
    warm = measured_warmup(env, env.action_space.n)
    n_a = env.action_space.n
    env.close()
    print("\nBoth continuations into the game, on the SAME twelve seeds. Nothing supplied.\n")
    STEPS, EP = 400, 12
    rnd = [episode(STEPS, warm, 400 + i, motion=True)["score"] for i in range(4)]
    print(f"random baseline: {np.mean(rnd):.0f}   {[int(x) for x in rnd]}\n")

    curves, sws = {}, {}
    for k, mo in (("nearest", False), ("moving", True)):
        mem = Memory(n_a)
        c, s = [], []
        for ep in range(EP):
            o = episode(STEPS, warm, 600 + ep, motion=mo, mem=mem)
            c.append(o["score"])
            s.append(o["switches"])
        curves[k], sws[k] = c, s
        print(f"  {k:8} {[int(x) for x in c]}")

    from scipy.stats import linregress, mannwhitneyu, spearmanr, wilcoxon
    A, B = np.array(curves["nearest"]), np.array(curves["moving"])
    try:
        _w, p_pair = wilcoxon(B, A, alternative="greater")
    except ValueError:
        p_pair = float("nan")
    _u, p_r = mannwhitneyu(B, rnd, alternative="greater")
    sl = linregress(np.arange(len(B)), B)
    rho, p_s = spearmanr(np.arange(len(B)), B)

    print(f"\n{'state':16}{'body':>18}{'mean':>8}{'vs random':>12}{'improves':>14}")
    print(f"{'whole-screen':16}{'none':>18}{WHOLE_MEAN:>8.0f}{'p=0.0001':>12}{'p=0.28':>14}")
    print(f"{'egocentric':16}{'track ids':>18}{EGO_MEAN:>8.0f}{'p=0.1578':>12}{'p=0.05':>14}")
    print(f"{'egocentric':16}{'chains, nearest':>18}{A.mean():>8.0f}{'':>12}{'':>14}")
    print(f"{'egocentric':16}{'chains, MOVING':>18}{B.mean():>8.0f}"
          f"{'p=' + format(p_r, '.4f'):>12}{'rho=' + format(rho, '+.2f'):>14}")
    print(f"{'egocentric':16}{'SUPPLIED':>18}{TAUGHT_MEAN:>8.0f}{'p=0.0014':>12}{'rho=+0.74':>14}")

    gap = TAUGHT_MEAN - EGO_MEAN
    print(f"\n-> 4. paired against the same seeds with nearest-continuation: "
          f"{B.mean() - A.mean():+.0f}, Wilcoxon p={p_pair:.4f}  "
          f"{'REAL' if p_pair < 0.05 else 'not established'}")
    print(f"   of the {gap:.0f} points a supplied body was worth, this wins back "
          f"{B.mean() - EGO_MEAN:+.0f} ({(B.mean() - EGO_MEAN) / gap:.0%})")
    print(f"   switches per episode: nearest {np.mean(sws['nearest']):.1f}, "
          f"moving {np.mean(sws['moving']):.1f}, track ids 3.9")
    print(f"   improves with practice: slope p={sl.pvalue:.4f}, Spearman p={p_s:.4f}  "
          f"{'YES' if p_s < 0.05 else 'not established'}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"oracle": agree,
         "measure": {k: {"on_body": res[k]["on_body"], "best": res[k]["best"],
                         "evidence": res[k]["evidence"], "held": res[k]["held"],
                         "scores": [None if np.isnan(x) else float(x)
                                    for x in res[k]["chain"].scores()]} for k in res},
         "curves": curves, "switches": sws, "random": rnd,
         "mean_moving": float(B.mean()), "mean_nearest": float(A.mean()),
         "p_paired": float(p_pair), "p_vs_random": float(p_r),
         "slope_p": float(sl.pvalue), "spearman_rho": float(rho), "spearman_p": float(p_s)},
        indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
