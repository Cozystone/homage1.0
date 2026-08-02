from __future__ import annotations

from packages.voice_loop.models import TranscriptSegment, VoiceIntent


def _normalized(text: str) -> str:
    return " ".join(text.strip().lower().split())


def detect_intent(segment: TranscriptSegment) -> VoiceIntent:
    """Classify voice intent with deterministic Korean/English rules only."""

    text = _normalized(segment.text)
    metadata = {"source_text": segment.text, "llm_used": False}
    if not text:
        return VoiceIntent("intent_ignore_noise", segment.segment_id, "ignore_noise", 1.0, True, metadata)
    if any(token in text for token in ["그만 말해", "stop talking", "stop speaking", "stop"]):
        return VoiceIntent("intent_stop_speaking", segment.segment_id, "stop_speaking", 0.98, True, metadata)
    if any(token in text for token in ["잠깐", "wait", "hold on", "interrupt"]):
        return VoiceIntent("intent_interruption", segment.segment_id, "interruption", 0.9, True, metadata)
    if any(token in text for token in ["뭘 배웠", "morning brief", "overnight", "아침 브리프"]):
        return VoiceIntent("intent_morning_brief", segment.segment_id, "morning_brief_request", 0.92, True, metadata)
    if any(token in text for token in ["지금 상태", "상태 알려", "status", "current state"]):
        return VoiceIntent("intent_autonomy_status", segment.segment_id, "autonomy_status_request", 0.94, True, metadata)
    if any(token in text for token in ["기억해", "remember this", "저장해", "외워"]):
        return VoiceIntent("intent_memory_command", segment.segment_id, "command", 0.87, True, metadata | {"memory_write_blocked": True})
    if text.startswith("아타노르") or text.startswith("atanor"):
        return VoiceIntent("intent_question", segment.segment_id, "ask_question", 0.75, True, metadata)
    return VoiceIntent("intent_question", segment.segment_id, "ask_question", 0.55, True, metadata)
