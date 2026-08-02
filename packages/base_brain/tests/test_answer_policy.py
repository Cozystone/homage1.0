"""The soft answer-mode policy + its self-tuning: routing is a fluid weighted decision
(not a hard rule gate), the default weights reproduce the measured-good behaviour, and the
tuner can SELF-CORRECT a degraded policy back to correct routing while never lowering
accuracy."""
from __future__ import annotations

import copy

from packages.base_brain.answer_policy import (
    MODES, FEATURES, decide_mode, extract_features, score_modes, _DEFAULT_WEIGHTS,
)
from packages.base_brain.answer_policy_tuning import accuracy, tune, _margin


def test_default_policy_routes_the_battery_correctly():
    acc, _ = accuracy()
    assert acc == 1.0, "default weights must reproduce the measured-good routing"


def test_decision_is_soft_and_auditable():
    # a decision returns a full score DISTRIBUTION (a blend), not just a hard label
    mode, scores = decide_mode("고양이가 왜 물어?", {"named_match": 0.9, "has_definition": True})
    assert set(scores) == set(MODES)
    assert mode == "engage"
    # definitional with strong grounding -> define, and it beats engage by a real margin
    mode2, scores2 = decide_mode("세포란?", {"named_match": 1.0, "has_definition": True})
    assert mode2 == "define" and scores2["define"] > scores2["engage"]


def test_grounding_strength_shifts_the_decision_fluidly():
    # SAME query shape, DIFFERENT grounding -> the DEFINE confidence moves continuously
    # (fluid, not a fixed rule): strong grounding gives a much higher define score, and a
    # bigger margin over abstain, than weak grounding.
    _, s_strong = decide_mode("X는 무엇인가?", {"named_match": 1.0, "has_definition": True})
    _, s_weak = decide_mode("X는 무엇인가?", {"named_match": 0.0, "has_definition": False})
    assert s_strong["define"] > s_weak["define"]                       # confidence scales with grounding
    strong_margin = s_strong["define"] - s_strong["abstain"]
    weak_margin = s_weak["define"] - s_weak["abstain"]
    assert strong_margin > weak_margin                                # the boundary moves fluidly
    # a rich neighbourhood tilts the same thin-grounding question toward synthesise
    _, s_synth = decide_mode("X에 대해 설명해줘", {"named_match": 0.0, "neighborhood": 0.9})
    assert s_synth["synthesize"] > s_weak["synthesize"]


def test_tuner_self_corrects_a_degraded_policy():
    # DEGRADE the engage weights (reproduce the original 'force a definition' bug)
    bad = copy.deepcopy(_DEFAULT_WEIGHTS)
    for f in ("cue_advice", "cue_opinion", "cue_causal", "cue_personal"):
        bad["engage"][f] = 0.2
    bad_acc, _ = accuracy(bad)
    assert bad_acc < 0.6                       # badly broken routing

    # margin-based coordinate descent recovers it
    w, margin = copy.deepcopy(bad), _margin(bad)
    for _ in range(40):
        improved = False
        for mode in MODES:
            for feat in FEATURES:
                for step in (0.4, -0.4):
                    t = copy.deepcopy(w)
                    t[mode][feat] = t[mode].get(feat, 0.0) + step
                    tm = _margin(t)
                    if tm > margin + 1e-9:
                        w, margin, improved = t, tm, True
        if not improved:
            break
    assert accuracy(w)[0] >= 0.95              # SELF-CORRECTED back to correct routing


def test_tune_never_lowers_accuracy_and_reports():
    r = tune(steps=5, delta=0.4, save=False)
    assert r["tuned_accuracy"] >= r["base_accuracy"]   # the guarantee: only ever improves
    assert 0.0 <= r["tuned_accuracy"] <= 1.0
