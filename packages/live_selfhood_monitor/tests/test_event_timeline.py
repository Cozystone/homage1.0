from packages.live_selfhood_monitor.event_timeline import append_life_event, group_events_by_type, last_event_of_type, timeline_summary
from packages.live_selfhood_monitor.heartbeat import make_heartbeat_event
from packages.live_selfhood_monitor.models import LifeSignEvent


def test_timeline_helpers() -> None:
    events = [make_heartbeat_event("2026-01-01T00:00:00Z")]
    tick = LifeSignEvent("tick-1", "2026-01-01T00:00:01Z", "tick", "tick", {"tick_id": "t1"})
    events = append_life_event(events, tick)
    grouped = group_events_by_type(events)
    assert len(grouped["heartbeat"]) == 1
    assert last_event_of_type(events, "tick") == tick
    assert timeline_summary(events)["tick_count"] == 1
