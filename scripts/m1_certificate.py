# -*- coding: utf-8 -*-
"""M1 — the certificate: error rate AMONG ACCEPTED answers, measured where it was not calibrated.

    python scripts/m1_certificate.py

WHAT M1 IS FOR. Every capability this system has is a capability someone has to decide whether to
trust. A certificate turns that decision into a measurement: with the abstention threshold set on one
split, the error rate among the answers it ACCEPTS on a disjoint split is bounded. That is what makes
it the door to unattended self-evolution -- the four self-checks catch failures already known, and
this bounds failures not yet met.

TWO THINGS THE EXISTING CALIBRATION RUN DOES NOT GIVE, and they are the whole of what was missing.

FIRST, THE WRONG QUANTITY. It reports P(accept | wrong) = 0.056 -- of the answers that were wrong,
how many slipped through. The certificate needs P(wrong | accept) -- of the answers it stood behind,
how many were wrong. Those differ by the base rate and are not interchangeable: with few wrong
answers in the pool, a high P(accept|wrong) can still mean a low error rate among accepted, and a low
one can still mean a high error rate if almost everything was wrong to begin with. The quantity a
user of the system experiences is the second.

SECOND, IN-SAMPLE. The threshold was fitted on all 268 answered items and the rate reported on those
same 268. Split conformal's guarantee requires the threshold to be chosen on a calibration set and
the error measured on a disjoint one; measured in-sample there is no guarantee, only a description of
the data it was fitted to. Today's post-mortem already made this a load-bearing correction --
development split before sealed measurement -- and this is the same rule applied to M1.

WHAT IS HONESTLY AVAILABLE. 268 answered items with 18 wrong is a thin pool. Split in half that is
about nine wrong per side, so the certificate comes with a Clopper-Pearson interval and the interval
is reported next to the point estimate, not behind it. A bound stated without its uncertainty at this
sample size would be the fourth instance of the pattern this session kept finding.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.conformal_gate import conformal as C          # noqa: E402
from packages.self_check.preflight import run as preflight   # noqa: E402

CAL = Path("data/conformal_gate/m1_calibration_full.json")
OUT = Path("data/conformal_gate/m1_certificate.json")


def _clopper_pearson(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Exact binomial interval. Exact rather than normal-approximate because k is small here, and the
    normal approximation is worst precisely when the count is near zero — which is the case a
    certificate is most tempted to overstate."""
    from scipy.stats import beta
    if n == 0:
        return 0.0, 1.0
    lo = 0.0 if k == 0 else float(beta.ppf((1 - level) / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - (1 - level) / 2, k + 1, n - k))
    return lo, hi


