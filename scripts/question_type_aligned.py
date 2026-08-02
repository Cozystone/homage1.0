# -*- coding: utf-8 -*-
"""The count-matched question-type test, on the SAME RULER as the experiment it argues with.

WHAT CAME BEFORE, and it needs restating because it was a disconfirmation that did not travel.
`dimensionality_from_many_samenesses` registered "participation ratio RISES with the number of
relations". Its own ladder:

    identity alone                                   PR 5.59   naming 0.768
    + depth                                          PR 4.53   naming 0.759
    + height                                         PR 3.21   naming 0.657
    + lighting                                       PR 4.33   naming 0.783
    + texture                                        PR 4.36   naming 0.773
    + colour                                         PR 4.05   naming 0.623

It FELL from the first addition and naming never improved. The hypothesis was refuted by its own
criteria, and the file that carries that refutation is the same file later cited as the fix.

THE SURVIVING READING, from both that ladder and the first run of this test, is narrower and it is
about KIND rather than count: every relation added there was computable FROM THE PATCH -- its median
depth, its image row, its pixel deviation, its saturation. Four spellings of "what does this look
like", mutually correlated in a rendered street. The one arm in either experiment that rose above its
own control was the one asking a different KIND of question.

THIS RUN PUTS THAT ON THE ORIGINAL'S RULER. Same radius 20, same pool 1, same optimiser, same steps,
identity held constant in every arm, and only the three added relations differing in type:

    APPEARANCE   depth, height, texture          what the patch looks like
    BEHAVIOURAL  self_moving, neighbour, persistence   what it does, what it is against, how long
                                                       it lasts -- none readable from the patch alone

REGISTERED BEFORE RUNNING:
    1  identity alone reproduces about 5.6. If it does not, this is not the original's ruler and no
       cross-experiment comparison may be drawn from it.
    2  count-matched, BEHAVIOURAL > APPEARANCE on participation ratio.
    3  and naming does not fall while dimensions rise, or the extra axes are noise.
    Failing 2 means question type is not the lever either, and the limit is capacity or corpus.

Run:  python scripts/question_type_aligned.py
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
OUT = "data/perception/question_type_aligned.json"
R, DIM, PER_FRAME, STRIDE, CAP = 20, 32, 26, 6, 40


def _ring_band(dep, y, x) -> int:
    o = R * 2
    y0, y1 = max(0, y - o), min(dep.shape[0], y + o)
    x0, x1 = max(0, x - o), min(dep.shape[1], x + o)
    ring = dep[y0:y1, x0:x1].astype(np.float32).copy()
    iy, ix = y - R - y0, x - R - x0
    if iy >= 0 and ix >= 0:
        ring[iy:iy + 2 * R, ix:ix + 2 * R] = np.nan
    v = ring[np.isfinite(ring) & (ring > 0.5)]
    return 0 if v.size == 0 else int(np.clip(np.log2(max(float(np.median(v)), 1.0)), 0, 7))


def harvest(eps, rng) -> tuple:
    P, A = [], []
    for ep in eps:
        files = sorted(glob.glob(os.path.join(EPISODES, ep, "*.npz")))[::STRIDE][:CAP]
        for fi in range(len(files) - 1):
            z, z2 = np.load(files[fi]), np.load(files[fi + 1])
            rgb, dep, sem, pose = z["rgb"], z["depth_m"].astype(np.float32), z["semantic"], z["pose"]
            dep2, pose2 = z2["depth_m"].astype(np.float32), z2["pose"]
            for _ in range(PER_FRAME):
                y = int(rng.integers(2 * R, rgb.shape[0] - 2 * R))
                x = int(rng.integers(2 * R, rgb.shape[1] - 2 * R))
                p = rgb[y - R:y + R, x - R:x + R].astype(np.float32)
                d = float(np.median(dep[y - R:y + R, x - R:x + R]))
                d2 = float(np.median(dep2[y - R:y + R, x - R:x + R]))
                if not (np.isfinite(d) and 0.5 < d <= 200.0):
                    continue
                mx, mn = p.max(2), p.min(2)
                a = {
                    # --- the original's keys, unchanged -------------------------------------------
                    "identity": "%s:%d:%d:%d" % (ep, fi // 2, y // 60, x // 60),
                    "depth": int(np.clip(np.log2(max(d, 1.0)), 0, 7)),
                    "height": int(y / rgb.shape[0] * 6),
                    "texture": int(np.clip(np.log2(max(float(p.std()), 1.0)) * 1.5, 0, 7)),
                    "colour": int(np.clip(float(np.mean((mx - mn) / np.maximum(mx, 1.0))) * 8, 0, 7)),
                    # --- questions the patch cannot answer about itself ---------------------------
                    "neighbour": _ring_band(dep, y, x),
                }
                moved = 0.0
                if np.isfinite(d2) and 0.5 < d2 <= 200.0:
                    moved = float(np.linalg.norm(to_world((x, y), d, pose, rgb.shape[:2])
                                                 - to_world((x, y), d2, pose2, rgb.shape[:2])))
                a["self_moving"] = int(np.clip(np.log2(max(moved, 0.05)) + 4, 0, 7))
                a["persistence"] = int(np.clip(np.log2(max(abs(d - d2), 0.02)) + 5, 0, 7))
                s = sem[y - R:y + R, x - R:x + R]
                v, c = np.unique(s, return_counts=True)
                a["_class"] = int(v[c.argmax()]) if c.max() >= 0.6 * s.size else -1
                P.append(rgb[y - R:y + R, x - R:x + R])
                A.append(a)
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
        k2 = keys[int(rng.integers(len(keys)))]
        if k2 == k:
            continue
        pool, neg = by[r][k], by[r][k2]
        out.append((pool[int(rng.integers(len(pool)))], pool[int(rng.integers(len(pool)))],
                    neg[int(rng.integers(len(neg)))]))
    return out


def train(patches, trips, epochs=14, batch=128, lr=2e-3, margin=0.3):
    import torch
    net = LS.make_net(DIM)                       # pool 1, exactly as the original
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    X = torch.from_numpy(patches.astype(np.float32) / 255.0).permute(0, 3, 1, 2)
    T = np.asarray(trips)
    for _ in range(epochs):
        perm = np.random.default_rng(0).permutation(len(T))
        for s in range(0, len(T) - batch, batch):
            idx = T[perm[s:s + batch]].reshape(-1)
            e = net(X[idx])
            e = e / e.norm(dim=1, keepdim=True).clamp(min=1e-6)
            a, p, n = e[0::3], e[1::3], e[2::3]
            loss = torch.relu(margin - (a * p).sum(1) + (a * n).sum(1)).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
    net.eval()
    return net


def participation_ratio(E) -> float:
    w = np.clip(np.linalg.eigvalsh(np.cov((E - E.mean(0)).T)), 0, None)
    return float(w.sum() ** 2 / max(1e-12, (w ** 2).sum()))


def naming(Etr, Atr, Ete, Ate) -> tuple:
    """Held-out nearest-centroid naming over the simulator's classes. Scoring only."""
    cls = sorted({a["_class"] for a in Atr if a["_class"] >= 0}
                 & {a["_class"] for a in Ate if a["_class"] >= 0})
    cls = [c for c in cls if sum(1 for a in Atr if a["_class"] == c) >= 20]
    if len(cls) < 3:
        return (float("nan"), 0.0, 0)
    C = []
    for c in cls:
        v = Etr[[i for i, a in enumerate(Atr) if a["_class"] == c]].mean(0)
        C.append(v / max(1e-9, np.linalg.norm(v)))
    C = np.stack(C)
    idx = [i for i, a in enumerate(Ate) if a["_class"] in cls]
    if not idx:
        return (float("nan"), 0.0, len(cls))
    X = Ete[idx]
    X = X / np.maximum(1e-9, np.linalg.norm(X, axis=1, keepdims=True))
    y = np.array([cls.index(Ate[i]["_class"]) for i in idx])
    return (float(((X @ C.T).argmax(1) == y).mean()), 1.0 / len(cls), len(cls))


