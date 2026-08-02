# -*- coding: utf-8 -*-
"""Learn what makes two views the same thing, and use it to merge tracks. No colour rule written by me.

    python scripts/learned_appearance_merge.py

Owner: 우리는 사람처럼 볼 수 있는 눈을 만들었는데 저렇게 색이랑 하나하나씩 다 알려줘야해?

No, and the objection lands: `d_dominant` and `d_hue` are me writing "quantise the dominant colour by
32", which is the same family of thing as the 31-verb lexicon. It is a training wheel, and the presence
measurement showed exactly where it costs -- detection is 100%, tracking is 100%, and ALL of the loss to
50.7% is in that hand-written key.

TWO PROBLEMS HAVE TO BE SEPARATED OR THE WRONG ONE GETS BUILT FIRST.

    object constancy   "the mouth moves and it is still the same body". Needs NO semantic category and
                       NO external images. Two views of one thing must be closer than views of two
                       things, and the supervision for that is in the video already: same track later =
                       positive, different track now = negative. This is the current bottleneck.
    semantic recognition  "this shape is an eraser". Needs labels or a large image corpus, and is a
                       DIFFERENT capability. It is what the Simple City goal will want, and building it
                       first would leave the present bottleneck untouched.

So this rung is constancy only, learned self-supervised from the game's own frames.

AND THE ORGAN ALREADY EXISTED, UNWIRED. `packages/perception/learned_signature.py` was written yesterday
-- "Learn what makes two views the same thing, from tracking, with nobody labelling anything" -- and
nothing in the repository called it. That is the fourth built-but-not-wired case this week, and this time
it was the exact thing being asked for.

THE CONTROL THAT MAKES THE ANSWER MEAN ANYTHING: the same conv encoder with RANDOM WEIGHTS. A random
conv net's features are often surprisingly good, so without this arm a win would say "conv features beat
a colour rule" rather than "the temporal supervision taught it something". That distinction is the whole
experiment.

REGISTERED, against the hand-written descriptor measured in the same run:
    1  separability: same-track pairs must sit above different-track pairs with a GAP, not an overlap
    2  unconditional on-body beats the hand rule's 50.7%
    3  and beats the random-weight encoder, or the supervision bought nothing
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception.learned_signature import (PATCH, Pairs, crop, embed,      # noqa: E402
                                                   make_net, separability, train)
from packages.perception.self_criterion import intention_momentum                  # noqa: E402
from packages.perception.sprite_tracker import SpriteTracker                       # noqa: E402
from scripts.appearance_presence import Buckets, d_dominant                        # noqa: E402
from scripts.atari_babble import blobs, sprite_mask                                # noqa: E402
from scripts.atari_find_body import measured_warmup                                # noqa: E402
from scripts.atari_play import make                                               # noqa: E402
from scripts.atari_taught import RAM_BODY, fit_ram_to_screen, screen_xy           # noqa: E402

OUT = Path("data/atari/learned_appearance_merge.json")
HAND_BEST = 0.507          # running-mode dominant colour, unconditional on-body


def rollout(steps: int, seed: int):
    """Frames, sprite tracks, and the oracle's body position. The oracle SCORES and never decides."""
    env = make()
    warm = measured_warmup(env, env.action_space.n)
    fit, agree = fit_ram_to_screen(env, warm, seed=seed)
    n_a = env.action_space.n
    env.close()
    env = make()
    obs, _ = env.reset(seed=seed)
    for _ in range(warm):
        obs, *_ = env.step(0)
    rng = np.random.default_rng(seed)
    buf = []
    for _ in range(40):
        obs, *_ = env.step(int(rng.integers(0, n_a)))
        buf.append(obs)
    bg = np.median(np.array(buf, dtype=np.int16), axis=0)

    tr = SpriteTracker(max_jump=22.0)
    frames, per_frame, truth, acts = [], [], [], []
    for _t in range(steps):
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
        frames.append(obs.copy())
        acts.append(a)
        per_frame.append([(k.id, k.pos.copy(), k.pos - before.get(k.id, k.pos)) for k in tr.tracks])
        truth.append(screen_xy(env.unwrapped.ale.getRAM(), fit, RAM_BODY))
    env.close()
    return frames, per_frame, np.array(truth), acts, agree


