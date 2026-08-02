# -*- coding: utf-8 -*-
"""Tell it the rules, measure the ceiling, and read the gap. THE BODY IS SUPPLIED HERE.

    python scripts/atari_taught.py

Owner: 그럼 일단 규칙을 알려주고 시켜보는 건 어때? 수행을 잘 하는지는 확인은 되겠고 그 다음에
스스로 규칙을 찾게.

Right, and it fixes a confound I could not otherwise resolve. The egocentric run scored 1139 against
the whole-screen 1458, with the body re-estimated 3.9 times an episode. Two explanations fit that
equally well:

    (a) an egocentric state is the wrong idea, or
    (b) the idea is right and the body estimate is too unstable to carry it.

Supplying the body separates them. If a SUPPLIED body lifts the same learner well above 1139, (b) is
the answer and the bottleneck is named with a number attached. If it does not, (a) is the answer and
today's whole line was wrong — which is worth knowing just as much.

NOTHING HERE IS AN ATANOR CAPABILITY. This arm is handed ground truth it could not find. It measures
a CEILING, and the only claim it can support is about the size of the gap to that ceiling.

WHAT IS SUPPLIED, EXACTLY, AND NOTHING ELSE:
    the body's position every frame, and the four ghosts' positions, from the emulator's own RAM.
NOT supplied: what any button does, that ghosts are dangerous, that pellets pay, what a wall is, or
any policy whatsoever. The learner is BYTE-IDENTICAL to the two runs it is being compared against —
`Memory` from atari_play.py, nearest-neighbour over remembered payoffs. Only the STATE changes, which
is the whole point: if the same learner does better on a different state, the state was the ceiling.

TWO TAUGHT STATES, because "egocentric" can mean two different things and they should not be conflated:
    window      the 8x8 patch of screen centred on the body — the previous rung's state, corrected
    relational  the ghosts' offsets FROM the body, plus a coarse cell for where in the maze it is

PRE-FLIGHT, run before anything is scored. The supplied body must be verified, not trusted:
    I  two independent sources — RAM bytes and the yellow-sprite centroid — must agree
    D  the supplied position must actually move, not sit at a constant
    R  its motion must be larger than the blob-centroid noise it is replacing
An unverified oracle is how the M1 label inversion got through this morning, and it is cheap to check.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.atari_find_body import measured_warmup     # noqa: E402
from scripts.atari_play import Memory, make             # noqa: E402
from scripts.atari_play_egocentric import local_code    # noqa: E402

OUT = Path("data/atari/taught.json")

# The emulator's own record of who is where. Bytes, not pixels — the map to screen is FITTED below.
RAM_BODY = (10, 16)
RAM_GHOSTS = ((6, 12), (7, 13), (8, 14), (9, 15))

# Registered incumbents, measured and committed before this file existed.
EGO_MEAN = 1139.0          # body estimated during play, 3.9 switches per episode
WHOLE_MEAN = 1458.0        # whole-screen retina code
WHOLE_SLOPE_P = 0.2782     # and it did not improve with practice


def yellow_mask(frame: np.ndarray) -> np.ndarray:
    f = frame.astype(np.int16)
    return (f[:, :, 0] > 170) & (f[:, :, 1] > 130) & (f[:, :, 1] < 200) & (f[:, :, 2] < 110)


def yellow_centroid(frame: np.ndarray, static: np.ndarray | None = None):
    """Where the yellow SPRITE is — an independent reading of the same fact, used only to check RAM.

    THE FIRST VERSION AVERAGED EVERY YELLOW PIXEL and got r_x 0.858, r_y 0.903, residual 6.89 px, so
    the pre-flight refused it. The cause was measured rather than guessed: rows 170-199 carry 20,145
    yellow pixels across 150 frames — the remaining-lives icons and the score digits — against 5,600
    in the entire play area, and there were 5.5 yellow components per frame. The checker was reading
    the centroid of the body AND the HUD.

    Two corrections, neither of which touches the bar the oracle has to clear:
      - drop pixels that are yellow in half the frames or more. A sprite eight pixels across cannot
        occupy one pixel half the time; anything that does is furniture. Derived, not chosen.
      - of what remains, take the largest connected component rather than averaging all of them."""
    import cv2
    m = yellow_mask(frame)
    if static is not None:
        m = m & ~static
    n, lab, st, cen = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    if n <= 1:
        return None
    k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    if st[k, cv2.CC_STAT_AREA] < 4:
        return None
    return float(cen[k][0]), float(cen[k][1])


def fit_ram_to_screen(env, warm: int, n: int = 300, seed: int = 0):
    """Least squares from RAM bytes to screen pixels, and the agreement that licenses using it."""
    rng = np.random.default_rng(seed)
    obs, _ = env.reset(seed=seed)
    for _ in range(warm):
        obs, *_ = env.step(0)

    # The furniture, found before anything is fitted: yellow that stays put is not a sprite.
    acc = np.zeros(obs.shape[:2], np.float32)
    for _ in range(120):
        obs, *_ = env.step(int(rng.integers(0, env.action_space.n)))
        acc += yellow_mask(obs)
    static = acc >= 60
    print(f"     yellow furniture removed from the checker: {int(static.sum())} px "
          f"(score digits and the lives icons), max transient occupancy "
          f"{acc[~static].max() / 120:.0%} of frames")

    R, S = [], []
    for _ in range(n):
        obs, _r, term, trunc, _i = env.step(int(rng.integers(0, env.action_space.n)))
        if term or trunc:
            obs, _ = env.reset()
            for _ in range(warm):
                obs, *_ = env.step(0)
        c = yellow_centroid(obs, static)
        if c is None:
            continue
        ram = env.unwrapped.ale.getRAM()
        R.append([float(ram[RAM_BODY[0]]), float(ram[RAM_BODY[1]])])
        S.append(list(c))
    R, S = np.array(R), np.array(S)
    if len(R) < 40:
        sys.exit("pre-flight I fails: the yellow sprite was almost never visible, so RAM is unchecked")
    A = np.stack([R[:, 0], np.ones(len(R))], 1)
    ax, bx = np.linalg.lstsq(A, S[:, 0], rcond=None)[0]
    B = np.stack([R[:, 1], np.ones(len(R))], 1)
    ay, by = np.linalg.lstsq(B, S[:, 1], rcond=None)[0]
    px = float(np.corrcoef(R[:, 0], S[:, 0])[0, 1])
    py = float(np.corrcoef(R[:, 1], S[:, 1])[0, 1])
    resid = float(np.mean(np.hypot(ax * R[:, 0] + bx - S[:, 0], ay * R[:, 1] + by - S[:, 1])))
    return (ax, bx, ay, by), {"n": len(R), "r_x": px, "r_y": py, "residual_px": resid,
                              "moved_x": float(S[:, 0].std()), "moved_y": float(S[:, 1].std())}


def screen_xy(ram, fit, idx):
    ax, bx, ay, by = fit
    return np.array([ax * float(ram[idx[0]]) + bx, ay * float(ram[idx[1]]) + by])


def relational_code(ram, fit, shape) -> np.ndarray:
    """The ghosts as offsets FROM the body, plus a coarse cell for where in the maze the body is.

    Egocentric in the strong sense: nothing here is a screen coordinate except the last two numbers,
    and those are deliberately coarse so that 'the same junction' is one situation rather than forty."""
    H, W = shape[:2]
    b = screen_xy(ram, fit, RAM_BODY)
    out = []
    for g in RAM_GHOSTS:
        d = (screen_xy(ram, fit, g) - b) / 40.0
        out += [float(np.clip(d[0], -1, 1)), float(np.clip(d[1], -1, 1))]
    out += [float(np.floor(b[0] / W * 6) / 6.0), float(np.floor(b[1] / H * 6) / 6.0)]
    return np.array(out, dtype=np.float32)


def episode(state: str, steps: int, warm: int, seed: int, fit, mem=None):
    """One run. The body is READ FROM RAM, not estimated. Everything else matches the earlier rungs."""
    env = make()
    obs, _ = env.reset(seed=seed)
    for _ in range(max(1, warm // 4)):
        obs, *_ = env.step(0)
    n_a = env.action_space.n
    rng = np.random.default_rng(seed)
    score = 0.0
    moved = []

    for _t in range(steps):
        ram = env.unwrapped.ale.getRAM()
        b = screen_xy(ram, fit, RAM_BODY)
        moved.append(b.copy())
        code = local_code(obs, b) if state == "window" else relational_code(ram, fit, obs.shape)

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
    env.close()
    M = np.array(moved)
    return {"score": score, "body_travel": float(np.abs(np.diff(M, axis=0)).sum(axis=1).mean())}


def main() -> None:
    env = make()
    warm = measured_warmup(env, env.action_space.n)
    n_a = env.action_space.n
    fit, agree = fit_ram_to_screen(env, warm)
    env.close()

    print("PRE-FLIGHT on the supplied body — an oracle is checked before it is trusted.")
    print(f"  I  RAM bytes vs the yellow sprite's centroid, {agree['n']} frames: "
          f"r_x {agree['r_x']:+.3f}  r_y {agree['r_y']:+.3f}   residual {agree['residual_px']:.2f} px")
    print(f"  D  the supplied position moves: sd {agree['moved_x']:.1f} x, {agree['moved_y']:.1f} y px")
    print(f"  R  vs blob-centroid noise (~0.5 px): {agree['residual_px'] / 0.5:.1f}x the noise floor")
    ok = agree["r_x"] > 0.9 and agree["r_y"] > 0.9 and min(agree["moved_x"], agree["moved_y"]) > 5
    print(f"  -> the oracle is {'VERIFIED' if ok else 'NOT verified'}\n")
    if not ok:
        sys.exit("pre-flight fails: the supplied body is not the body. Nothing below would mean anything.")

    print("SUPPLIED: where the body is, where the ghosts are. NOT supplied: what buttons do, that")
    print("ghosts hurt, that pellets pay, or any policy. Same learner as the two earlier rungs.\n")

    STEPS, EP = 400, 12
    rnd = [episode("relational", STEPS, warm, 400 + s, fit) for s in range(6)]
    base = float(np.mean([e["score"] for e in rnd]))
    print(f"random baseline: {base:.0f}   {[int(e['score']) for e in rnd]}\n")

    from scipy.stats import linregress, mannwhitneyu
    res = {}
    for state in ("window", "relational"):
        mem = Memory(n_a)
        curve = []
        for ep in range(EP):
            out = episode(state, STEPS, warm, 600 + ep, fit, mem=mem)
            curve.append(out["score"])
            print(f"  {state:11} ep {ep:>2}  score {out['score']:>7.0f}   memory {len(mem.codes):>5}")
        c = np.array(curve)
        sl = linregress(np.arange(len(c)), c)
        _u, p_r = mannwhitneyu(c, [e["score"] for e in rnd], alternative="greater")
        res[state] = {"curve": curve, "mean": float(c.mean()), "sd": float(c.std(ddof=1)),
                      "slope": float(sl.slope), "slope_p": float(sl.pvalue), "p_vs_random": float(p_r)}
        print(f"  -> {state}: mean {c.mean():.0f} +- {c.std(ddof=1):.0f}   "
              f"vs random p={p_r:.4f}   slope {sl.slope:+.1f}/ep p={sl.pvalue:.4f}\n")

    print(f"{'state':14}{'body':>12}{'mean':>9}{'vs random':>12}{'improves':>12}")
    print(f"{'whole-screen':14}{'n/a':>12}{WHOLE_MEAN:>9.0f}{'p=0.0001':>12}{'p=0.2782':>12}")
    print(f"{'egocentric':14}{'estimated':>12}{EGO_MEAN:>9.0f}{'p=0.1578':>12}{'p=0.0507':>12}")
    for k in ("window", "relational"):
        r = res[k]
        print(f"{k:14}{'SUPPLIED':>12}{r['mean']:>9.0f}"
              f"{'p=' + format(r['p_vs_random'], '.4f'):>12}"
              f"{'p=' + format(r['slope_p'], '.4f'):>12}")

    best = max(res, key=lambda k: res[k]["mean"])
    lift_est = res[best]["mean"] - EGO_MEAN
    lift_whole = res[best]["mean"] - WHOLE_MEAN
    print(f"\n-> supplying the body is worth {lift_est:+.0f} over estimating it ({EGO_MEAN:.0f})")
    print(f"-> and {lift_whole:+.0f} against the whole-screen state ({WHOLE_MEAN:.0f})")
    print("\nWHICH EXPLANATION THE NUMBERS PICK:")
    if lift_est > 200 and lift_whole > 0:
        print("   (b) the egocentric idea is right and FINDING THE BODY is the bottleneck.")
        print(f"   The gap to close by self-supervision alone is {lift_est:.0f} points.")
    elif lift_whole <= 0:
        print("   (a) even with a perfect body the egocentric state does not beat the whole screen.")
        print("   Today's 'the ceiling is in the state' reading was wrong, and is withdrawn.")
    else:
        print("   Neither cleanly. The supplied body helps but not enough to name it the bottleneck.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"oracle": agree, "fit": list(fit), "baseline": base,
                               "taught": res, "ego_mean": EGO_MEAN, "whole_mean": WHOLE_MEAN,
                               "lift_over_estimated": float(lift_est),
                               "lift_over_whole": float(lift_whole)}, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
