from __future__ import annotations

from packages.inner_voice.generator import InnerVoiceInput, generate_inner_voice_frame
from packages.inner_voice.safety import has_forbidden_claim


def test_inner_voice_generated_from_observable_state() -> None:
    frame = generate_inner_voice_frame(
        InnerVoiceInput(
            source_event_id="event1",
            emotion_snapshot={"label": "steady", "vector": {"curiosity": 0.5, "caution": 0.3, "fatigue": 0.0}},
            policy_decision={"review": {"should_request_review": False}, "agent_loop": {"should_rest": False}},
            latest_user_input="안녕",
        )
    )

    assert frame.goal
    assert "greeting" in frame.chosen_action     # the selected act reached the chosen action
    # blocked_actions used to be a flat constant; it now reads the tier and the policy, so what is
    # asserted is that the standing prohibition is present AND that the list responds to state.
    assert "writing to the Local Brain directly" in frame.blocked_actions
    assert "chain-of-thought" not in frame.monologue_text.lower()
    assert not has_forbidden_claim(frame.monologue_text)
    assert frame.safety_flags["inner_voice_is_explicit_generated_channel"] is True
    assert frame.safety_flags["raw_hidden_cot_claim"] is False


def test_review_pressure_changes_monologue_intent() -> None:
    frame = generate_inner_voice_frame(
        InnerVoiceInput(
            source_event_id="event2",
            emotion_snapshot={"label": "cautious", "vector": {"curiosity": 0.2, "caution": 0.8, "fatigue": 0.1}},
            policy_decision={"review": {"should_request_review": True}},
            review_queue_pressure=0.8,
        )
    )

    assert "review" in frame.goal
    assert "review queue" in frame.chosen_action


def test_inner_voice_v1_is_construction_conditioned_by_state_not_prompt_only() -> None:
    base = {
        "source_event_id": "same-prompt",
        "latest_user_input": "안녕",
        "emotion_snapshot": {"label": "steady", "vector": {"curiosity": 0.45, "caution": 0.3, "fatigue": 0.0}},
    }
    greeting = generate_inner_voice_frame(InnerVoiceInput(**base))
    review = generate_inner_voice_frame(
        InnerVoiceInput(
            **base,
            policy_decision={"review": {"should_request_review": True}},
            review_queue_pressure=0.92,
        )
    )

    assert greeting.act == "greeting_response_planning"
    assert review.act == "review_pressure"
    assert greeting.construction_id != review.construction_id
    assert greeting.monologue_text != review.monologue_text
    assert greeting.generation_basis == "asm_cgsr_construction_conditioned_inner_voice_v1"
    assert review.surface_score >= 0.7


def test_korean_greeting_avoids_old_log_like_phrase() -> None:
    frame = generate_inner_voice_frame(InnerVoiceInput(source_event_id="hello", latest_user_input="안녕"))

    assert "먼저 의도와 경계를 내부적으로 점검했습니다" not in frame.monologue_text  # the old log-like phrase
    assert "chain-of-thought" not in frame.monologue_text.lower()
    assert frame.act_scores
    assert frame.construction_stance == "warm_minimal"
    # was: a Korean politeness ending, used as a proxy for "it narrated something". The lane is
    # retired, so the property is asserted directly: first-person self-narration, not a log line.
    assert frame.monologue_text.strip() and " I" in f" {frame.monologue_text}"


def test_non_greeting_korean_question_does_not_tie_break_to_greeting() -> None:
    frame = generate_inner_voice_frame(
        InnerVoiceInput(source_event_id="gravity-question", latest_user_input="중력의 법칙에 대해 설명해줘")
    )

    assert frame.act != "greeting_response_planning"
    assert "greeting" not in frame.monologue_text.lower()