def harvest_from_tracks(frames, per_frame, max_pairs: int = 1200, min_gap: int = 4, seed: int = 0):
    """Anchor and positive from ONE track at two times; negative from another track at the same time.

    The module ships a harvester over optical-flow point tracks; sprite tracks are the better
    supervision here because a sprite is the thing whose identity is in question."""
    rng = np.random.default_rng(seed)
    where = collections.defaultdict(list)
    for t, rows in enumerate(per_frame):
        for tid, pos, _d in rows:
            where[tid].append((t, pos))
    A, P, N = [], [], []
    ids = [i for i, v in where.items() if len(v) >= min_gap + 2]
    for _ in range(max_pairs * 6):
        if len(A) >= max_pairs or not ids:
            break
        n = ids[int(rng.integers(0, len(ids)))]
        v = where[n]
        i0 = int(rng.integers(0, len(v) - min_gap))
        i1 = int(rng.integers(i0 + min_gap, len(v)))
        t0, p0 = v[i0]
        t1, p1 = v[i1]
        others = [(tid, pos) for tid, pos, _d in per_frame[t0] if tid != n]
        if not others:
            continue
        mtid, mpos = others[int(rng.integers(0, len(others)))]
        ca, cp, cn = crop(frames[t0], p0), crop(frames[t1], p1), crop(frames[t0], mpos)
        if ca is None or cp is None or cn is None:
            continue
        A.append(ca)
        P.append(cp)
        N.append(cn)
    z = np.zeros((0, PATCH, PATCH, 3), np.uint8)
    return Pairs(np.array(A, np.uint8) if A else z, np.array(P, np.uint8) if P else z,
                 np.array(N, np.uint8) if N else z)


def score_buckets(keyfn, per_frame, frames, truth, acts, steps):
    """Running-mode keying -- the best hand scheme -- with the key function swapped in."""
    look, seen = {}, collections.defaultdict(collections.Counter)
    mem = collections.defaultdict(list)
    hist = collections.defaultdict(dict)
    for t, rows in enumerate(per_frame):
        for tid, pos, d in rows:
            k = keyfn(frames[t], pos)
            seen[tid][k] += 1
            look[tid] = seen[tid].most_common(1)[0][0]
            if abs(d[0]) > 0.5 or abs(d[1]) > 0.5:
                mem[look[tid]].append((acts[t], float(d[0]), float(d[1])))
            hist[look[tid]][t] = pos
    scored = [(b, intention_momentum(ev)) for b, ev in mem.items() if len(ev) >= 12]
    if not scored:
        return None
    chosen = max(scored, key=lambda x: x[1])[0]

    def st(b):
        ts = sorted(hist.get(b, {}))
        if not ts:
            return 0.0, 0.0, 0.0
        P = np.array([hist[b][t] for t in ts])
        hit = np.hypot(P[:, 0] - truth[ts, 0], P[:, 1] - truth[ts, 1]) < 8.0
        p = len(ts) / steps
        return p, float(hit.mean()), p * float(hit.mean())

    p, c, o = st(chosen)
    alls = [st(b) for b, _s in scored]
    return {"buckets": len({look[t] for t in look}), "presence": p,
            "on_body_given_present": c, "on_body_overall": o,
            "chance_overall": float(np.mean([x[2] for x in alls]))}


