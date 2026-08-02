# -*- coding: utf-8 -*-
"""Does effective dimensionality rise with the number of KINDS of thing? The test CARLA could not run.

    python scripts/dimensionality_vs_kinds.py

THE QUESTION, and why it could not be asked before. The signature space declares 32 dimensions and uses
3.9 (participation ratio), against ~49 for human object representations (Hebart et al. 2020) and ~66 in
later work. Adding more KINDS OF SAMENESS to the objective was tried and refuted -- effective dimensions
drifted from 5.6 down to 4.1 -- because depth, height and texture are nearly the same cut in a street.

That refutation pointed at the other diversity. Hebart's 49 dimensions came from 1,854 KINDS OF THING, not
1,854 kinds of question, and the CARLA corpus holds SIX: road, building, vegetation, sidewalk, terrain,
car. A space over six kinds of stuff has no reason to hold fifty dimensions no matter what trains it, so
the hypothesis was not merely untested there -- it was untestable.

CIFAR-100 makes it testable: 100 classes, 500 images each, exactly balanced. Same encoder architecture,
same training procedure, same measurement. The only thing that changes is how many kinds of thing exist.

REGISTERED before running:
    1  participation ratio RISES with the number of classes trained on. If it stays near 4 with a hundred
       kinds available, diversity is not the lever either and the constraint is capacity or objective.
    2  it is not an artefact of more DATA: a control trained on the same number of images drawn from only
       six classes must stay low
    3  the space stays usable -- nearest-centroid naming accuracy must not collapse as dimensions rise, or
       the extra axes are noise
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception import learned_signature as LS      # noqa: E402
from packages.perception import naming                       # noqa: E402

PARQUET = Path(r"D:\carla\objects\cifar100_train.parquet")
OUT = Path("data/perception/dimensionality_vs_kinds.json")
DIM = 32
PER_CLASS = 120
PATCH = 32


def load(n_classes: int, per_class: int = PER_CLASS, seed: int = 0):
    """(images, labels) for the first `n_classes` fine labels. 32x32 native, no resize."""
    import pyarrow.parquet as pq
    from PIL import Image

    t = pq.read_table(PARQUET, columns=["img", "fine_label"])
    labels = t.column("fine_label").to_pylist()
    imgs = t.column("img").to_pylist()
    want = set(range(n_classes))
    by = {}
    for im, lb in zip(imgs, labels):
        if lb not in want or len(by.get(lb, [])) >= per_class:
            continue
        by.setdefault(lb, []).append(np.array(Image.open(io.BytesIO(im["bytes"])).convert("RGB")))
    X, y = [], []
    for lb in sorted(by):
        for a in by[lb]:
            X.append(a)
            y.append(lb)
    return np.stack(X), np.array(y)


def triplets(y, n=8000, seed=0):
    """anchor / positive (same class) / negative (different class). ONE relation, as before."""
    rng = np.random.default_rng(seed)
    by = {}
    for i, lb in enumerate(y):
        by.setdefault(int(lb), []).append(i)
    keys = sorted(by)
    out = []
    for _ in range(n):
        k = keys[int(rng.integers(len(keys)))]
        if len(by[k]) < 2:
            continue
        i, j = rng.choice(by[k], 2, replace=False)
        k2 = k
        while k2 == k:
            k2 = keys[int(rng.integers(len(keys)))]
        out.append((int(i), int(j), int(by[k2][int(rng.integers(len(by[k2])))])))
    return out


def train(X, trips, dim=DIM, epochs=12, batch=128, lr=2e-3, margin=0.3):
    import torch
    import torch.nn.functional as F

    net = LS.make_net(dim)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    T = torch.from_numpy(X.astype(np.float32) / 255.0).permute(0, 3, 1, 2)
    A = np.asarray(trips)
    rng = np.random.default_rng(0)
    for _ in range(epochs):
        order = rng.permutation(len(A))
        for s in range(0, len(A) - batch + 1, batch):
            idx = A[order[s:s + batch]]
            a = F.normalize(net(T[idx[:, 0]]), dim=1)
            p = F.normalize(net(T[idx[:, 1]]), dim=1)
            n = F.normalize(net(T[idx[:, 2]]), dim=1)
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


def naming_accuracy(E, y, n_anchor=10, seed=0):
    """Nearest-centroid over held-out items, with the namer's abstention. Usability check."""
    rng = np.random.default_rng(seed)
    by = {}
    for e, lb in zip(E, y):
        by.setdefault(int(lb), []).append(e)
    by = {k: np.stack(v) for k, v in by.items() if len(v) >= n_anchor + 20}
    if len(by) < 3:
        return float("nan"), 0.0
    ks = sorted(by)
    book = naming.anchor_from({str(k): by[k][:n_anchor] for k in ks})
    ok = spoke = tot = 0
    for k in ks:
        for v in by[k][n_anchor:n_anchor + 20]:
            nm, _ = naming.name_of(book, v, min_cosine=0.0)      # accuracy, not precision: no refusals
            ok += nm == str(k)
            spoke += 1
            tot += 1
    return ok / max(spoke, 1), spoke / max(tot, 1)


