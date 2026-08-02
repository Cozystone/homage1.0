"""The mind acts on its own goals — but ONLY within the OBSERVE capability tier.
Higher tiers are proposal-only and can never be auto-run."""
from __future__ import annotations

from packages.continuous_self.action import (
    Action,
    TIER_OBSERVE,
    TIER_MUTATE,
    TIER_CODE,
    act,
    plan_action,
    take_initiative,
)
from packages.continuous_self.self_state import Observation, SelfState, evolve


def test_plan_maps_resolve_goal_to_a_readonly_measure():
    a = plan_action({"kind": "resolve", "id": "g1"})
    assert a is not None and a.tier == TIER_OBSERVE and a.autonomous_ok
    assert a.kind == "measure_coverage_gaps"


def test_mutate_and_code_actions_are_never_autonomous():
    for tier in (TIER_MUTATE, TIER_CODE):
        a = Action("dangerous", tier, "g", "should require a human")
        assert a.autonomous_ok is False
        rec = act(SelfState(), a, observe_fn=lambda kind: {"did": "SHOULD NOT RUN"})
        assert rec["blocked"] is True and rec["executed"] is False
        assert "outcome" not in rec  # the effect callable was never invoked


def test_observe_action_runs_and_feeds_outcome_back():
    s = SelfState()
    a = plan_action({"kind": "resolve", "id": "g1"})
    seen = {}

    def probe(kind: str) -> dict:
        seen["kind"] = kind
        return {"open_gaps": 35}

    rec = act(s, a, observe_fn=probe)
    assert rec["executed"] is True and rec["blocked"] is False
    assert seen["kind"] == "measure_coverage_gaps"
    # the mind PERCEIVES the outcome — the loop is closed.
    assert s.last_action["outcome"]["open_gaps"] == 35
    assert "35" in s.current_thought


def test_take_initiative_uses_the_primary_goal():
    s = SelfState()
    # give the self a real goal first
    for _ in range(4):
        evolve(s, Observation(deficit_count=20), rate=0.4)
    rec = take_initiative(s, observe_fn=lambda kind: {"open_gaps": 20})
    assert rec is not None and rec["tier"] == TIER_OBSERVE


def test_no_goal_no_action():
    s = SelfState()
    assert take_initiative(s, observe_fn=lambda kind: {}) is None


def test_faulty_probe_never_breaks_the_life():
    s = SelfState()
    a = plan_action({"kind": "resolve", "id": "g1"})

    def boom(kind: str) -> dict:
        raise RuntimeError("probe down")

    rec = act(s, a, observe_fn=boom)  # must not raise
    # a failed probe is honestly NOT "executed", and the error is recorded, not hidden.
    assert rec["executed"] is False and "error" in rec["outcome"]
    assert "막혔다" in s.current_thought
