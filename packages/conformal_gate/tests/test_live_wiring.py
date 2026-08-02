# -*- coding: utf-8 -*-
"""Membrane live-wiring tests: the flag-OFF no-op (safety proof) and the flag-ON gate behavior.

The #1 invariant: with ATANOR_MEMBRANE_LIVE unset, every wiring entry point is a pure passthrough
that returns the SAME object it was given -> the live answer path is byte-identical to pre-membrane.
"""
from __future__ import annotations

import importlib

import pytest

from packages.conformal_gate import live_wiring as LW


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    # each test starts with the flag OFF and caches cleared
    monkeypatch.delenv("ATANOR_MEMBRANE_LIVE", raising=False)
    monkeypatch.delenv("ATANOR_MEMBRANE_FAILSAFE", raising=False)
    LW._calib_cache.clear()
    LW._warned_uncalibrated = False
    yield


def _sample_result():
    return {
        "answer": "Capital of Japan is Tokyo.",
        "answer_kind": "grounded_composition",
        "confidence": 0.88,
        "reasoning_certificate": {
            "derivation_kind": "grounded_composition",
            "anchor_concept": {"label": "Japan"},
            "steps": [{"type": "triple", "fact": "Japan capital Tokyo"}],
            "evidence_concepts": ["Japan", "Tokyo"],
        },
    }


# ---------------------------------------------------------------- flag OFF = identical no-op
def test_flag_off_gate_answer_returns_same_object(monkeypatch):
    r = _sample_result()
    out = LW.gate_answer(r, query="q", language="en")
    assert out is r                                   # SAME object -> byte-identical
    assert "_membrane" not in out and "_membrane_signals" not in out


def test_flag_off_attach_signals_is_noop(monkeypatch):
    r = _sample_result()
    before = dict(r)
    out = LW.attach_membrane_signals(r, subgraph=object(), anchor="Japan")
    assert out is r and r == before                   # nothing added


def test_flag_off_membrane_live_false():
    assert LW.membrane_live() is False


def test_flag_off_gate_answer_none_passthrough():
    assert LW.gate_answer(None, query="q", language="en") is None


# ---------------------------------------------------------------- flag ON, uncalibrated fail-safe
def test_on_uncalibrated_passthrough_default(monkeypatch):
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    monkeypatch.setattr(LW, "_load_calibration", lambda: None)
    r = _sample_result()
    out = LW.gate_answer(r, query="q", language="en")
    # answer preserved, marked as uncertified passthrough, NO certificate fabricated
    assert out["answer"] == r["answer"]
    assert out["_membrane"]["status"] == "uncalibrated_passthrough"
    assert "membrane_certificate" not in out.get("reasoning_certificate", {})


def test_on_uncalibrated_abstain_optin(monkeypatch):
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    monkeypatch.setenv("ATANOR_MEMBRANE_FAILSAFE", "abstain")
    monkeypatch.setattr(LW, "_load_calibration", lambda: None)
    out = LW.gate_answer(_sample_result(), query="q", language="en")
    assert out["answer_kind"] == "honest_abstain"
    assert out["_membrane"]["decision"] == "ABSTAIN"


# ---------------------------------------------------------------- flag ON, calibrated: accept/abstain
def _gate_with_qhat(q_hat: float):
    from packages.conformal_gate.gate import ConformalGate
    from packages.conformal_gate import conformal as C
    # split gate with an explicit marginal threshold; bin ignored -> uses q_hat
    return ConformalGate(alpha=0.1, method="split", q_hat=q_hat, calibration_n=100)


def test_on_calibrated_accepts_grounded(monkeypatch):
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    # grounded answer: conf 0.88 + 2 support paths -> low nonconformity; generous q_hat -> ACCEPT
    monkeypatch.setattr(LW, "_load_calibration", lambda: _gate_with_qhat(0.9))
    r = _sample_result()
    out = LW.gate_answer(r, query="q", language="en")
    assert out["answer"] == r["answer"]               # answer kept
    assert out["_membrane"]["decision"] == "ACCEPT"
    assert out["reasoning_certificate"]["membrane_certificate"]["method"] == "split"


