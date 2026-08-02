# -*- coding: utf-8 -*-
"""Synthetic score/label streams for the sealed conformal gates. Deterministic (seeded).

nonconformity is HIGHER for WRONG examples; a controllable AUC sets how weakly the score
separates wrong from correct. The point of NS-1 is that the certificate holds even when the
AUC is bad (~0.68), paying only in abstention.
"""
from __future__ import annotations

import math
import numpy as np


def norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation, |err| < 1.2e-9).

    Used only to place gaussian means so a target AUC is realized; the realized AUC is then
    MEASURED (never assumed) in the tests via conformal.empirical_auc.
    """
    if not (0.0 < p < 1.0):
        raise ValueError("p in (0,1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def gaussian_stream(rng: np.random.Generator, n: int, *, mu_c: float, sig_c: float,
                    mu_w: float, sig_w: float, wrong_frac: float = 0.5):
    """Return (scores, labels): label 1 = correct ~N(mu_c,sig_c), 0 = wrong ~N(mu_w,sig_w)."""
    n_wrong = int(round(n * wrong_frac))
    n_correct = n - n_wrong
    sc = rng.normal(mu_c, sig_c, size=n_correct)
    sw = rng.normal(mu_w, sig_w, size=n_wrong)
    scores = np.concatenate([sc, sw])
    labels = np.concatenate([np.ones(n_correct, dtype=int), np.zeros(n_wrong, dtype=int)])
    perm = rng.permutation(n)
    return scores[perm], labels[perm]


def auc_stream(rng: np.random.Generator, n: int, auc: float, *, wrong_frac: float = 0.5):
    """Unit-variance stream whose score realizes a target AUC (wrong ranked high).

    With sig=1 and mu_c=0, AUC = Phi(mu_w / sqrt(2)) => mu_w = sqrt(2) * Phi^{-1}(AUC).
    """
    mu_w = math.sqrt(2.0) * norm_ppf(auc)
    return gaussian_stream(rng, n, mu_c=0.0, sig_c=1.0, mu_w=mu_w, sig_w=1.0,
                           wrong_frac=wrong_frac)
