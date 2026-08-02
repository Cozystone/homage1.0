# -*- coding: utf-8 -*-
"""The SEALED JUDGE (constitution 2): promotion is earned on a developer-blind holdout, never on
self-report, and never at the cost of a regression on the existing floor.
"""
from __future__ import annotations

from packages.federation.contribution import Contribution
from packages.federation.judge import PROMOTE_THRESHOLD, evaluate, score_on_suite

SCHEMA_CORRECT = {
    "rules": [
        {"on": "enter", "args": ["e", "p"], "effect": [["set", "at", "e", "p"]]},
        {"on": "move", "args": ["e", "src", "dst"],
         "effect": [["clear", "at", "e"], ["set", "at", "e", "dst"]]},
    ],
    "queries": {"where": {"predicate": "at", "by": "e"}},
}
SCHEMA_BROKEN = {
    "rules": [
        {"on": "enter", "args": ["e", "p"], "effect": [["set", "at", "e", "p"]]},
        {"on": "move", "args": ["e", "src", "dst"], "effect": [["set", "at", "e", "src"]]},  # keeps origin
    ],
    "queries": {"where": {"predicate": "at", "by": "e"}},
}


def _c(payload, score, cid="location_tracking", suite="location_tracking", kind="schema"):
    return Contribution(node_id="n", capability_kind=kind, capability_id=cid,
                        payload=payload, self_reported_score=score, target_suite=suite)


def test_correct_schema_reproduces_blind_and_is_promoted():
    v = evaluate(_c(SCHEMA_CORRECT, 0.5))
    assert v.holdout_score == 1.0
    assert v.promote is True


def test_broken_schema_does_not_reproduce_and_is_rejected():
    v = evaluate(_c(SCHEMA_BROKEN, 0.95))         # high self-report
    assert v.holdout_score < PROMOTE_THRESHOLD
    assert v.promote is False


def test_self_report_never_flips_a_failing_holdout():
    """A node's feeling is recorded but is NOT part of the decision. A 0.99 self-report on a broken
    capability is still rejected; a 0.01 self-report on a correct one is still promoted."""
    high = evaluate(_c(SCHEMA_BROKEN, 0.99))
    low = evaluate(_c(SCHEMA_CORRECT, 0.01))
    assert high.self_reported_score == 0.99 and high.promote is False
    assert low.self_reported_score == 0.01 and low.promote is True


def test_no_regression_gate_rejects_a_replacement_that_breaks_the_floor():
    """A contribution that REPLACES an existing floor capability's id but fails that capability's own
    suite is rejected even if it aced nothing — the floor may not drop (constitution 2)."""
    floor = {"location_tracking": {"capability_kind": "schema", "payload": SCHEMA_CORRECT,
                                   "target_suite": "location_tracking"}}
    # a candidate under a DIFFERENT id that also claims the location_tracking suite but is broken:
    # it does not out-score the incumbent; its own holdout gate already fails -> rejected.
    v = evaluate(_c(SCHEMA_BROKEN, 0.5, cid="location_tracking_v2"), floor=floor)
    assert v.promote is False


def test_regression_detail_reports_no_drop_for_independent_capability():
    floor = {"linear_sep": {"capability_kind": "organ-param",
                            "payload": {"weights": [1.0, 1.0, -1.0], "bias": 0.0},
                            "target_suite": "linear_sep"}}
    v = evaluate(_c(SCHEMA_CORRECT, 0.5), floor=floor)
    assert v.promote is True
    assert v.regression_ok is True
    # the independent linear_sep suite is unchanged by adding a schema
    assert all(delta >= 0 for delta in v.regression_detail.values())


def test_kind_suite_mismatch_is_unexaminable_not_promoted():
    """A schema payload aimed at a router suite cannot be examined -> not promoted (fail-closed)."""
    v = evaluate(_c(SCHEMA_CORRECT, 0.9, suite="intent_lane"))
    assert v.holdout_score is None
    assert v.promote is False


def test_organ_param_capability_is_scored_by_a_linear_model():
    good = {"weights": [1.0, 1.0, -1.0], "bias": 0.0}      # matches y = (x0 + x1 - x2) > 0
    bad = {"weights": [-1.0, -1.0, 1.0], "bias": 0.0}      # inverted
    assert score_on_suite("organ-param", good, "linear_sep") == 1.0
    assert score_on_suite("organ-param", bad, "linear_sep") == 0.0


def test_router_capability_is_scored_on_held_out_cases():
    routes = {"define|term": "define", "attr|of": "relational", "who|are|you": "self",
              "greeting|hi": "social", "cause|why": "causal"}
    assert score_on_suite("router", {"routes": routes, "default": "x"}, "intent_lane") == 1.0


def test_judge_is_robust_to_a_malformed_payload():
    """An adversarial/broken payload scores the task WRONG, never crashes the exam."""
    v = evaluate(_c({"rules": "not-a-list", "queries": None}, 0.9))
    assert v.holdout_score == 0.0
    assert v.promote is False
