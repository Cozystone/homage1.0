# -*- coding: utf-8 -*-
"""E2: derive the merge radius from what tracking already knows, and let the learned eye be judged fairly.

    python scripts/merge_radius_e2.py

The learned embedding lost to my hand-written colour rule, 42.7% against 48.5% unconditional on-body, and
the cause was named rather than guessed: it OVER-SPLITS -- 55 buckets against 8, with higher purity and
worse presence. The suspect was the radius.

WHY THE OLD RADIUS COULD NOT WORK IN 32 DIMENSIONS. `Buckets.calibrate` took half the median
nearest-neighbour distance among distinct descriptors. In a 4-dimensional colour space that is a
reasonable notion of "close". In a 32-dimensional embedding, pairwise distances CONCENTRATE -- the
nearest neighbour is barely nearer than the average -- so half of the median is far too small and every
view of the body becomes its own bucket. The heuristic was calibrated on one geometry and reused on
another.

THE RADIUS SHOULD COME FROM THE SAME/DIFFERENT DISTRIBUTION, WHICH TRACKING ALREADY SUPPLIES. Anchors and
positives are the same object; the negative in each triplet is a different one. So calibrate the radius as
the point that best separates those two distance distributions -- Youden's J, which has no free parameter
-- and the procedure is dimension-agnostic by construction rather than by luck.

AND THE HAND RULE GETS THE SAME TREATMENT. Comparing a learned descriptor under a properly derived radius
against a hand descriptor under the old heuristic would be measuring the calibration, not the descriptor.
Both arms are calibrated the same way, which is the same discipline that made the ACE2 comparison fair
when standardisation was missing.

REGISTERED:
    1  the over-splitting resolves -- bucket count must actually fall, since that was the named cause
    2  the learned eye beats the hand rule's 48.5% under matched calibration
    3  and beats the same architecture with random weights, or the supervision bought nothing
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception.learned_signature import Pairs, crop, embed, make_net, train   # noqa: E402
from scripts.appearance_presence import d_dominant                                       # noqa: E402
from scripts.learned_appearance_merge import (harvest_from_tracks, rollout,              # noqa: E402
                                              score_buckets)

OUT = Path("data/atari/merge_radius_e2.json")
HAND_PRIOR, LEARNED_PRIOR = 0.485, 0.427


def youden_radius(same: np.ndarray, diff: np.ndarray) -> tuple:
    """The distance that best separates same-object from different-object pairs. No free parameter.

    Youden's J is max(TPR - FPR) over candidate thresholds, and the candidates are the observed
    distances themselves, so nothing is chosen by me and nothing depends on the dimension."""
    if not len(same) or not len(diff):
        return 0.0, 0.0
    cand = np.unique(np.concatenate([same, diff]))
    if len(cand) > 400:
        cand = np.quantile(cand, np.linspace(0, 1, 400))
    best, bj = 0.0, -1.0
    for r in cand:
        tpr = float((same <= r).mean())          # same object correctly merged
        fpr = float((diff <= r).mean())          # different objects wrongly merged
        if tpr - fpr > bj:
            best, bj = float(r), tpr - fpr
    return best, bj


class CalibratedBuckets:
    """Nearest-match bucketing whose radius came from the same/different distribution."""

    def __init__(self, radius: float):
        self.radius = float(radius)
        self.keys: list = []

    def key(self, v) -> int:
        v = np.asarray(v, np.float32)
        if self.keys:
            K = np.array(self.keys, np.float32)
            d = np.linalg.norm(K - v, axis=1)
            j = int(np.argmin(d))
            if d[j] <= self.radius:
                return j
        self.keys.append(tuple(v.tolist()))
        return len(self.keys) - 1


def pair_distances(vec_of, pairs: Pairs):
    """Euclidean distance between anchor/positive and anchor/negative, in the descriptor's own space."""
    A, P, N = vec_of(pairs.a), vec_of(pairs.p), vec_of(pairs.n)
    same = np.linalg.norm(A - P, axis=1)
    diff = np.linalg.norm(A - N, axis=1)
    return same, diff


