from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from packages.voice_loop.intent import detect_intent
from packages.voice_loop.models import TranscriptSegment, VoiceIntent


TurnState = Literal["listening", "user_speaking", "thinking", "speaking", "interrupted", "idle"]


@dataclass
class TurnManager:
    """Deterministic transcript-driven turn manager.

    It never opens a microphone. Callers feed transcript segments explicitly.
    """

    silence_timeout_ms: int = 900
    state: TurnState = "idle"

    def start_listening(self) -> None:
        self.state = "listening"

    def start_speaking(self) -> None:
        self.state = "speaking"

    def handle_transcript(self, segment: TranscriptSegment) -> VoiceIntent | None:
        if not segment.text.strip():
            self.state = "listening"
            return detect_intent(segment)
        self.state = "thinking" if segment.final else "user_speaking"
        intent = detect_intent(segment)
        if intent.intent_type in {"stop_speaking", "interruption"}:
            self.state = "interrupted"
        elif segment.final:
            self.state = "thinking"
        return intent

    def finish_response(self) -> None:
        self.state = "idle"
