from __future__ import annotations

from packages.voice_loop.event_bridge import process_transcript
from packages.voice_loop.mock_tts import MockTTSAdapter
from packages.voice_loop.models import TranscriptSegment


def test_event_bridge_never_writes_memory_or_candidate() -> None:
    result = process_transcript(TranscriptSegment("t", "s", "이거 기억해줘", "ko-KR"), MockTTSAdapter())
    assert result.writes_local_brain is False
    assert result.writes_cloud_brain is False
    assert result.candidate_ingestion is False
    assert result.plan.writes_local_brain is False
    assert result.plan.writes_cloud_brain is False
    assert result.requires_user_review is True


def test_event_bridge_uses_autonomy_route_for_status() -> None:
    result = process_transcript(TranscriptSegment("t", "s", "지금 상태 알려줘", "ko-KR"), MockTTSAdapter())
    assert result.route_target == "autonomy_kernel"
    assert result.output is not None
    assert result.output.generated_audio_persisted is False