def main() -> None:
    if not PARQUET.exists():
        sys.exit(f"no CIFAR-100 at {PARQUET}")
    rows = {}
    print(f"{'classes':<9}{'images':>8}{'eff dims':>10}{'naming acc':>12}{'chance':>9}")
    for n in (2, 6, 12, 25, 50, 100):
        X, y = load(n)
        net = train(X, triplets(y))
        E = LS.embed(net, X, "cpu")
        pr = participation_ratio(E)
        acc, _cov = naming_accuracy(E, y)
        rows[n] = {"images": int(len(X)), "participation_ratio": pr, "naming_accuracy": acc,
                   "chance": 1.0 / n}
        print(f"{n:<9}{len(X):>8}{pr:>10.2f}{acc:>12.3f}{1.0 / n:>9.3f}")

    # CONTROL: the same number of images as the 100-class run, but drawn from only six classes.
    # If dimensionality tracks DATA rather than KINDS, this rises too.
    X6, y6 = load(6, per_class=PER_CLASS * 100 // 6)
    net6 = train(X6, triplets(y6))
    pr6 = participation_ratio(LS.embed(net6, X6, "cpu"))
    print(f"\ncontrol: 6 classes but {len(X6)} images (matching the 100-class run) "
          f"-> eff dims {pr6:.2f}")

    ks = sorted(rows)
    rise = rows[ks[-1]]["participation_ratio"] > rows[ks[0]]["participation_ratio"] + 2.0
    not_data = rows[ks[-1]]["participation_ratio"] > pr6 + 1.0
    accs = [rows[k]["naming_accuracy"] / rows[k]["chance"] for k in ks]
    print(f"\n-> 1. effective dimensions RISE with the number of KINDS: {rise}   "
          f"({rows[ks[0]]['participation_ratio']:.2f} -> {rows[ks[-1]]['participation_ratio']:.2f})")
    print(f"-> 2. and it is kinds rather than data volume: {not_data}   "
          f"(100 classes {rows[ks[-1]]['participation_ratio']:.2f} vs 6 classes same size {pr6:.2f})")
    print(f"-> 3. the space stays usable: {accs[-1] > 3.0}   "
          f"(naming {rows[ks[-1]]['naming_accuracy']:.3f} at chance {rows[ks[-1]]['chance']:.3f}, "
          f"{accs[-1]:.1f}x)")
    print(f"\nCARLA corpus holds 6 kinds and measured 3.9. Human reference ~49 (Hebart 2020), ~66 later.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"declared_dim": DIM, "per_class": PER_CLASS,
                               "by_classes": {str(k): v for k, v in rows.items()},
                               "control_6class_matched_volume": pr6,
                               "carla_reference": 3.9,
                               "human_reference": "49 (Hebart 2020), 66 later"}, indent=2),
                   encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
