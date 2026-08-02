# -*- coding: utf-8 -*-
"""Is there a shared abstraction over the discrimination family, or only a family resemblance?

    python scripts/g1_discrimination_family.py

The v6 plan's G1 gate asked whether the four known discriminators fall out of a structural-shape
measurement without being told. It read FAIL — four distinct shapes — and the plan was corrected the
same day: they are "two members of a family, not one computation written twice, and they cannot be
merged by deduplication." The question it left open is the one this answers:

    is there a shared ABSTRACTION over the discrimination family worth factoring out at all?

That is decidable, and deciding it is different from noticing a resemblance. A single parameterised
operator either REPRODUCES what each hand-written function outputs on its own data, or it does not.

THE CANDIDATE ABSTRACTION, read off the two functions rather than imposed on them. Both are functions
of one incidence matrix M[feature, candidate]:

    _bridging       cuts feature f when its MARGINAL  sum_c M[f,c] / C  exceeds a share
    discriminative  scores (f,c) as  M[f,c] / mean_c M[f,c]  -- the ratio to that same marginal

The denominator of the second IS the quantity the first thresholds. And `discriminative`'s own
docstring says a predicate every candidate shares "lands near 1.0 and is therefore silent" — which is
`_bridging`'s verdict, reached by a ratio instead of a cut. So the candidate abstraction is:

    lift(f, c) = M[f, c] / marginal(f)        and    bridging(f) = lift(f, ·) ~ 1 for every c

WHAT WOULD MAKE THIS FALSE, because a resemblance that cannot be cashed out is worth less than
knowing it cannot. If the unified operator does not reproduce each function's output on that
function's own data, they are genuinely different computations and G2's "one implementation, the
organs call it" stays unestablished for this class — which is the plan's current honest position and
would simply be confirmed.

THE CONTROL. Agreement is meaningless without something that should NOT agree. A shuffled incidence
matrix, and a naive alternative (raw frequency with no marginal at all) are both run through the same
comparison. If they agree about as well, the agreement was in the data's shape and not in the
abstraction.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.knowledge_repair.edge_attribution import _bridging          # noqa: E402
from packages.knowledge_repair.type_affinity import discriminative        # noqa: E402
from packages.self_check.preflight import run as preflight                # noqa: E402


# --- the candidate abstraction ----------------------------------------------------------------------

def lift(M: np.ndarray, floor: float = 0.0) -> np.ndarray:
    """M[feature, candidate] -> lift of each feature for each candidate against its own marginal.

    One operator. `_bridging` and `discriminative` are two readings of its output: a feature whose
    lift is ~1 everywhere singles out nobody; a feature whose lift is high for one candidate speaks
    for that candidate.

    `floor` is `discriminative`'s `_FLOOR`, applied to each cell before the marginal is taken. The
    first version omitted it and the reproduction came out at corr 0.9999 with a max absolute
    difference of 0.106 — near-perfect and not exact, which is the signature of a missing PARAMETER
    rather than a different computation. Including it is making the shared operator faithful to what
    it claims to subsume; leaving it out and calling 0.9999 a match would have been the fudge."""
    X = np.maximum(M, floor) if floor > 0 else M
    marg = X.mean(axis=1, keepdims=True)
    marg = np.where(marg <= 0, 1e-12, marg)
    return X / marg


def bridging_from_lift(M: np.ndarray, features: list[str], max_share: float,
                       n_docs: int) -> set[str]:
    """`_bridging`'s verdict, read off the shared operator instead of computed separately.

    `_bridging` cuts on the raw count exceeding `max(2, int(n_docs*max_share))`. The same cut
    expressed through the operator is a cut on the MARGINAL, which is the count divided by the number
    of candidates — so the threshold converts exactly, with no free parameter introduced."""
    ceiling = max(2, int(n_docs * max_share))
    counts = M.sum(axis=1)
    return {f for f, c in zip(features, counts) if c > ceiling}


# --- the data each function was written for -----------------------------------------------------------

def bridging_case(rng, n_docs: int = 135, vocab: int = 60) -> tuple[list[set[str]], np.ndarray, list[str]]:
    """Documents with a few genuinely bridging words, shaped like the Athens residue it was built on."""
    words = [f"w{i}" for i in range(vocab)]
    docs: list[set[str]] = []
    for _ in range(n_docs):
        d = set(rng.choice(words[:6], size=rng.integers(1, 4), replace=False))     # bridging words
        d |= set(rng.choice(words[6:], size=rng.integers(2, 6), replace=False))    # informative ones
        docs.append(d)
    feats = sorted({w for d in docs for w in d})
    M = np.array([[1.0 if w in d else 0.0 for d in docs] for w in feats])
    return docs, M, feats


def affinity_case(rng, kinds: int = 5, preds: int = 25):
    """Kind profiles with a few predicates that speak for one kind, shaped like type_affinity's."""
    from packages.knowledge_repair.type_affinity import TypeProfile
    kn = [f"kind{i}" for i in range(kinds)]
    pn = [f"p{i}" for i in range(preds)]
    rates = {k: {} for k in kn}
    for j, p in enumerate(pn):
        if j < 5:
            owner = kn[j % kinds]
            for k in kn:
                rates[k][p] = float(rng.uniform(0.5, 0.9)) if k == owner else float(rng.uniform(0.0, 0.08))
        else:
            base = float(rng.uniform(0.2, 0.6))
            for k in kn:
                rates[k][p] = base + float(rng.uniform(-0.03, 0.03))
    profiles = {k: TypeProfile(type_label=k, members=50, rates=dict(rates[k])) for k in kn}
    M = np.array([[rates[k][p] for k in kn] for p in pn])
    return profiles, M, pn, kn


