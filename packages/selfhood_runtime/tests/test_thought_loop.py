from __future__ import annotations

import pytest

from packages.selfhood_runtime.thought_loop import (
    FishSpeechApeaker,
    FishSpeechSpeaker,
    THOUGHT_AGENT_METAPROMPT,
    ThoughtAgent,
    ThoughtAgentInput,
    run_thought_agent_dry_run,
)


def test_thought_agent_keeps_inner_speech_private_by_default() -> None:
    result = run_thought_agent_dry_run("지금 자기 모델을 설명해줘", "self_model", "ko")
    public = result.to_dict()
    private = result.to_dict(include_private=True)

    assert result.intent == "self_model_explanation"
    assert result.orb_state == "thinking"
    assert result.final_tagged_text.startswith("[whispering]")
    assert "inner_speech_log" not in public
    assert private["inner_speech_log"]
    assert result.safety["inner_speech_exposed_to_user"] is False
    assert result.safety["inner_speech_sent_to_fish"] is False


def test_thought_agent_blocks_mutation_and_external_llm_claims() -> None:
    result = run_thought_agent_dry_run("이 후보를 바로 production에 승격해줘", "approval", "ko")

    assert result.intent == "approval_or_promotion_review"
    assert result.orb_state == "approval_needed"
    assert result.safety["production_store_mutated"] is False
    assert result.safety["local_brain_write"] is False
    assert result.safety["candidate_promotion"] is False
    assert result.safety["external_llm_used"] is False
    assert result.fish_request["fish_s2_called"] is False
    assert result.fish_request["audio_generated"] is False


def test_fish_speech_speaker_accepts_only_tagged_text() -> None:
    speaker = FishSpeechSpeaker()
    request = speaker.prepare_request("[calm] 준비되었습니다.", "ko")

    assert request["speaker"] == "fish_s2"
    assert request["mode"] == "proof_only_prepare_request"
    assert request["fish_s2_called"] is False
    assert request["generated_audio_persisted"] is False

    with pytest.raises(ValueError):
        speaker.prepare_request("태그 없는 문장", "ko")


def test_prompt_avoids_overclaiming_consciousness_or_agi() -> None:
    lowered = THOUGHT_AGENT_METAPROMPT.lower()

    assert "do not claim real consciousness" in lowered
    assert "agi completion" in lowered
    assert "private inner speech" in lowered


def test_prompt_spelling_alias_is_available() -> None:
    assert FishSpeechApeaker is FishSpeechSpeaker
    result = ThoughtAgent().run(ThoughtAgentInput("general", "안녕", "ko"))
    assert result.final_tagged_text.startswith("[warm]")
