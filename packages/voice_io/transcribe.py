"""Local speech-to-text — voice I/O v0 (roadmap ③).

LOCAL-FIRST BY CONSTRUCTION: faster-whisper (CTranslate2 Whisper) runs on this
machine's CPU; audio never leaves the device. Whisper is a speech RECOGNITION
model, not a generative LLM in the answer path — the No-LLM rule governs how
answers are produced, and transcription only produces the user's own words.
(The browser's SpeechRecognition API is explicitly NOT used: Chrome routes it
through Google's cloud, which breaks the local-first contract.)

The model loads lazily on first use (downloads once to the local HF cache) and
is cached per (model, compute) for the process lifetime. Failure is honest:
whisper_available() lets callers say "STT engine not installed" instead of
pretending to hear."""
from __future__ import annotations

import io
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any

_MODEL_LOCK = threading.Lock()
_MODELS: dict[tuple[str, str], Any] = {}

DEFAULT_MODEL = os.environ.get("ATANOR_WHISPER_MODEL", "base")
DEFAULT_COMPUTE = os.environ.get("ATANOR_WHISPER_COMPUTE", "int8")


@dataclass(frozen=True)
class TranscribeResult:
    text: str
    language: str
    language_probability: float
    duration_ms: float
    model: str
    local_only: bool = True          # architecture fact, stated on every result

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _model(name: str, compute: str) -> Any:
    key = (name, compute)
    with _MODEL_LOCK:
        if key not in _MODELS:
            from faster_whisper import WhisperModel

            _MODELS[key] = WhisperModel(name, device="cpu", compute_type=compute)
        return _MODELS[key]


def transcribe_wav_bytes(data: bytes, *, model: str = DEFAULT_MODEL,
                         compute: str = DEFAULT_COMPUTE,
                         language: str | None = None) -> TranscribeResult:
    """Transcribe an audio container (wav/webm/ogg — ffmpeg-decodable) held in memory.
    Silence yields empty text, never an invented sentence."""
    started = time.perf_counter()
    segments, info = _model(model, compute).transcribe(
        io.BytesIO(data), language=language, vad_filter=True)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    return TranscribeResult(
        text=text,
        language=str(info.language or ""),
        language_probability=float(info.language_probability or 0.0),
        duration_ms=(time.perf_counter() - started) * 1000.0,
        model=f"faster-whisper/{model}/{compute}",
    )
