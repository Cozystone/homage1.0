# -*- coding: utf-8 -*-
"""Does the eye's encoder CONTAIN category information, or merely fail to read it out?

WHY THIS AND NOT SOMETHING ELSE. A self-consistent name book, anchors and test through one encoder,
held out on episodes the anchors never saw, scored 0.156 against a chance of 0.125. Two very
different worlds produce that number:

    the READOUT is bad     the information is in there and a centroid-and-cosine cannot get at it.
                           Then the fix is small and the encoder stays.
    the FEATURES are bad   InfoNCE over point tracks learned SAME THING, and same-kind was never in
                           the objective, so it is not in the embedding to be read. Then no naming
                           scheme on top of it will ever work and the encoder itself has to change.

A linear probe separates them, and it is the ceiling arm from the owner's own doctrine: hand the
answer over, measure what is reachable, and put a number on the gap. A probe cannot invent
information that is absent, so whatever it reaches is a floor on what the features hold.

THE PROBE'S SCORE IS NOT A CAPABILITY CLAIM. It is trained on labels ATANOR does not get to see at
runtime. It says what is IN the encoder, nothing about what the eye can do unaided.

Run:  python scripts/probe_encoder_categories.py
"""
from __future__ import annotations

import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.perception import learned_signature as LS       # noqa: E402

EPISODES = r"D:\carla\episodes"
NETS = {"v1": r"D:\carla\depth_model\signature_net.pt",
        "v2": r"D:\carla\depth_model\signature_net_v2.pt"}
WORDS = {1: "building", 2: "fence", 5: "pole", 6: "roadline", 7: "road", 8: "sidewalk",
         9: "vegetation", 10: "car", 11: "wall", 14: "ground", 22: "terrain"}
PURE = 0.9


def harvest(eps, per_word: int, seed: int, patch: int) -> dict:
    rng = np.random.default_rng(seed)
    out: dict = {k: [] for k in WORDS}
    for ep in eps:
        for f in sorted(glob.glob(os.path.join(EPISODES, ep, "*.npz")))[::3]:
            if all(len(v) >= per_word for v in out.values()):
                return out
            d = np.load(f)
            rgb, sem = d["rgb"], d["semantic"]
            h, w = sem.shape
            for _ in range(200):
                x = int(rng.integers(patch, w - patch))
                y = int(rng.integers(patch, h - patch))
                win = sem[y - patch // 2:y + patch // 2, x - patch // 2:x + patch // 2]
                if win.size == 0:
                    continue
                ids, cnt = np.unique(win, return_counts=True)
                k = int(ids[int(np.argmax(cnt))])
                if k not in out or cnt.max() / win.size < PURE or len(out[k]) >= per_word:
                    continue
                q = LS.crop_at(rgb, (x, y), patch)
                if q is not None:
                    out[k].append(q)
    return out


def _softmax_probe(Xtr, ytr, Xte, yte, n_cls, steps=900, lr=0.5, l2=1e-3):
    """Multinomial logistic regression by plain gradient descent — no sklearn dependency.

    Linear ON PURPOSE. A deep probe would report what a new network can learn from pixels, which is a
    different question; a linear one reports what is already laid out in the embedding."""
    rng = np.random.default_rng(0)
    W = rng.normal(0, 0.01, (Xtr.shape[1], n_cls))
    b = np.zeros(n_cls)
    Y = np.eye(n_cls)[ytr]
    for _ in range(steps):
        z = Xtr @ W + b
        z -= z.max(1, keepdims=True)
        p = np.exp(z)
        p /= p.sum(1, keepdims=True)
        g = (p - Y) / len(Xtr)
        W -= lr * (Xtr.T @ g + l2 * W)
        b -= lr * g.sum(0)
    pred = (Xte @ W + b).argmax(1)
    return float((pred == yte).mean())


def main() -> None:
    eps = sorted(e for e in os.listdir(EPISODES) if e.startswith("ep"))
    print("%-4s %6s %8s %10s %10s %8s" %
          ("net", "patch", "words", "centroid", "linear", "chance"))
    for tag, path in NETS.items():
        net, patch = LS.load_encoder(path)
        tr = harvest(eps[0:24], 120, 0, patch)
        te = harvest(eps[40:62], 120, 1, patch)
        names = [WORDS[k] for k in WORDS if len(tr[k]) >= 40 and len(te[k]) >= 40]
        idx = {n: i for i, n in enumerate(names)}
        inv = {v: k for k, v in WORDS.items()}
        Xtr, ytr, Xte, yte = [], [], [], []
        for n in names:
            e = LS.embed(net, np.stack(tr[inv[n]]))
            Xtr.append(e / np.maximum(1e-9, np.linalg.norm(e, axis=1, keepdims=True)))
            ytr += [idx[n]] * len(e)
            e = LS.embed(net, np.stack(te[inv[n]]))
            Xte.append(e / np.maximum(1e-9, np.linalg.norm(e, axis=1, keepdims=True)))
            yte += [idx[n]] * len(e)
        Xtr, Xte = np.concatenate(Xtr), np.concatenate(Xte)
        ytr, yte = np.array(ytr), np.array(yte)
        C = np.stack([Xtr[ytr == i].mean(0) for i in range(len(names))])
        C /= np.maximum(1e-9, np.linalg.norm(C, axis=1, keepdims=True))
        cen = float(((Xte @ C.T).argmax(1) == yte).mean())
        lin = _softmax_probe(Xtr, ytr, Xte, yte, len(names))
        print("%-4s %6d %8d %10.3f %10.3f %8.3f"
              % (tag, patch, len(names), cen, lin, 1.0 / len(names)))
    print()
    print("centroid = what naming actually does today. linear = what is IN the embedding at all.")
    print("if linear is also near chance, the objective never put kinds in there and the encoder "
          "itself has to change.")


if __name__ == "__main__":
    main()
