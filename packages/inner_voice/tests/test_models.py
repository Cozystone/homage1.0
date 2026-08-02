from __future__ import annotations

from packages.inner_voice.models import InnerVoiceFrame, InnerVoiceLog, inner_voice_safety_flags, utc_now


def test_log_bounds_and_product_redaction() -> None:
    log = InnerVoiceLog(max_entries=2)
    for index in range(3):
        log.append(
            InnerVoiceFrame(
                frame_id=f"f{index}",
                source_event_id="test",
                timestamp=utc_now(),
                mode="lab_visible",
                goal="goal",
                felt_state_label="steady",
                tension="balance",
                candidate_actions=["observe"],
                chosen_action="answer",
                blocked_actions=["Local Brain 직접 쓰기"],
                uncertainty="낮음",
                next_intent="safe next",
                monologue_text="지금은 steady 상태를 유지하고 있습니다.",
            )
        )

    assert len(log.frames) == 2
    assert log.frames[0].frame_id == "f1"
    assert log.redact_for_product()["raw_inner_voice_hidden"] is True
    assert inner_voice_safety_flags()["raw_hidden_cot_claim"] is False
