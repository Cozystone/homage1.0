# -*- coding: utf-8 -*-
"""Put the learned mask on the live path and measure the organs that consume it. The deletion condition.

    python scripts/wire_learned_mask.py

The standing rule from docs/ATANOR_eye_learned_vs_wired_2026-07-30.md: a learned replacement must BEAT
the rule on a measured number before the rule is deleted -- and beating it in isolation is not enough,
because every other perception organ eats its output. `sprite_mask` feeds blobs, blobs feed the tracker,
the tracker feeds the body criterion. A mask that scores better alone and poisons the chain is worse.

So the condition is registered here, in the organs' own terms, before anything is swapped:

    1  BLOBS DO NOT EXPLODE. At a 20% background false-positive rate the mask marks a lot of stray
       pixels, and `min_px=10` is supposed to wash them out. If blob count balloons, tracking is fed
       noise and nothing downstream can be trusted.
    2  BODY-FINDING HOLDS OR IMPROVES. Unconditional on-body is 58.8% with the hand mask under E2's
       calibration; the learned mask must not lose that.
    3  THE THING ONLY IT CAN DO SHOWS UP DOWNSTREAM. Static sprites must reach the blob layer -- the
       pellet map failed at 0.7% screen coverage precisely because subtraction had already deleted them.
    4  and against the same architecture with RANDOM weights, so a win is the learning and not the conv.

If 1 and 2 hold and 3 is a real gain, the rule may be deleted. If not, it stays and this file says so.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception.learned_mask import LearnedMask, patches_at                 # noqa: E402
from packages.perception.learned_signature import Pairs, crop, embed, train          # noqa: E402
from packages.perception.self_criterion import intention_momentum                    # noqa: E402
from packages.perception.sprite_tracker import SpriteTracker                         # noqa: E402
from scripts.atari_babble import blobs, sprite_mask                                  # noqa: E402
from scripts.atari_find_body import measured_warmup                                  # noqa: E402
from scripts.atari_play import make                                                 # noqa: E402
from scripts.atari_taught import RAM_BODY, fit_ram_to_screen, screen_xy             # noqa: E402
from scripts.learned_appearance_merge import harvest_from_tracks                     # noqa: E402
from scripts.learned_segmentation import pellet_truth, sample                        # noqa: E402
from scripts.merge_radius_e2 import CalibratedBuckets, pair_distances, youden_radius  # noqa: E402

OUT = Path("data/atari/wire_learned_mask.json")
WEIGHTS = Path("data/language/learned_mask.pt")
HAND_BODY = 0.588          # E2's in-sample figure with the hand mask


def frames_of(steps: int, seed: int):
    env = make()
    warm = measured_warmup(env, env.action_space.n)
    fit, agree = fit_ram_to_screen(env, warm, seed=seed)
    n_a = env.action_space.n
    obs, _ = env.reset(seed=seed)
    for _ in range(warm):
        obs, *_ = env.step(0)
    rng = np.random.default_rng(seed)
    buf = []
    for _ in range(40):
        obs, *_ = env.step(int(rng.integers(0, n_a)))
        buf.append(obs)
    bg = np.median(np.array(buf, dtype=np.int16), axis=0)
    frames, acts, truth = [], [], []
    for _ in range(steps):
        a = int(rng.integers(0, n_a))
        for _ in range(3):
            obs, _r, term, trunc, _i = env.step(a)
            if term or trunc:
                obs, _ = env.reset()
                for _ in range(warm):
                    obs, *_ = env.step(0)
        frames.append(obs.copy())
        acts.append(a)
        truth.append(screen_xy(env.unwrapped.ale.getRAM(), fit, RAM_BODY))
    env.close()
    return frames, bg, acts, np.array(truth), agree


def chain(mask_of, frames, acts, truth, dev, net_for_key=None):
    """blobs -> tracker -> appearance buckets -> body criterion, with the mask swapped in."""
    tr = SpriteTracker(max_jump=22.0)
    per_frame, blob_counts = [], []
    for t, f in enumerate(frames):
        bl = blobs(mask_of(f))
        blob_counts.append(len(bl))
        before = {k.id: k.pos.copy() for k in tr.tracks}
        tr.step(bl, action=acts[t], moving_only=False)
        per_frame.append([(k.id, k.pos.copy(), k.pos - before.get(k.id, k.pos)) for k in tr.tracks])

    pairs = harvest_from_tracks(frames, per_frame)
    if len(pairs) < 150:
        return {"blobs_mean": float(np.mean(blob_counts)), "on_body_overall": 0.0,
                "note": "too few triplets to calibrate"}
    cut = len(pairs) // 5
    ho = Pairs(pairs.a[:cut], pairs.p[:cut], pairs.n[:cut])
    net = net_for_key or train(Pairs(pairs.a[cut:], pairs.p[cut:], pairs.n[cut:]),
                               epochs=25, device=dev)
    same, diff = pair_distances(lambda x: embed(net, x, dev), ho)
    r, _j = youden_radius(same, diff)
    B = CalibratedBuckets(r)

    look, seen = {}, collections.defaultdict(collections.Counter)
    mem = collections.defaultdict(list)
    hist = collections.defaultdict(dict)
    for t, rows in enumerate(per_frame):
        for tid, pos, d in rows:
            c = crop(frames[t], pos)
            k = -1 if c is None else B.key(embed(net, c[None], dev)[0])
            seen[tid][k] += 1
            look[tid] = seen[tid].most_common(1)[0][0]
            if abs(d[0]) > 0.5 or abs(d[1]) > 0.5:
                mem[look[tid]].append((acts[t], float(d[0]), float(d[1])))
            hist[look[tid]][t] = pos
    scored = [(b, intention_momentum(ev)) for b, ev in mem.items() if len(ev) >= 12]
    if not scored:
        return {"blobs_mean": float(np.mean(blob_counts)), "on_body_overall": 0.0,
                "note": "no bucket reached 12 samples"}
    chosen = max(scored, key=lambda x: x[1])[0]
    ts = sorted(hist.get(chosen, {}))
    P = np.array([hist[chosen][t] for t in ts]) if ts else np.zeros((0, 2))
    hit = (np.hypot(P[:, 0] - truth[ts, 0], P[:, 1] - truth[ts, 1]) < 8.0) if ts else np.zeros(0)
    pres = len(ts) / len(frames)
    return {"blobs_mean": float(np.mean(blob_counts)), "buckets": len(B.keys),
            "presence": pres, "on_body_given_present": float(hit.mean()) if len(hit) else 0.0,
            "on_body_overall": pres * (float(hit.mean()) if len(hit) else 0.0),
            "radius": r, "net": net}


def main() -> None:
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    frames, bg, acts, truth, agree = frames_of(500, seed=3)
    pel = pellet_truth(frames)
    print(f"oracle verified r_x {agree['r_x']:.3f}; it SCORES and never decides")
    print(f"{len(frames)} frames, {int(pel.sum())} static-pellet pixels by behaviour, {dev}\n")

    X, Y = sample(frames, bg)
    lm = LearnedMask(dev).fit(X, Y)
    lm.threshold_for_fpr(frames[::20], lambda f: ~sprite_mask(f, bg) & ~pel, fpr=0.20)
    rm = LearnedMask(dev)
    rm.threshold_for_fpr(frames[::20], lambda f: ~sprite_mask(f, bg) & ~pel, fpr=0.20)
    print(f"learned mask threshold {lm.threshold:.4f}, random-init {rm.threshold:.4f} "
          f"(both set by the BACKGROUND's own distribution at 20% FPR)\n")

    arms = {"hand rule (incumbent)": lambda f: sprite_mask(f, bg),
            "LEARNED mask": lambda f: lm.mask(f, stride=2),
            "random-weight mask (control)": lambda f: rm.mask(f, stride=2)}

    print(f"{'mask':<30}{'blobs/frame':>13}{'buckets':>9}{'presence':>10}"
          f"{'|present':>10}{'ON-BODY':>9}{'pellet px':>11}")
    res, shared_net = {}, None
    for name, mof in arms.items():
        r = chain(mof, frames, acts, truth, dev, net_for_key=shared_net)
        if name == "hand rule (incumbent)":
            shared_net = r.pop("net", None)          # same identity net for every arm: fair comparison
        else:
            r.pop("net", None)
        m = mof(frames[-1])
        r["pellet_px_visible"] = int((m & pel).sum())
        res[name] = r
        print(f"{name:<30}{r['blobs_mean']:>13.1f}{r.get('buckets', 0):>9}"
              f"{r.get('presence', 0):>9.1%}{r.get('on_body_given_present', 0):>10.1%}"
              f"{r['on_body_overall']:>9.1%}{r['pellet_px_visible']:>11}", flush=True)

    H, L, C = (res["hand rule (incumbent)"], res["LEARNED mask"],
               res["random-weight mask (control)"])
    ok1 = L["blobs_mean"] < 3 * H["blobs_mean"]
    ok2 = L["on_body_overall"] >= H["on_body_overall"] - 0.02
    ok3 = L["pellet_px_visible"] > 10 * max(H["pellet_px_visible"], 1)
    ok4 = L["on_body_overall"] > C["on_body_overall"] + 0.02
    print(f"\n-> 1. blobs do not explode: {ok1}  ({H['blobs_mean']:.1f} -> {L['blobs_mean']:.1f} "
          f"per frame)")
    print(f"-> 2. body-finding holds: {ok2}  ({H['on_body_overall']:.1%} -> "
          f"{L['on_body_overall']:.1%};  E2's hand figure was {HAND_BODY:.1%})")
    print(f"-> 3. static sprites reach the blob layer: {ok3}  "
          f"({H['pellet_px_visible']} -> {L['pellet_px_visible']} pellet px in the mask)")
    print(f"-> 4. beats random weights: {ok4}  ({C['on_body_overall']:.1%})")
    verdict = ("THE RULE MAY BE DELETED" if (ok1 and ok2 and ok3 and ok4)
               else "THE RULE STAYS -- the replacement does not yet win downstream")
    print(f"\n{verdict}")

    WEIGHTS.parent.mkdir(parents=True, exist_ok=True)
    lm.save(WEIGHTS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"arms": res, "conditions": {"blobs": ok1, "body": ok2,
                                                           "static": ok3, "control": ok4},
                               "verdict": verdict}, indent=2, default=str), encoding="utf-8")
    print(f"wrote {OUT} and {WEIGHTS}")


if __name__ == "__main__":
    main()
