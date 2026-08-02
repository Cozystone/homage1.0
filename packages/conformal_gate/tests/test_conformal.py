# -*- coding: utf-8 -*-
"""SEALED GATES for the conformal abstention core (M1 / NS-1), pure-synthetic proof.

Gate (a) COVERAGE GUARANTEE holds on a KNOWN-bad-AUC (~0.68) stream: at alpha in
         {0.05,0.1,0.2} the held-out accepted false-accept rate <= alpha (in expectation
         over the calibration draw), and a WEAK score still holds the guarantee at the
         cost of HIGHER abstention.
Gate (b) MONDRIAN conditional coverage: two domains of different score quality; a pooled
         threshold VIOLATES alpha on the hard domain while per-bin calibration restores it.
Gate (c) CRC monotone-loss bound: the marginal false-accept RATE is bounded at alpha, and
         a general graded loss obeys E[loss * 1(accept)] <= alpha.

Deterministic (seeded). Guarantees are marginal over the calibration draw, so the coverage
gates assert the MEAN over many independent trials (the exact object conformal bounds),
and also print a single-draw table for the record.
"""
from __future__ import annotations

import numpy as np
import pytest

from packages.conformal_gate import conformal as C
from packages.conformal_gate.tests._synth import auc_stream, gaussian_stream

ALPHAS = (0.05, 0.10, 0.20)
SLACK = 0.01          # finite-sample slack on the MEAN over trials (guarantee is on the mean)


# ======================================================================================
# basic correctness of the quantile / threshold primitives
# ======================================================================================
def test_conformal_quantile_index_matches_spec():
    # ceil((n+1)*level)-th smallest. n=9, level=0.9 -> ceil(10*0.9)=9 -> 9th smallest.
    xs = list(range(1, 10))  # 1..9
    assert C.conformal_quantile(xs, 0.9) == 9
    # level too high for the sample -> +inf (cannot certify)
    assert C.conformal_quantile([1, 2, 3], 0.99) == C.ACCEPT_ALL


def test_selective_threshold_lower_tail_and_floor():
    w = np.arange(1, 101, dtype=float)  # 1..100 wrong scores, m=100
    # floor((100+1)*0.1)=10 -> 10th smallest = 10.0
    assert C.selective_threshold(w, 0.10) == 10.0
    # alpha so small that floor((m+1)*alpha) < 1 -> abstain-all
    assert C.selective_threshold(w, 0.001) == C.ABSTAIN_ALL
    # no wrong exemplars -> cannot certify -> abstain-all (never fabricate safety)
    assert C.selective_threshold([], 0.1) == C.ABSTAIN_ALL


def test_accept_is_single_comparison():
    assert C.accept(0.3, 0.5) is True
    assert C.accept(0.5, 0.5) is True     # boundary accepted (s <= q_hat)
    assert C.accept(0.51, 0.5) is False


# ======================================================================================
# Gate (a) — coverage guarantee on a KNOWN bad AUC (~0.68)
# ======================================================================================
def test_gate_a_coverage_on_weak_auc(capsys):
    rng = np.random.default_rng(20260723)
    # First: verify the stream really has the bad AUC we claim (measured, not assumed).
    s0, y0 = auc_stream(rng, 40000, auc=0.68)
    measured_auc = C.empirical_auc(s0, y0)
    assert 0.66 <= measured_auc <= 0.70, f"stream AUC off target: {measured_auc:.4f}"

    n_cal, n_ho, trials = 2000, 8000, 300
    # accumulate the certified quantity P(accept|wrong) and the honest price (abstention)
    fa_given_wrong = {a: [] for a in ALPHAS}
    abstain = {a: [] for a in ALPHAS}
    err_among_acc = {a: [] for a in ALPHAS}
    for _ in range(trials):
        sc, yc = auc_stream(rng, n_cal, auc=0.68)
        sh, yh = auc_stream(rng, n_ho, auc=0.68)
        for a in ALPHAS:
            q = C.calibrate(sc, yc, a)
            rep = C.evaluate(sh, yh, q, a)
            fa_given_wrong[a].append(rep.false_accept_given_wrong)
            abstain[a].append(rep.abstain_rate)
            err_among_acc[a].append(rep.error_among_accepted)

    print(f"\n[gate a] synthetic stream measured AUC = {measured_auc:.4f} (target 0.68), "
          f"{trials} trials, n_cal={n_cal}, n_ho={n_ho}")
    print("  alpha | mean P(accept|wrong) [CERTIFIED<=a] | mean abstain-rate (price) | "
          "mean err-among-accepted")
    for a in ALPHAS:
        mfa = float(np.mean(fa_given_wrong[a]))
        mab = float(np.mean(abstain[a]))
        mea = float(np.mean(err_among_acc[a]))
        print(f"  {a:0.2f}  |        {mfa:0.4f}               |        {mab:0.4f}          "
              f"|     {mea:0.4f}")
        # THE CERTIFICATE: mean over calibration draws of P(accept|wrong) <= alpha.
        assert mfa <= a + SLACK, f"alpha={a}: certified false-accept {mfa:.4f} > {a}+slack"

    captured = capsys.readouterr()
    print(captured.out)