def main() -> None:
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    STEPS = 600
    frames, per_frame, truth, acts, agree = rollout(STEPS, seed=3)
    print(f"oracle verified r_x {agree['r_x']:.3f}; it SCORES and never decides")
    print(f"{STEPS} frames, {sum(len(r) for r in per_frame)} track observations, {dev}\n")

    pairs = harvest_from_tracks(frames, per_frame)
    print(f"self-supervised pairs harvested from tracking alone: {len(pairs)}  "
          f"(no labels, no external images)")
    if len(pairs) < 200:
        sys.exit("too few pairs to train on; refusing to report a number from a handful")

    cut = len(pairs) // 5
    ho = Pairs(pairs.a[:cut], pairs.p[:cut], pairs.n[:cut])
    trn = Pairs(pairs.a[cut:], pairs.p[cut:], pairs.n[cut:])

    nets = {"learned (temporal supervision)": train(trn, epochs=30, device=dev,
                                                    log=lambda s: print(s, flush=True)),
            "random weights (control)": make_net().to(dev)}
    rows = {}
    for name, net in nets.items():
        ea, ep, en = (embed(net, x, dev) for x in (ho.a, ho.p, ho.n))
        sep = separability((ea * ep).sum(1), (ea * en).sum(1))
        rows[name] = {"separability": sep}
        print(f"\n  {name}")
        print(f"    same-track cosine median {sep['same_median']}, p10 {sep['same_p10']}")
        print(f"    other-track  median {sep['diff_median']}, p90 {sep['diff_p90']}")
        print(f"    gap {sep['gap']}   separable {sep['separable']}   overlap {sep['overlap']}",
              flush=True)

    print("\nnow as the bucket key, with the same running-mode scheme as the hand rule:\n", flush=True)
    print(f"{'key':<34}{'buckets':>9}{'presence':>10}{'|present':>10}{'OVERALL':>9}{'chance':>8}")
    B_hand = Buckets(True)
    # Track positions carry no size, so a constant stands in for it: the size dimension is then the
    # same for every candidate and the comparison is decided by colour alone, which is the point.
    _pb = lambda p: (float(p[0]), float(p[1]), 8.0)
    B_hand.calibrate([d_dominant(frames[t], _pb(p)) for t in range(0, STEPS, 7)
                      for _i, p, _d in per_frame[t]][:400])
    res = {}
    res["dominant colour (hand-written)"] = score_buckets(
        lambda f, p: B_hand.key(d_dominant(f, _pb(p))), per_frame, frames, truth, acts, STEPS)
    for name, net in nets.items():
        B = Buckets(True)
        cal = []
        for t in range(0, STEPS, 7):
            for _i, p, _d in per_frame[t]:
                c = crop(frames[t], p)
                if c is not None:
                    cal.append(embed(net, c[None], dev)[0])
        B.calibrate(cal[:400])

        def key(f, p, _net=net, _B=B):
            c = crop(f, p)
            return -1 if c is None else _B.key(embed(_net, c[None], dev)[0])

        res[name] = score_buckets(key, per_frame, frames, truth, acts, STEPS)
    for k, r in res.items():
        if r is None:
            print(f"{k:<34}{'no bucket reached 12 samples':>46}")
            continue
        print(f"{k:<34}{r['buckets']:>9}{r['presence']:>9.1%}{r['on_body_given_present']:>10.1%}"
              f"{r['on_body_overall']:>9.1%}{r['chance_overall']:>8.1%}")

    L = res.get("learned (temporal supervision)")
    C = res.get("random weights (control)")
    H = res.get("dominant colour (hand-written)")
    if L and H and C:
        print(f"\n-> 2. beats the hand-written colour rule: "
              f"{L['on_body_overall'] > H['on_body_overall']}  "
              f"({H['on_body_overall']:.1%} -> {L['on_body_overall']:.1%})")
        print(f"-> 3. THE SUPERVISION earns its keep, not just the conv: "
              f"{L['on_body_overall'] > C['on_body_overall'] + 0.02}  "
              f"(random weights {C['on_body_overall']:.1%})")
        print("\n   Constancy only. Nothing here recognises a category, and nothing here needed an")
        print("   external image or a label -- the supervision was in the tracking all along.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"pairs": len(pairs), "arms": rows, "bucketing": res,
                               "hand_best_prior": HAND_BEST}, indent=2, default=str),
                   encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
