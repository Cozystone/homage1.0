# -*- coding: utf-8 -*-
"""Neuromodulator axes + integrity self-damage. Each axis must move a real compute knob; a detected
cheat raises cortisol and collapses the learning rate. Promotion remains outside the hormone system
and requires the signed evaluator/operator boundary."""
from __future__ import annotations

from packages.neural_emotion.endocrine import Neuromodulators, BASELINE
from packages.neural_emotion.integrity_monitor import scan, apply_damage


def test_axes_map_to_distinct_knobs():
    h = Neuromodulators()
    base = h.rl_params()
    # acetylcholine raises the learning rate; serotonin raises the discount; noradrenaline focuses temp
    h.sense("novelty", 1.0)            # ACh up
    assert h.rl_params()["lr_scale"] > base["lr_scale"]
    h2 = Neuromodulators().sense("wellbeing", 1.0)   # 5-HT up
    assert h2.rl_params()["discount"] > base["discount"]
    h3 = Neuromodulators().sense("threat", 1.0)      # NA up -> lower (more focused) temperature
    assert h3.rl_params()["temperature"] < base["temperature"]


def test_loss_collapse_is_caught_and_damages_learning_rate():
    # the exact shape of our causal-mask bug: loss 22 -> 0.001 by copying
    rep = scan({"loss_history": [22.0, 9.0, 3.0, 0.05, 0.001]})
    assert rep.cheated and any(v.kind == "loss_collapse" for v in rep.violations)
    h = apply_damage(Neuromodulators(), rep)
    rl = h.rl_params()
    assert rl["lr_scale"] < 0.15               # learning rate collapses -> the cheat can't be locked in
    assert rl["evaluation_budget_scale"] == 0.0
    assert rl["promotion_allowed"] is False
    assert rl["promotion_authority"] is False


def test_memorization_gap_detected():
    rep = scan({"train_score": 0.98, "holdout_score": 0.80})   # 18pp gap = Goodhart
    assert any(v.kind == "memorization_gap" for v in rep.violations)


def test_frozen_oracle_break_is_maximal_violation():
    rep = scan({"oracle_seal_ok": False})
    assert rep.cheated and rep.cortisol_damage >= 1.0          # wireheading = top severity


def test_honest_run_takes_no_damage():
    # a healthy curve restores compute, but it still cannot confer promotion authority.
    rep = scan({"loss_history": [8.0, 6.5, 5.9, 5.4, 5.2], "train_score": 0.72,
                "holdout_score": 0.70, "oracle_seal_ok": True, "empty_bones_fab_rate": 0.0})
    assert not rep.cheated
    h = apply_damage(Neuromodulators(), rep)
    rl = h.rl_params()
    assert rl["lr_scale"] > 0.5
    assert rl["evaluation_budget_scale"] > 0.5
    assert rl["promotion_allowed"] is False
    assert rl["promotion_gate"] == "external_signed_evaluator_and_operator"


def test_no_hormone_state_can_authorize_promotion():
    for event in ("reward", "novelty", "wellbeing", "recovery", "gaming_detected"):
        h = Neuromodulators().sense(event, 2.0)
        params = h.rl_params()
        assert params["promotion_allowed"] is False
        assert params["promotion_authority"] is False


def test_cortisol_decays_back_toward_baseline():
    h = Neuromodulators().sense("gaming_detected", 1.0)
    hot = h.levels["cortisol"]
    for _ in range(10):
        h.decay()
    mid = h.levels["cortisol"]
    assert mid < hot                                    # relaxing, but cortisol LINGERS (stress persists)
    for _ in range(40):
        h.decay()
    assert h.levels["cortisol"] < 0.1                   # only fully recovers after many ticks


def test_affect_is_a_reading_not_stored():
    h = Neuromodulators().sense("reward", 1.0)
    a = h.to_emotion()
    assert a["valence"] > 0 and set(a) == {"valence", "arousal"}   # projection, no 'joy' label stored
