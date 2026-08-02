# -*- coding: utf-8 -*-
"""Does naming a WHOLE THING lift the ceiling that naming a crop of it sits under?

THE NUMBER THIS ANSWERS TO. Told the answers outright, the encoder names 40x40 crops at 0.367 on
held-out episodes against a chance of 0.125. That is the CEILING, so no relation set and no loss
function beats it -- and it is low. A crop of wall and a crop of fence are not distinguishable at
that size, and no objective creates information the input does not carry.

`common_fate.things` returns whole objects, verified at 0.884 purity against 0.599 for chance. If the
ceiling is set by how much of the thing is visible rather than by capacity, showing the whole thing
should move it.

THE CONTROL IS THE SAME REGIONS SEEN TWO WAYS, which is what makes this clean rather than another
sampling difference:

    crop    the 40x40 centred on the region -- what naming does today
    whole   the region's whole bounding box, resized to 40x40 -- same pixels of input, more of the
            object and less of its detail

Identical regions, identical labels, identical count, identical net, steps and held-out episodes. The
only thing that differs is how much of the object reaches the encoder. Both arms are CEILING arms,
trained on the simulator's classes, so neither is a capability claim; what is being compared is what
the architecture can hold about a thing given a view of it.

REGISTERED BEFORE RUNNING:
    1  whole > crop. If it is not, the limit is capacity and the encoder has to grow, and no amount
       of better segmentation will help.
    2  crop reproduces about 0.37, or this is not the same measurement as the one it argues with.

Run:  python scripts/whole_object_ceiling.py
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
OUT = "data/perception/whole_object_ceiling.json"
SIDE, DIM, STRIDE = 40, 32, 3


def _resize(img, side=SIDE):
    import cv2
    return cv2.resize(img, (side, side), interpolation=cv2.INTER_AREA)


def collect(eps) -> tuple:
    """Every thing found, in both representations, with the class it really is."""
    crops, wholes, labels = [], [], []
    for ep in eps:
        fs = sorted(glob.glob(os.path.join(EPISODES, ep, "*.npz")))
        for i in range(0, len(fs) - 1, STRIDE):
            a, b = np.load(fs[i]), np.load(fs[i + 1])
            rgb, sem, dm = a["rgb"], a["semantic"], a["depth_m"].astype("float32")
            for r in CF.things(rgb, b["rgb"], dm):
                ys, xs = np.nonzero(r.mask)
                if xs.size == 0:
                    continue
                y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
                if (y1 - y0) < 8 or (x1 - x0) < 8:
                    continue
                cy, cx = int(ys.mean()), int(xs.mean())
                h, w = rgb.shape[:2]
                if not (SIDE // 2 <= cy < h - SIDE // 2 and SIDE // 2 <= cx < w - SIDE // 2):
                    continue
                v = sem[r.mask]
                ids, cnt = np.unique(v, return_counts=True)
                if cnt.max() / v.size < 0.6:
                    continue                       # a mixed region has no single right answer
                labels.append(int(ids[int(np.argmax(cnt))]))
                crops.append(rgb[cy - SIDE // 2:cy + SIDE // 2, cx - SIDE // 2:cx + SIDE // 2])
                wholes.append(_resize(rgb[y0:y1, x0:x1]))
    return np.stack(crops), np.stack(wholes), np.array(labels)


def train_supervised(X, y, n_cls, epochs=20, batch=64, lr=2e-3):
    import torch
    net = LS.make_net(DIM)
    head = torch.nn.Linear(DIM, n_cls)
    opt = torch.optim.Adam(list(net.parameters()) + list(head.parameters()), lr=lr)
    lossf = torch.nn.CrossEntropyLoss()
    Xt = torch.from_numpy(X.astype(np.float32) / 255.0).permute(0, 3, 1, 2)
    yt = torch.tensor(y)
    for _ in range(epochs):
        perm = torch.randperm(len(yt))
        for s in range(0, max(1, len(yt) - batch), batch):
            i = perm[s:s + batch]
            e = net(Xt[i])
            e = e / e.norm(dim=1, keepdim=True).clamp(min=1e-6)
            loss = lossf(head(e), yt[i])
            opt.zero_grad()
            loss.backward()
            opt.step()
    net.eval()
    return net


def score(net, Xtr, ytr, Xte, yte, n_cls) -> float:
    Etr, Ete = LS.embed(net, Xtr), LS.embed(net, Xte)
    C = []
    for c in range(n_cls):
        m = Etr[ytr == c]
        C.append(m.mean(0) / max(1e-9, np.linalg.norm(m.mean(0))) if len(m) else np.zeros(DIM))
    C = np.stack(C)
    Ete = Ete / np.maximum(1e-9, np.linalg.norm(Ete, axis=1, keepdims=True))
    return float(((Ete @ C.T).argmax(1) == yte).mean())


def main() -> None:
    eps = sorted(e for e in os.listdir(EPISODES) if e.startswith("ep"))
    Ctr, Wtr, Ltr = collect(eps[0:16])
    Cte, Wte, Lte = collect(eps[44:56])
    keep = sorted({c for c in set(Ltr) & set(Lte) if (Ltr == c).sum() >= 12 and (Lte == c).sum() >= 6})
    idx = {c: i for i, c in enumerate(keep)}
    mtr, mte = np.isin(Ltr, keep), np.isin(Lte, keep)
    ytr = np.array([idx[c] for c in Ltr[mtr]])
    yte = np.array([idx[c] for c in Lte[mte]])
    print("things: train %d | held-out %d | classes %d | chance %.3f"
          % (mtr.sum(), mte.sum(), len(keep), 1 / len(keep)))
    rows = {}
    print("%-30s %10s" % ("representation", "naming"))
    for tag, Xtr, Xte in (("crop  (40x40 centre)", Ctr[mtr], Cte[mte]),
                          ("whole (the thing, resized)", Wtr[mtr], Wte[mte])):
        net = train_supervised(Xtr, ytr, len(keep))
        acc = score(net, Xtr, ytr, Xte, yte, len(keep))
        rows[tag] = {"naming_heldout": acc, "chance": 1 / len(keep)}
        print("%-30s %10.3f" % (tag, acc))
    lift = rows["whole (the thing, resized)"]["naming_heldout"] - \
        rows["crop  (40x40 centre)"]["naming_heldout"]
    print("\nlift from seeing the whole thing: %+.3f" % lift)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"rows": rows, "lift": lift, "classes": [int(c) for c in keep],
                   "note": "both arms are CEILING arms trained on simulator labels; this compares "
                           "what the architecture can hold, not what the eye does unaided"},
                  f, indent=1)
    print("wrote %s" % OUT)


if __name__ == "__main__":
    main()
