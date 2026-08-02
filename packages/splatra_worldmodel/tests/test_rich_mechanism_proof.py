# -*- coding: utf-8 -*-
"""End-to-end RICH mechanism proof (fast config): the honest, robust invariants on the
contact-rich / non-rigid dynamics a global linear map cannot fit.

We assert what MUST hold for the make-or-break test to be valid -- budget, quarantine
correctness (re-verified under the new dynamics), collapse-safety, real learning (beats the
no-model persistence baseline), generalization (not memorization), and that the verdict is
reported. We do NOT hard-assert a specific BETTER/EQUAL/WORSE verdict (that is the honest
empirical output of the harness). We DO assert the scientific point of the rung: on richer
dynamics JEPA is materially closer to / better than linear than on the near-linear toy
(where it was 2.58x WORSE)."""
from __future__ import annotations

from packages.splatra_worldmodel.mechanism_proof import format_scorecard
from packages.splatra_worldmodel.rich_mechanism_proof import (
    RichProofConfig,
    Scorecard,
    run_rich_mechanism_proof,
)

_CACHE: dict[str, Scorecard] = {}


def _proof() -> Scorecard:
    if "s" not in _CACHE:
        _CACHE["s"] = run_rich_mechanism_proof(RichProofConfig.fast())
    return _CACHE["s"]


def test_neuro_budget_under_25m():
    s = _proof()
    assert s.param_counts["trainable_total"] < 25_000_000
    assert s.param_counts["total_incl_ema"] < 25_000_000


def test_physics_truth_quarantine_reverified_under_new_dynamics():
    # BINDING: re-verify the gate still catches injected violations under the NEW dynamics.
    s = _proof()
    q = s.quarantine
    assert q.true_transitions_quarantined == 0      # observed contact dynamics is physical
    assert q.true_transitions_checked > 0
    assert q.injected_total > 0
    assert q.injected_quarantined == q.injected_total   # every injected violation caught
    assert q.quarantined_after_filter == q.injected_total
    assert q.kept_after_filter > 0
    assert len(q.example_reasons) > 0


def test_collapse_guard_keeps_latent_alive():
    s = _proof()
    assert s.train_report.emb_std_min > 0.1
    assert s.train_report.emb_std_mean > 0.3


def test_jepa_learns_real_dynamics_beats_persistence():
    s = _proof()
    # JEPA-over-turbovec must beat the no-model baseline on held-out (it learns real dynamics).
    assert s.jepa_heldout < 0.6 * s.persistence_heldout


def test_generalizes_not_memorizes():
    s = _proof()
    assert s.jepa_heldout < 6.0 * max(s.jepa_train, 1e-6)


def test_contact_regime_is_active():
    # the harness is exercising the contact-rich regime, not a settled/free-fall degenerate.
    s = _proof()
    assert s.contact_fraction_train > 0.5
    assert s.contact_fraction_heldout > 0.5


def test_jepa_competitive_with_linear_on_rich_dynamics():
    # The scientific point of this rung: the near-linear toy gave JEPA/linear = 2.58 (WORSE).
    # On dynamics a global linear map CANNOT fit, JEPA is materially closer / better. This is
    # seed-robust (the fast config measures ~0.99); we assert a loose, unambiguous bound that
    # still clearly separates from the toy's 2.58.
    s = _proof()
    assert s.jepa_vs_linear_ratio > 0.0
    assert s.jepa_vs_linear_ratio < 1.6, s.jepa_vs_linear_ratio


def test_verdict_is_reported():
    s = _proof()
    assert s.verdict in {"BETTER", "EQUAL", "WORSE"}
    assert s.n_train_transitions > 0


def test_scorecard_formats():
    s = _proof()
    text = format_scorecard(s)
    assert "VERDICT" in text
    assert "PHYSICS-TRUTH" in text
