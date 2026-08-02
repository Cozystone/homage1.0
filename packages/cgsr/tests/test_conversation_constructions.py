from __future__ import annotations

from packages.cgsr.cgsr.conversation_constructions import all_conversation_frames, frames_for_act


def test_conversation_frames_have_safety_constraints() -> None:
    frames = all_conversation_frames()

    assert frames
    for frame in frames:
        assert "external_llm=false" in frame.safety_constraints
        assert "external_sllm=false" in frame.safety_constraints
        assert "rule_based_answer_used=false" in frame.safety_constraints
        assert "local_brain_write=false" in frame.safety_constraints
        assert "production_store_mutated=false" in frame.safety_constraints


def test_frames_for_act_returns_only_matching_act() -> None:
    frames = frames_for_act("voice_question")

    assert frames
    assert {frame.act for frame in frames} == {"voice_question"}
