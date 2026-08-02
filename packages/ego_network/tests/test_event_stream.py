from __future__ import annotations

from packages.ego_network.event_stream import EgoEvent, InMemoryEgoEventStream, utc_now


def test_event_stream_emits_and_consumes_morning_gift() -> None:
    stream = InMemoryEgoEventStream()
    event = EgoEvent("e", "ego.morning_gift", utc_now(), "Morning gift", {}, requires_user_action=True)
    stream.append_event(event)
    assert stream.list_events("ego.morning_gift")[0].requires_user_action is True
    consumed = stream.consume_events("ego.morning_gift")
    assert consumed == [event]
    assert stream.list_events() == []
