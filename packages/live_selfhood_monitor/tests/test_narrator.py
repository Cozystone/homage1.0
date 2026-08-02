from packages.live_selfhood_monitor.heartbeat import make_heartbeat_event
from packages.live_selfhood_monitor.monitor import build_snapshot_from_events
from packages.live_selfhood_monitor.narrator import narrate_snapshot


def test_narration_mentions_safety_without_overclaim() -> None:
    snapshot = build_snapshot_from_events([make_heartbeat_event()])
    text = narrate_snapshot(snapshot)
    assert "실제 기억 저장" in text
    assert "real consciousness" not in text.lower()
    assert "agi achieved" not in text.lower()