def test_on_calibrated_abstains_lowconf(monkeypatch):
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    # strict q_hat below the answer's nonconformity -> ABSTAIN
    monkeypatch.setattr(LW, "_load_calibration", lambda: _gate_with_qhat(0.05))
    weak = _sample_result()
    weak["confidence"] = 0.5
    weak["reasoning_certificate"]["evidence_concepts"] = []
    weak["reasoning_certificate"]["steps"] = []
    out = LW.gate_answer(weak, query="q", language="en")
    assert out["answer_kind"] == "honest_abstain"
    assert out["_membrane"]["decision"] == "ABSTAIN"
    # the certificate is the REAL gate decision, not a fabricated number
    cert = out["reasoning_certificate"]["membrane_certificate"]
    assert cert["nonconformity"] > cert["q_hat"]


def test_on_never_regates_existing_abstention(monkeypatch):
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    monkeypatch.setattr(LW, "_load_calibration", lambda: _gate_with_qhat(0.05))
    r = {"answer": "I don't have that on record.", "answer_kind": "honest_abstain",
         "confidence": 0.8, "reasoning_certificate": {}}
    out = LW.gate_answer(r, query="q", language="en")
    assert out is r                                   # untouched


def _curated_gc_result():
    """A REAL grounded_composition answer carries the closed-vocabulary composition guarantee that
    the plain _sample_result() (no guarantees) lacks -> it is the source-verified curated shape."""
    r = _sample_result()
    r["reasoning_certificate"]["guarantees"] = {
        "external_llm": False, "fabricated_facts": False,
        "inferred": False, "composition_vocabulary_closed": True,
    }
    return r


def test_on_source_verified_curated_passthrough(monkeypatch):
    """A provenance-backed curated composition (composition_vocabulary_closed) is accepted on its
    provenance BEFORE the conformal decision -- even an abstain-all gate never touches it. This is the
    fix for 'capital of France' abstaining: its own too-reliable Mondrian bin was abstain-all."""
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    monkeypatch.setattr(LW, "_load_calibration", lambda: _gate_with_qhat(float("-inf")))  # abstain-all
    r = _curated_gc_result()
    out = LW.gate_answer(r, query="q", language="en")
    assert out is r                                   # same object, answer kept
    assert out["_membrane"]["reason"] == "source_verified_passthrough"
    assert out["reasoning_certificate"]["membrane_certificate"]["basis"] == "source_verified_passthrough"


def test_on_bulk_relational_is_not_passed_through(monkeypatch):
    """The noisy bulk relational lane carries verified=True but NOT composition_vocabulary_closed,
    so it is NEVER passed through -- it always faces the conformal gate (here abstain-all -> ABSTAIN)."""
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    monkeypatch.setattr(LW, "_load_calibration", lambda: _gate_with_qhat(float("-inf")))
    r = {
        "answer": "Michelangelo's occupation is ninja, cook.",
        "answer_kind": "relational_edge_lookup",
        "confidence": 0.9,
        "reasoning_certificate": {
            "derivation_kind": "relational_edge_lookup",
            "guarantees": {"external_llm": False, "fabricated_facts": False,
                           "inferred": False, "verified": True},
            "steps": [], "evidence_concepts": [],
        },
    }
    out = LW.gate_answer(r, query="q", language="en")
    assert out["answer_kind"] == "honest_abstain"     # gated, not passed through
    assert out["_membrane"]["decision"] == "ABSTAIN"


