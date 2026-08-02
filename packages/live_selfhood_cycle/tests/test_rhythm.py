from packages.live_selfhood_cycle.models import Need, Observation, RhythmPolicy, RhythmState
from packages.live_selfhood_cycle.rhythm import choose_next_rhythm, derive_rhythm_state


def test_adaptive_rhythm_shortens_delay_for_backlog():
    observation = Observation("o", "candidate_backlog", "attention", "backlog", payload={"count": 8})
    state = derive_rhythm_state([observation], RhythmPolicy(entropy_seed="b"))
    decision = choose_next_rhythm(state, [observation], [Need("n", "promotion_review_needed", "review")], RhythmPolicy(entropy_seed="b"))
    assert decision.next_tick_delay_seconds < 300
    assert decision.should_observe is True


def test_adaptive_rhythm_lengthens_delay_for_resource_pressure():
    observation = Observation("o", "disk_resource", "low", "low disk", "warning", payload={"free_gib": 10})
    state = derive_rhythm_state([observation], RhythmPolicy(entropy_seed="r"))
    decision = choose_next_rhythm(state, [observation], [Need("n", "quality_audit_needed", "disk", "warning")], RhythmPolicy(entropy_seed="r"))
    assert decision.next_mode == "resting"
    assert decision.next_tick_delay_seconds >= 300


def test_same_seed_is_deterministic_and_different_seed_is_safe():
    state = RhythmState("rhythm", "curious", 0.8, 0.9, 0.5, 0.2, 0.0, 0.0, None, 300, "test")
    a = choose_next_rhythm(state, [], [], RhythmPolicy(entropy_seed="same"))
    b = choose_next_rhythm(state, [], [], RhythmPolicy(entropy_seed="same"))
    c = choose_next_rhythm(state, [], [], RhythmPolicy(entropy_seed="other"))
    assert a.to_dict() == b.to_dict()
    assert c.safety_flags["randomness_never_executes_irreversible_actions"] is True
