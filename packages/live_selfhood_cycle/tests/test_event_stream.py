from packages.live_selfhood_cycle.event_stream import InMemoryLifeEventStream


def test_event_stream_is_in_memory():
    stream = InMemoryLifeEventStream()
    stream.emit("life.tick", {"tick": "one"})
    stream.emit("life.brief_ready", {"brief": "ready"})
    assert [event.event_type for event in stream.list_events()] == ["life.tick", "life.brief_ready"]
