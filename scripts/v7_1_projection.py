# -*- coding: utf-8 -*-
"""V7-1 — does the behaviour geometry survive projection into the hyperdimensional space?

    python scripts/v7_1_projection.py

The rung is registered in `ATANOR_axis_v7_learned_substrate_2026-07-29.md` §3 and has not been run:

> **V7-1 · Does the geometry survive projection into the hyperdimensional space?**
> The sparse profile is the easy case; FHRR is the claim. Project profiles into `HoloSpace` and check
> the neighbourhood structure is preserved.
> *Gate:* the ranking of nearest neighbours agrees with the sparse-basis ranking above a threshold
> fixed in advance. A projection that scrambles neighbourhoods is a coding scheme again.

V7-0 passed on the sparse named-predicate basis (49 entities, four held-out kinds). This asks whether
that geometry is still there after the profiles are carried into FHRR — because if it is not, the
hyperdimensional space is a coding scheme again and the axis has nothing to travel through.

THE THRESHOLD IS MEASURED BEFORE THE PROJECTION IS RUN, which is the whole procedural point. "Fixed
in advance" is not satisfied by choosing a number in advance; a number chosen without knowing the
measurement's null is the error this project has now committed four times, most recently by
registering an absolute bar below chance. So the null is measured first — the same agreement
statistic under a RANDOM projection of the same rank and dimension — and the bar is set from it. The
real projection is only then run.

WHAT THE PROJECTION IS. A profile is a sparse vector over named predicates. Carrying it into FHRR is
the standard VSA role-filler bundle: bind each predicate's atom to a magnitude-carrying phase and
superpose. Nothing is trained. The claim under test is not that a clever encoder preserves structure
-- it is that THIS space, the one five organs already share, can hold behaviour at all.

WHAT WOULD KILL THE RUNG. Neighbourhood agreement at or near the random-projection null. That would
say the hash-seeded atoms scramble what the sparse basis had, and §1's diagnosis -- the geometry
carries zero behavioural information -- would extend to any attempt to put behaviour into it without
replacing the atoms themselves.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path("data/transfer_gate/v7_1_projection.json")
DIM = 2048
K = 5                      # neighbourhood size the agreement is measured over


def profiles_matrix() -> tuple[np.ndarray, list[str], list[str], list[str]]:
    """Entity x predicate behaviour matrix, and each entity's kind. Read, never authored."""
    from packages.kind_prediction.eval import CORPUS

    preds = sorted({f[1] for row in CORPUS for f in row["facts"]})
    ents, kinds, M = [], [], []
    for row in CORPUS:
        have = {}
        for f in row["facts"]:
            have[f[1]] = have.get(f[1], 0) + 1
        v = np.array([float(have.get(p, 0)) for p in preds])
        if v.sum() <= 0:
            continue
        ents.append(row["entity"])
        kinds.append(row["kind"])
        M.append(v / v.sum())                      # prevalence-shaped, not count-shaped
    return np.array(M), ents, kinds, preds


def to_fhrr(M: np.ndarray, preds: list[str], dim: int = DIM) -> np.ndarray:
    """Role-filler bundle: superpose each predicate's atom weighted by the profile's magnitude."""
    from packages.vsa_reasoning.fhrr_core import atom

    A = np.stack([atom(p)[:dim] for p in preds])   # (P, dim) complex
    return M.astype(np.complex128) @ A             # (N, dim)


def random_projection(M: np.ndarray, dim: int, seed: int) -> np.ndarray:
    """The NULL: the same shape of carrying, with atoms that are equally arbitrary but redrawn.

    This is what "the projection preserved nothing beyond what any projection preserves" looks like,
    and it is the number the gate's bar has to clear."""
    rng = np.random.default_rng(seed)
    A = np.exp(1j * rng.uniform(0, 2 * np.pi, (M.shape[1], dim)))
    return M.astype(np.complex128) @ A


