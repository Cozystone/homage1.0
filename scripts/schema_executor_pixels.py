# -*- coding: utf-8 -*-
"""Rung A again, PIXELS ONLY. Nothing reads RAM to decide anything — not even to count deaths.

    python scripts/schema_executor_pixels.py [n_episodes]

Owner: 내가 RAM 쓰지말고 픽셀화면 읽고만 판단하게 하랬잖아.

Correct, and the previous rung broke it. `schema_executor_pacman.py` took the body's and the ghosts'
positions from RAM and ACTED on them. Using ground truth as an INSTRUMENT — scoring a pixel method
against it — is a different thing from using it as a PERCEPT, and only the first is allowed. The
result stands as a statement about the executor and does not stand as a statement about the agent.

WHAT CHANGES. Every position now comes from the screen:
    sprites     background subtraction over a rollout, then connected components
    the body    the motion-restricted chain whose displacement the button presses predict best.
                Measured today at 57% of frames on the body, against 4.1% for the version that
                continued to the nearest blob regardless of motion. It is wrong 43% of the time and
                that degradation is part of the result rather than an excuse for it.
    the others  every other moving blob
    DEATHS      counted from the life icons in the HUD, not from RAM byte 123.

THE DEATH COUNTER IS ITSELF AN INSTRUMENT, so it gets a pre-flight before it scores anything: its
count is checked against the RAM byte ONCE, on a throwaway rollout, and if they disagree the run
aborts. That is the allowed use of ground truth — verifying a pixel instrument — and it is the same
discipline that caught the supplied oracle at r_x 0.858 earlier today.

UNCHANGED, so that the comparison is about perception and nothing else: the schema, the executor, the
rollout, the online action-map learning, the three arms, and the two registered comparisons.

    1  avoid dies LESS than random
    2  avoid dies less than chase — the polarity control, without which claim nothing

REGISTERED BEFORE RUNNING: with the body wrong 43% of the time this is expected to be weaker than the
RAM version (avoid 10.56 vs random 12.71, p=0.0132). How much weaker is the number that says what
pixel-level body-finding actually costs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.image_schema import MetricScene, Proximity, choose            # noqa: E402
from scripts.atari_babble import blobs, match, sprite_mask                  # noqa: E402
from scripts.atari_find_body import measured_warmup                         # noqa: E402
from scripts.atari_play import make                                         # noqa: E402
from packages.perception.self_criterion import intention_momentum            # noqa: E402
from scripts.body_across_episodes import appearance                          # noqa: E402
from packages.perception.sprite_tracker import SpriteTracker                  # noqa: E402
from scripts.schema_executor_pacman import ActionMap, HORIZON               # noqa: E402

OUT = Path("data/language/schema_executor_pixels_v8.json")
#: Command-evidence keyed by APPEARANCE, carried across episodes. Track ids fragment -- 66 of them
#: held the body across 700 frames -- and all of those land in one appearance bucket, which took
#: on-body from 42.9% at episode length to 86.7%. The dict is module level on purpose: the body's
#: identity outlives the reset, so its evidence should too.
APPEARANCE_MEMORY: dict = {}


def yellow(frame: np.ndarray) -> np.ndarray:
    f = frame.astype(np.int16)
    return (f[:, :, 0] > 170) & (f[:, :, 1] > 130) & (f[:, :, 1] < 200) & (f[:, :, 2] < 110)


class LifeCounter:
    """Lives read off a band of the HUD. The band is LOCATED ONCE by calibration, then it is pixels.

    The first version derived the play area from background subtraction and got a constant 0. The
    cause was measured rather than guessed: the score digits change every time a pellet is eaten, so
    subtraction calls them moving sprites and the derived 'play area' swallowed the whole HUD. Located
    properly, rows 174-185 hold the spare-life icons and their connected-component count matches the
    emulator's own counter on 100.0% of frames."""

    def __init__(self, r0: int, r1: int):
        self.r0, self.r1 = r0, r1

    def count(self, frame: np.ndarray) -> int:
        import cv2
        m = yellow(frame)[self.r0:self.r1]
        n, _lab, st, _c = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
        return int(sum(1 for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= 6))


def _pick_me(tracks, look, bucket, last_me):
    """Exactly ONE track is the body, chosen inside the appearance bucket by temporal continuity.

    Naming every track in the bucket "me" overwrote its position each frame, so the observed
    displacement was noise, the learned action map never became ready, and the executor steered on 6%
    of steps instead of 70%. An appearance bucket says WHAT the body looks like; it does not say which
    of two same-looking blobs it is, and continuity does."""
    cand = [t for t in tracks if look.get(t.id) == bucket]
    if not cand:
        return None
    if last_me is None:
        return cand[0]
    import numpy as _np
    return min(cand, key=lambda t: float(_np.hypot(t.pos[0] - last_me[0], t.pos[1] - last_me[1])))


