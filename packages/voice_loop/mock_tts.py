from __future__ import annotations

from collections.abc import Iterable

from packages.voice_loop.models import VoiceOutputEvent
from packages.voice_loop.tts_adapter import TTSAdapter


class MockTTSAdapter(TTSAdapter):
    """Deterministic TTS adapter that never writes generated audio."""

    def __init__(self, engine: str = "mock") -> None:
        self.engine = engine
        self.loaded = False

    def load(self) -> None:
        self.loaded = True

    def is_available(self) -> bool:
        return True

    def runtime_info(self) -> dict[str, object]:
        return {"adapter": "mock_tts", "available": True, "generated_audio_persisted": False}

    def synthesize(self, text: str, language: str, style: str) -> VoiceOutputEvent:
        self.load()
        return VoiceOutputEvent(
            event_id="mock_tts_event",
            text=text,
            language=language,
            tts_engine=self.engine,
            audio_path=None,
            streaming=False,
            ttfa_ms=0.0,
            rtf=0.0,
            generated_audio_persisted=False,
            requires_user_review=True,
            metadata={"style": style, "adapter": "mock_tts"},
        )

    def synthesize_stream(self, text: str, language: str, style: str) -> Iterable[VoiceOutputEvent]:
        yield self.synthesize(text, language, style)
