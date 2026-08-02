# -*- coding: utf-8 -*-
"""V7-2 — is a fitted transformation domain-blind?

    python scripts/v7_2_domain_blind.py

Registered in `ATANOR_axis_v7_learned_substrate_2026-07-29.md` §3, unrun:

> **V7-2 · Is a fitted transformation domain-blind?**
> Fit something on one region (e.g. a direction that separates two kinds) and apply it to points from
> a region it never saw.
> *Gate:* it performs above chance on the unseen region. This is the first rung that could actually
> be called transfer.

Run exactly as written: a direction is fitted to separate ONE pair of kinds, and is then asked to
separate a DIFFERENT pair whose entities were not in the fit and whose kinds the direction has never
been shown. Nothing is refitted on the unseen pair.

WHY THIS IS THE FIRST RUNG THAT COULD BE CALLED TRANSFER. The earlier rungs ask whether the space
holds structure. This asks whether an OPERATION defined in one part of it means anything in another
part — which is v7's actual claim, that "an operation learned as 'move points like this' is
automatically defined on every point in the space, including points nobody was thinking about when it
was fitted."

THE NULL IS MEASURED, NOT ASSUMED, and it is not 0.5. A direction fitted on kinds A/B is a real
direction in a space where all the kinds live, so some of its separating power on C/D could come from
the sheer geometry of profiles rather than from anything transferable. Two nulls are therefore run:

    random direction     what an arbitrary direction achieves on the same pair
    shuffled labels      what the fitted direction achieves when C/D's labels are scrambled

A result that beats 0.5 but not these is not transfer; it is the shape of the data.

REPORTED WHICHEVER WAY IT LANDS. A negative here would say the space carries kind structure locally
and nothing global — which is worth knowing before anything is built on top, and is exactly what the
ladder was ordered to find out cheaply.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path("data/transfer_gate/v7_2_domain_blind.json")
MIN_PER_KIND = 4


def load_space() -> tuple[np.ndarray, list[str], list[str]]:
    """Behaviour profiles and kinds, the same basis V7-0 passed on."""
    from packages.kind_prediction.eval import CORPUS

    preds = sorted({f[1] for r in CORPUS for f in r["facts"]})
    X, kinds = [], []
    for r in CORPUS:
        have: dict[str, int] = {}
        for f in r["facts"]:
            have[f[1]] = have.get(f[1], 0) + 1
        v = np.array([float(have.get(p, 0)) for p in preds])
        if v.sum() <= 0:
            continue
        X.append(v / v.sum())
        kinds.append(r["kind"])
    return np.array(X), kinds, preds


def direction(X: np.ndarray, kinds: list[str], a: str, b: str) -> np.ndarray:
    """The centroid difference — the simplest thing that could be called 'a direction that separates
    two kinds', and deliberately the simplest, so a positive result is not about a clever fit."""
    ia = [i for i, k in enumerate(kinds) if k == a]
    ib = [i for i, k in enumerate(kinds) if k == b]
    d = X[ia].mean(axis=0) - X[ib].mean(axis=0)
    n = np.linalg.norm(d)
    return d / n if n > 1e-12 else d


def separation(X: np.ndarray, kinds: list[str], c: str, d_: str, direc: np.ndarray) -> float:
    """AUC of the projection onto `direc` at telling kind c from kind d_. 0.5 is chance."""
    ic = [i for i, k in enumerate(kinds) if k == c]
    id_ = [i for i, k in enumerate(kinds) if k == d_]
    pc, pd = X[ic] @ direc, X[id_] @ direc
    wins = sum(1.0 for x in pc for y in pd if x > y) + 0.5 * sum(1.0 for x in pc for y in pd if x == y)
    return wins / max(len(pc) * len(pd), 1)


