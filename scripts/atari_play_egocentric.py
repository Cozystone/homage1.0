# -*- coding: utf-8 -*-
"""Play again, but see the world from wherever the body turns out to be. Nobody says where that is.

    python scripts/atari_play_egocentric.py

The whole-screen version beat random by 45% (p=0.0001) and did NOT improve with practice: slope
+25.8 per episode at p=0.28, and episode 0 already scored 1630. Memory helped immediately and did not
accumulate. That is a ceiling in the STATE, not in the learning — a coarse summary of the entire
screen cannot tell "a ghost is to my left" from "a ghost is to my right", so two situations demanding
opposite actions are remembered as one.

SO THE STATE BECOMES EGOCENTRIC, and the body is still not supplied. It is estimated DURING play by
the statistic that failed as a stated task: the body is the blob whose displacement the command
predicts. Every step updates that estimate; the state is a small window of the screen centred on the
current best candidate.

WHY THIS IS A REAL TEST OF THE BY-PRODUCT IDEA. If the estimate is wrong, the window is centred on a
ghost and the state is uninformative, so the score cannot rise. The score is therefore a check on the
body estimate that does not depend on my believing it — which is what "find the body" as a stated
task never had. Body identity emerged more cleanly when nobody asked for it than when it was posed;
here the score asks for it without naming it.

WHAT IS AND IS NOT GIVEN, unchanged: the screen, nine buttons, the score. Not which button does what,
not which sprite is the body, not where the walls are.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.atari_babble import blobs, match, sprite_mask     # noqa: E402
from scripts.atari_find_body import command_prediction, measured_warmup   # noqa: E402
from scripts.atari_play import Memory, make                    # noqa: E402

OUT = Path("data/atari/play_egocentric.json")
WIN = 40          # side of the egocentric window, in screen pixels
CODE = 8          # side it is reduced to


def local_code(frame: np.ndarray, xy) -> np.ndarray:
    """A small view centred on the body. Coarse, like the retina, but LOCAL."""
    import cv2
    H, W = frame.shape[:2]
    x, y = int(xy[0]), int(xy[1])
    h = WIN // 2
    x0, y0 = max(0, min(x - h, W - WIN)), max(0, min(y - h, H - WIN))
    patch = frame[y0:y0 + WIN, x0:x0 + WIN]
    if patch.shape[0] != WIN or patch.shape[1] != WIN:
        patch = cv2.resize(patch.astype(np.float32), (WIN, WIN))
    g = cv2.resize(patch.astype(np.float32).mean(axis=2), (CODE, CODE),
                   interpolation=cv2.INTER_AREA)
    return (g / 255.0).reshape(-1)


def episode(mode: str, steps: int, warm: int, seed: int, mem=None):
    """One run. The body estimate is carried and updated throughout; nothing is told."""
    from packages.perception.attention import frame_signature

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

    tracks: dict[int, list] = defaultdict(list)
    prev = blobs(sprite_mask(obs, bg))
    ids = list(range(len(prev)))
    nxt = len(prev)
    body_id, body_xy = None, np.array([obs.shape[1] / 2, obs.shape[0] / 2])
    score = 0.0
    body_switches = 0

    for t in range(steps):
        code = local_code(obs, body_xy) if mode != "whole" else frame_signature(obs)
        if mem is None or mode == "random":
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
        if mem is not None and mode != "random":
            mem.learn(code, a, pay)

        cur = blobs(sprite_mask(obs, bg))
        new_ids: list = [None] * len(cur)
        for i0, i1, dx, dy in match(prev, cur, max_jump=12.0):
            new_ids[i1] = ids[i0]
            if abs(dx) > 0.5 or abs(dy) > 0.5:
                tracks[ids[i0]].append((a, dx, dy))
        for k in range(len(cur)):
            if new_ids[k] is None:
                new_ids[k] = nxt
                nxt += 1
        prev, ids = cur, new_ids

        # THE BODY ESTIMATE, updated from play. Whichever track the command predicts best.
        if t % 25 == 24:
            best, bid = -1.0, None
            for tr, rows in tracks.items():
                if len(rows) < 12:
                    continue
                s = command_prediction(rows)
                if s > best:
                    best, bid = s, tr
            if bid is not None and bid != body_id:
                body_id = bid
                body_switches += 1
        if body_id is not None and body_id in ids:
            body_xy = np.array(cur[ids.index(body_id)][:2])
    env.close()
    return {"score": score, "body_switches": body_switches, "tracks": len(tracks)}


def main() -> None:
    env = make()
    warm = measured_warmup(env, env.action_space.n)
    n_a = env.action_space.n
    env.close()
    print("Given: the screen, the buttons, the score. The body is ESTIMATED during play.\n")

    STEPS, EP = 400, 12
    rnd = [episode("random", STEPS, warm, seed=400 + s) for s in range(8)]
    base = float(np.mean([e["score"] for e in rnd]))
    print(f"random baseline: {base:.0f}   {[int(e['score']) for e in rnd]}\n")

    mem = Memory(n_a)
    curve, switches = [], []
    for ep in range(EP):
        out = episode("ego", STEPS, warm, seed=600 + ep, mem=mem)
        curve.append(out["score"])
        switches.append(out["body_switches"])
        print(f"  episode {ep:>2}  score {out['score']:>7.0f}   memory {len(mem.codes):>5}   "
              f"body re-estimated {out['body_switches']:>2}x")

    c = np.array(curve)
    R = np.array([e["score"] for e in rnd])
    from scipy.stats import linregress, mannwhitneyu
    u, p_r = mannwhitneyu(c, R, alternative="greater")
    sl = linregress(np.arange(len(c)), c)
    f4, l4 = c[:4].mean(), c[-4:].mean()

    WHOLE_MEAN, WHOLE_SLOPE_P = 1458.0, 0.2782
    print(f"\negocentric  n={len(c)}  mean {c.mean():.0f}  std {c.std(ddof=1):.0f}")
    print(f"whole-screen (previous rung): mean {WHOLE_MEAN:.0f}, slope p={WHOLE_SLOPE_P}\n")
    print(f"-> beats random          : p = {p_r:.4f}   {'REAL' if p_r < 0.05 else 'not established'}")
    print(f"-> improves within the run: slope {sl.slope:+.1f}/ep, p = {sl.pvalue:.4f}   "
          f"{'REAL' if sl.pvalue < 0.05 else 'NOT established'}")
    print(f"   (the whole-screen state did not improve either: p={WHOLE_SLOPE_P})")
    print(f"-> beats the whole-screen state: {c.mean() > WHOLE_MEAN} "
          f"({c.mean():.0f} vs {WHOLE_MEAN:.0f})")
    print(f"   body re-estimated {np.mean(switches):.1f}x per episode — a stable estimate switches rarely")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"baseline": base, "curve": curve, "switches": switches,
                               "mean": float(c.mean()), "p_vs_random": float(p_r),
                               "slope": float(sl.slope), "slope_p": float(sl.pvalue),
                               "first4": float(f4), "last4": float(l4),
                               "whole_screen_mean": WHOLE_MEAN}, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
