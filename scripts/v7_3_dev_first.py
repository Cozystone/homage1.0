# -*- coding: utf-8 -*-
"""A-side lever fitted on the DEV split, checked there first, and only then read against B.

    python scripts/v7_3_dev_first.py            # dev only
    python scripts/v7_3_dev_first.py --read-b   # after dev says it helps

V7-2 established that a direction fitted on one kind pair separates a pair it has never seen, above a
fair random-direction null (0.798 vs 0.743, p=1.4e-11 over 210 transfers). That says the profile
space has structure a fitted direction can carry ACROSS kinds. This turns that into an A-side lever.

THE LEVER. Fit the discriminative subspace on the 14 DEV kinds — between-kind scatter against
within-kind scatter, the ordinary Fisher construction — and score entities in that subspace instead of
in the raw predicate basis. The subspace is a property of "what distinguishes kinds in general", so
if V7-2's finding is real it should sharpen decisions about kinds the subspace never saw.

WHY THE DEV SPLIT AND NOT B. The dev corpus holds 14 kinds and B holds 8, and they are DISJOINT
(checked, overlap zero). Fitting on B's own kinds would be fitting on the thing being measured, and
the transfer reading would mean nothing. Fitting on dev makes B's kinds genuinely unseen.

THE LEVER FAILED, AND THEN THE HARNESS FAILED HARDER. On dev the projection scored worse than the
raw basis, so B was not read — the discipline held. But the raw baseline in this harness reads
coverage 0.0380, six placements out of 158, while dev through the REAL substrate scorer
(`behaviour_of` -> `decisive_kind`) reads coverage 0.3291 with accuracy 0.6731. This file scores by
cosine to a centroid; B scores by support x coverage x lift. They are not the same scorer, so what
was measured here was the harness and not the lever. Fifth time today that a test failed to test the
thing it named.

AND THE LEVER CANNOT BE MADE COMPATIBLE, which is the finding worth keeping. `kind_match` depends on
prevalence being an ABSOLUTE claim in [0,1] about a named predicate — `painting` holds `creator` at
0.785 means most paintings do. A linear subspace projection destroys exactly that, and the codebase
already records what happens: renormalising prevalence away made a densely-documented grape class
look like a mixture and it swallowed two shipyards. So V7-2's fitted-direction structure cannot be
carried into `rank_kinds` by projection without repeating a documented failure.

What CAN carry it, in the prevalence basis, is `_lifts` — weighting each predicate by how much more
it says one kind than the candidates average. That is the same idea expressed without leaving the
basis, and it is already applied. I do not currently have a second lever that preserves the
semantics.

AND DEV IS READ FIRST, WHICH IS THE PROCEDURAL POINT. B is a frozen domain with a registered seal;
every reading of it spends the measurement. Today the gate was read after work that was never checked
anywhere cheaper, it regressed, and I then spent three readings isolating a 2x2 that dev could have
answered for free. So the lever is judged on dev, and B is only read if dev says it helps.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEV = Path("packages/substrate/devsplit.json")


def load_dev() -> tuple[list[dict], dict]:
    d = json.loads(DEV.read_text(encoding="utf-8"))
    return d["corpus"], d["prevalences"]


def basis_of(prevalences: dict) -> list[str]:
    return sorted({p for pv in prevalences.values() for p in pv})


def vec(shares: dict, basis: list[str]) -> np.ndarray:
    return np.array([float(shares.get(p, 0.0)) for p in basis])


def fisher_subspace(X: np.ndarray, labels: list[str], k: int = 6,
                    ridge: float = 1e-3) -> np.ndarray:
    """Directions maximising between-kind scatter over within-kind scatter. (basis, k)

    Ridge on the within-class scatter because with 158 entities over a basis this wide the matrix is
    near-singular; without it the top 'directions' are noise directions with tiny within-class
    variance, which is the classic way this construction produces something that looks decisive and
    generalises to nothing."""
    kinds = sorted(set(labels))
    mu = X.mean(axis=0)
    Sw = np.zeros((X.shape[1], X.shape[1]))
    Sb = np.zeros_like(Sw)
    for kd in kinds:
        idx = [i for i, L in enumerate(labels) if L == kd]
        if len(idx) < 2:
            continue
        Xi = X[idx]
        mi = Xi.mean(axis=0)
        D = Xi - mi
        Sw += D.T @ D
        d = (mi - mu).reshape(-1, 1)
        Sb += len(idx) * (d @ d.T)
    Sw += ridge * np.trace(Sw) / max(Sw.shape[0], 1) * np.eye(Sw.shape[0])
    vals, vecs = np.linalg.eig(np.linalg.solve(Sw, Sb))
    order = np.argsort(-np.real(vals))[:k]
    W = np.real(vecs[:, order])
    return W / (np.linalg.norm(W, axis=0, keepdims=True) + 1e-12)


def score_in(Xq: np.ndarray, centroids: dict, W: np.ndarray | None) -> list[tuple[str, float]]:
    """Rank kinds by cosine to their centroid, optionally after projecting through W."""
    q = Xq @ W if W is not None else Xq
    out = []
    for kd, c in centroids.items():
        cc = c @ W if W is not None else c
        nq, nc = np.linalg.norm(q), np.linalg.norm(cc)
        out.append((kd, float(q @ cc / (nq * nc)) if nq > 1e-12 and nc > 1e-12 else 0.0))
    return sorted(out, key=lambda kv: -kv[1])


def evaluate_split(X: np.ndarray, labels: list[str], W: np.ndarray | None,
                   margin: float = 1.6, folds: int = 5, seed: int = 0) -> dict:
    """Leave-fold-out: centroids from the other folds, decide with the same decisiveness rule as B."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(X))
    right = wrong = abstain = 0
    for f in range(folds):
        te = idx[f::folds]
        tr = np.array([i for i in idx if i not in set(te.tolist())])
        cents = {}
        for kd in sorted(set(labels)):
            ii = [i for i in tr if labels[i] == kd]
            if ii:
                cents[kd] = X[ii].mean(axis=0)
        for i in te:
            ranked = score_in(X[i], cents, W)
            if len(ranked) < 2 or ranked[0][1] <= 0:
                abstain += 1
                continue
            top, runner = ranked[0], ranked[1]
            if runner[1] > 0 and top[1] < runner[1] * margin:
                abstain += 1
            elif top[0] == labels[i]:
                right += 1
            else:
                wrong += 1
    placed = right + wrong
    return {"correct": right, "wrong": wrong,
            "coverage": round(placed / len(X), 6) if len(X) else 0.0,
            "accuracy_on_placed": round(right / placed, 6) if placed else 0.0}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--read-b", action="store_true",
                    help="only after dev says the lever helps; B is a frozen domain")
    ap.add_argument("--k", type=int, default=6)
    args = ap.parse_args()

    corpus, prevalences = load_dev()
    basis = basis_of(prevalences)
    X, labels = [], []
    for row in corpus:
        sh = row.get("shares") or {}
        if not sh:
            have: dict[str, float] = {}
            for f in row.get("facts", []):
                have[f[1]] = have.get(f[1], 0.0) + 1.0
            tot = sum(have.values()) or 1.0
            sh = {p: v / tot for p, v in have.items()}
        v = vec(sh, basis)
        if v.sum() <= 0:
            continue
        X.append(v)
        labels.append(row["kind"])
    X = np.array(X)
    print(f"dev: {len(X)} entities, {len(set(labels))} kinds, basis {len(basis)} predicates")
    print(f"dev kinds are disjoint from B's (checked separately)\n")

    raw = evaluate_split(X, labels, None)
    W = fisher_subspace(X, labels, k=args.k)
    proj = evaluate_split(X, labels, W)

    print(f"{'':22}{'correct':>9}{'wrong':>7}{'coverage':>10}{'acc_placed':>12}")
    print(f"{'raw predicate basis':22}{raw['correct']:>9}{raw['wrong']:>7}"
          f"{raw['coverage']:>10.4f}{raw['accuracy_on_placed']:>12.4f}")
    print(f"{'Fisher subspace k=' + str(args.k):22}{proj['correct']:>9}{proj['wrong']:>7}"
          f"{proj['coverage']:>10.4f}{proj['accuracy_on_placed']:>12.4f}")

    helps = (proj["correct"] > raw["correct"] and proj["wrong"] <= raw["wrong"]) or \
            (proj["accuracy_on_placed"] > raw["accuracy_on_placed"] and
             proj["coverage"] >= raw["coverage"])
    print(f"\n-> on DEV the lever {'HELPS' if helps else 'does NOT help'}")
    if not helps:
        print("   B is NOT read. A lever that does not help where it was fitted has no claim on a "
              "frozen domain, and every reading of B spends the measurement.")

    out = Path("data/transfer_gate/v7_3_dev_first.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"dev_raw": raw, "dev_projected": proj, "k": args.k,
                               "helps_on_dev": bool(helps), "b_read": bool(helps and args.read_b)},
                              indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
