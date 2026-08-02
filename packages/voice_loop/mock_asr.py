from __future__ import annotations

from typing import Iterable

from packages.voice_loop.asr_adapter import ASRAdapter
from packages.voice_loop.models import TranscriptSegment


class MockASRAdapter(ASRAdapter):
    """Deterministic ASR adapter for tests and proof scenarios."""

    def __init__(self, transcript: str = "아타노르, 지금 상태 알려줘", language: str = "ko-KR") -> None:
        self.transcript = transcript
        self.language = language
        self.loaded = False

    def load(self) -> None:
        self.loaded = True

    def is_available(self) -> bool:
        return True

    def runtime_info(self) -> dict[str, object]:
        return {"adapter": "mock_asr", "available": True, "external_service": False}

    def transcribe_file(self, path: str, target_lang: str) -> list[TranscriptSegment]:
        self.load()
        return [
            TranscriptSegment(
                segment_id="mock_segment_0",
                source_id=path,
                text=self.transcript,
                language=target_lang or self.language,
                start_ms=0,
                end_ms=1200,
                confidence=0.99,
                final=True,
                metadata={"adapter": "mock_asr", "transcript_persisted": False},
            )
        ]

    def transcribe_stream(self, chunks: Iterable[bytes], target_lang: str) -> list[TranscriptSegment]:
        consumed = sum(1 for _ in chunks)
        return [
            TranscriptSegment(
                segment_id="mock_stream_segment_0",
                source_id="mock_stream",
                text=self.transcript,
                language=target_lang or self.language,
                confidence=0.98,
                final=True,
                metadata={"adapter": "mock_asr", "chunks_seen": consumed, "transcript_persisted": False},
            )
        ]