def test_on_never_regates_relational_abstention(monkeypatch):
    """honest_abstain_relational is already an abstention -> never re-gated (never flipped to accept)."""
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    monkeypatch.setattr(LW, "_load_calibration", lambda: _gate_with_qhat(0.9))
    r = {"answer": "I don't hold a grounded capital fact for X yet.",
         "answer_kind": "honest_abstain_relational", "confidence": 0.2,
         "reasoning_certificate": {}}
    out = LW.gate_answer(r, query="q", language="en")
    assert out is r                                   # untouched


def test_on_gate_fault_falls_back_to_answer(monkeypatch):
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")

    def _boom():
        raise RuntimeError("calibration load blew up")

    monkeypatch.setattr(LW, "_load_calibration", _boom)
    r = _sample_result()
    out = LW.gate_answer(r, query="q", language="en")
    assert out is r                                   # fault -> today's answer, no regression


# ---------------------------------------------------------------- signal plumbing (ON) from real sg
def test_on_attach_signals_from_real_subgraph(monkeypatch):
    monkeypatch.setenv("ATANOR_MEMBRANE_LIVE", "1")
    from packages.graph_scale.spreading_activation import spread
    facts = {
        "Japan": [("Japan", "capital", "Tokyo"), ("Japan", "is_a", "country")],
        "Tokyo": [("Tokyo", "is_a", "city")],
    }
    sg = spread("Japan", lambda t: facts.get(t, []), intent_preds=("capital",))
    r = _sample_result()
    LW.attach_membrane_signals(r, subgraph=sg, anchor="Japan")
    sig = r["_membrane_signals"]
    assert set(sig) >= {"activation_mass", "support_path_count", "top_delivered"}
    assert all(isinstance(v, (int, float)) for v in sig.values())   # JSON-safe, no live object
    assert sig["support_path_count"] >= 1


# ---------------------------------------------------------------- artifact round-trip (inf-safe)
def test_qhat_json_roundtrip():
    for v in (0.37, float("-inf"), float("inf")):
        assert LW._qhat_from_json(LW.qhat_to_json(v)) == v


def test_calibration_load_from_disk(tmp_path, monkeypatch):
    import json
    doc = {"version": 1, "method": "mondrian", "alpha": 0.1,
           "bin_q_hat": {"capital": 0.4, "population": "__abstain_all__"},
           "fallback_q_hat": 0.3, "calibration_n": 50}
    p = tmp_path / "membrane_calibration.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(LW, "_CALIB_PATH", p)
    LW._calib_cache.clear()
    gate = LW._load_calibration()
    assert gate is not None and gate.method == "mondrian"
    assert gate.bin_q_hat["capital"] == 0.4
    assert gate.bin_q_hat["population"] == float("-inf")   # uncertifiable bin -> abstain-all
    assert gate.fallback_q_hat == 0.3


def test_has_calibrated_bin(tmp_path, monkeypatch):
    """A lane routes through the gate ONLY when its OWN Mondrian bin is calibrated (else it stays
    ungated rather than borrow the pooled fallback -- the define-lane fix's safety guard)."""
    import json
    doc = {"version": 1, "method": "mondrian", "alpha": 0.1,
           "bin_q_hat": {"relational_edge_lookup": 0.22, "ontology_graph_derivation": 0.4},
           "fallback_q_hat": 0.22, "calibration_n": 300}
    p = tmp_path / "membrane_calibration.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(LW, "_CALIB_PATH", p)
    LW._calib_cache.clear()
    assert LW.has_calibrated_bin("ontology_graph_derivation") is True
    assert LW.has_calibrated_bin("relational_edge_lookup") is True
    assert LW.has_calibrated_bin("some_uncalibrated_bin") is False


def test_has_calibrated_bin_false_when_no_artifact(monkeypatch):
    """No artifact at all -> no bin is calibrated (so a lane stays ungated / fail-safe passthrough)."""
    monkeypatch.setattr(LW, "_load_calibration", lambda: None)
    assert LW.has_calibrated_bin("ontology_graph_derivation") is False
