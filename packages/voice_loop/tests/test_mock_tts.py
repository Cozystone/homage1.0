from __future__ import annotations

from packages.voice_loop.mock_tts import MockTTSAdapter


def test_mock_tts_output_is_deterministic_and_not_persisted() -> None:
    adapter = MockTTSAdapter()
    event = adapter.synthesize("안녕하세요", "ko-KR", "calm")
    assert event.tts_engine == "mock"
    assert event.audio_path is None
    assert event.generated_audio_persisted is False
    assert event.requires_user_review is True
