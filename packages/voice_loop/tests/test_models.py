from __future__ import annotations

import pytest

from packages.voice_loop.models import AudioSource, VoiceLoopConfig, VoiceOutputEvent, VoiceResponsePlan


def test_audio_source_blocks_microphone_consent_in_proof_mode() -> None:
    with pytest.raises(ValueError):
        AudioSource("mic", "microphone_disabled", user_consented=True)


def test_config_defaults_are_safe() -> None:
    config = VoiceLoopConfig()
    assert config.allow_microphone is False
    assert config.allow_voice_clone is False
    assert config.write_local_brain is False
    assert config.write_cloud_brain is False
    assert config.require_user_review is True


def test_voice_plan_rejects_memory_writes() -> None:
    with pytest.raises(ValueError):
        VoiceResponsePlan("p", "i", "text", "ko-KR", "calm", True, True, writes_local_brain=True)
    with pytest.raises(ValueError):
        VoiceResponsePlan("p", "i", "text", "ko-KR", "calm", True, True, writes_cloud_brain=True)


def test_output_event_rejects_audio_persistence() -> None:
    with pytest.raises(ValueError):
        VoiceOutputEvent("o", "text", "ko-KR", "mock", generated_audio_persisted=True)