def main() -> None:
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    STEPS = 600
    frames, per_frame, truth, acts, agree = rollout(STEPS, seed=3)
    print(f"oracle verified r_x {agree['r_x']:.3f}; it SCORES and never decides")
    pairs = harvest_from_tracks(frames, per_frame)
    print(f"{len(pairs)} self-supervised triplets from tracking\n")
    if len(pairs) < 200:
        sys.exit("too few triplets; refusing to report a number from a handful")
    cut = len(pairs) // 5
    ho = Pairs(pairs.a[:cut], pairs.p[:cut], pairs.n[:cut])
    trn = Pairs(pairs.a[cut:], pairs.p[cut:], pairs.n[cut:])

    net = train(trn, epochs=30, device=dev, log=lambda s: print(s, flush=True))
    rnd = make_net().to(dev)

    _pb = lambda p: (float(p[0]), float(p[1]), 8.0)      # noqa: E731  tracks carry no size

    def hand_vecs(patches):
        # the hand descriptor applied to a patch: its own centre stands in for the blob position
        return np.stack([d_dominant(p, (p.shape[1] / 2, p.shape[0] / 2, 8.0)) for p in patches])

    arms = {
        "dominant colour (hand-written)": (hand_vecs, lambda f, p: d_dominant(f, _pb(p))),
        "learned (temporal supervision)": (lambda x: embed(net, x, dev),
                                           lambda f, p: (embed(net, crop(f, p)[None], dev)[0]
                                                         if crop(f, p) is not None else None)),
        "random weights (control)": (lambda x: embed(rnd, x, dev),
                                     lambda f, p: (embed(rnd, crop(f, p)[None], dev)[0]
                                                   if crop(f, p) is not None else None)),
    }

    print(f"{'descriptor':<34}{'radius':>9}{'J':>7}{'buckets':>9}{'presence':>10}"
          f"{'|present':>10}{'OVERALL':>9}")
    res = {}
    for name, (vec_of, key_of) in arms.items():
        same, diff = pair_distances(vec_of, ho)
        r, j = youden_radius(same, diff)
        B = CalibratedBuckets(r)

        def key(f, p, _B=B, _k=key_of):
            v = _k(f, p)
            return -1 if v is None else _B.key(v)

        s = score_buckets(key, per_frame, frames, truth, acts, STEPS)
        if s is None:
            print(f"{name:<34}{'no bucket reached 12 samples':>54}")
            continue
        s.update({"radius": r, "youden_J": j,
                  "same_median": float(np.median(same)), "diff_median": float(np.median(diff))})
        res[name] = s
        print(f"{name:<34}{r:>9.3f}{j:>7.3f}{s['buckets']:>9}{s['presence']:>9.1%}"
              f"{s['on_body_given_present']:>10.1%}{s['on_body_overall']:>9.1%}", flush=True)

    H = res.get("dominant colour (hand-written)")
    L = res.get("learned (temporal supervision)")
    C = res.get("random weights (control)")
    if H and L and C:
        print(f"\n-> 1. the over-splitting resolves: {L['buckets'] < 30}  "
              f"(was 55 buckets under the old radius, now {L['buckets']})")
        print(f"-> 2. the learned eye beats the hand rule under MATCHED calibration: "
              f"{L['on_body_overall'] > H['on_body_overall']}  "
              f"({H['on_body_overall']:.1%} vs {L['on_body_overall']:.1%})")
        print(f"-> 3. and beats random weights: "
              f"{L['on_body_overall'] > C['on_body_overall'] + 0.02}  "
              f"({C['on_body_overall']:.1%})")
        print(f"\n   prior, under the old dimension-blind radius: hand {HAND_PRIOR:.1%}, "
              f"learned {LEARNED_PRIOR:.1%}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"triplets": len(pairs), "arms": res,
                               "prior": {"hand": HAND_PRIOR, "learned": LEARNED_PRIOR}},
                              indent=2, default=str), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
