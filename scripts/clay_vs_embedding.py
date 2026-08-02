# -*- coding: utf-8 -*-
"""Is a thing better held as a SHAPE YOU COULD REBUILD than as a point in an embedding?

OWNER'S PROPOSAL, and it is a different theory of what a concept IS. Show a person many apples, hand
them clay, and they can make one. What they kept was not a coordinate that separates apples from
pears; it was something they can BUILD FROM. So store a learned object as a flexible standard shape
-- SPLATRA-particle-like -- and recognise the next one by how well that shape can be made to fit.

WHY IT IS WORTH TESTING NOW RATHER THAN LATER. The discriminative path was measured to a hard low
ceiling today: told the answers outright, the encoder names whole objects at 0.333 against a chance of
0.167. A 32-dimensional embedding must crush a thing into a point, and everything the point cannot
carry is gone. A reconstruction has no such bottleneck -- and, decisive for this project, it comes
with a FREE ORACLE. You do not need a label to know whether your clay apple is right; you look at the
apple. The analogy is not decoration, it is the scoring rule.

WHAT WAS ALREADY THERE AND WHAT WAS MISSING. The clay exists -- packages/splatra_imagination has
generators, packages/imagination compiles a thought into a scene. But archetypes.py is 224 lines of
HAND-WRITTEN generators (orbs, golden-angle spirals) with no `fit`, `learn` or `train` anywhere in it.
The shapes were authored, not observed. That is precisely the gap the owner's proposal closes, so the
prototypes here are fitted to what the eye actually saw.

THE COMPARISON IS BUDGET-MATCHED, which is what makes it a test rather than a demonstration:

    embedding      the 32-dim learned signature of the thing            32 numbers
    clay           how badly each of 32 observed prototypes must be     32 numbers
                   stretched to explain this thing

Same regions, same labels, same held-out episodes, same nearest-centroid readout. Only the
representation differs.

REGISTERED BEFORE RUNNING:
    1  clay > embedding on held-out naming. If not, reconstruction is not the lever here and the
       ceiling is about capacity, not about the shape of the representation.
    2  the clay features are not merely SIZE in disguise -- a control using only each region's area
       and mean depth must score below both.

Run:  python scripts/clay_vs_embedding.py
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.perception import common_fate as CF                          # noqa: E402
from packages.perception import learned_signature as LS                    # noqa: E402

EPISODES = r"D:\carla\episodes"
NET = r"D:\carla\depth_model\signature_net_v2.pt"
OUT = "data/perception/clay_vs_embedding.json"
GRID, K, STRIDE = 12, 32, 3


def _canvas(rgb, dep, mask, y0, y1, x0, x1) -> np.ndarray:
    """One thing as something you could rebuild: its silhouette, its surface, its colour.

    Normalised out of its own box, so the SHAPE is what is kept and not the position or the scale --
    the same reason a person's idea of an apple is not tied to how far away it was."""
    import cv2
    sub = mask[y0:y1, x0:x1].astype(np.float32)
    sil = cv2.resize(sub, (GRID, GRID), interpolation=cv2.INTER_AREA)
    d = dep[y0:y1, x0:x1].astype(np.float32).copy()
    d[~mask[y0:y1, x0:x1]] = np.nan
    good = np.isfinite(d) & (d > 0.5)
    if good.sum() < 4:
        return None
    med = float(np.median(d[good]))
    rel = np.where(good, (d - med) / max(1e-3, med), 0.0).astype(np.float32)
    prof = cv2.resize(np.clip(rel, -1, 1), (GRID, GRID), interpolation=cv2.INTER_AREA)
    px = rgb[y0:y1, x0:x1][mask[y0:y1, x0:x1]]
    col = np.concatenate([np.histogram(px[:, c], bins=6, range=(0, 256))[0] for c in range(3)])
    col = col.astype(np.float32) / max(1.0, col.sum())
    return np.concatenate([sil.ravel(), prof.ravel(), col])