def _setup(env, warm: int, rng, n_a: int):
    """Background, play-area extent, and the first blob frame — all from the screen."""
    obs = None
    buf = []
    for _ in range(40):
        obs, *_ = env.step(int(rng.integers(0, n_a)))
        buf.append(obs)
    bg = np.median(np.array(buf, dtype=np.int16), axis=0)
    rows = np.zeros(obs.shape[0], bool)
    for f in buf[-20:]:
        rows |= sprite_mask(f, bg).any(axis=1)
    play_bottom = int(np.nonzero(rows)[0].max()) + 2 if rows.any() else obs.shape[0]
    return bg, play_bottom, obs


def preflight(warm: int, seed: int = 0, steps: int = 700) -> dict:
    """Locate the life display on the screen and verify it. Ground truth is used HERE and nowhere else:
    calibrating an instrument against it is allowed; perceiving with it is not."""
    import cv2
    env = make()
    n_a = env.action_space.n
    rng = np.random.default_rng(seed)
    env.reset(seed=seed)
    for _ in range(warm):
        env.step(0)
    frames, ram = [], []
    for _ in range(steps):
        obs, _r, term, trunc, _i = env.step(int(rng.integers(0, n_a)))
        frames.append(obs)
        ram.append(int(env.unwrapped.ale.getRAM()[123]))
        if term or trunc:
            break
    env.close()
    R = np.array(ram)
    H = frames[0].shape[0]
    best = (-1.0, 0)
    for r0 in range(0, H - 12, 6):
        a = np.array([float(yellow(f)[r0:r0 + 12].sum()) for f in frames])
        if a.std() > 0 and R.std() > 0:
            c = abs(float(np.corrcoef(a, R)[0, 1]))
            if c > best[0]:
                best = (c, r0)
    r0 = best[1]
    lc = LifeCounter(r0, r0 + 12)
    P = np.array([lc.count(f) for f in frames])
    same = float((P == R).mean())
    return {"band": [r0, r0 + 12], "band_corr": best[0], "frames": len(P),
            "exact_agreement": same,
            "pixel_values": sorted(set(P.tolist())), "ram_values": sorted(set(R.tolist())),
            "ok": same > 0.9}


