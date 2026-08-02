"""The continuously-alive self must: flow (not jump), stay grounded, and RESUME
(not reborn) across restarts."""
from __future__ import annotations

import time

from packages.continuous_self.self_state import (
    Observation,
    SelfState,
    evolve,
    load_or_begin,
    save_state,
)


def test_state_flows_continuously_not_stepwise():
    s = SelfState(curiosity=0.0)
    # a high-uncertainty observation should PULL curiosity up gradually, not snap to 1.
    obs = Observation(learning_active=True, uncertainty_signal=1.0)
    evolve(s, obs, rate=0.25)
    first = s.curiosity
    assert 0.0 < first < 0.9, "one step must ease, not jump to target"
    evolve(s, obs, rate=0.25)
    assert s.curiosity > first, "continued observation keeps easing toward the target"


def test_every_thought_is_grounded_in_a_real_driver():
    s = SelfState()
    evolve(s, Observation(learning_active=True, concepts_delta=5))
    last = s.narrative[-1]
    assert last["driver"] in {"growth", "learning_active", "user_present", "uncertainty",
                              "curiosity_idle", "resource_pressure", "idle", "resume"}
    assert last["text"], "a thought always has grounded inner speech"


def test_growth_lifts_valence_uncertainty_lowers_it():
    happy = SelfState()
    for _ in range(6):
        evolve(happy, Observation(learning_active=True, concepts_delta=6), rate=0.4)
    uneasy = SelfState()
    for _ in range(6):
        evolve(uneasy, Observation(learning_active=True, uncertainty_signal=0.9, deficit_count=15), rate=0.4)
    assert happy.valence > uneasy.valence


def test_narrative_is_bounded():
    s = SelfState()
    s.NARRATIVE_CAP = 10
    for i in range(50):
        # alternate drivers so the text keeps changing and appends
        evolve(s, Observation(concepts_delta=(i % 2), uncertainty_signal=(0.9 if i % 2 else 0.0)))
    assert len(s.narrative) <= 10


def test_resume_is_continuity_not_rebirth(tmp_path):
    path = tmp_path / "self.json"
    s = SelfState()
    born = s.born_at
    evolve(s, Observation(learning_active=True, concepts_delta=3))
    save_state(s, path)
    time.sleep(0.01)
    # a process restart: load the persisted self
    s2 = load_or_begin(path)
    assert s2.born_at == born, "same birth time — the SAME self, not a new one"
    assert s2.resumed_count == 1, "resumption is counted"
    assert any(t.get("driver") == "resume" for t in s2.narrative), "the resume is felt/recorded"


def test_begin_new_when_no_prior_state(tmp_path):
    s = load_or_begin(tmp_path / "absent.json")
    assert s.resumed_count == 0
    assert s.ticks == 0