def collect(eps) -> tuple:
    net, patch = LS.load_encoder(NET)
    canvases, embeds, labels, plain = [], [], [], []
    for ep in eps:
        fs = sorted(glob.glob(os.path.join(EPISODES, ep, "*.npz")))
        for i in range(0, len(fs) - 1, STRIDE):
            a, b = np.load(fs[i]), np.load(fs[i + 1])
            rgb, sem, dm = a["rgb"], a["semantic"], a["depth_m"].astype("float32")
            for r in CF.things(rgb, b["rgb"], dm):
                ys, xs = np.nonzero(r.mask)
                if xs.size < 40:
                    continue
                y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
                if (y1 - y0) < 8 or (x1 - x0) < 8:
                    continue
                v = sem[r.mask]
                ids, cnt = np.unique(v, return_counts=True)
                if cnt.max() / v.size < 0.6:
                    continue
                cv = _canvas(rgb, dm, r.mask, y0, y1, x0, x1)
                if cv is None:
                    continue
                cy, cx = int(ys.mean()), int(xs.mean())
                q = LS.crop_at(rgb, (cx, cy), patch)
                if q is None:
                    continue
                canvases.append(cv)
                embeds.append(LS.embed(net, q[None])[0])
                labels.append(int(ids[int(np.argmax(cnt))]))
                dv = dm[r.mask]
                dv = dv[np.isfinite(dv) & (dv > 0.5)]
                plain.append([float(r.mask.sum()) ** 0.5,
                              float(np.median(dv)) if dv.size else 0.0])
    return (np.stack(canvases), np.stack(embeds), np.array(labels), np.array(plain))


def fit_prototypes(C, k=K, iters=25, seed=0) -> np.ndarray:
    """The clay: k shapes fitted to what was actually seen. Plain k-means, deliberately.

    Anything cleverer would make it unclear whether a win came from the IDEA -- keep a thing as
    something rebuildable -- or from the fitting machinery."""
    rng = np.random.default_rng(seed)
    P = C[rng.choice(len(C), size=min(k, len(C)), replace=False)].copy()
    for _ in range(iters):
        d = ((C[:, None, :] - P[None, :, :]) ** 2).sum(2)
        a = d.argmin(1)
        for j in range(len(P)):
            m = C[a == j]
            if len(m):
                P[j] = m.mean(0)
    return P


def residuals(C, P) -> np.ndarray:
    """How badly each prototype has to be stretched to explain each thing. THE representation."""
    d = np.sqrt(((C[:, None, :] - P[None, :, :]) ** 2).sum(2))
    return d / np.maximum(1e-6, d.mean(1, keepdims=True))     # relative: scale drops out


def name(Xtr, ytr, Xte, yte, k) -> float:
    Xtr = Xtr / np.maximum(1e-9, np.linalg.norm(Xtr, axis=1, keepdims=True))
    Xte = Xte / np.maximum(1e-9, np.linalg.norm(Xte, axis=1, keepdims=True))
    C = np.stack([Xtr[ytr == c].mean(0) if (ytr == c).any() else np.zeros(Xtr.shape[1])
                  for c in range(k)])
    C = C / np.maximum(1e-9, np.linalg.norm(C, axis=1, keepdims=True))
    return float(((Xte @ C.T).argmax(1) == yte).mean())


def main() -> None:
    eps = sorted(e for e in os.listdir(EPISODES) if e.startswith("ep"))
    Ctr, Etr, Ltr, Ptr = collect(eps[0:16])
    Cte, Ete, Lte, Pte = collect(eps[44:56])
    keep = sorted({c for c in set(Ltr) & set(Lte)
                   if (Ltr == c).sum() >= 12 and (Lte == c).sum() >= 6})
    idx = {c: i for i, c in enumerate(keep)}
    mtr, mte = np.isin(Ltr, keep), np.isin(Lte, keep)
    ytr = np.array([idx[c] for c in Ltr[mtr]])
    yte = np.array([idx[c] for c in Lte[mte]])
    print("things: train %d | held-out %d | classes %d | chance %.3f"
          % (mtr.sum(), mte.sum(), len(keep), 1 / len(keep)))

    P = fit_prototypes(Ctr[mtr])
    rows = {
        "clay (32 fitted prototypes)": name(residuals(Ctr[mtr], P), ytr,
                                            residuals(Cte[mte], P), yte, len(keep)),
        "embedding (32-dim signature)": name(Etr[mtr], ytr, Ete[mte], yte, len(keep)),
        "control (size + depth only)": name(Ptr[mtr], ytr, Pte[mte], yte, len(keep)),
    }
    print("%-32s %10s" % ("representation", "naming"))
    for k, v in rows.items():
        print("%-32s %10.3f" % (k, v))
    lift = rows["clay (32 fitted prototypes)"] - rows["embedding (32-dim signature)"]
    print("\nclay minus embedding: %+.3f" % lift)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"rows": rows, "lift_over_embedding": lift, "chance": 1 / len(keep),
                   "classes": [int(c) for c in keep], "prototypes": int(K),
                   "note": "prototypes are FITTED to observed things, not authored; both arms carry "
                           "32 numbers per thing and share regions, labels and readout"},
                  f, indent=1)
    print("wrote %s" % OUT)


if __name__ == "__main__":
    main()
