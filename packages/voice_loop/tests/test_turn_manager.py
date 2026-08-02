from __future__ import annotations

from packages.voice_loop.models import TranscriptSegment
from packages.voice_loop.turn_manager import TurnManager


def test_turn_manager_handles_final_transcript() -> None:
    manager = TurnManager()
    manager.start_listening()
    intent = manager.handle_transcript(TranscriptSegment("t", "s", "아타노르, 지금 상태 알려줘", "ko-KR"))
    assert intent is not None
    assert intent.intent_type == "autonomy_status_request"
    assert manager.state == "thinking"


def test_turn_manager_handles_stop_barge_in() -> None:
    manager = TurnManager()
    manager.start_speaking()
    intent = manager.handle_transcript(TranscriptSegment("t", "s", "그만 말해", "ko-KR"))
    assert intent is not None
    assert intent.intent_type == "stop_speaking"
    assert manager.state == "interrupted"
