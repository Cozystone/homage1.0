"""Voice I/O v0 — local STT endpoint contract: honest availability, bounded input,
silence never becomes an invented sentence."""
from __future__ import annotations

import io
import math
import struct
import wave

import pytest
from fastapi.testclient import TestClient

from app.main import app
from packages.voice_io import whisper_available

client = TestClient(app)


def _wav_bytes(seconds: float = 1.0, freq: float = 0.0, rate: int = 16000) -> bytes:
    """Mono 16-bit wav: silence (freq=0) or a sine tone — no speech either way."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(seconds * rate)
        frames = b"".join(
            struct.pack("<h", int(6000 * math.sin(2 * math.pi * freq * i / rate)) if freq else 0)
            for i in range(n))
        w.writeframes(frames)
    return buf.getvalue()


def test_status_reports_local_engine_honestly():
    body = client.get("/api/voice/status").json()
    assert body["stt_available"] is whisper_available()
    assert body["audio_leaves_device"] is False


def test_empty_audio_is_a_400():
    res = client.post("/api/voice/transcribe", files={"file": ("a.wav", b"", "audio/wav")})
    assert res.status_code in (400, 503)


@pytest.mark.skipif(not whisper_available(), reason="faster-whisper not installed")
def test_silence_transcribes_to_empty_text_not_invention():
    res = client.post("/api/voice/transcribe",
                      files={"file": ("s.wav", _wav_bytes(1.2), "audio/wav")})
    assert res.status_code == 200
    body = res.json()
    assert body["text"] == ""            # VAD hears nothing; nothing is fabricated
    assert body["local_only"] is True
    assert body["model"].startswith("faster-whisper/")
