# -*- coding: utf-8 -*-
"""Unit tests for NS-2 (semantic_entropy) and NS-5 (resonance_verifier) primitives, using REAL
engine code (graph_scale.spread, vsa_reasoning.fhrr_core) on tiny hand-built cases."""
from __future__ import annotations

import numpy as np

from packages.conformal_gate.nonconformity import (
    SignalVector, from_resonance_margin, from_semantic_entropy, nonconformity,
)
from packages.conformal_gate.resonance_verifier import (
    build_codebook, verify_binding, weighted_superposition,
)
from packages.conformal_gate.semantic_entropy import semantic_entropy, semantic_entropy_full


def _graph(mult: dict) -> "callable":
    """mult = {class_index: n_duplicate_is_a_edges}. Answer = which class hub dominates."""
    facts: dict = {}
    for cls, m in mult.items():
        for _ in range(m):
            facts.setdefault("e", []).append(("e", "is_a", f"H{cls}"))
        facts.setdefault(f"H{cls}", []).append((f"H{cls}", "trait", f"V{cls}"))
    return lambda t: facts.get(t, [])


HUBS = [f"H{k}" for k in range(6)]


# ---- NS-2 semantic entropy -----------------------------------------------------------------
def test_entropy_zero_when_unanimous():
    r = semantic_entropy_full("e", _graph({0: 5}), answer_values=HUBS, K=20, seed=1, p_drop=0.35)
    assert r.entropy == 0.0
    assert r.modal_answer == "H0" and r.modal_fraction == 1.0


def test_entropy_high_when_balanced_race():
    r = semantic_entropy_full("e", _graph({0: 3, 1: 3}), answer_values=HUBS, K=24, seed=2, p_drop=0.35)
    # a genuine coin flip between two hubs -> normalized entropy near its max
    assert r.entropy > 0.6
    assert r.n_clusters >= 2


def test_entropy_monotone_in_race_closeness():
    e_lop = semantic_entropy("e", _graph({0: 6, 1: 2}), answer_values=HUBS, K=24, seed=3, p_drop=0.35)
    e_close = semantic_entropy("e", _graph({0: 4, 1: 3}), answer_values=HUBS, K=24, seed=3, p_drop=0.35)
    e_bal = semantic_entropy("e", _graph({0: 3, 1: 3}), answer_values=HUBS, K=24, seed=3, p_drop=0.35)
    assert e_lop < e_close < e_bal


def test_entropy_reader_abstains_on_no_answer():
    # a result whose modal answer is None -> max doubt (never the degenerate 'unanimous -> 0')
    r = semantic_entropy_full("nowhere", lambda t: [], answer_values=HUBS, K=8, seed=0)
    assert r.modal_answer is None
    sv = from_semantic_entropy(r)
    assert sv.semantic_entropy == 1.0
    assert nonconformity(sv) == 1.0            # only signal, maxed -> gate abstains


def test_entropy_reader_accepts_float_and_result():
    assert from_semantic_entropy(0.4).semantic_entropy == 0.4
    assert from_semantic_entropy(None).present() == {}   # failed compute -> absent signal


# ---- NS-5 resonance verifier ---------------------------------------------------------------
def test_verifier_accepts_clean_binding_rejects_superposition():
    cb, labels = build_codebook(["VA", "VB", "VC", "VD"])
    clean = weighted_superposition([("VA", 1.0)])
    mixed = weighted_superposition([("VA", 0.5), ("VB", 0.5)])
    vc = verify_binding(clean, cb, labels)
    vm = verify_binding(mixed, cb, labels)
    assert vc["accepted"] and vc["top_label"] == "VA" and vc["margin"] > 0.5
    # a 50/50 superposition of two atoms fails to converge -> tiny margin -> reject
    assert vm["margin"] < 0.2
    assert not vm["converged"]
    # and the reject carries HIGHER nonconformity than the clean accept
    assert nonconformity(from_resonance_margin(vm)) > nonconformity(from_resonance_margin(vc))


def test_verifier_null_on_empty_or_zero():
    cb, labels = build_codebook(["VA", "VB"])
    assert verify_binding(np.zeros(0), cb, labels)["resonance"] is None
    assert verify_binding(np.zeros(2048), cb, labels)["resonance"] is None
    assert verify_binding(weighted_superposition([("VA", 1.0)]), np.zeros((0, 0)), [])["resonance"] is None
    # null verdict -> absent signal (abstain if it is the only one)
    assert from_resonance_margin(verify_binding(np.zeros(0), cb, labels)).present() == {}


def test_verifier_expected_label_gate():
    cb, labels = build_codebook(["VA", "VB", "VC"])
    q = weighted_superposition([("VA", 1.0)])
    assert verify_binding(q, cb, labels, expected_label="VA")["accepted"]
    assert not verify_binding(q, cb, labels, expected_label="VB")["accepted"]   # winner != expected


def test_margin_shrinks_monotonically_with_competing_mass():
    cb, labels = build_codebook(["VA", "VB", "VC", "VD"])
    prev = 2.0
    for w2 in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        m = verify_binding(weighted_superposition([("VA", 1.0), ("VB", w2)]), cb, labels)["margin"]
        assert m <= prev + 1e-9
        prev = m
