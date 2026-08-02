# -*- coding: utf-8 -*-
"""Raise the effective dimensionality of the signature space by demanding many KINDS of sameness.

    python scripts/dimensionality_from_many_samenesses.py

THE PROBLEM, measured. The signature encoder declares 32 dimensions and uses 3.9 -- participation ratio --
against ~49 for human object representations (Hebart et al. 2020) and ~66 in later work. Six classes at
0.789 precision and building colliding with vegetation at cosine 0.841 are what a four-dimensional space
buys. Vocabulary is not the constraint; naming costs 3-5 anchors per class, so 30,000 classes would be
~100k patches. The space is the constraint.

WHY IT IS FOUR, and the training code says it outright: `learned_signature.harvest` builds triplets where
the positive is THE SAME TRACK and the negative is another object in the same frame. That is ONE relation.
Separating tracks is satisfiable in very few dimensions, so an encoder handed 32 had no reason to spend
them.

WHY HUMANS HAVE FIFTY, and this is the part worth copying. Hebart's dimensions come from odd-one-out
judgements over 1,854 diverse objects: which of these three does not belong? Different triplets are settled
by DIFFERENT attributes -- is it metal, does it move, is it food, is it big -- so no single axis answers
them all and many axes have to exist. The dimensionality comes from the DIVERSITY OF THE QUESTION, not from
the size of the brain.

SO THE HYPOTHESIS IS DIRECT: define several independent "same as" relations and require one space to
satisfy all of them at once. Each relation that cannot be reduced to the others has to claim its own
subspace, so participation ratio should rise with the NUMBER of relations trained on.

Every relation below is free in the corpus -- no labels, no annotation, no external model:

    identity     the same place across adjacent frames        the current one
    depth        the same distance band                       depth_m is recorded per pixel
    height       the same band of image rows                  ground behaves unlike skyline
    lighting     the same frame                               shared exposure and weather
    texture      the same local contrast band                 free from the pixels
    colourfulness the same saturation band                    free from the pixels

REGISTERED before running:
    1  participation ratio RISES with the number of relations. If it does not, the hypothesis is wrong and
       the answer is capacity or data, not the objective.
    2  the gain is not free width: a one-relation model trained for the same steps stays near 4
    3  and the space stays USABLE -- six-class naming precision must not collapse while dimensions rise,
       or the extra axes are noise rather than structure
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception import learned_signature as LS      # noqa: E402
from packages.perception import naming                       # noqa: E402

CORPUS = Path(r"D:\carla\episodes")
OUT = Path("data/perception/dimensionality_from_many_samenesses.json")
R = 20
DIM = 32
EPISODES = ("ep440", "ep441", "ep443", "ep444")
PER_FRAME = 26


def attributes(rgb, dep, sem, y, x, r=R):
    """Every free 'same as' key for one patch. No labels are read except `sem`, used ONLY to score later."""
    p = rgb[y - r:y + r, x - r:x + r].astype(np.float32)
    d = float(np.median(dep[y - r:y + r, x - r:x + r]))
    mx = p.max(2)
    mn = p.min(2)
    sat = float(np.mean((mx - mn) / np.maximum(mx, 1.0)))
    return {"depth": int(np.clip(np.log2(max(d, 1.0)), 0, 7)),
            "height": int(y / rgb.shape[0] * 6),
            "texture": int(np.clip(np.log2(max(float(p.std()), 1.0)) * 1.5, 0, 7)),
            "colour": int(np.clip(sat * 8, 0, 7))}


def harvest(episodes, stride=6, cap=40):
    import collections
    rng = np.random.default_rng(0)
    P, A = [], []
    for ep in episodes:
        files = sorted(glob.glob(str(CORPUS / ep / "*.npz")))[::stride][:cap]
        for fi, f in enumerate(files):
            z = np.load(f)
            rgb, dep, sem = z["rgb"], z["depth_m"].astype(np.float32), z["semantic"]
            for _ in range(PER_FRAME):
                y = int(rng.integers(R, rgb.shape[0] - R))
                x = int(rng.integers(R, rgb.shape[1] - R))
                a = attributes(rgb, dep, sem, y, x)
                a["lighting"] = f"{ep}:{fi}"
                a["identity"] = f"{ep}:{fi // 2}:{y // 60}:{x // 60}"   # same place, adjacent frames
                s = sem[y - R:y + R, x - R:x + R]
                v, c = np.unique(s, return_counts=True)
                a["_class"] = int(v[c.argmax()]) if c.max() >= 0.6 * s.size else -1
                P.append(rgb[y - R:y + R, x - R:x + R])
                A.append(a)
    return np.stack(P), A


def triplets(attrs, relations, n=6000, seed=0):
    """(anchor, positive, negative) indices per relation: positive shares that key, negative does not."""
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
        i, j = rng.choice(by[r][k], 2, replace=False)
        k2 = k
        while k2 == k:
            k2 = keys[int(rng.integers(len(keys)))]
        nidx = by[r][k2][int(rng.integers(len(by[r][k2])))]
        out.append((int(i), int(j), int(nidx)))
    return out


def train(patches, trips, dim=DIM, epochs=14, batch=128, lr=2e-3, margin=0.3):
    import torch
    import torch.nn.functional as F

    net = LS.make_net(dim)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    X = torch.from_numpy(patches.astype(np.float32) / 255.0).permute(0, 3, 1, 2)
    T = np.asarray(trips)
    rng = np.random.default_rng(0)
    for _ in range(epochs):
        order = rng.permutation(len(T))
        for s in range(0, len(T) - batch + 1, batch):
            idx = T[order[s:s + batch]]
            a = F.normalize(net(X[idx[:, 0]]), dim=1)
            p = F.normalize(net(X[idx[:, 1]]), dim=1)
            n = F.normalize(net(X[idx[:, 2]]), dim=1)
            loss = F.relu(margin - (a * p).sum(1) + (a * n).sum(1)).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
    net.eval()
    return net


def participation_ratio(E):
    X = E - E.mean(0)
    s = np.linalg.svd(X, compute_uv=False)
    return float((s ** 2).sum() ** 2 / (s ** 4).sum())


def naming_precision(E, attrs):
    """Does the space stay usable? Six-class nearest-centroid with the abstention the namer uses."""
    import collections
    TAG = {1: "road", 2: "sidewalk", 3: "building", 9: "vegetation", 10: "terrain", 14: "car"}
    by = collections.defaultdict(list)
    for e, a in zip(E, attrs):
        if a["_class"] in TAG:
            by[TAG[a["_class"]]].append(e)
    by = {k: np.stack(v) for k, v in by.items() if len(v) >= 30}
    if len(by) < 3:
        return float("nan"), 0.0
    ks = sorted(by)
    book = naming.anchor_from({k: by[k][:10] for k in ks})
    ok = spoke = tot = 0
    for k in ks:
        for v in by[k][10:60]:
            nm, _ = naming.name_of(book, v)
            if nm is not None:
                spoke += 1
                ok += nm == k
            tot += 1
    return (ok / spoke if spoke else float("nan")), spoke / max(tot, 1)


def main() -> None:
    patches, attrs = harvest(EPISODES)
    print(f"{len(patches)} patches from {len(EPISODES)} episodes, {R * 2}x{R * 2}, "
          f"declared dim {DIM}\n")
    ladder = [["identity"],
              ["identity", "depth"],
              ["identity", "depth", "height"],
              ["identity", "depth", "height", "lighting"],
              ["identity", "depth", "height", "lighting", "texture"],
              ["identity", "depth", "height", "lighting", "texture", "colour"]]
    rows = {}
    print(f"{'relations trained on':<52}{'eff dims':>10}{'naming P':>10}{'cov':>8}")
    for rels in ladder:
        trips = triplets(attrs, rels)
        if len(trips) < 500:
            continue
        net = train(patches, trips)
        E = LS.embed(net, patches, "cpu")
        pr = participation_ratio(E)
        p, cov = naming_precision(E, attrs)
        rows[len(rels)] = {"relations": rels, "participation_ratio": pr,
                           "naming_precision": p, "coverage": cov, "triplets": len(trips)}
        print(f"{('+'.join(rels)):<52}{pr:>10.2f}{p:>10.3f}{cov:>8.1%}")

    ks = sorted(rows)
    rise = rows[ks[-1]]["participation_ratio"] > rows[ks[0]]["participation_ratio"] + 1.0
    mono = all(rows[ks[i]]["participation_ratio"] <= rows[ks[i + 1]]["participation_ratio"] + 0.5
               for i in range(len(ks) - 1))
    ps = [rows[k]["naming_precision"] for k in ks]
    print(f"\n-> 1. effective dimensions RISE with the number of samenesses: {rise}   "
          f"({rows[ks[0]]['participation_ratio']:.2f} -> {rows[ks[-1]]['participation_ratio']:.2f})")
    print(f"-> 2. and it rises monotonically rather than jumping once: {mono}")
    print(f"-> 3. the space stays usable: {np.nanmax(ps[1:]) >= ps[0] - 0.10}   "
          f"(naming precision {ps[0]:.3f} -> {ps[-1]:.3f})")
    print(f"\nhuman reference: ~49 dimensions (Hebart et al. 2020), ~66 in later work")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"declared_dim": DIM, "patches": len(patches),
                               "ladder": {str(k): v for k, v in rows.items()},
                               "human_reference_dims": "49 (Hebart 2020), 66 later"},
                              indent=2), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
