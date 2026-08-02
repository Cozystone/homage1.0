# -*- coding: utf-8 -*-
"""Split conformal prediction + Conformal Risk Control (CRC) + Mondrian binning.

Pure numpy. No ATANOR imports, no network, no I/O. This is the *membrane math*:
a distribution-free, finite-sample certificate that a WEAK confidence score can still
gate acceptance with a provable error bound — the score's AUC only sets the ABSTENTION
PRICE, never the safety.

Sign convention (used everywhere in this package)
-------------------------------------------------
`s` is a NONCONFORMITY score: HIGHER = LESS confident / more likely wrong.
The gate ACCEPTS iff ``s <= q_hat`` and ABSTAINS iff ``s > q_hat``.
(In confidence terms c = -s, "confidence below threshold -> abstain" — same thing.)

The two certificates
--------------------
Let calibration examples carry label y in {correct=1, wrong=0}, exchangeable with a
future example. Fix a target level alpha in (0,1).

1. SPLIT CONFORMAL (``calibrate`` / ``selective_threshold``) certifies the
   *conditional* false-accept probability::

       P( accept | wrong ) = P( s <= q_hat | y = wrong ) <= alpha .

   Construction: q_hat = the k-th smallest nonconformity score among the WRONG
   calibration examples, with k = floor((m+1)*alpha), m = #wrong. Proof: under
   exchangeability the rank of a fresh wrong score among the m+1 wrong scores is
   uniform on {1..m+1}; {s_new <= s_(k)} implies rank <= k, so the probability is
   k/(m+1) <= alpha. (Vovk; Angelopoulos & Bates, "A Gentle Introduction to
   Conformal Prediction", 2023 — the standard split-conformal quantile lemma,
   applied to the lower tail of the wrong class.)

2. CONFORMAL RISK CONTROL (``crc_threshold``) certifies the *marginal* expected
   loss of acceptance for any bounded, monotone loss::

       E[ L_{n+1}(t_hat) ] <= alpha ,   L_i(t) = loss_i * 1[ s_i <= t ] ,  0 <= L_i <= B .

   With loss_i = 1[y_i = wrong] this is the marginal false-accept RATE
   P( accept AND wrong ) <= alpha. Construction (Angelopoulos, Bates, Candes,
   Jordan, Malik, "Conformal Risk Control", ICLR 2024, arXiv:2208.02814):
   pick the largest acceptance threshold t with

       ( n * Rhat(t) + B ) / (n + 1) <= alpha ,   Rhat(t) = mean_i L_i(t) .

   L_i is non-increasing as the acceptance region shrinks, so the CRC theorem applies.
   If even "accept nothing" fails the bound (alpha < B/(n+1)), the method cannot
   certify at this alpha and returns -inf (abstain-all) — reported honestly, never faked.

MONDRIAN (``calibrate_mondrian``): run split conformal separately within each bin
(e.g. per domain). Marginal calibration only guarantees the *pooled* rate; a bin whose
scores are poorly separated is silently under-protected by a pooled threshold. Per-bin
thresholds restore per-bin (conditional) validity. (Vovk, "Conditional validity of
inductive conformal predictors", 2012 — Mondrian conformal prediction.)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

# The "accept nothing" threshold: with nonconformity >= 0 always, s <= -inf is never
# true, so acceptance is empty (maximally safe / maximal abstention).
ABSTAIN_ALL = float("-inf")
# The "accept everything" threshold (used only where a level cannot constrain).
ACCEPT_ALL = float("inf")


# --------------------------------------------------------------------------------------
# Canonical conformal quantiles
# --------------------------------------------------------------------------------------
def conformal_quantile(scores: Sequence[float], level: float) -> float:
    """Standard split-conformal UPPER quantile at coverage ``level`` in (0,1).

    Returns the ``ceil((n+1)*level)``-th smallest of ``scores`` (the exact index in the
    task spec / Angelopoulos & Bates). Guarantees ``P(s_new <= q) >= level`` for a fresh
    exchangeable score. If ``level`` needs an index beyond the sample (``> n``) the level
    cannot be certified from this much data -> returns +inf (conservative: covers all).
    """
    s = np.sort(np.asarray(scores, dtype=float))
    n = s.size
    if n == 0:
        return ACCEPT_ALL
    if not (0.0 < level < 1.0):
        raise ValueError(f"level must be in (0,1); got {level}")
    k = math.ceil((n + 1) * level)
    if k > n:
        return ACCEPT_ALL
    if k < 1:
        return float(s[0])
    return float(s[k - 1])


def selective_threshold(wrong_scores: Sequence[float], alpha: float) -> float:
    """LOWER-tail conformal threshold on the WRONG class.

    Returns q_hat = the ``floor((m+1)*alpha)``-th smallest wrong score so that a fresh
    wrong example is accepted (``s <= q_hat``) with probability <= alpha (see module
    docstring, certificate 1). ``m = len(wrong_scores)``.

    If ``floor((m+1)*alpha) < 1`` even the single most-conforming wrong example cannot be
    admitted within budget -> returns -inf (accept nothing => maximal abstention, still
    safe). If there are no wrong calibration examples -> also -inf (cannot certify a
    false-accept budget without any wrong exemplars; abstain rather than fabricate safety).
    """
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0,1); got {alpha}")
    w = np.sort(np.asarray(wrong_scores, dtype=float))
    m = w.size
    if m == 0:
        return ABSTAIN_ALL
    k = math.floor((m + 1) * alpha)
    if k < 1:
        return ABSTAIN_ALL
    if k > m:
        k = m
    return float(w[k - 1])


def jitter_scores(scores: Sequence[float], rng: "np.random.Generator",
                  eps: float = 1e-6) -> np.ndarray:
    """Randomized tie-breaking (smoothed conformal predictors, Vovk 2005).

    Adds tiny symmetric noise so EXACT ties are broken uniformly at random. Needed when the
    nonconformity is DISCRETE — e.g. the recognition-ladder confidence takes only a handful
    of distinct values — because a deterministic threshold that lands on a tie cluster
    accepts the WHOLE cluster and can exceed alpha. Apply the SAME jitter transform to
    calibration and inference scores. Pairing the ladder with a continuous signal (activation
    mass) achieves the same effect without randomness; this is the fallback when only the
    discrete signal is available.
    """
    s = np.asarray(scores, dtype=float)
    return s + rng.uniform(-eps, eps, size=s.shape)


def guaranteed_conditional_bound(m: int, alpha: float) -> float:
    """The exact finite-sample bound on P(accept | wrong) for ``selective_threshold``:
    ``floor((m+1)*alpha)/(m+1)`` (<= alpha). Useful in the certificate."""
    if m <= 0:
        return 0.0
    return math.floor((m + 1) * alpha) / (m + 1)


# --------------------------------------------------------------------------------------
# Split conformal calibration (labels)  ->  q_hat
# --------------------------------------------------------------------------------------
def _as_wrong_mask(labels: Sequence) -> np.ndarray:
    """label -> True where the example is WRONG / should-abstain.

    Accepts {1=correct, 0=wrong}, or booleans (True=correct), or the strings
    'correct'/'wrong'. Anything falsy-but-not-1 is treated as wrong.
    """
    lab = list(labels)
    out = np.empty(len(lab), dtype=bool)
    for i, v in enumerate(lab):
        if isinstance(v, str):
            out[i] = v.strip().lower() in ("wrong", "incorrect", "abstain", "0", "false", "bad")
        else:
            out[i] = not bool(v)  # 0/False -> wrong
    return out


def calibrate(scores: Sequence[float], labels: Sequence, alpha: float) -> float:
    """Split-conformal calibration for accepted-error control.

    ``scores``: nonconformity per calibration example (higher = less confident).
    ``labels``: 1/True = correct (should accept), 0/False = wrong (should abstain).
    Returns q_hat such that ACCEPT iff ``s <= q_hat`` certifies P(accept|wrong) <= alpha.
    """
    scores = np.asarray(scores, dtype=float)
    wrong = _as_wrong_mask(labels)
    return selective_threshold(scores[wrong], alpha)


def accept(score: float, q_hat: float) -> bool:
    """The single inference-time comparison. ACCEPT iff nonconformity ``score <= q_hat``."""
    return bool(score <= q_hat)


# --------------------------------------------------------------------------------------
# Mondrian (per-bin) calibration
# --------------------------------------------------------------------------------------
def calibrate_mondrian(scores: Sequence[float], labels: Sequence, bins: Sequence,
                       alpha: float) -> dict:
    """Per-bin split-conformal calibration for conditional coverage.

    Returns ``{bin_key: q_hat}``. Each bin is calibrated on its OWN wrong examples, so
    P(accept | wrong, bin) <= alpha holds within every bin — even when a pooled
    (marginal) threshold would violate alpha inside a poorly-separated bin.

    A bin with no wrong exemplars gets q_hat = -inf (cannot certify -> abstain-all in
    that bin). Callers should fall back to the pooled threshold or widen bins if that is
    too costly (a reported trade-off, never a silent accept).
    """
    scores = np.asarray(scores, dtype=float)
    wrong = _as_wrong_mask(labels)
    bins = list(bins)
    out: dict = {}
    for b in sorted(set(bins), key=lambda x: (str(type(x)), str(x))):
        mask = np.array([bb == b for bb in bins], dtype=bool)
        out[b] = selective_threshold(scores[mask & wrong], alpha)
    return out


# --------------------------------------------------------------------------------------
# Conformal Risk Control (general monotone loss)  ->  t_hat
# --------------------------------------------------------------------------------------
@dataclass
class CRCResult:
    t_hat: float                 # accept iff nonconformity s <= t_hat
    alpha: float
    n: int
    bound: float                 # (n*Rhat(t_hat)+B)/(n+1), the certified <= alpha value
    B: float
    certifiable: bool            # False => alpha below 1/(n+1) floor => abstain-all
    empirical_risk: float        # Rhat(t_hat) on the calibration set


def crc_threshold(scores: Sequence[float], loss_when_accepted: Sequence[float],
                  alpha: float, *, B: float | None = None) -> CRCResult:
    """Conformal Risk Control for a general bounded monotone acceptance loss.

    ``scores``: nonconformity per calibration example.
    ``loss_when_accepted``: loss_i >= 0 incurred IF example i is accepted (0 if abstained).
        For false-accept-rate control pass ``1.0`` for wrong, ``0.0`` for correct; graded
        severities (e.g. 1.0 for a harmful error, 0.3 for a benign one) are also valid.
    ``B``: upper bound on the loss (defaults to max(loss, 1.0)). The CRC theorem requires
        the per-example loss to be bounded by B.

    Returns a :class:`CRCResult`. Accepting iff ``s <= t_hat`` certifies
    ``E[ loss * 1(accept) ] <= alpha`` for a fresh exchangeable example (Angelopoulos et
    al., ICLR 2024). Picks the LARGEST such t (least abstention consistent with safety).
    """
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0,1); got {alpha}")
    s = np.asarray(scores, dtype=float)
    loss = np.asarray(loss_when_accepted, dtype=float)
    if s.shape != loss.shape:
        raise ValueError("scores and loss_when_accepted must be the same length")
    n = s.size
    if n == 0:
        return CRCResult(ABSTAIN_ALL, alpha, 0, 0.0, float(B or 1.0), False, 0.0)
    if np.any(loss < 0):
        raise ValueError("losses must be non-negative")
    Bv = float(B) if B is not None else float(max(1.0, loss.max() if loss.size else 1.0))

    # rhs of  Rhat(t) <= ((n+1)*alpha - B)/n
    rhs = ((n + 1) * alpha - Bv) / n
    if rhs < 0:
        # Even accepting nothing gives bound B/(n+1) > alpha: cannot certify at this alpha.
        return CRCResult(ABSTAIN_ALL, alpha, n, Bv / (n + 1), Bv, False, 0.0)

    order = np.argsort(s, kind="mergesort")
    s_sorted = s[order]
    loss_sorted = loss[order]
    # Rhat when accepting the first j smallest-score examples = cumsum(loss)/n.
    cum = np.cumsum(loss_sorted) / n           # cum[j-1] = Rhat after accepting j smallest
    # Largest prefix length j (0..n) with Rhat <= rhs. j=0 (accept none) has Rhat=0 <= rhs.
    ok = cum <= rhs + 1e-12
    if not ok.any():
        j = 0
    else:
        j = int(np.nonzero(ok)[0].max()) + 1   # number of accepted (prefix length)
    if j == 0:
        t_hat = ABSTAIN_ALL
        rhat = 0.0
    else:
        t_hat = float(s_sorted[j - 1])
        rhat = float(cum[j - 1])
        # Guard ties: including all examples equal to t_hat must not break the bound.
        tie = float(np.sum(loss[s <= t_hat]) / n)
        if tie > rhs + 1e-12:
            # step back below this score value
            below = s_sorted < t_hat
            if below.any():
                t_hat = float(s_sorted[below][-1])
                rhat = float(np.sum(loss[s <= t_hat]) / n)
            else:
                t_hat, rhat = ABSTAIN_ALL, 0.0
    bound = (n * rhat + Bv) / (n + 1)
    return CRCResult(t_hat, alpha, n, bound, Bv, True, rhat)


# --------------------------------------------------------------------------------------
# Empirical audit helpers (for the sealed gates / reporting)
# --------------------------------------------------------------------------------------
@dataclass
class CoverageReport:
    alpha: float
    n_eval: int
    accept_rate: float
    abstain_rate: float
    false_accept_given_wrong: float   # P(accept | wrong)  -- certified by split conformal
    false_accept_rate: float          # P(accept AND wrong) -- certified by CRC
    error_among_accepted: float       # P(wrong | accepted) -- reported, not directly certified
    n_wrong: int
    n_accept: int


def evaluate(scores: Sequence[float], labels: Sequence, q_hat: float,
             alpha: float) -> CoverageReport:
    """Measure the honest price and the achieved error on a held-out split.

    Reports THREE distinct error notions (see module docstring): the split-conformal
    certified P(accept|wrong), the CRC certified P(accept AND wrong), and the reported-only
    ratio P(wrong|accepted). Being explicit about which is certified is the honest report.
    """
    s = np.asarray(scores, dtype=float)
    wrong = _as_wrong_mask(labels)
    acc = s <= q_hat
    n = s.size
    n_wrong = int(wrong.sum())
    n_acc = int(acc.sum())
    fa_and_wrong = int(np.sum(acc & wrong))
    return CoverageReport(
        alpha=alpha,
        n_eval=n,
        accept_rate=n_acc / n if n else 0.0,
        abstain_rate=1.0 - (n_acc / n) if n else 1.0,
        false_accept_given_wrong=(fa_and_wrong / n_wrong) if n_wrong else 0.0,
        false_accept_rate=(fa_and_wrong / n) if n else 0.0,
        error_among_accepted=(fa_and_wrong / n_acc) if n_acc else 0.0,
        n_wrong=n_wrong,
        n_accept=n_acc,
    )


def empirical_auc(scores: Sequence[float], labels: Sequence) -> float:
    """AUC of the nonconformity score for ranking wrong-above-correct (higher s = wrong).

    = P(s_wrong > s_correct) + 0.5 P(tie), computed exactly via rank statistics. Used to
    *measure* (not assume) the "known bad AUC ~0.68" of the synthetic proof stream.
    """
    s = np.asarray(scores, dtype=float)
    wrong = _as_wrong_mask(labels)
    pos = s[wrong]          # wrong = the class the score should rank HIGH
    neg = s[~wrong]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    # Mann-Whitney U with average (tie-corrected) ranks, scipy-free.
    ar = _average_ranks(np.concatenate([pos, neg]))
    r_pos = ar[: pos.size].sum()
    auc = (r_pos - pos.size * (pos.size + 1) / 2.0) / (pos.size * neg.size)
    return float(auc)


def _average_ranks(v: np.ndarray) -> np.ndarray:
    """Average (tie-corrected) ranks, 1-based, in original order."""
    order = np.argsort(v, kind="mergesort")
    ranks = np.empty(v.size, dtype=float)
    sv = v[order]
    i = 0
    while i < v.size:
        j = i
        while j + 1 < v.size and sv[j + 1] == sv[i]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        ranks[order[i : j + 1]] = avg
        i = j + 1
    return ranks
