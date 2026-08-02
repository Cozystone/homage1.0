from datetime import datetime, timedelta, timezone

from packages.live_selfhood_monitor.heartbeat import classify_alive_status, heartbeat_is_stale, make_heartbeat_event
from packages.live_selfhood_monitor.monitor import build_snapshot_from_events


def test_recent_heartbeat_is_alive_or_idle() -> None:
    snapshot = build_snapshot_from_events([make_heartbeat_event("2026-01-01T00:00:00Z")], generated_at="2026-01-01T00:00:01Z")
    assert classify_alive_status(snapshot, datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)) in {"alive", "idle"}


def test_stale_heartbeat_is_stalled() -> None:
    old = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat().replace("+00:00", "Z")
    assert heartbeat_is_stale(old, 120)


def test_make_heartbeat_event_is_read_only() -> None:
    event = make_heartbeat_event()
    assert event.event_type == "heartbeat"
    assert event.mutating is False
