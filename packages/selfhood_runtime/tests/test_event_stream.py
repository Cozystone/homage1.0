from __future__ import annotations

from packages.selfhood_runtime.event_stream import InMemorySelfhoodEventStream


def test_event_stream_is_in_memory() -> None:
    stream = InMemorySelfhoodEventStream()
    stream.append("observe", "Observed")
    assert stream.list_events()[0].event_type == "observe"
    assert stream.to_dicts()[0]["message"] == "Observed"
