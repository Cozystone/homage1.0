from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.routers import dual_brain
from packages.voice_loop.local_tts import LocalTTSResult, local_voice_audio_dir


def _fake_voice_synthesis(
    text: str,
    *,
    language: str = "ko",
    rate: int = 0,
    volume: int = 100,
    sentence_gap_ms: int = 220,
) -> LocalTTSResult:
    root = local_voice_audio_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "atanor_voice_11111111111111111111111111111111.wav"
    path.write_bytes(b"RIFF$\x00\x00\x00WAVEfmt ")
    return LocalTTSResult(engine="windows_sapi", audio_path=path, audio_url=f"/api/voice-loop/audio/{path.name}", rate=rate, volume=volume)


def test_chat_atanor_returns_clean_answer_and_compact_trace(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={"question": "GraphRAG가 근거 문서를 어떻게 사용해서 답변을 검증하나요?", "language": "ko", "include_trace": True},
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert "Local Brain" not in result["answer"]
    assert "Cloud Brain" not in result["answer"]
    assert result["compact_trace"]["working_memory"]["local_brain_write"] is False
    assert result["answer_engine"]["external_llm"] is False
    assert result["answer_engine"]["external_sllm"] is False


def test_dashboard_conversation_voice_output_is_audio_truthful(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dual_brain, "synthesize_windows_sapi", _fake_voice_synthesis)
    client = TestClient(app)

    response = client.post(
        "/api/chat/atanor",
        json={"question": "안녕", "language": "ko", "mode": "conversation", "brain_mode": "conversation"},
    )

    assert response.status_code == 200
    result = response.json()["result"]
    voice_output = result["voice_output"]
    assert voice_output["requested"] is True
    assert voice_output["enabled"] is True
    assert voice_output["selected_engine"] in {"fallback", "fish_2", "fish_1_5"}
    assert voice_output["tts_engine"] == "windows_sapi"
    assert voice_output["audio_available"] is True
    assert voice_output["audio_url"] == "/api/voice-loop/audio/atanor_voice_11111111111111111111111111111111.wav"
    assert voice_output["error_reason"] is None
    assert voice_output["text_fallback"] is True
    assert voice_output["microphone_enabled"] is False
    assert voice_output["always_listening_enabled"] is False
    assert voice_output["raw_voice_saved"] is False
    assert voice_output["external_service"] is False
    assert voice_output["generated_audio_persisted"] is False
    assert voice_output["estimated_duration_ms"] >= 900
    assert voice_output["speech_sync_source"] == "estimated_from_text_length"
    assert voice_output["fallback_prosody_applied"] is True
    assert voice_output["fallback_prosody_source"] == "neural_emotion_voice_controls"
    assert -4 <= voice_output["local_tts_rate"] <= 0
    assert 58 <= voice_output["local_tts_volume"] <= 88
    assert 160 <= voice_output["local_tts_sentence_gap_ms"] <= 340
    controls = voice_output["neural_emotion_voice_controls"]
    assert controls["audio_available"] is True
    assert controls["real_emotion_claim"] is False
    assert controls["fallback_voice_style"] == "soft_warm_local_speech_with_breathing_pauses"
    assert controls["fallback_delivery"] == "short_phrase_breathing_ssml"
    assert controls["emotion_hint"] in {"calm", "warm", "curious", "cautious"}
    assert result["local_brain_write"] is False

    audio_response = client.get(voice_output["audio_url"])
    assert audio_response.status_code == 200
    assert audio_response.headers["content-type"].startswith("audio/wav")
