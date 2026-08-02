from __future__ import annotations

from packages.voice_loop.intent import detect_intent
from packages.voice_loop.models import TranscriptSegment


def _segment(text: str, language: str = "ko-KR") -> TranscriptSegment:
    return TranscriptSegment("t", "s", text, language)


def test_korean_intent_detection() -> None:
    assert detect_intent(_segment("아타노르, 지금 상태 알려줘")).intent_type == "autonomy_status_request"
    assert detect_intent(_segment("밤새 뭘 배웠어?")).intent_type == "morning_brief_request"
    assert detect_intent(_segment("그만 말해")).intent_type == "stop_speaking"
    assert detect_intent(_segment("잠깐")).intent_type == "interruption"


def test_english_intent_detection() -> None:
    assert detect_intent(_segment("ATANOR, what did you learn overnight?", "en-US")).intent_type == "morning_brief_request"
    assert detect_intent(_segment("Stop talking", "en-US")).intent_type == "stop_speaking"


def test_memory_command_requires_review() -> None:
    intent = detect_intent(_segment("이거 기억해줘"))
    assert intent.intent_type == "command"
    assert intent.requires_user_review is True
    assert intent.metadata["memory_write_blocked"] is True


def test_empty_noise_is_ignored() -> None:
    assert detect_intent(_segment("   ")).intent_type == "ignore_noise"