def episode(mode: str, warm: int, seed: int, band, cap: int = 3000):
    env = make()
    n_a = env.action_space.n
    rng = np.random.default_rng(seed)
    obs, _ = env.reset(seed=seed)
    for _ in range(max(1, warm // 4)):
        obs, *_ = env.step(0)
    bg, pb, obs = _setup(env, warm, rng, n_a)
    lc = LifeCounter(band[0], band[1])

    prev_b = blobs(sprite_mask(obs, bg))
    # ATTEMPT 8: the tracker still separates the sprites, but command-evidence is now keyed by
    # APPEARANCE and carried across episodes, which took on-body from 42.9% at episode length to 86.7%.
    # Whether 86% is ENOUGH is exactly what this run asks: 100% steered the executor and 57% produced
    # no steering at all with the polarity control inverted.
    ch = SpriteTracker(max_jump=22.0)
    look: dict = {}
    me_id, me_pos = None, None
    amap = ActionMap(n_a)
    last_pos: dict = {}
    vel: dict = {}
    body_i, lives = None, lc.count(obs)
    score, steps, deaths, guided = 0.0, 0, 0, 0

    for t in range(cap):
        me = _pick_me(ch.tracks, look, body_i, me_pos) if body_i is not None else None
        me_id = me.id if me is not None else None
        pos, names = {}, []
        for tk in ch.tracks:
            k = "me" if tk.id == me_id else f"m{tk.id}"
            pos[k] = (float(tk.pos[0]), float(tk.pos[1]))
            names.append(k)
        if me is not None:
            me_pos = me.pos.copy()
        scene = MetricScene(pos=pos, radius=8.0)

        if mode == "random" or body_i is None or not amap.ready() or len(names) < 2:
            a = int(rng.integers(0, n_a))
        else:
            pol = -1 if mode == "avoid" else 1
            others = [k for k in names if k != "me"]
            near = min(others, key=lambda k: scene.distance("me", k) or 1e9)

            def rollout(sc: MetricScene, act: int) -> MetricScene:
                nxt = {}
                for k, p in sc._pos.items():
                    d = amap.delta(act) * HORIZON if k == "me" else \
                        np.array(vel.get(k, (0.0, 0.0))) * HORIZON
                    nxt[k] = (p[0] + d[0], p[1] + d[1])
                return MetricScene(pos=nxt, radius=8.0)

            pick, _v = choose(list(range(n_a)), rollout,
                              [Proximity("me", near, polarity=pol)], scene)
            a = int(pick) if pick is not None else int(rng.integers(0, n_a))
            guided += pick is not None

        done = False
        for _ in range(3):
            obs, r, term, trunc, _i = env.step(a)
            score += float(r)
            if term or trunc:
                done = True
                break
        steps += 1

        bl = blobs(sprite_mask(obs, bg))
        before = {tk.id: tk.pos.copy() for tk in ch.tracks}
        ch.step(bl, action=a, moving_only=False)
        for tk in ch.tracks:
            if tk.id not in look:
                j = (int(np.argmin([np.hypot(b0[0] - tk.pos[0], b0[1] - tk.pos[1]) for b0 in bl]))
                     if bl else None)
                look[tk.id] = appearance(obs, bl[j]) if j is not None else (0, 0, 0, 0)
            d = tk.pos - before.get(tk.id, tk.pos)
            if abs(d[0]) > 0.5 or abs(d[1]) > 0.5:
                APPEARANCE_MEMORY.setdefault(look[tk.id], []).append((a, float(d[0]), float(d[1])))
        if t % 25 == 24:
            scored = [(bk, intention_momentum(ev)) for bk, ev in APPEARANCE_MEMORY.items()
                      if len(ev) >= 12]
            if scored:
                body_i = max(scored, key=lambda x: x[1])[0]
        for tk in ch.tracks:
            k = "me" if tk.id == me_id else f"m{tk.id}"
            q = np.array([float(tk.pos[0]), float(tk.pos[1])])
            if k in last_pos:
                d = q - last_pos[k]
                vel[k] = tuple(d) if np.hypot(*d) < 40 else (0.0, 0.0)
                if k == "me" and np.hypot(*d) < 40:
                    amap.learn(a, d)
            last_pos[k] = q

        nl = lc.count(obs)
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
    env.close()
    pf = preflight(warm)
    print("PRE-FLIGHT on the PIXEL life-counter — calibrated once against the emulator, then never again.")
    print(f"  life display located at rows {pf['band'][0]}-{pf['band'][1]} (|corr| {pf['band_corr']:.3f})")
    print(f"  pixel count vs RAM byte over {pf['frames']} frames: exact agreement "
          f"{pf['exact_agreement']:.1%}")
    print(f"  values seen  pixel {pf['pixel_values']}   ram {pf['ram_values']}")
    print(f"  -> the counter is {'USABLE' if pf['ok'] else 'NOT usable'}\n")
    if not pf["ok"]:
        sys.exit("the pixel life-counter does not track lives; deaths cannot be scored from the screen")

    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    print("PIXELS ONLY. Nothing below reads RAM. Body, ghosts, and deaths all come from the screen.\n")
    res = {}
    for mode in ("random", "avoid", "chase"):
        runs = [episode(mode, warm, 800 + s, pf["band"]) for s in range(N)]
        res[mode] = runs
        d = np.array([r["per1000"] for r in runs])
        print(f"  {mode:8} deaths/1000 {d.mean():>6.2f} +- {d.std(ddof=1):>5.2f}   "
              f"score {np.mean([r['score'] for r in runs]):>6.0f}   "
              f"steps {np.mean([r['steps'] for r in runs]):>5.0f}   "
              f"schema chose {np.mean([r['guided'] for r in runs]):>5.0f}x")

    from scipy.stats import mannwhitneyu
    A = np.array([r["per1000"] for r in res["avoid"]])
    R = np.array([r["per1000"] for r in res["random"]])
    C = np.array([r["per1000"] for r in res["chase"]])
    p1 = mannwhitneyu(A, R, alternative="less").pvalue
    p2 = mannwhitneyu(A, C, alternative="less").pvalue

    print(f"\n-> 1. avoid dies less than random: {A.mean():.2f} vs {R.mean():.2f}, p = {p1:.4f}   "
          f"{'REAL' if p1 < 0.05 else 'not established'}")
    print(f"-> 2. avoid dies less than chase : {A.mean():.2f} vs {C.mean():.2f}, p = {p2:.4f}   "
          f"{'REAL' if p2 < 0.05 else 'not established'}")
    print(f"\n   the RAM version, which does not count as an agent result: "
          f"avoid 10.56 vs random 12.71, p=0.0132")
    print(f"   what pixel-level body-finding costs: {A.mean() - 10.56:+.2f} deaths per thousand steps")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"preflight": pf, "n": N, "runs": res,
                               "p_vs_random": float(p1), "p_vs_chase": float(p2)},
                              indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
