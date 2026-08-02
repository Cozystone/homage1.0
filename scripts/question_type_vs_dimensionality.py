# -*- coding: utf-8 -*-
"""Is it the NUMBER of questions that buys dimensions, or the KIND of question?

WHERE THIS COMES FROM. `dimensionality_from_many_samenesses` established the diagnosis: the signature
encoder declares 32 dimensions and uses 3.9, against ~49 for human object representations (Hebart
2020), because `harvest` asks exactly one question -- is this the same track? Separating tracks is
satisfiable in very few dimensions, so 32 were handed over and four were spent.

Its fix was to add relations, and the result was thin: participation ratio went 3.9 -> about 4.5
across five added relations, and naming precision wobbled between 0.62 and 0.78 without trend.

READING THE RELATIONS EXPLAINS WHY. depth is the patch's median distance, height is its image row,
texture is its pixel standard deviation, colour is its saturation. Every one is computable FROM THE
PATCH ITSELF. They are four spellings of "what does this patch look like", and in a rendered street
they co-vary hard. Hebart's fifty axes do not come from asking about appearance five ways; they come
from questions that are settled by DIFFERENT KINDS OF FACT -- is it metal, does it move, is it food.

SO THE CONTROL IS COUNT-MATCHED, which the original comparison was not. Four appearance relations
against four MIXED ones, same encoder, same patches, same steps, same seed. If dimensionality follows
the count, the two score alike. If it follows the kind, the mixed set wins.

THE NEW QUESTIONS ARE ALL FREE, and none is about how a patch looks:

    self_moving   did this thing move in the WORLD, beyond what my own motion explains? Needs pose
                  and depth, both recorded; the round trip is checked to 0.137 m. This is behaviour.
    neighbour     what is it up against -- the depth band of the ring around it, not of it. This is
                  relational: the same fence is a different neighbour of road than of sky.
    persistence   how many frames does it survive as a thing? A car passes and a wall does not. This
                  is temporal, and no single frame contains it.

REGISTERED BEFORE RUNNING, so the result can disappoint:
    1  count-matched, MIXED beats APPEARANCE on participation ratio. If it does not, question type is
       not the lever and the limit is capacity or corpus.
    2  the extra axes are structure and not noise: six-class naming must not fall as dimensions rise.
    3  one relation alone stays near 4, so nothing here is bought by training longer.

Run:  python scripts/question_type_vs_dimensionality.py
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.perception import learned_signature as LS         # noqa: E402
from packages.perception.world_frame import to_world            # noqa: E402

EPISODES = r"D:\carla\episodes"
OUT = "data/perception/question_type_vs_dimensionality.json"
R = 10                       # patch radius; 20 px side, matching signature_net_v2
DIM = 32
CAP = 46                     # patches per frame
STRIDE = 5


def _appearance(rgb, dep, y, x):
    p = rgb[y - R:y + R, x - R:x + R].astype(np.float32)
    d = float(np.median(dep[y - R:y + R, x - R:x + R]))
    mx, mn = p.max(2), p.min(2)
    sat = float(np.mean((mx - mn) / np.maximum(mx, 1.0)))
    return {"depth": int(np.clip(np.log2(max(d, 1.0)), 0, 7)),
            "height": int(y / rgb.shape[0] * 6),
            "texture": int(np.clip(np.log2(max(float(p.std()), 1.0)) * 1.5, 0, 7)),
            "colour": int(np.clip(sat * 8, 0, 7))}


def _neighbour(dep, y, x):
    """The depth band of the RING around the patch — what it is up against, not what it is."""
    o = R * 2
    y0, y1 = max(0, y - o), min(dep.shape[0], y + o)
    x0, x1 = max(0, x - o), min(dep.shape[1], x + o)
    ring = dep[y0:y1, x0:x1].copy()
    iy0, ix0 = y - R - y0, x - R - x0
    if iy0 >= 0 and ix0 >= 0:
        ring[iy0:iy0 + 2 * R, ix0:ix0 + 2 * R] = np.nan
    v = ring[np.isfinite(ring) & (ring > 0.5)]
    if v.size == 0:
        return 0
    return int(np.clip(np.log2(max(float(np.median(v)), 1.0)), 0, 7))


def harvest(eps, want: int) -> tuple:
    """Patches with every free key, including the ones that need two frames and a pose."""
    rng = np.random.default_rng(0)
    P, A = [], []
    for ep in eps:
        fs = sorted(glob.glob(os.path.join(EPISODES, ep, "*.npz")))
        for i in range(0, len(fs) - 2, STRIDE):
            if len(P) >= want:
                return np.stack(P), A
            a, b = np.load(fs[i]), np.load(fs[i + 1])
            rgb, dep, pose = a["rgb"], a["depth_m"].astype("float32"), a["pose"]
            rgb2, dep2, pose2 = b["rgb"], b["depth_m"].astype("float32"), b["pose"]
            h, w = dep.shape
            for _ in range(CAP):
                y = int(rng.integers(2 * R, h - 2 * R))
                x = int(rng.integers(2 * R, w - 2 * R))
                q = LS.crop_at(rgb, (x, y), 2 * R)
                if q is None:
                    continue
                z = float(np.median(dep[y - R:y + R, x - R:x + R]))
                z2 = float(np.median(dep2[y - R:y + R, x - R:x + R]))
                if not (np.isfinite(z) and 0.5 < z <= 200.0):
                    continue
                att = _appearance(rgb, dep, y, x)
                att["neighbour"] = _neighbour(dep, y, x)
                # BEHAVIOUR, not looks: how far this world point moved once my own motion is out.
                moved = 0.0
                if np.isfinite(z2) and 0.5 < z2 <= 200.0:
                    p1 = to_world((x, y), z, pose, rgb.shape[:2])
                    p2 = to_world((x, y), z2, pose2, rgb2.shape[:2])
                    moved = float(np.linalg.norm(p2 - p1))
                att["self_moving"] = int(np.clip(np.log2(max(moved, 0.05)) + 4, 0, 7))
                att["persistence"] = int(np.clip(np.log2(max(abs(z - z2), 0.02)) + 5, 0, 7))
                att["_id"] = len(P)
                P.append(q)
                A.append(att)
    return np.stack(P), A


def triplets(attrs, relations, n=6000, seed=0):
    rng = np.random.default_rng(seed)
    by = {r: {} for r in relations}
    for i, a in enumerate(attrs):
        for r in relations:
            by[r].setdefault(a[r], []).append(i)
    out = []
    for _ in range(n):
        r = relations[int(rng.integers(len(relations)))]
        keys = [k for k, v in by[r].items() if len(v) >= 2]
        if len(keys) < 2:
            continue
        k = keys[int(rng.integers(len(keys)))]
        pool = by[r][k]
        a = pool[int(rng.integers(len(pool)))]
        p = pool[int(rng.integers(len(pool)))]
        k2 = keys[int(rng.integers(len(keys)))]
        if k2 == k:
            continue
        neg = by[r][k2]
        out.append((a, p, neg[int(rng.integers(len(neg)))]))
    return out


def train(patches, trips, epochs=14, batch=128, lr=2e-3, margin=0.3):
    import torch
    net = LS.make_net(DIM, pool=2)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    X = torch.from_numpy(patches.astype(np.float32) / 255.0).permute(0, 3, 1, 2)
    T = np.asarray(trips)
    for _ in range(epochs):
        perm = np.random.default_rng(0).permutation(len(T))
        for s in range(0, len(T) - batch, batch):
            idx = T[perm[s:s + batch]]
            e = net(X[idx.reshape(-1)])
            e = e / e.norm(dim=1, keepdim=True).clamp(min=1e-6)
            a, p, n = e[0::3], e[1::3], e[2::3]
            loss = torch.relu(margin - (a * p).sum(1) + (a * n).sum(1)).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
    net.eval()
    return net


def participation_ratio(E):
    C = np.cov((E - E.mean(0)).T)
    w = np.linalg.eigvalsh(C)
    w = np.clip(w, 0, None)
    return float(w.sum() ** 2 / max(1e-12, (w ** 2).sum()))


APPEARANCE = ["depth", "height", "texture", "colour"]
MIXED = ["depth", "texture", "self_moving", "neighbour"]


def main() -> None:
    eps = sorted(e for e in os.listdir(EPISODES) if e.startswith("ep"))
    P, A = harvest(eps[0:20], 4200)
    print("harvested %d patches" % len(P))
    rows = {}
    for tag, rels in (("one relation (control)", ["depth"]),
                      ("four APPEARANCE", APPEARANCE),
                      ("four MIXED", MIXED),
                      ("all seven", APPEARANCE + ["self_moving", "neighbour", "persistence"])):
        trips = triplets(A, rels)
        net = train(P, trips)
        E = LS.embed(net, P)
        pr = participation_ratio(E)
        rows[tag] = {"relations": rels, "participation_ratio": pr, "triplets": len(trips)}
        print("%-26s  relations %d   effective dims %5.2f" % (tag, len(rels), pr))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"rows": rows, "human_reference_dims": "49 (Hebart 2020), 66 later",
                   "prior_one_relation": 3.9}, f, indent=1, ensure_ascii=False)
    print("\nwrote %s" % OUT)


if __name__ == "__main__":
    main()