def neighbours(X: np.ndarray, k: int) -> np.ndarray:
    """Indices of each row's k nearest others, by cosine on the real inner product."""
    if np.iscomplexobj(X):
        S = np.real(X @ X.conj().T)
        n = np.sqrt(np.real(np.einsum("ij,ij->i", X, X.conj())))
    else:
        S = X @ X.T
        n = np.linalg.norm(X, axis=1)
    n = np.where(n <= 0, 1e-12, n)
    S = S / np.outer(n, n)
    np.fill_diagonal(S, -np.inf)
    return np.argsort(-S, axis=1)[:, :k]


def agreement(a: np.ndarray, b: np.ndarray) -> float:
    """Mean overlap of the two k-neighbourhoods, per row. 1.0 = identical neighbourhoods."""
    return float(np.mean([len(set(x) & set(y)) / len(x) for x, y in zip(a, b)]))


def main() -> None:
    M, ents, kinds, preds = profiles_matrix()
    print(f"entities {len(ents)}   predicates {len(preds)}   kinds {len(set(kinds))}")

    sparse_nn = neighbours(M, K)

    # ---- STEP 1: measure the null, BEFORE the real projection is built ----
    nulls = [agreement(sparse_nn, neighbours(random_projection(M, DIM, s), K)) for s in range(30)]
    nulls = np.array(nulls)
    bar = float(np.percentile(nulls, 95))
    print(f"\nNULL (random atoms, same shape): mean {nulls.mean():.4f}  p95 {bar:.4f}")
    print(f"BAR FIXED AT {bar:.4f} — the 95th percentile of the null, registered before the real "
          f"projection is computed")

    # ---- STEP 2: only now, the real thing ----
    X = to_fhrr(M, preds, DIM)
    real = agreement(sparse_nn, neighbours(X, K))
    passed = real > bar

    print(f"\nFHRR projection neighbourhood agreement @k={K}: {real:.4f}")
    print(f"-> V7-1 {'PASSES' if passed else 'FAILS'} "
          f"({real:.4f} {'>' if passed else '<='} {bar:.4f})")

    # a second reading that does not depend on k: does same-kind still beat cross-kind after the
    # projection? V7-0's own question, asked of the projected space.
    def same_vs_cross(Z):
        if np.iscomplexobj(Z):
            S = np.real(Z @ Z.conj().T)
            nn = np.sqrt(np.real(np.einsum("ij,ij->i", Z, Z.conj())))
        else:
            S = Z @ Z.T
            nn = np.linalg.norm(Z, axis=1)
        nn = np.where(nn <= 0, 1e-12, nn)
        S = S / np.outer(nn, nn)
        same, cross = [], []
        for i in range(len(kinds)):
            for j in range(i + 1, len(kinds)):
                (same if kinds[i] == kinds[j] else cross).append(S[i, j])
        return float(np.mean(same)), float(np.mean(cross))

    s0, c0 = same_vs_cross(M)
    s1, c1 = same_vs_cross(X)
    print(f"\nsame-kind vs cross-kind similarity")
    print(f"  sparse basis : same {s0:.4f}  cross {c0:.4f}  gap {s0-c0:+.4f}")
    print(f"  after FHRR   : same {s1:.4f}  cross {c1:.4f}  gap {s1-c1:+.4f}")
    kept = (s1 - c1) / (s0 - c0) if abs(s0 - c0) > 1e-9 else float("nan")
    print(f"  gap retained : {kept:.1%}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"rung": "V7-1", "entities": len(ents), "predicates": len(preds), "k": K, "dim": DIM,
         "null_mean": round(float(nulls.mean()), 5), "bar_p95_of_null": round(bar, 5),
         "bar_fixed_before_real_projection": True,
         "fhrr_agreement": round(real, 5), "passes": bool(passed),
         "same_cross_gap_sparse": round(s0 - c0, 5),
         "same_cross_gap_fhrr": round(s1 - c1, 5),
         "gap_retained": round(float(kept), 5),
         "claims": "whether FHRR preserves the sparse basis's neighbourhood structure",
         "not_claimed": "that a preserved geometry makes transfer work — that is V7-2"},
        indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
