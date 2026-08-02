from __future__ import annotations

from collections.abc import Iterable

from packages.voice_loop.models import VoiceOutputEvent
from packages.voice_loop.runtime_availability import check_fish_runtime
from packages.voice_loop.tts_adapter import TTSAdapter, TTSRuntimeUnavailable


class FishTTSAdapter(TTSAdapter):
    """Local Fish Speech adapter shell with safe fallback semantics.

    The adapter intentionally does not download weights, clone voices, or
    persist generated audio. Runtime-specific wiring can be added only after
    explicit model installation and voice-profile consent gates exist.
    """

    def __init__(self, engine: str = "fish_2", allow_voice_clone: bool = False) -> None:
        if allow_voice_clone:
            raise ValueError("voice cloning is disabled without explicit future consent")
        if engine not in {"fish_2", "fish_1_5"}:
            raise ValueError("engine must be fish_2 or fish_1_5")
        self.engine = engine
        self._loaded = False
        self._unavailable_reason: str | None = None

    def load(self) -> None:
        availability = check_fish_runtime(self.engine)
        if not availability.available:
            self._unavailable_reason = availability.reason or availability.status
            raise TTSRuntimeUnavailable(self._unavailable_reason)
        self._loaded = True

    def is_available(self) -> bool:
        if self._loaded:
            return True
        try:
            self.load()
        except TTSRuntimeUnavailable:
            return False
        return True

    def runtime_info(self) -> dict[str, object]:
        return {
            "adapter": "fish_tts",
            "engine": self.engine,
            "available": self._loaded,
            "unavailable_reason": self._unavailable_reason,
            "voice_clone_enabled": False,
            "audio_output_available": False,
            "generated_audio_persisted": False,
            "external_service": False,
        }

    def synthesize(self, text: str, language: str, style: str) -> VoiceOutputEvent:
        if not self.is_available():
            raise TTSRuntimeUnavailable(self._unavailable_reason or "Fish runtime unavailable")
        # Fish packages and model path are available, but the concrete synthesis
        # call is intentionally not guessed here. A future adapter must wire the
        # installed Fish API explicitly and return a browser-playable temp URL.
        raise TTSRuntimeUnavailable("Fish runtime configured, but synthesis adapter is not wired")

    def synthesize_stream(self, text: str, language: str, style: str) -> Iterable[VoiceOutputEvent]:
        yield self.synthesize(text, language, style)
