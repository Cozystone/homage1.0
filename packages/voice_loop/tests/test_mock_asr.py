from __future__ import annotations

from packages.voice_loop.mock_asr import MockASRAdapter


def test_mock_asr_transcript_is_deterministic() -> None:
    adapter = MockASRAdapter("아타노르, 지금 상태 알려줘")
    first = adapter.transcribe_file("fixture.wav", "ko-KR")[0]
    second = adapter.transcribe_file("fixture.wav", "ko-KR")[0]
    assert first.text == second.text
    assert first.final is True
    assert first.metadata["transcript_persisted"] is False


def test_mock_asr_stream_consumes_provided_chunks_only() -> None:
    adapter = MockASRAdapter("hello")
    segment = adapter.transcribe_stream([b"a", b"b"], "en-US")[0]
    assert segment.metadata["chunks_seen"] == 2
    assert segment.source_id == "mock_stream"