def main() -> None:
    X, kinds, preds = load_space()
    counts = {k: kinds.count(k) for k in set(kinds)}
    usable = sorted([k for k, n in counts.items() if n >= MIN_PER_KIND])
    print(f"entities {len(X)}   predicates {len(preds)}")
    print(f"kinds with >= {MIN_PER_KIND} members: {usable}   (counts { {k: counts[k] for k in usable} })")
    if len(usable) < 4:
        sys.exit("need at least four usable kinds to have a fit pair and a disjoint unseen pair")

    rng = np.random.default_rng(0)
    rows = []
    for fit_pair in itertools.combinations(usable, 2):
        d = direction(X, kinds, *fit_pair)
        for test_pair in itertools.combinations(usable, 2):
            if set(test_pair) & set(fit_pair):
                continue                      # the unseen pair must share NO kind with the fit
            auc = separation(X, kinds, *test_pair, d)
            # null 1: an arbitrary direction
            rand = [separation(X, kinds, *test_pair, _unit(rng, X.shape[1])) for _ in range(60)]
            # null 2: the fitted direction against scrambled labels of the unseen pair
            shuf = []
            for _ in range(60):
                kk = list(kinds)
                idx = [i for i, k in enumerate(kk) if k in test_pair]
                lab = [kk[i] for i in idx]
                rng.shuffle(lab)
                for i, L in zip(idx, lab):
                    kk[i] = L
                shuf.append(separation(X, kk, *test_pair, d))
            rows.append({"fit": list(fit_pair), "test": list(test_pair), "auc": auc,
                         "null_random": float(np.mean(rand)),
                         "null_random_p95": float(np.percentile(rand, 95)),
                         "null_shuffled_p95": float(np.percentile(shuf, 95))})

    A = np.array([abs(r["auc"] - 0.5) + 0.5 for r in rows])       # direction-agnostic: |AUC-0.5|
    NR = np.array([max(r["null_random_p95"], 1 - r["null_random_p95"]) for r in rows])
    NS = np.array([max(r["null_shuffled_p95"], 1 - r["null_shuffled_p95"]) for r in rows])
    print(f"\n{len(rows)} (fit pair -> unseen pair) transfers, kinds disjoint\n")
    print(f"  fitted direction on unseen pairs : mean |AUC| {A.mean():.4f}   median {np.median(A):.4f}")
    print(f"  null, random direction (p95)     : mean {NR.mean():.4f}")
    print(f"  null, shuffled labels  (p95)     : mean {NS.mean():.4f}")
    beat_rand = float(np.mean(A > NR))
    beat_shuf = float(np.mean(A > NS))
    print(f"\n  beats the random-direction null on {beat_rand:.1%} of transfers")
    print(f"  beats the shuffled-label null  on {beat_shuf:.1%} of transfers")

    passed = A.mean() > max(NR.mean(), NS.mean()) and beat_rand > 0.5 and beat_shuf > 0.5
    print(f"\n-> V7-2 {'PASSES' if passed else 'FAILS'}: a direction fitted on one kind pair "
          f"{'does' if passed else 'does NOT'} separate an unseen pair above its own nulls")

    top = sorted(rows, key=lambda r: -abs(r["auc"] - 0.5))[:5]
    print("\nstrongest transfers (for inspection, not as the result):")
    for r in top:
        print(f"  {r['fit'][0][:14]:16}/{r['fit'][1][:14]:16} -> "
              f"{r['test'][0][:14]:16}/{r['test'][1][:14]:16}  AUC {r['auc']:.3f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"rung": "V7-2", "entities": int(len(X)), "usable_kinds": usable,
         "transfers": len(rows),
         "fitted_mean_abs_auc": round(float(A.mean()), 5),
         "null_random_mean": round(float(NR.mean()), 5),
         "null_shuffled_mean": round(float(NS.mean()), 5),
         "beats_random_frac": round(beat_rand, 4),
         "beats_shuffled_frac": round(beat_shuf, 4),
         "passes": bool(passed), "detail": rows,
         "claims": "whether a direction fitted on one kind pair separates a kind-disjoint pair",
         "not_claimed": "that this is E5; the frozen-domain gate is V7-3"},
        indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote", OUT)


def _unit(rng, n: int) -> np.ndarray:
    v = rng.normal(size=n)
    return v / (np.linalg.norm(v) or 1.0)


if __name__ == "__main__":
    main()
