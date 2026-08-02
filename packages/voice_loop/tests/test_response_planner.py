from __future__ import annotations

from packages.voice_loop.intent import detect_intent
from packages.voice_loop.models import TranscriptSegment
from packages.voice_loop.response_planner import plan_response


def test_status_response_is_safe() -> None:
    intent = detect_intent(TranscriptSegment("t", "s", "아타노르, 지금 상태 알려줘", "ko-KR"))
    plan = plan_response(intent)
    assert plan.can_speak is True
    assert plan.writes_local_brain is False
    assert plan.writes_cloud_brain is False
    assert plan.metadata["external_llm_used"] is False


def test_memory_response_requires_approval_and_blocks_write() -> None:
    intent = detect_intent(TranscriptSegment("t", "s", "remember this", "en-US"))
    plan = plan_response(intent, language="en-US")
    assert plan.requires_user_review is True
    assert plan.writes_local_brain is False
    assert "승인" in plan.text or "approval" in plan.metadata