ARMS = {
    "identity alone (control)": ["identity"],
    "identity + 3 APPEARANCE": ["identity", "depth", "height", "texture"],
    "identity + 3 BEHAVIOURAL": ["identity", "self_moving", "neighbour", "persistence"],
}


def main() -> None:
    eps = sorted(e for e in os.listdir(EPISODES) if e.startswith("ep"))
    Ptr, Atr = harvest(eps[0:14], np.random.default_rng(0))
    Pte, Ate = harvest(eps[44:54], np.random.default_rng(1))
    print("train %d patches | held-out %d patches" % (len(Ptr), len(Pte)))
    rows = {}
    print("%-28s %6s %10s %10s %8s" % ("arm", "rels", "eff dims", "naming", "chance"))
    for tag, rels in ARMS.items():
        net = train(Ptr, triplets(Atr, rels))
        Etr, Ete = LS.embed(net, Ptr), LS.embed(net, Pte)
        pr = participation_ratio(Etr)
        acc, ch, k = naming(Etr, Atr, Ete, Ate)
        rows[tag] = {"relations": rels, "participation_ratio": pr, "naming_heldout": acc,
                     "chance": ch, "classes": k}
        print("%-28s %6d %10.2f %10.3f %8.3f" % (tag, len(rels), pr, acc, ch))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"rows": rows, "original_identity_alone": 5.59,
                   "human_reference_dims": "49 (Hebart 2020), 66 later"}, f, indent=1)
    print("\nwrote %s" % OUT)


if __name__ == "__main__":
    main()
