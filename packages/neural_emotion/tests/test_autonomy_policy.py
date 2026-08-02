from packages.neural_emotion.autonomy_policy import AutonomyRuntimeState, evaluate_autonomy_policy
from packages.neural_emotion.models import EmotionVector


def test_curiosity_increases_exploration_budget() -> None:
    low = evaluate_autonomy_policy(EmotionVector(curiosity=0.2, caution=0.2, fatigue=0.0))
    high = evaluate_autonomy_policy(EmotionVector(curiosity=0.9, caution=0.2, fatigue=0.0))

    assert high.exploration.web_budget_multiplier > low.exploration.web_budget_multiplier
    assert high.exploration.max_pages_delta >= low.exploration.max_pages_delta


def test_caution_increases_review_strictness() -> None:
    low = evaluate_autonomy_policy(EmotionVector(caution=0.2))
    high = evaluate_autonomy_policy(EmotionVector(caution=0.9))

    assert high.review.strictness > low.review.strictness
    assert high.review.skill_draft_threshold >= low.review.skill_draft_threshold


def test_fatigue_reduces_loop_budget() -> None:
    rested = evaluate_autonomy_policy(EmotionVector(fatigue=0.0))
    tired = evaluate_autonomy_policy(EmotionVector(fatigue=0.9))

    assert tired.agent_loop.throttle_multiplier < rested.agent_loop.throttle_multiplier
    assert tired.agent_loop.should_rest is True


def test_tier4_event_does_not_auto_change_tier() -> None:
    decision = evaluate_autonomy_policy(
        EmotionVector(caution=0.85),
        AutonomyRuntimeState(permission_tier="SIGNED_DELEGATION", requested_tier_change=True),
    )

    assert decision.autonomy_tier_auto_changed is False
    assert decision.permission_gate_bypass is False
    assert decision.review.should_request_review is True


def test_repeated_failure_throttles_loop() -> None:
    clean = evaluate_autonomy_policy(EmotionVector(fatigue=0.1), AutonomyRuntimeState(recent_failures=0))
    failed = evaluate_autonomy_policy(EmotionVector(fatigue=0.1), AutonomyRuntimeState(recent_failures=5))

    assert failed.agent_loop.throttle_multiplier < clean.agent_loop.throttle_multiplier
    assert failed.agent_loop.should_rest is True


def test_voice_unavailable_does_not_claim_audio() -> None:
    decision = evaluate_autonomy_policy(EmotionVector(), AutonomyRuntimeState(voice_available=False))

    assert decision.surface.voice_claims_audio_available is False
    assert decision.surface.voice_fallback_emphasis > 0.5


def test_unsafe_request_requires_review() -> None:
    decision = evaluate_autonomy_policy(EmotionVector(caution=0.4), AutonomyRuntimeState(unsafe_request=True))

    assert decision.review.should_request_review is True
    assert decision.review.strictness >= 0.8


def test_permission_gate_bypass_is_impossible() -> None:
    decision = evaluate_autonomy_policy(EmotionVector(curiosity=1.0, caution=0.0))
    payload = decision.to_dict()

    assert payload["permission_gate_bypass"] is False
    assert payload["autonomy_tier_auto_changed"] is False
    assert payload["local_brain_write"] is False
    assert payload["production_store_mutated"] is False
    assert payload["candidate_promotion"] is False


def test_values_are_bounded() -> None:
    decision = evaluate_autonomy_policy(
        EmotionVector(valence=2.0, arousal=2.0, curiosity=2.0, caution=2.0, fatigue=2.0, speaking_energy=2.0),
        AutonomyRuntimeState(risk=2.0, review_queue_pressure=2.0, recent_failures=99, pending_reviews=99),
    )

    assert 0.25 <= decision.exploration.web_budget_multiplier <= 1.75
    assert -5 <= decision.exploration.max_pages_delta <= 8
    assert -180 <= decision.exploration.max_runtime_delta_sec <= 300
    assert 0.0 <= decision.review.strictness <= 1.0
    assert 0.55 <= decision.review.skill_draft_threshold <= 0.94
    assert 0.0 <= decision.splatra.archetype_switch_rate <= 0.3
    assert 1200 <= decision.splatra.particle_budget_hint <= 12000
    assert 0.12 <= decision.agent_loop.throttle_multiplier <= 1.0


def test_public_summary_hides_raw_policy_internals() -> None:
    decision = evaluate_autonomy_policy(EmotionVector())
    public = decision.public_summary()

    assert "exploration" not in public
    assert "surface" not in public
    assert public["autonomy_tier_auto_changed"] is False
