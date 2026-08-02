# -*- coding: utf-8 -*-
"""Make stationarity information instead of noise, and re-run the deletion condition.

    python scripts/motion_aware_consumers.py

The wiring test said the rule stays, and named the reason: every consumer was built on "a blob is a
moving thing". A learned mask that also returns stationary things therefore broke all of them --
blobs 10 -> 111.6, buckets 7 -> 396, body-finding 71.2% -> 0.2% -- and the union of both masks was worse
than either alone (20.8%). Nothing was wrong with the mask; the assumption was wired into its consumers.

So this rung changes the CONSUMERS, which is what the verdict specified rather than what I would have
preferred to do.

    the tracker now classifies each track as moving or static, with the cut DERIVED by one pass of 1-D
      k-means over the observed median speeds -- a pellet sits at ~0 and a sprite at several pixels a
      step, which is why a split exists to be found
    the body criterion looks only at MOVING tracks. A stationary thing cannot have its displacement
      predicted by a command because it has no displacement; including it was feeding the statistic noise
    static tracks become a MAP rather than a nuisance -- which is the thing the pellet map wanted and
      could not have, since background subtraction had already deleted the pellets

REGISTERED, and the incumbent gets the SAME motion-aware consumers so the comparison is about the mask:
    1  body-finding with the learned mask holds at the incumbent's level
    2  blobs stay bounded
    3  the static tracks actually recover the pellets -- coverage against pellet ground truth derived by
       BEHAVIOUR (there early, gone late, never back), where the old map managed 0.7% of the screen
    4  and the learned mask beats the same architecture with random weights

If 1-3 hold, the rule may be deleted. The condition is not relaxed because the first attempt failed.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception.learned_mask import LearnedMask                              # noqa: E402
from packages.perception.learned_signature import Pairs, crop, embed, train           # noqa: E402
from packages.perception.self_criterion import intention_momentum                     # noqa: E402
from packages.perception.sprite_tracker import SpriteTracker                          # noqa: E402
from scripts.atari_babble import blobs, sprite_mask                                   # noqa: E402
from scripts.learned_appearance_merge import harvest_from_tracks                      # noqa: E402
from scripts.learned_segmentation import pellet_truth, sample                         # noqa: E402
from scripts.merge_radius_e2 import CalibratedBuckets, pair_distances, youden_radius  # noqa: E402
from scripts.wire_learned_mask import frames_of                                       # noqa: E402

OUT = Path("data/atari/motion_aware_consumers.json")


def chain(mask_of, frames, acts, truth, pel, dev, shared_net=None):
    """blobs -> tracker -> MOTION SPLIT -> buckets over moving tracks only -> body criterion."""
    tr = SpriteTracker(max_jump=22.0)
    per_frame, counts = [], []
    for t, f in enumerate(frames):
        bl = blobs(mask_of(f))
        counts.append(len(bl))
        before = {k.id: k.pos.copy() for k in tr.tracks}
        tr.step(bl, action=acts[t], moving_only=False)
        per_frame.append([(k.id, k.pos.copy(), k.pos - before.get(k.id, k.pos)) for k in tr.tracks])

    # THE SPLIT MUST SEE HISTORY. SpriteTracker.motion_split() reads self.tracks, and the tracker
    # PRUNES dead tracks -- so it classifies only the handful alive at the final frame. That gave one
    # moving track out of thirteen and drove every arm, including the incumbent, to 0.0% on-body: a
    # measurement of my plumbing rather than of the design. The displacements are already collected
    # per frame, so the classification belongs here, over every id ever seen.
    speeds: dict = collections.defaultdict(list)
    for rows in per_frame:
        for tid, _pos, d in rows:
            speeds[tid].append(float(np.hypot(d[0], d[1])))
    med = {tid: float(np.median(v)) for tid, v in speeds.items() if v}
    if len(med) >= 4 and max(med.values()) - min(med.values()) > 1e-6:
        sp = np.array(list(med.values()))
        lo, hi = float(sp.min()), float(sp.max())
        for _ in range(20):
            mid = (lo + hi) / 2.0
            a, b = sp[sp <= mid], sp[sp > mid]
            if not len(a) or not len(b):
                break
            lo, hi = float(a.mean()), float(b.mean())
        speed_cut = (lo + hi) / 2.0
    else:
        speed_cut = 0.5
    moving_ids = {tid for tid, v in med.items() if v > speed_cut}
    static_ids = set(med) - moving_ids
    moving, static = moving_ids, static_ids

    # THE MAP, free once stationarity is information: where the static things were.
    smap = np.zeros(frames[0].shape[:2], bool)
    for rows in per_frame:
        for tid, pos, _d in rows:
            if tid not in moving_ids:
                y, x = int(round(pos[1])), int(round(pos[0]))
                if 0 <= y < smap.shape[0] and 0 <= x < smap.shape[1]:
                    smap[max(0, y - 2):y + 3, max(0, x - 2):x + 3] = True

    pairs = harvest_from_tracks(frames, per_frame)
    if len(pairs) < 150:
        return {"blobs_mean": float(np.mean(counts)), "on_body_overall": 0.0,
                "map_recall": 0.0, "map_frac": float(smap.mean()),
                "note": "too few triplets"}
    cut = len(pairs) // 5
    ho = Pairs(pairs.a[:cut], pairs.p[:cut], pairs.n[:cut])
    net = shared_net or train(Pairs(pairs.a[cut:], pairs.p[cut:], pairs.n[cut:]),
                              epochs=25, device=dev)
    same, diff = pair_distances(lambda x: embed(net, x, dev), ho)
    r, _j = youden_radius(same, diff)
    B = CalibratedBuckets(r)

    look, seen = {}, collections.defaultdict(collections.Counter)
    mem = collections.defaultdict(list)
    hist = collections.defaultdict(dict)
    for t, rows in enumerate(per_frame):
        for tid, pos, d in rows:
            if tid not in moving_ids:
                continue                     # a static thing has no displacement to predict
            c = crop(frames[t], pos)
            k = -1 if c is None else B.key(embed(net, c[None], dev)[0])
            seen[tid][k] += 1
            look[tid] = seen[tid].most_common(1)[0][0]
            if abs(d[0]) > 0.5 or abs(d[1]) > 0.5:
                mem[look[tid]].append((acts[t], float(d[0]), float(d[1])))
            hist[look[tid]][t] = pos
    scored = [(b, intention_momentum(ev)) for b, ev in mem.items() if len(ev) >= 12]
    out = {"blobs_mean": float(np.mean(counts)), "buckets": len(B.keys),
           "moving_tracks": len(moving), "static_tracks": len(static), "speed_cut": speed_cut,
           "map_frac": float(smap.mean()),
           "map_recall": float(smap[pel].mean()) if pel.sum() else 0.0,
           "net": net}
    if not scored:
        out.update({"presence": 0.0, "on_body_given_present": 0.0, "on_body_overall": 0.0})
        return out
    chosen = max(scored, key=lambda x: x[1])[0]
    ts = sorted(hist.get(chosen, {}))
    P = np.array([hist[chosen][t] for t in ts]) if ts else np.zeros((0, 2))
    hit = (np.hypot(P[:, 0] - truth[ts, 0], P[:, 1] - truth[ts, 1]) < 8.0) if ts else np.zeros(0)
    pres = len(ts) / len(frames)
    acc = float(hit.mean()) if len(hit) else 0.0
    out.update({"presence": pres, "on_body_given_present": acc, "on_body_overall": pres * acc})
    return out


def main() -> None:
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    frames, bg, acts, truth, agree = frames_of(500, seed=3)
    pel = pellet_truth(frames)
    print(f"oracle verified r_x {agree['r_x']:.3f}; it SCORES and never decides")
    print(f"{len(frames)} frames, {int(pel.sum())} static-pellet px by behaviour, {dev}\n")

    X, Y = sample(frames, bg)
    bgm = lambda f: ~sprite_mask(f, bg) & ~pel      # noqa: E731
    lm = LearnedMask(dev).fit(X, Y)
    lm.threshold_for_fpr(frames[::20], bgm, fpr=0.02)
    rm = LearnedMask(dev)
    rm.threshold_for_fpr(frames[::20], bgm, fpr=0.02)
    print(f"operating point set by the background at FPR 2%: learned {lm.threshold:.4f}, "
          f"random {rm.threshold:.4f}\n")

    arms = {"hand rule (incumbent)": lambda f: sprite_mask(f, bg),
            "LEARNED mask": lambda f: lm.mask(f, stride=2),
            "random-weight (control)": lambda f: rm.mask(f, stride=2)}

    print(f"{'mask':<26}{'blobs':>7}{'mov/stat':>10}{'presence':>10}{'|present':>10}"
          f"{'ON-BODY':>9}{'map recall':>12}{'map area':>10}")
    res, shared = {}, None
    for name, mof in arms.items():
        r = chain(mof, frames, acts, truth, pel, dev, shared_net=shared)
        if shared is None:
            shared = r.pop("net", None)
        else:
            r.pop("net", None)
        res[name] = r
        split = f"{r.get('moving_tracks', 0)}/{r.get('static_tracks', 0)}"
        print(f"{name:<26}{r['blobs_mean']:>7.1f}{split:>10}"
              f"{r.get('presence', 0):>9.1%}{r.get('on_body_given_present', 0):>10.1%}"
              f"{r['on_body_overall']:>9.1%}{r['map_recall']:>11.1%}{r['map_frac']:>10.1%}",
              flush=True)

    H, L, C = res["hand rule (incumbent)"], res["LEARNED mask"], res["random-weight (control)"]
    ok1 = L["on_body_overall"] >= H["on_body_overall"] - 0.02
    ok2 = L["blobs_mean"] < 3 * H["blobs_mean"]
    ok3 = L["map_recall"] > 0.30 and L["map_recall"] > 3 * H["map_recall"]
    ok4 = L["on_body_overall"] > C["on_body_overall"] + 0.02
    print(f"\n-> 1. body-finding holds: {ok1}  ({H['on_body_overall']:.1%} -> {L['on_body_overall']:.1%})")
    print(f"-> 2. blobs bounded: {ok2}  ({H['blobs_mean']:.1f} -> {L['blobs_mean']:.1f})")
    print(f"-> 3. the static map recovers the pellets: {ok3}  "
          f"(hand {H['map_recall']:.1%} -> learned {L['map_recall']:.1%}; "
          f"the old pellet map covered 0.7% of the screen)")
    print(f"-> 4. beats random weights: {ok4}  ({C['on_body_overall']:.1%})")
    verdict = ("THE RULE MAY BE DELETED" if (ok1 and ok2 and ok3 and ok4)
               else "THE RULE STAYS -- the replacement still does not win downstream")
    print(f"\n{verdict}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"arms": res, "conditions": {"body": ok1, "blobs": ok2,
                                                           "map": ok3, "control": ok4},
                               "verdict": verdict}, indent=2, default=str), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
