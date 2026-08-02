# -*- coding: utf-8 -*-
"""Tests for within-percept recurrent refinement (RPT-1's deep sensory feedback loop).

The two properties that make this an HONEST organ, not a probe-gaming stub:
  * a noisy/ambiguous percept is measurably SHARPENED across iterations and STABILISES;
  * an unresolvable percept (tied evidence, unhelpful context) honestly GIVES UP — it converges to
    its true low confidence and reports 'unresolved', it does NOT fabricate certainty.
Plus: convergence is real, top-down context changes the settled percept (the recurrence signature),
and flat input cannot manufacture confidence (the anti-wireheading guard).
"""
from __future__ import annotations

import numpy as np

from packages.perception_recurrence.refinement import (
    refine, refine_with_plausibility, plausibility_prior,
    ACCEPT, KAPPA, W_FB,
)


# ---------------------------------------------------------------- sharpening (the RPT property)
def test_ambiguous_percept_is_sharpened_across_iterations_and_stabilises():
    """A low-confidence read + agreeing context is refined upward and settles."""
    tr = refine(["cup", "bowl", "mug"], [0.42, 0.33, 0.25], context=[0.62, 0.23, 0.15])
    assert tr.initial_confidence < ACCEPT              # started ambiguous
    assert tr.converged is True                        # it stabilised
    assert tr.resolved is True and tr.status == "sharpened"
    assert tr.confidence >= ACCEPT                     # ended usable
    assert tr.delta_confidence > 0.15                  # measurably sharper than the feed-forward read
    assert tr.winner == "cup"
    # the trajectory is the sharpening curve and it is (weakly) monotone increasing to the fixed point
    traj = tr.trajectory
    assert traj[0] == tr.initial_confidence
    assert traj[-1] == tr.confidence
    assert all(traj[i + 1] >= traj[i] - 1e-9 for i in range(len(traj) - 1))


def test_trajectory_actually_moves_and_is_bounded_length():
    tr = refine(["a", "b", "c"], [0.42, 0.33, 0.25], context=[0.62, 0.23, 0.15])
    assert len(tr.trajectory) >= 3                     # more than one refinement step happened
    assert tr.iterations <= 16                         # bounded (cheap)
    assert tr.confidence - tr.initial_confidence == tr.delta_confidence


# ---------------------------------------------------------------- honest give-up (no fabrication)
def test_unresolvable_percept_honestly_gives_up_without_fabricating_confidence():
    """Tied evidence + flat context: the loop must NOT invent a winner's certainty."""
    tr = refine(["left", "right", "other"], [0.40, 0.40, 0.20], context=[0.34, 0.33, 0.33])
    assert tr.converged is True                        # it still settles (it is a contraction)
    assert tr.resolved is False                        # but it is NOT resolved
    assert tr.status == "unresolved_ambiguous"
    assert tr.confidence < ACCEPT                      # confidence stayed honestly low
    assert tr.confidence < 0.5                         # nowhere near a fabricated certainty
    assert tr.delta_confidence < 0.05                  # it barely moved — no manufactured sharpening


def test_flat_evidence_and_flat_context_cannot_manufacture_confidence():
    """The anti-wireheading guard: uniform in -> (near-)uniform out. No certainty from nothing."""
    tr = refine(["x", "y", "z"], [1.0, 1.0, 1.0], context=[1.0, 1.0, 1.0])
    assert tr.resolved is False
    assert abs(tr.confidence - 1.0 / 3) < 1e-6         # exactly uniform fixed point
    assert tr.status == "unresolved_ambiguous"


def test_running_out_of_iteration_budget_is_an_honest_give_up_not_a_victory():
    """If it has not stabilised within the budget, it reports did_not_stabilize, not a settled value."""
    tr = refine(["a", "b", "c"], [0.42, 0.33, 0.25], context=[0.62, 0.23, 0.15], max_iter=2)
    assert tr.converged is False
    assert tr.resolved is False
    assert tr.status == "did_not_stabilize"


# ---------------------------------------------------------------- recurrence signature + context
def test_same_evidence_different_top_down_context_settles_to_a_different_percept():
    """The RPT signature within a percept: identical bottom-up evidence, different top-down state ->
    different settled interpretation (the loop integrates recurrent top-down state)."""
    scores = [0.40, 0.38, 0.22]
    a = refine(["p", "q", "r"], scores, context=[0.70, 0.20, 0.10])
    b = refine(["p", "q", "r"], scores, context=[0.20, 0.70, 0.10])
    assert a.winner == "p" and b.winner == "q"         # context decided the winner
    assert a.final != b.final                          # same evidence, different settled percept


def test_top_down_context_can_override_a_wrong_looking_feed_forward_winner():
    """A confident-but-impossible glimpse is corrected by the plausibility prior (winner flips)."""
    # detector leans toward an indoor-IMPLAUSIBLE reading; plausibility top-down suppresses it
    tr = refine_with_plausibility(["고래", "노트북", "컵"], [0.45, 0.30, 0.25])
    assert tr.winner_initial == "고래"                  # the raw feed-forward read
    assert tr.winner != "고래"                          # top-down context corrected it
    assert tr.flipped is True


def test_plausibility_prior_downweights_impossible_indoor_objects():
    prior = plausibility_prior(["고래", "노트북"])       # whale (impossible) vs laptop (fine)
    assert prior[1] > prior[0]                          # laptop carries more top-down prior mass
    assert abs(float(prior.sum()) - 1.0) < 1e-9


# ---------------------------------------------------------------- already-confident + edges
def test_already_confident_percept_is_confirmed_not_inflated_falsely():
    # a percept already near the ceiling has little room to climb -> 'confirmed' (moved < margin)
    tr = refine(["dog", "cat", "fox"], [0.96, 0.02, 0.02], context=[0.90, 0.06, 0.04])
    assert tr.resolved is True
    assert tr.status == "confirmed"
    assert tr.winner == "dog"
    assert tr.converged is True


def test_confident_percept_that_still_sharpens_is_labelled_sharpened_honestly():
    # a strong-but-not-ceilinged read that recurrence pushes measurably higher is 'sharpened', not a lie
    tr = refine(["dog", "cat", "fox"], [0.80, 0.12, 0.08], context=[0.50, 0.30, 0.20])
    assert tr.resolved is True and tr.winner == "dog"
    assert tr.status == "sharpened" and tr.delta_confidence >= 0.05


def test_no_context_leans_only_on_evidences_own_tilt():
    """Without context, the loop may sharpen an evidence tilt but cannot invent one from flat scores."""
    flat = refine(["a", "b"], [1.0, 1.0])              # no context, flat evidence
    assert flat.resolved is False                       # nothing to sharpen -> honest give-up
    leaning = refine(["a", "b", "c"], [0.55, 0.25, 0.20])   # a real tilt, no context
    assert leaning.confidence >= leaning.initial_confidence  # it may sharpen its own tilt


def test_convergence_gain_is_sub_critical_by_construction():
    """The honesty invariant lives in the constants: self-feedback gain < 1 (contraction => converges,
    and flat input has a unique uniform fixed point)."""
    assert KAPPA * W_FB < 1.0


def test_single_candidate_is_trivially_resolved():
    tr = refine(["only"], [0.9])
    assert tr.winner == "only"
    assert abs(tr.confidence - 1.0) < 1e-9
