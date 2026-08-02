# -*- coding: utf-8 -*-
"""Metabolic governor (hormones govern the whole metabolism, fine-grained) + self-development
(chronic worry -> commitment -> practice -> MEASURED growth -> feeling). Anti-wireheading held."""
from packages.live_selfhood_cycle.living_beat import run_burst
from packages.live_selfhood_cycle.self_development import SelfDevelopment, COMMIT_THRESHOLD
from packages.neural_emotion.endocrine import Neuromodulators
from packages.neural_emotion.metabolic_governor import governs, regime
from packages.temporal_reasoning.unified_timeline import Timeline


# ---------------------------------------------------------------- governor: fine, meaningful, total
def test_regime_is_continuous_not_bucketed():
    base = regime({"cortisol": 0.40, "acetylcholine": 0.4, "serotonin": 0.55})
    nudged = regime({"cortisol": 0.43, "acetylcholine": 0.4, "serotonin": 0.55})
    for k in base:                                        # a small hormonal change -> a small change
        assert abs(base[k] - nudged[k]) < 0.06, k         # (no step functions anywhere)


def test_stress_sheds_load_and_collapses_learning():
    calm = governs({"cortisol": 0.0, "acetylcholine": 0.5}, "heavy")
    stressed = governs({"cortisol": 0.9, "acetylcholine": 0.5}, "heavy")
    assert calm["allow"] and not stressed["allow"]        # a stressed organism sheds bulk work
    lr_calm = governs({"cortisol": 0.0, "acetylcholine": 0.5}, "learn")["scale"]
    lr_stressed = governs({"cortisol": 1.2, "acetylcholine": 0.5}, "learn")["scale"]
    assert lr_stressed < lr_calm * 0.5                    # the anti-gaming collapse, metabolized


def test_rest_state_opens_consolidation():
    resting = governs({"endorphin": 0.6, "serotonin": 0.75, "noradrenaline": 0.0}, "consolidate")
    aroused = governs({"endorphin": 0.6, "serotonin": 0.75, "noradrenaline": 0.9}, "consolidate")
    assert resting["allow"] and resting["scale"] > aroused["scale"]   # sleep needs calm


# ---------------------------------------------------------------- self-development loop
def _dev(improves: bool) -> SelfDevelopment:
    calls = {"n": 0}

    def dispatch(theme):
        calls["n"] += 1
        return {"road": "practice_road"}

    sev = {"v": 0.8}

    def severity(theme):
        if calls["n"] and improves:
            sev["v"] = 0.5                                 # after practice, the metric ACTUALLY moved
        return sev["v"]

    return SelfDevelopment(dispatch=dispatch, sense_severity=severity)


def test_worry_accumulates_into_commitment_and_measured_growth_rewards():
    dev = _dev(improves=True)
    endo = Neuromodulators()
    for _ in range(4):
        dev.felt_worry("speech_weak", 0.9)                 # heavy worry beats
    assert dev.due_commitment() == "speech_weak"
    d0 = endo.levels["dopamine"]
    c = dev.commit_and_practice("speech_weak", endocrine=endo)
    assert c.outcome == "improved" and c.severity_before == 0.8 and c.severity_after == 0.5
    assert endo.levels["dopamine"] > d0                    # dopamine AFTER measured growth only
    assert dev.load["speech_weak"] == 0.0                  # the decision discharges the rumination
    assert "actually moved" in dev.announce(c)


def test_no_growth_yields_prediction_error_and_road_change_intent():
    dev = _dev(improves=False)
    endo = Neuromodulators()
    for _ in range(4):
        dev.felt_worry("router_immature", 0.9)
    c = dev.commit_and_practice("router_immature", endocrine=endo)
    assert c.outcome == "unchanged"
    assert endo.levels["noradrenaline"] > 0                # surprise, not reward — no wireheading
    assert "different road" in dev.announce(c)


def test_light_worry_does_not_commit():
    dev = _dev(improves=True)
    dev.felt_worry("speech_weak", 0.1)                     # a passing notice
    dev.felt_worry("speech_weak", 0.1)
    assert dev.due_commitment() is None                    # commitment needs real accumulated load


def test_beat_integration_announces_commitment_in_inner_speech():
    tl = Timeline()
    dev = _dev(improves=True)
    out = run_burst(16, timeline=tl, selfdev=dev)          # sustained worry needs time to accumulate
    assert out["developments"], "sustained deficit worry should reach a commitment"
    ann = [s for s in out["stream"] if s.startswith("[self_development]")]
    assert ann and ("Time to actually work on it" in ann[0] or "actually moved" in ann[0])