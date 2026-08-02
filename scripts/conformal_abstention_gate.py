# -*- coding: utf-8 -*-
"""M1 / NS-1 — the abstention threshold, calibrated across scenes instead of chosen, with a certificate.

    python scripts/conformal_abstention_gate.py --pages 300

WHY THIS AND NOT A LEARNED PRIOR. Three rungs went into repairing a per-scene null test and a fourth into
learning a prior over gap shapes, and the corpus then showed the diagnosis had been wrong: at n = 10 the
per-scene statistic reaches AUC 0.909. It RANKS well. What it cannot do is reach an absolute threshold --
p lands near 0.015 against an alpha registered at 0.01 -- and discrimination and decision are not the same
thing. Collapsing them is what sent four rungs after the wrong fix. The score was never uninformative; it
was uncalibrated.

So the threshold is CALIBRATED rather than chosen, which is what conformal prediction is for and what the
roadmap's first shovel already specified. Nothing new is invented here: the score is the existing
single-population p, the calibration set is the rendered-page corpus, and the bins are per sample size --
Mondrian, exactly as M1 describes, because the score's distribution depends on n and one global threshold
would be miscalibrated at both ends.

WHAT A CERTIFICATE IS AND IS NOT. Calibration promises that AMONG THE SETS IT ACCEPTS, the error rate is at
most alpha, on data drawn like the calibration data. It promises nothing about coverage -- a gate can honour
any alpha by abstaining always -- so coverage is reported beside it and a gate that buys its error rate by
refusing everything is recorded as the failure it is.

REGISTERED BEFORE RUNNING:
    1  the certificate holds on HELD-OUT pages: accepted-set error rate <= alpha, per bin
    2  coverage beats the fixed alpha = 0.01 threshold registered this morning -- the whole point
    3  and it is not bought by abstaining: coverage must be well above zero to count at all
    4  Mondrian bins EARN their place -- per-n calibration must beat one global threshold, or drop it
    5  packages/self_check gates the verdict
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.self_check import preflight                                  # noqa: E402
from scripts.scene_corpus_gaps import SIZES, scenes, windows               # noqa: E402

OUT = Path("data/perception/conformal_abstention_gate.json")
CACHE = Path("data/perception/scene_corpus_cache.npz")
ALPHA = 0.10          # the error rate the certificate promises among ACCEPTED sets
FIXED = 0.01          # the threshold registered by hand this morning, the thing to beat


def corpus(pages: int, refresh: bool = False):
    """Cached with the CONTINUOUS score as well as the p-value, because p has no resolution to spend.

    The first run calibrated on the p-value and every threshold came back at 1.0000, accepting everything.
    The cause is resolution, not calibration: with 60 null draws p can only take 61 values and a large mass
    of sets sit at exactly 1.0, so a threshold on p cannot separate what it accepts from what it does not.
    Conformal prediction needs a continuous nonconformity score and eta^2 is one -- p is its quantised
    shadow. The `resolution` check in packages/self_check flagged this before I had read the cause."""
    if CACHE.exists() and not refresh:
        z = np.load(CACHE)
        print(f"corpus from cache: {len(z['y'])} gap sets over "
              f"{len(np.unique(z['pg']))} rendered pages")
        return z["y"].astype(bool), z["N"], z["P"], z["pg"], z["eta2"]
    sc = scenes(pages)
    X, y, N, P, pg = windows(sc)
    eta2 = X[:, 1]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(CACHE, y=y, N=N, P=P, pg=pg, eta2=eta2)
    print(f"rendered {len(sc)} pages -> {len(y)} gap sets, cached to {CACHE}")
    return y, N, P, pg, eta2


# CALIBRATION IS DELEGATED. What stood here was a hand-rolled quantile sweep, and packages/conformal_gate
# already implements split conformal, Conformal Risk Control (Angelopoulos et al., ICLR 2024) and Mondrian
# per-bin coverage, with `guaranteed_conditional_bound` for the finite-sample certificate my version simply
# did not have. It also ships `jitter_scores` -- smoothed conformal predictors, Vovk 2005 -- which is the
# standard handling for exactly the tie mass I spent a rung discovering by hand: 4,275 of 8,835 gap sets sit
# at a score of 1.0, and jitter takes that to a single tie.
#
# Keeping my version would have been the third reimplementation of an existing organ in one day, and the
# most expensive: mine reported 0% error among accepted, which LOOKS better than the real gate's 7.9%, but
# it is a different quantity chosen by optimising the calibration set. The certified quantity is
# false-accept-given-wrong, and only the real gate bounds it.
from packages.conformal_gate import conformal as CG                        # noqa: E402


def calibrate(score, label, alpha: float, rng=None):
    """Split-conformal threshold from packages/conformal_gate, with its own tie-breaking applied."""
    s = CG.jitter_scores(np.asarray(score, float), rng or np.random.default_rng(0))
    return float(CG.calibrate(s, np.asarray(label, bool), alpha))


def evaluate(tau, score, label, rng=None):
    """The gate's own coverage report, renamed into this script's columns. No arithmetic of mine."""
    if tau is None:
        return {"coverage": 0.0, "error": 0.0, "accepted": 0, "certificate_holds": True,
                "vacuous": True, "false_accept_given_wrong": 0.0}
    s = CG.jitter_scores(np.asarray(score, float), rng or np.random.default_rng(0))
    r = CG.evaluate(s, np.asarray(label, bool), float(tau), ALPHA)
    d = r._asdict() if hasattr(r, "_asdict") else vars(r)
    return {"coverage": float(d["accept_rate"]), "error": float(d["error_among_accepted"]),
            "accepted": int(d["n_accept"]),
            "false_accept_given_wrong": float(d["false_accept_given_wrong"]),
            # THE CERTIFICATE IS ON FALSE-ACCEPT-GIVEN-WRONG, not on error-among-accepted. Checking the
            # wrong column is how a gate gets called certified when it is not.
            "certificate_holds": bool(d["n_accept"] == 0
                                      or d["false_accept_given_wrong"] <= ALPHA),
            "vacuous": bool(d["n_accept"] == 0)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=300)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()

    y, N, P, pg, eta2 = corpus(a.pages, a.refresh)
    # LOW SCORE MEANS ACCEPT, so the continuous score is inverted: a HIGH eta^2 is evidence FOR a
    # boundary, where a low p was. Same convention, continuous resolution.
    S = 1.0 - eta2
    pages = np.unique(pg)
    split = pages[int(0.7 * len(pages))]
    cal, te = pg < split, pg >= split
    print(f"calibration {cal.sum()} sets on {len(np.unique(pg[cal]))} pages   "
          f"held out {te.sum()} on {len(np.unique(pg[te]))} pages   alpha {ALPHA}")

    # --- the hand-chosen threshold this morning, for contrast
    fixed = evaluate(FIXED, P[te], y[te])          # the hand-chosen p threshold, unchanged
    glob = calibrate(S[cal], y[cal], ALPHA)
    global_ = evaluate(glob, S[te], y[te])

    print(f"\n{'gate':<34}{'threshold':>11}{'coverage':>10}{'err|acc':>9}{'FA|wrong':>10}{'cert':>7}")
    print(f"{'hand-chosen alpha = 0.01':<34}{FIXED:>11.4f}{fixed['coverage']:>10.1%}"
          f"{fixed['error']:>9.1%}{fixed['false_accept_given_wrong']:>10.1%}{str(fixed['certificate_holds']):>7}")
    print(f"{'calibrated, ONE global threshold':<34}"
          f"{(glob if glob is not None else float('nan')):>11.4f}{global_['coverage']:>10.1%}"
          f"{global_['error']:>9.1%}{global_['false_accept_given_wrong']:>10.1%}{str(global_['certificate_holds']):>7}")

    # --- Mondrian: one threshold per sample size
    rows, cov_num, cov_den, err_num, err_den = {}, 0, 0, 0.0, 0
    print(f"\n{'Mondrian bin':<16}{'cal sets':>9}{'threshold':>11}{'test sets':>10}"
          f"{'coverage':>10}{'err|acc':>9}{'FA|wrong':>10}{'cert':>7}")
    for n_fixed in SIZES:
        c, t = cal & (N == n_fixed), te & (N == n_fixed)
        if c.sum() < 40 or t.sum() < 40:
            continue
        tau = calibrate(S[c], y[c], ALPHA)
        ev = evaluate(tau, S[t], y[t])
        rows[f"n={n_fixed}"] = {"threshold": tau, **ev, "cal_sets": int(c.sum()),
                                "test_sets": int(t.sum())}
        cov_num += ev["accepted"]
        cov_den += int(t.sum())
        err_num += ev["error"] * ev["accepted"]
        err_den += ev["accepted"]
        print(f"{f'n = {n_fixed}':<16}{int(c.sum()):>9}"
              f"{(tau if tau is not None else float('nan')):>11.4f}{int(t.sum()):>10}"
              f"{ev['coverage']:>10.1%}{ev['error']:>9.1%}{ev['false_accept_given_wrong']:>10.1%}{str(ev['certificate_holds']):>7}")

    mon_cov = cov_num / max(cov_den, 1)
    mon_err = err_num / max(err_den, 1)
    print(f"\n{'MONDRIAN, pooled':<16}{'':>9}{'':>11}{cov_den:>10}{mon_cov:>10.1%}{mon_err:>9.1%}")

    all_hold = all(r["certificate_holds"] for r in rows.values())
    print(f"\n-> 1. the certificate holds on held-out pages, every bin: {all_hold}")
    print(f"-> 2. coverage beats the hand-chosen alpha = 0.01: "
          f"{mon_cov > fixed['coverage'] + 0.05}   ({fixed['coverage']:.1%} -> {mon_cov:.1%})")
    print(f"-> 3. and is not bought by abstaining: {mon_cov > 0.3}   ({mon_cov:.1%} accepted)")
    print(f"-> 4. Mondrian earns its place over one global threshold: "
          f"{mon_cov > global_['coverage'] + 0.02 or (all_hold and not global_['certificate_holds'])}"
          f"   (global {global_['coverage']:.1%} cov / {global_['error']:.1%} err vs "
          f"Mondrian {mon_cov:.1%} / {mon_err:.1%})")

    v = preflight.run("M1: a calibrated abstention threshold buys coverage at a certified error rate",
                      observed_source="chromium layout", intended_source="chromium layout",
                      base_rate=float(y[te].mean()), n=int(te.sum()),
                      real_score=mon_cov, control_score=fixed["coverage"],
                      target_size=max(ALPHA - mon_err, 1e-6), unit_size=0.02)
    print(f"\n-> PREFLIGHT  may_promote: {v.may_promote}")
    for c in v.checks:
        mark = "green" if c.green else ("FAILED" if c.ran else "COULD NOT RUN")
        print(f"     {c.name:<14}{mark:<15}{c.detail}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"alpha": ALPHA, "fixed_threshold": FIXED, "fixed": fixed,
                               "global": {"threshold": glob, **global_}, "mondrian": rows,
                               "mondrian_pooled": {"coverage": mon_cov, "error": mon_err},
                               "preflight": v.as_dict()}, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
