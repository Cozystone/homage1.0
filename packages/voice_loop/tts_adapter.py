from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from packages.voice_loop.models import VoiceOutputEvent


class TTSRuntimeUnavailable(RuntimeError):
    """Raised when a local TTS runtime is not installed or cannot be loaded."""


class TTSAdapter(ABC):
    """Base interface for local TTS adapters."""

    @abstractmethod
    def load(self) -> None:
        """Load the local TTS runtime."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return whether the local runtime is available."""

    @abstractmethod
    def runtime_info(self) -> dict[str, object]:
        """Return bounded runtime metadata."""

    @abstractmethod
    def synthesize(self, text: str, language: str, style: str) -> VoiceOutputEvent:
        """Synthesize a response without persisting generated audio in proof mode."""

    @abstractmethod
    def synthesize_stream(self, text: str, language: str, style: str) -> Iterable[VoiceOutputEvent]:
        """Yield streaming synthesis events when supported."""