def test_gate_a_weak_score_pays_in_abstention_not_safety(capsys):
    """A WEAK score (0.68 AUC) still holds the guarantee, but abstains far more than a
    strong score (0.90 AUC) at the same alpha. Safety is invariant to AUC; price is not."""
    rng = np.random.default_rng(7)
    n_cal, n_ho, trials, alpha = 3000, 12000, 200, 0.10
    rows = {}
    for tag, auc in (("weak(0.68)", 0.68), ("strong(0.90)", 0.90)):
        fa, ab = [], []
        for _ in range(trials):
            sc, yc = auc_stream(rng, n_cal, auc=auc)
            sh, yh = auc_stream(rng, n_ho, auc=auc)
            q = C.calibrate(sc, yc, alpha)
            rep = C.evaluate(sh, yh, q, alpha)
            fa.append(rep.false_accept_given_wrong)
            ab.append(rep.abstain_rate)
        rows[tag] = (float(np.mean(fa)), float(np.mean(ab)))

    print(f"\n[gate a/price] alpha={alpha}: weak vs strong score")
    print("  score       | mean P(accept|wrong) | mean abstain-rate")
    for tag, (mfa, mab) in rows.items():
        print(f"  {tag:11s} |       {mfa:0.4f}        |     {mab:0.4f}")
    # both hold the guarantee...
    assert rows["weak(0.68)"][0] <= alpha + SLACK
    assert rows["strong(0.90)"][0] <= alpha + SLACK
    # ...but the weak score's honest price (abstention) is strictly higher.
    assert rows["weak(0.68)"][1] > rows["strong(0.90)"][1] + 0.05
    print(capsys.readouterr().out)


# ======================================================================================
# Gate (b) — Mondrian conditional coverage
# ======================================================================================
def _two_domain_stream(rng, n, *, a_frac=0.70):
    """Domain A: clean/well-separated (wrong scores ~5). Domain B: hard/overlapping
    (wrong scores ~2.5, wide). A dominates the pool (70%), so a pooled threshold is pulled
    UP toward A and becomes too permissive for B's low-scoring wrong answers."""
    n_a = int(round(n * a_frac))
    n_b = n - n_a
    sa, ya = gaussian_stream(rng, n_a, mu_c=0.0, sig_c=1.0, mu_w=5.0, sig_w=1.0)
    sb, yb = gaussian_stream(rng, n_b, mu_c=0.0, sig_c=1.0, mu_w=2.5, sig_w=1.5)
    scores = np.concatenate([sa, sb])
    labels = np.concatenate([ya, yb])
    bins = np.array(["A"] * n_a + ["B"] * n_b)
    return scores, labels, bins


def test_gate_b_mondrian_fixes_conditional_violation(capsys):
    rng = np.random.default_rng(31337)
    alpha = 0.10
    # calibrate both pooled and per-bin on the same calibration set
    sc, yc, bc = _two_domain_stream(rng, 6000)
    q_pooled = C.calibrate(sc, yc, alpha)
    q_bins = C.calibrate_mondrian(sc, yc, bc, alpha)

    # evaluate per-domain on a large fresh held-out
    sh, yh, bh = _two_domain_stream(rng, 60000)
    wrong = (yh == 0)

    def per_domain_fa(q_for):
        out = {}
        for d in ("A", "B"):
            m = (bh == d) & wrong
            acc = sh[m] <= (q_for if np.isscalar(q_for) else q_bins[d])
            out[d] = float(np.mean(acc)) if m.sum() else 0.0
        return out

    fa_pooled = {d: float(np.mean(sh[(bh == d) & wrong] <= q_pooled)) for d in ("A", "B")}
    fa_mond = {d: float(np.mean(sh[(bh == d) & wrong] <= q_bins[d])) for d in ("A", "B")}
    # pooled marginal (mixed) false-accept-given-wrong, to show marginal validity holds
    fa_pooled_marginal = float(np.mean(sh[wrong] <= q_pooled))

    print(f"\n[gate b] Mondrian, alpha={alpha}")
    print(f"  pooled q_hat = {q_pooled:.3f} ; per-bin q_hat = "
          f"{{A:{q_bins['A']:.3f}, B:{q_bins['B']:.3f}}}")
    print(f"  pooled MARGINAL P(accept|wrong) = {fa_pooled_marginal:.4f}  (<= alpha: marginal valid)")
    print("  domain | pooled P(accept|wrong) | mondrian P(accept|wrong)")
    for d in ("A", "B"):
        print(f"    {d}    |       {fa_pooled[d]:0.4f}         |        {fa_mond[d]:0.4f}")

    # marginal validity holds for the pooled threshold...
    assert fa_pooled_marginal <= alpha + 0.02
    # ...but the pooled threshold VIOLATES alpha inside the hard domain B (conditional fail).
    assert fa_pooled["B"] > alpha + 0.05, f"expected pooled to violate on B, got {fa_pooled['B']:.4f}"
    # Mondrian per-bin restores conditional coverage on BOTH domains.
    assert fa_mond["A"] <= alpha + 0.02
    assert fa_mond["B"] <= alpha + 0.02
    print(capsys.readouterr().out)