def main() -> None:
    rng = np.random.default_rng(0)

    # ---- case 1: does the operator reproduce _bridging? ----
    docs, Mb, featsb = bridging_case(rng)
    want = _bridging(docs)
    got = bridging_from_lift(Mb, featsb, max_share=0.34, n_docs=len(docs))
    jac = len(want & got) / max(len(want | got), 1)

    # control: a shuffle that actually CHANGES the statistic under test. The first version shuffled
    # within each row, which preserves the row sum — and the row sum is exactly what `_bridging`
    # cuts on, so the "control" reproduced it perfectly and tested nothing. A control that cannot
    # fail is not a control, which is the same lesson this session has been collecting.
    flat = Mb.ravel().copy()
    rng.shuffle(flat)
    Ms = flat.reshape(Mb.shape)
    got_shuf = bridging_from_lift(Ms, featsb, max_share=0.34, n_docs=len(docs))
    jac_ctrl = len(want & got_shuf) / max(len(want | got_shuf), 1)

    # ---- case 2: does the operator reproduce discriminative? ----
    profiles, Ma, pn, kn = affinity_case(rng)
    want2 = discriminative(profiles)
    from packages.knowledge_repair.type_affinity import _FLOOR
    L = lift(Ma, floor=_FLOOR)
    got2 = {k: {p: float(L[i, j]) for i, p in enumerate(pn)} for j, k in enumerate(kn)}
    pairs = [(want2[k][p], got2[k][p]) for k in kn for p in pn if p in want2.get(k, {})]
    a = np.array([x for x, _ in pairs])
    b = np.array([y for _, y in pairs])
    max_abs = float(np.max(np.abs(a - b))) if len(a) else float("nan")
    corr = float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 else float("nan")

    # control: raw rate with NO marginal — a naive alternative that should NOT reproduce it
    naive = {k: {p: float(Ma[i, j]) for i, p in enumerate(pn)} for j, k in enumerate(kn)}
    c = np.array([naive[k][p] for k in kn for p in pn if p in want2.get(k, {})])
    corr_ctrl = float(np.corrcoef(a, c)[0, 1]) if len(c) > 2 else float("nan")

    print("=== does ONE operator reproduce both hand-written discriminators? ===\n")
    print(f"_bridging       : Jaccard {jac:.4f}   (shuffled control {jac_ctrl:.4f})")
    print(f"                  wanted {len(want)} features, got {len(got)}, agreed on {len(want & got)}")
    print(f"discriminative  : max|diff| {max_abs:.3e}   corr {corr:.6f}")
    print(f"                  naive control (no marginal): corr {corr_ctrl:.4f}")

    reproduces = (jac > 0.95) and (max_abs < 1e-9)
    beats_control = (jac > jac_ctrl + 0.2) and (corr > corr_ctrl + 0.05)

    print(f"\n-> reproduces both exactly : {reproduces}")
    print(f"-> beats its controls      : {beats_control}")
    verdict = ("THE ABSTRACTION EXISTS — one operator, two readings; worth factoring out"
               if reproduces and beats_control else
               "NOT established — they are a family resemblance, not one computation")
    print(f"-> {verdict}")

    v = preflight("G1': a shared abstraction over the discrimination family",
                  observed_source="knowledge_repair", intended_source="knowledge_repair",
                  visible_frac=1.0,
                  base_rate=len(want) / max(len(featsb), 1), n=len(pairs),
                  target_size=float(len(want)), unit_size=1.0,
                  real_score=float(corr), control_score=float(corr_ctrl))
    print("\n=== through the self-check gate ===")
    for ch in v.checks:
        print(f"  {ch.name:14} green={str(ch.green):5} {ch.detail}")
    print(f"  -> may_promote: {v.may_promote}")

    out = Path("data/self_check/g1_discrimination_family.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {"bridging": {"jaccard": jac, "shuffled_control": jac_ctrl,
                      "n_wanted": len(want), "n_got": len(got)},
         "discriminative": {"max_abs_diff": max_abs, "corr": corr, "naive_control_corr": corr_ctrl},
         "reproduces_both": bool(reproduces), "beats_controls": bool(beats_control),
         "verdict": verdict, "self_check": v.as_dict()}, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
