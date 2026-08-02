# -*- coding: utf-8 -*-
"""End-to-end mechanism proof (fast config): the honest, robust invariants.

We assert what MUST hold for the mechanism to be real -- NOT that JEPA beats the linear
baseline (on this mostly-linear toy it does not; that is the honest verdict the harness
reports). We assert: budget, quarantine correctness, collapse-safety, and that the JEPA
learns REAL dynamics (beats the no-model persistence baseline and generalizes to held-out).
"""
from __future__ import annotations

from packages.splatra_worldmodel.mechanism_proof import (
    ProofConfig,
    Scorecard,
    format_scorecard,
    run_mechanism_proof,
)

_CACHE: dict[str, Scorecard] = {}


def _proof() -> Scorecard:
    if "s" not in _CACHE:
        _CACHE["s"] = run_mechanism_proof(ProofConfig.fast())
    return _CACHE["s"]


def test_neuro_budget_under_25m():
    s = _proof()
    assert s.param_counts["trainable_total"] < 25_000_000
    assert s.param_counts["total_incl_ema"] < 25_000_000


def test_physics_truth_quarantine_is_correct():
    s = _proof()
    q = s.quarantine
    # observed dynamics is physical -> nothing true is quarantined
    assert q.true_transitions_quarantined == 0
    assert q.true_transitions_checked > 0
    # every injected physics violation is caught (never learned)
    assert q.injected_total > 0
    assert q.injected_quarantined == q.injected_total
    # mixed buffer: only the violations are removed
    assert q.quarantined_after_filter == q.injected_total
    assert q.kept_after_filter > 0
    assert len(q.example_reasons) > 0


def test_collapse_guard_keeps_latent_alive():
    s = _proof()
    assert s.train_report.emb_std_min > 0.1
    assert s.train_report.emb_std_mean > 0.3


def test_jepa_learns_real_dynamics_beats_persistence():
    s = _proof()
    # the whole point: JEPA-over-turbovec must beat the no-model baseline on held-out.
    assert s.jepa_heldout < 0.8 * s.persistence_heldout


def test_generalizes_not_memorizes():
    s = _proof()
    # held-out error is bounded relative to train -> structure, not memorization
    assert s.jepa_heldout < 6.0 * max(s.jepa_train, 1e-6)


def test_verdict_is_reported():
    s = _proof()
    assert s.verdict in {"BETTER", "EQUAL", "WORSE"}
    assert s.jepa_vs_linear_ratio > 0.0
    # the training set was gated by the physics membrane
    assert s.n_train_transitions > 0


def test_scorecard_formats():
    s = _proof()
    text = format_scorecard(s)
    assert "VERDICT" in text
    assert "PHYSICS-TRUTH" in text
    assert "param count" in text
