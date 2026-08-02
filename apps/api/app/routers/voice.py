"""Voice I/O v0 — local STT endpoint (roadmap ③).

POST /api/voice/transcribe  (multipart file OR raw body) -> {text, language, ...}
GET  /api/voice/status      -> engine availability, honestly reported.

TTS v0 lives client-side on speechSynthesis (the OS's own local voices); the
backend adds nothing there yet and says so in /status."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from packages.voice_io import transcribe_wav_bytes, whisper_available

router = APIRouter(prefix="/api/voice", tags=["voice"])

_MAX_AUDIO_BYTES = 20 * 1024 * 1024   # ~10 min of 16k mono wav; bounded on purpose


@router.get("/status")
def voice_status() -> dict[str, Any]:
    return {
        "stt_available": whisper_available(),
        "stt_engine": "faster-whisper (local CPU)" if whisper_available() else None,
        "tts": "client speechSynthesis (OS local voices) — no backend TTS yet",
        "audio_leaves_device": False,
    }


@router.post("/transcribe")
async def voice_transcribe(file: UploadFile = File(...)) -> dict[str, Any]:
    if not whisper_available():
        raise HTTPException(status_code=503, detail="local STT engine not installed (faster-whisper)")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty audio")
    if len(data) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="audio too large (20MB bound)")
    try:
        return transcribe_wav_bytes(data).to_dict()
    except Exception as exc:  # decode failures are the client's honest 400, not a 500
        raise HTTPException(status_code=400, detail=f"could not decode audio: {exc}") from exc
