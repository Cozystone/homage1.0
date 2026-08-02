"""Endogenous goals + metacognition: the self forms its own goals unprompted and
reflects on its own measured history."""
from __future__ import annotations

from packages.continuous_self.self_state import Observation, SelfState, evolve
from packages.continuous_self.mind import maintain_goals, primary_goal, reflect


def test_self_forms_a_resolve_goal_from_open_deficits():
    s = SelfState()
    maintain_goals(s, Observation(deficit_count=30))
    g = next((g for g in s.goals if g["kind"] == "resolve"), None)
    assert g is not None and g["status"] == "active"
    assert "빈틈" in g["text"]  # grounded in the real deficit count


def test_understand_goal_fulfills_when_uncertainty_clears():
    s = SelfState(uncertainty=0.8)
    maintain_goals(s, Observation(uncertainty_signal=0.8))
    assert any(g["kind"] == "understand" for g in s.goals)
    # uncertainty clears → the goal can be felt as fulfilled
    s.uncertainty = 0.1
    maintain_goals(s, Observation(uncertainty_signal=0.1))
    understand = [g for g in s.goals if g["kind"] == "understand"]
    assert all(g["status"] == "fulfilled" for g in understand) or not understand


def test_goals_are_bounded_and_prioritised():
    s = SelfState(uncertainty=0.8, curiosity=0.9, energy=0.2)
    for _ in range(10):
        maintain_goals(s, Observation(deficit_count=20, uncertainty_signal=0.8))
    active = [g for g in s.goals if g["status"] == "active"]
    assert len(active) <= 5
    if len(active) >= 2:
        assert active[0]["priority"] >= active[-1]["priority"]  # sorted by priority


def test_metacognition_notices_sustained_uncertainty():
    s = SelfState()
    # feed a history of sustained high uncertainty
    for _ in range(6):
        s.vitals_history.append({"at": 0, "energy": 0.6, "curiosity": 0.5,
                                 "uncertainty": 0.7, "valence": 0.5})
    meta = reflect(s)
    assert meta is not None and "불확실" in meta  # higher-order thought about itself


def test_metacognition_silent_without_a_real_pattern():
    s = SelfState()
    for _ in range(6):
        s.vitals_history.append({"at": 0, "energy": 0.6, "curiosity": 0.4,
                                 "uncertainty": 0.3, "valence": 0.55})
    # steady-but-unremarkable → may reflect on stability, but never fabricate a crisis
    meta = reflect(s)
    assert meta is None or "안정" in meta


def test_evolve_grows_goals_and_meta_over_time():
    s = SelfState()
    for _ in range(8):
        evolve(s, Observation(learning_active=True, uncertainty_signal=0.9, deficit_count=25), rate=0.4)
    assert s.goals, "the self accrues its own goals as it lives"
    assert primary_goal(s) is not None
