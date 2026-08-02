# -*- coding: utf-8 -*-
"""The answer-time ConformalGate: ACCEPT (certified) / ABSTAIN + certificate."""
from __future__ import annotations

import numpy as np

from packages.conformal_gate import conformal as C
from packages.conformal_gate.gate import ConformalGate
from packages.conformal_gate.nonconformity import SignalVector
from packages.conformal_gate.tests._synth import auc_stream, gaussian_stream


def _calibration_on_nonconformity(rng, n, auc=0.68):
    """Build a calibration set whose scores live in the adapter's [0,1] nonconformity space
    (so the gate's q_hat is directly comparable to SignalVector nonconformities)."""
    # map gaussian scores to (0,1) via logistic so wrong -> higher nonconformity
    s, y = auc_stream(rng, n, auc=auc)
    nc = 1.0 / (1.0 + np.exp(-s))
    return nc, y


def test_gate_accept_below_threshold_abstain_above():
    rng = np.random.default_rng(11)
    nc, y = _calibration_on_nonconformity(rng, 4000)
    gate = ConformalGate.from_calibration(nc, y, alpha=0.10)
    # a very confident answer (KNOWN, strong confidence, rich support) -> low nonconformity
    strong = SignalVector(epistemic_rung="KNOWN", graded_confidence=0.97,
                          activation_mass=6.0, support_path_count=8)
    # a weak answer (GUESSED, low confidence, no support) -> high nonconformity
    weak = SignalVector(epistemic_rung="GUESSED", graded_confidence=0.2,
                        activation_mass=0.1, support_path_count=0)
    d_strong = gate.decide(strong)
    d_weak = gate.decide(weak)
    assert d_strong.accept is True and "certified accept" in d_strong.reason
    assert d_weak.accept is False and "abstain" in d_weak.reason
    assert d_strong.nonconformity < d_weak.nonconformity


def test_gate_abstains_on_empty_signals_never_fabricates():
    rng = np.random.default_rng(12)
    nc, y = _calibration_on_nonconformity(rng, 3000)
    gate = ConformalGate.from_calibration(nc, y, alpha=0.20)
    d = gate.decide(SignalVector())
    assert d.accept is False
    assert d.nonconformity == 1.0
    assert "never fabricate" in d.reason


def test_gate_certificate_fields():
    rng = np.random.default_rng(13)
    nc, y = _calibration_on_nonconformity(rng, 5000)
    gate = ConformalGate.from_calibration(nc, y, alpha=0.10)
    d = gate.decide(SignalVector(epistemic_rung="KNOWN", graded_confidence=0.95))
    cert = d.certificate
    assert cert["alpha"] == 0.10
    assert cert["method"] == "split"
    assert cert["guarantee"].startswith("P(accept|wrong)")
    assert cert["guaranteed_bound"] is not None and cert["guaranteed_bound"] <= 0.10
    assert "achieved_estimate" in cert and "abstain_rate" in cert["achieved_estimate"]
    assert cert["signals_present"] == ["epistemic_rung", "graded_confidence"]


def test_gate_mondrian_per_bin_decision():
    rng = np.random.default_rng(14)
    # two bins in nonconformity space with different separation
    na, nb = 3000, 3000
    sa, ya = gaussian_stream(rng, na, mu_c=-2.0, sig_c=1.0, mu_w=2.0, sig_w=1.0)
    sb, yb = gaussian_stream(rng, nb, mu_c=-1.0, sig_c=1.0, mu_w=0.5, sig_w=1.0)
    s = 1.0 / (1.0 + np.exp(-np.concatenate([sa, sb])))
    y = np.concatenate([ya, yb])
    b = np.array(["A"] * na + ["B"] * nb)
    gate = ConformalGate.from_mondrian(s, y, b, alpha=0.10)
    assert set(gate.bin_q_hat) == {"A", "B"}
    # the harder bin B gets a stricter (lower) threshold than A
    assert gate.bin_q_hat["B"] <= gate.bin_q_hat["A"]
    # an unseen bin falls back to the pooled threshold (documented), not a silent accept
    d = gate.decide(SignalVector(epistemic_rung="KNOWN", graded_confidence=0.95), bin="C")
    assert "fallback" in d.reason or "abstain" in d.reason


def test_gate_crc_constructor():
    rng = np.random.default_rng(15)
    nc, y = _calibration_on_nonconformity(rng, 4000)
    loss = (y == 0).astype(float)
    gate = ConformalGate.from_crc(nc, loss, alpha=0.10)
    assert gate.method == "crc"
    d = gate.decide(SignalVector(epistemic_rung="KNOWN", graded_confidence=0.96,
                                 activation_mass=5.0, support_path_count=7))
    assert d.certificate["guarantee"].startswith("E[loss")
    assert gate.achieved["certifiable"] is True
