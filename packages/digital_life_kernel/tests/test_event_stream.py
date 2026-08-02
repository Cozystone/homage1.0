from __future__ import annotations

from packages.digital_life_kernel.event_stream import InMemoryLifeEventStream


def test_event_stream_emits_ordered_events():
    stream = InMemoryLifeEventStream()
    first = stream.emit("life.signal_detected", "Signal", {"x": 1})
    second = stream.emit("life.action_proposed", "Action", {"y": 2})

    assert first.event_id == "life_event_1"
    assert second.event_id == "life_event_2"
    assert len(stream.list_events()) == 2
