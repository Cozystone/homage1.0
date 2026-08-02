from __future__ import annotations

import pytest

from packages.voice_loop.local_tts import (
    LocalTTSUnavailable,
    is_valid_voice_audio_name,
    synthesize_windows_sapi,
    voice_audio_path,
    windows_sapi_ssml,
)


def test_voice_audio_filename_validation() -> None:
    assert is_valid_voice_audio_name("atanor_voice_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.wav")
    assert not is_valid_voice_audio_name("../secret.wav")
    assert not is_valid_voice_audio_name("atanor_voice_short.wav")


def test_voice_audio_path_rejects_path_traversal() -> None:
    with pytest.raises(ValueError):
        voice_audio_path("../secret.wav")


def test_windows_sapi_fallback_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("ATANOR_ENABLE_WINDOWS_TTS_FALLBACK", "0")
    with pytest.raises(LocalTTSUnavailable):
        synthesize_windows_sapi("hello", language="en")


def test_windows_sapi_ssml_adds_breathing_breaks() -> None:
    ssml = windows_sapi_ssml("안녕. 오늘은 천천히 말할게.", language="ko", rate=-4, volume=74, sentence_gap_ms=260)

    assert 'xml:lang="ko-KR"' in ssml
    assert 'rate="medium"' in ssml
    assert '<break time="260ms"/>' in ssml
