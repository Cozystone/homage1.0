# -*- coding: utf-8 -*-
"""M3 / NS-2 + NS-5 — real-signal measurement, asserted as a regression.

Honest scope (same as _m3_probe): a SMALL in-memory graph built from REAL engine code
(EpistemicGraph + spreading_activation.spread + fhrr_core), NOT the 141M store. It proves the
two NEW nonconformity signals RAISE the AUC and DROP the abstention price of the conformal gate
over M1's signals -- on the error mode they are built for (multi-path AMBIGUITY) -- while being
provably BLIND to the exception error mode (the honest boundary that sets the price floor).

Uses conformal.empirical_auc + calibrate + evaluate (same math as M1's gate).
"""
from __future__ import annotations

import numpy as np
import pytest

from packages.conformal_gate import conformal as C
from packages.conformal_gate.nonconformity import nonconformity
from packages.conformal_gate.tests._m3_probe import build_probe, config_signal

SEEDS = range(7000, 7012)          # 12 graphs (~0.26s each) — enough to stabilize the certificate mean
ALPHA = 0.10
CONFIGS = ("baseline", "ns2", "ns5", "both")


@pytest.fixture(scope="module")
def probes():
    return {sd: build_probe(sd) for sd in SEEDS}


def _sweep(probes, exc_scale=None):
    """Return {config: {'auc','abstain','fa','fa_jit'}} averaged over the graphs."""
    out = {c: {"auc": [], "abstain": [], "fa": [], "fa_jit": []} for c in CONFIGS}
    for sd, recs in probes.items():
        y = np.array([r.label for r in recs], dtype=int)
        rng = np.random.default_rng(sd)
        idx = rng.permutation(len(recs)); half = len(recs) // 2
        cal, ho = idx[:half], idx[half:]
        for cfg in CONFIGS:
            s = np.array([nonconformity(config_signal(r, cfg)) for r in recs], dtype=float)
            out[cfg]["auc"].append(C.empirical_auc(s, y))
            q = C.calibrate(s[cal], y[cal], ALPHA)
            rep = C.evaluate(s[ho], y[ho], q, ALPHA)
            out[cfg]["abstain"].append(rep.abstain_rate)
            out[cfg]["fa"].append(rep.false_accept_given_wrong)
            sj = C.jitter_scores(s, np.random.default_rng(sd + 1), eps=1e-6)
            qj = C.calibrate(sj[cal], y[cal], ALPHA)
            out[cfg]["fa_jit"].append(C.evaluate(sj[ho], y[ho], qj, ALPHA).false_accept_given_wrong)
    return {c: {k: float(np.mean(v)) for k, v in d.items()} for c, d in out.items()}


def test_new_signals_raise_auc_and_drop_abstention(probes, capsys):
    r = _sweep(probes)
    print("\n[M3] full probe, alpha=0.10, %d graphs" % len(list(SEEDS)))
    print("  config    |  AUC   | abstain | P(accept|wrong) raw/jit")
    for cfg in CONFIGS:
        print("  %-9s | %.4f | %.4f  | %.4f / %.4f"
              % (cfg, r[cfg]["auc"], r[cfg]["abstain"], r[cfg]["fa"], r[cfg]["fa_jit"]))

    # (1) both new signals materially RAISE the nonconformity AUC over M1's baseline
    assert r["ns2"]["auc"] >= r["baseline"]["auc"] + 0.10
    assert r["ns5"]["auc"] >= r["baseline"]["auc"] + 0.10
    # (2) and materially DROP the abstention PRICE
    assert r["ns2"]["abstain"] <= r["baseline"]["abstain"] - 0.03
    assert r["ns5"]["abstain"] <= r["baseline"]["abstain"] - 0.03
    print(capsys.readouterr().out)


def test_certificate_holds_regardless_of_signal(probes):
    """M1 thesis: split conformal certifies P(accept|wrong)<=alpha IN EXPECTATION for ANY score; a
    weak/strong score only changes the PRICE. The certificate is a marginal guarantee, so a single
    finite-sample run has honest slack from two sources: (i) finite held-out wrong counts, and
    (ii) MODE-1 ambiguity labels are a designed ~coin-flip, so the engine's tie-break — resolved via
    PYTHONHASHSEED-dependent set iteration order — shifts a few labels PER PROCESS, a shift that is
    correlated across graphs and so NOT reduced by averaging. M3's 300-trial mean lands fa_jit at
    0.0499/0.0989/0.1994 (dead-on alpha); this per-process assertion therefore uses a ~2.5-sigma
    slack sized to the wrong-sample count, which still catches any gross violation (broken conformal
    math would blow past it) without flaking on the legitimate tie-order variance. The root cross-
    process non-determinism in RingCodebook's builtin hash (fhrr_core.py:95) is flagged separately."""
    r = _sweep(probes)
    for cfg in CONFIGS:
        assert r[cfg]["fa_jit"] <= ALPHA + 0.05, (cfg, r[cfg]["fa_jit"])


def test_signals_are_blind_to_exceptions_by_construction(probes):
    """Honest boundary: NS-2 entropy and NS-5 margin flag AMBIGUITY, not confidently-wrong
    inheritance exceptions. Exception-wrong records must look like clean-correct ones."""
    ent = {"clean_ok": [], "amb": [], "exc_wrong": []}
    mar = {"clean_ok": [], "amb": [], "exc_wrong": []}
    for recs in probes.values():
        for rec in recs:
            if rec.mode == "clean" and rec.label == 1:
                b = "clean_ok"
            elif rec.mode == "amb":
                b = "amb"
            elif rec.mode == "exc" and rec.label == 0:
                b = "exc_wrong"
            else:
                continue
            ent[b].append(rec.entropy)
            if rec.margin is not None:
                mar[b].append(rec.margin)
    e_clean, e_amb, e_exc = np.mean(ent["clean_ok"]), np.mean(ent["amb"]), np.mean(ent["exc_wrong"])
    m_clean, m_amb, m_exc = np.mean(mar["clean_ok"]), np.mean(mar["amb"]), np.mean(mar["exc_wrong"])
    # ambiguity is loud on both signals ...
    assert e_amb >= e_clean + 0.3
    assert m_amb <= m_clean - 0.3
    # ... exceptions are silent on both (indistinguishable from clean-correct) -> the honest floor
    assert abs(e_exc - e_clean) < 0.1
    assert abs(m_exc - m_clean) < 0.1


def test_lever_at_full_force_when_error_is_visible(probes):
    """Ablation: remove the BLIND exception mode -> the ONLY error is ambiguity -> the price
    collapses. Proves the full-probe floor is the blind mode, not a limit of the signals."""
    abl = {sd: build_probe(sd, exc_scale=0.0) for sd in list(SEEDS)[:4]}
    r = _sweep(abl)
    assert r["both"]["auc"] >= 0.82
    assert r["both"]["abstain"] <= r["baseline"]["abstain"] - 0.30   # a large, real drop
