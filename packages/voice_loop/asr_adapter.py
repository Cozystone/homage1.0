from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from packages.voice_loop.models import TranscriptSegment


class ModelRuntimeUnavailable(RuntimeError):
    """Raised when a local proof runtime is not installed or cannot be loaded."""


class ASRAdapter(ABC):
    """Base interface for local ASR adapters.

    Implementations must not open a microphone, call an external service, or
    persist transcripts unless a future explicit consent path is added.
    """

    @abstractmethod
    def load(self) -> None:
        """Load the local ASR runtime."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return whether the local runtime is available."""

    @abstractmethod
    def runtime_info(self) -> dict[str, object]:
        """Return bounded runtime metadata."""

    @abstractmethod
    def transcribe_file(self, path: str, target_lang: str) -> list[TranscriptSegment]:
        """Transcribe a local file into transcript segments."""

    @abstractmethod
    def transcribe_stream(self, chunks: Iterable[bytes], target_lang: str) -> list[TranscriptSegment]:
        """Transcribe already-provided audio chunks without microphone access."""