def load_pairs() -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Nonconformity scores, wrong-labels and bins, as recorded by the calibration run."""
    d = json.loads(CAL.read_text(encoding="utf-8"))
    pairs = d.get("pairs") or d.get("calibration_pairs") or []
    if not pairs:
        sys.exit(f"{CAL} holds no per-item pairs — rerun build_membrane_calibration.py with a build "
                 f"that records them; a certificate cannot be computed from summary statistics alone")
    s = np.array([float(p["score"]) for p in pairs])
    w = np.array([bool(p.get("wrong", not p.get("correct", True))) for p in pairs])
    b = [str(p.get("bin", "pooled")) for p in pairs]
    return s, w, b


def certify(scores: np.ndarray, wrong: np.ndarray, alpha: float, seed: int = 0,
            repeats: int = 200) -> dict:
    """Split, calibrate on one half, measure the accepted-error rate on the other. Repeat.

    Repeating over random splits is not to find a good one — the reported figure is the MEDIAN and
    the spread is reported with it. A single split at this sample size would be one draw presented as
    a property."""
    rng = np.random.default_rng(seed)
    n = len(scores)
    errs, absts, accepted_counts, wrong_accepted = [], [], [], []
    for _ in range(repeats):
        idx = rng.permutation(n)
        cut = n // 2
        ci, ti = idx[:cut], idx[cut:]
        # LABELS ARE "CORRECT", NOT "WRONG". `_as_wrong_mask` reads 1/True as CORRECT, so passing a
        # wrong-mask inverts the calibration: the threshold gets fitted to the CORRECT answers'
        # scores instead of the wrong ones. The first run of this script did exactly that and
        # produced zero errors at 92% abstention — a system that had stopped answering, wearing the
        # look of a perfect certificate. The self-check gate refused it on the discriminator check
        # (100% overlap, because the same/different populations were handed over inverted too), and
        # that refusal is what surfaced the bug.
        q = C.calibrate(scores[ci], ~wrong[ci], alpha)
        acc = scores[ti] <= q
        n_acc = int(acc.sum())
        if n_acc == 0:
            errs.append(0.0)
            absts.append(1.0)
            accepted_counts.append(0)
            wrong_accepted.append(0)
            continue
        k = int((wrong[ti] & acc).sum())
        errs.append(k / n_acc)
        absts.append(1.0 - n_acc / len(ti))
        accepted_counts.append(n_acc)
        wrong_accepted.append(k)
    e = np.array(errs)
    a = np.array(absts)
    k_tot, n_tot = int(np.sum(wrong_accepted)), int(np.sum(accepted_counts))
    lo, hi = _clopper_pearson(k_tot, n_tot)
    return {"alpha": alpha,
            "error_among_accepted_median": round(float(np.median(e)), 5),
            "error_among_accepted_p90": round(float(np.percentile(e, 90)), 5),
            "pooled_wrong_accepted": k_tot, "pooled_accepted": n_tot,
            "pooled_error_rate": round(k_tot / max(n_tot, 1), 5),
            "ci95": [round(lo, 5), round(hi, 5)],
            "abstention_median": round(float(np.median(a)), 4),
            "splits": repeats,
            "holds": bool(np.median(e) <= alpha),
            "holds_at_upper_bound": bool(hi <= alpha)}


def main() -> None:
    scores, wrong, bins = load_pairs()
    print(f"answered items: {len(scores)}   wrong: {int(wrong.sum())}   "
          f"base error rate: {wrong.mean():.3f}")
    print(f"nonconformity AUC (wrong above correct): {C.empirical_auc(scores, wrong):.4f}\n")

    rows = []
    print(f"{'alpha':>7}{'err|accept':>12}{'ci95':>20}{'abstain':>10}{'holds':>8}{'at UB':>8}")
    for alpha in (0.20, 0.10, 0.05, 0.02):
        r = certify(scores, wrong, alpha)
        rows.append(r)
        print(f"{alpha:>7.2f}{r['pooled_error_rate']:>12.4f}"
              f"{str(r['ci95']):>20}{r['abstention_median']:>10.3f}"
              f"{str(r['holds']):>8}{str(r['holds_at_upper_bound']):>8}")

    main_r = next(r for r in rows if r["alpha"] == 0.10)
    v = preflight(
        "M1: conformal abstention certificate at alpha=0.10",
        observed_source="seal_knowledge_holdout", intended_source="seal_knowledge_holdout",
        visible_frac=1.0,
        base_rate=float(wrong.mean()), n=int(len(scores)),
        target_size=float(int(wrong.sum())), unit_size=1.0,
        same=list(scores[wrong]), different=list(scores[~wrong]),   # high score = wrong; "same" is
        # the population the threshold must sit above, i.e. the wrong ones

        max_overlap=0.25)
    print("\n=== through the self-check gate ===")
    for c in v.checks:
        print(f"  {c.name:14} green={str(c.green):5} {c.detail}")
    print(f"  -> may_promote: {v.may_promote}")
    if not v.may_promote:
        for r_ in v.why_not():
            print("     -", r_)

    OUT.write_text(json.dumps(
        {"source": str(CAL), "answered": int(len(scores)), "wrong": int(wrong.sum()),
         "auc": round(float(C.empirical_auc(scores, ~wrong)), 4),
         "certificates": rows, "self_check": v.as_dict(),
         "claims": "error rate among ACCEPTED answers, threshold calibrated on a disjoint split",
         "not_claimed": "a guarantee at any alpha whose Clopper-Pearson upper bound exceeds it"},
        indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