# ======================================================================================
# Gate (c) — CRC monotone-loss bound on the marginal false-accept rate
# ======================================================================================
def test_gate_c_crc_bounds_marginal_false_accept_rate(capsys):
    rng = np.random.default_rng(2208)
    n_cal, n_ho, trials = 3000, 12000, 300
    rates = {a: [] for a in ALPHAS}
    thresh = {a: [] for a in ALPHAS}
    for _ in range(trials):
        sc, yc = auc_stream(rng, n_cal, auc=0.68)
        sh, yh = auc_stream(rng, n_ho, auc=0.68)
        loss_cal = (yc == 0).astype(float)          # false-accept loss = 1 for wrong
        for a in ALPHAS:
            res = C.crc_threshold(sc, loss_cal, a)
            # marginal false-accept RATE on held-out: P(accept AND wrong)
            fa_rate = float(np.mean((sh <= res.t_hat) & (yh == 0)))
            rates[a].append(fa_rate)
            thresh[a].append(res.t_hat)

    print(f"\n[gate c] CRC marginal false-accept rate, auc=0.68, {trials} trials")
    print("  alpha | mean P(accept AND wrong) [CERTIFIED<=a] | mean t_hat")
    for a in ALPHAS:
        mr = float(np.mean(rates[a]))
        mt = float(np.mean(thresh[a]))
        print(f"  {a:0.2f}  |            {mr:0.4f}                    |   {mt:0.3f}")
        assert mr <= a + SLACK, f"CRC marginal rate {mr:.4f} > alpha {a}+slack"
    print(capsys.readouterr().out)


def test_gate_c_crc_general_graded_loss():
    """CRC with a GENERAL bounded monotone loss (severity-weighted), not just 0/1: the
    certified quantity E[loss * 1(accept)] is bounded at alpha."""
    rng = np.random.default_rng(99)
    alpha = 0.10
    vals = []
    for _ in range(200):
        sc, yc = auc_stream(rng, 3000, auc=0.68)
        sh, yh = auc_stream(rng, 12000, auc=0.68)
        # graded severity: half the wrong answers are "harmful" (loss 1.0), half "benign" (0.4)
        sev_cal = np.where(yc == 0, rng.choice([1.0, 0.4], size=yc.size), 0.0)
        res = C.crc_threshold(sc, sev_cal, alpha, B=1.0)
        # held-out severity for the SAME mechanism (fresh draw)
        sev_ho = np.where(yh == 0, rng.choice([1.0, 0.4], size=yh.size), 0.0)
        risk = float(np.mean(sev_ho * (sh <= res.t_hat)))
        vals.append(risk)
    assert float(np.mean(vals)) <= alpha + 0.01


def test_gate_c_crc_cannot_certify_tiny_alpha():
    """Honesty path: when alpha < 1/(n+1) even accepting nothing fails the CRC inequality;
    the method reports it cannot certify and abstains-all (never a silent accept)."""
    rng = np.random.default_rng(1)
    s, y = auc_stream(rng, 10, auc=0.68)     # n=10 -> floor 1/(n+1) ~ 0.09
    res = C.crc_threshold(s, (y == 0).astype(float), 0.05)
    assert res.certifiable is False
    assert res.t_hat == C.ABSTAIN_ALL


def test_evaluate_reports_three_error_notions():
    rng = np.random.default_rng(5)
    s, y = auc_stream(rng, 5000, auc=0.68)
    q = C.calibrate(s, y, 0.1)
    rep = C.evaluate(s, y, q, 0.1)
    # the three notions are distinct and all in [0,1]
    for v in (rep.false_accept_given_wrong, rep.false_accept_rate, rep.error_among_accepted,
              rep.accept_rate, rep.abstain_rate):
        assert 0.0 <= v <= 1.0
    assert abs(rep.accept_rate + rep.abstain_rate - 1.0) < 1e-9
