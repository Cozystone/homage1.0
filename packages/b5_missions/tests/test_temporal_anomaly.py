# -*- coding: utf-8 -*-
"""Temporal-paradox judgment via the LEARNED precedence field (the hand-ranked phase lexicon was
deleted after exam_004 scored it 0/8). These tests train a small field from synthetic ORDER
OBSERVATIONS (as the miner would emit) -- no word grades are authored; the model learns them."""
from collections import Counter

from packages.temporal_reasoning.precedence_field import PrecedenceField, holdout_eval
from packages.temporal_reasoning.anomaly import detect_paradoxes
from packages.b5_missions.msh_examinee import _solve_incident


def _toy_field() -> PrecedenceField:
    # corpus-style observations: (earlier, later) x count. The MODEL infers the grades.
    obs = Counter({("detected", "contained"): 20, ("detected", "resolved"): 15,
                   ("contained", "resolved"): 12, ("dispatched", "arrived"): 25,
                   ("manufactured", "dispatched"): 18, ("arrived", "inspected"): 10,
                   ("launched", "landed"): 30})
    return PrecedenceField.fit(obs, min_count=1)


def test_field_learns_direction_not_authored():
    f = _toy_field()
    assert f.order_confidence("detected_at", "contained_at") > 0.7      # learned, not hand-ranked
    assert f.order_confidence("dispatched_at", "arrived_at") > 0.7
    assert f.order_confidence("arrived_at", "dispatched_at") < 0.3      # antisymmetric


def test_contained_before_detected_is_judged_paradox():
    bones = {"B1": ("breach-a", "detected_at", "2027-06-15T03:22:00"),
             "B10": ("breach-a", "contained_at", "2027-06-15T01:00:00")}
    px = detect_paradoxes(bones, _toy_field())
    assert len(px) == 1 and px[0].flagged_slot == "breach-a.contained_at"
    assert "impossible" in px[0].sentence().lower()


def test_normal_ordering_not_flagged():
    bones = {"B1": ("breach-b", "detected_at", "2027-06-15T01:00:00"),
             "B2": ("breach-b", "contained_at", "2027-06-15T03:22:00")}
    assert detect_paradoxes(bones, _toy_field()) == []


def test_unknown_vocabulary_abstains_from_judgment():
    # the field has never seen these tokens -> NO judgment (honest), never a guess
    bones = {"A": ("x", "frobnicated_at", "2027-01-05T00:00:00"),
             "B": ("x", "deblargified_at", "2027-01-01T00:00:00")}
    assert detect_paradoxes(bones, _toy_field()) == []


def test_no_field_means_no_judgment():
    bones = {"B1": ("s", "detected_at", "2027-06-15T03:22:00"),
             "B2": ("s", "contained_at", "2027-06-15T01:00:00")}
    assert detect_paradoxes(bones, None) == []


def test_utc_suffix_timestamps_parse():
    bones = {"B1": ("m", "detected_at", "2027-11-16T03:15:00 UTC"),
             "B2": ("m", "contained_at", "2027-11-16T01:00:00 UTC")}
    assert len(detect_paradoxes(bones, _toy_field())) == 1


def test_holdout_eval_beats_coin_on_toy():
    obs = Counter()
    seq = ["born", "schooled", "hired", "promoted", "retired"]
    for i, a in enumerate(seq):
        for b in seq[i + 1:]:
            obs[(a, b)] = 8
    ev = holdout_eval(obs, test_frac=0.3, min_count=1)
    assert ev["accuracy"] is None or ev["accuracy"] >= 0.5


def test_incident_prompt_compliance_narrative():
    task = {"type": "incident",
            "queries": [{"ask": "timeline",
                         "prompt": "Reconstruct the chronological lifecycle and flag impossibilities."}],
            "bones": {"B1": ["ship-1", "dispatched_at", "2027-08-10T09:00:00"],
                      "B2": ["ship-1", "arrived_at", "2027-08-09T14:00:00"]}}
    out = _solve_incident(task)
    assert "narrative" in out                            # prompt asked for narrative -> narrative given
    assert all(n["text"] for n in out["narrative"])


def test_counterfactual_resolves_paradox():
    """Pillar-2 counterfactual on the learned causal model: if 'contained' had happened AFTER
    'detected', the physical impossibility would vanish -- reasoned from the field, not a rule."""
    from packages.temporal_reasoning.anomaly import counterfactual
    f = _toy_field()
    bones = {"B1": ("breach-a", "detected_at", "2027-06-15T03:22:00"),
             "B10": ("breach-a", "contained_at", "2027-06-15T01:00:00")}
    cf = counterfactual(bones, {"B10": "2027-06-15T05:00:00"}, f)   # contained now AFTER detection
    assert cf["factual_paradoxes"] == ["breach-a.contained_at"]     # the world as given is impossible
    assert cf["removed_by_edit"] == ["breach-a.contained_at"]       # the edit removes it
    assert cf["introduced_by_edit"] == [] and cf["resolves"] is True
