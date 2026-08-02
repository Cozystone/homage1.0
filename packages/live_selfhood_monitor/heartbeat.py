from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import LifeSignEvent, LifeSignsSnapshot


def utc_now_iso() -> str:
    """Return a UTC ISO timestamp for monitor events."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO timestamp, accepting a trailing Z."""

    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def seconds_since(timestamp: str | None, now: datetime | None = None) -> float | None:
    """Return age in seconds for a timestamp, or None if it cannot be parsed."""

    parsed = parse_timestamp(timestamp)
    if parsed is None:
        return None
    current = now or datetime.now(timezone.utc)
    return max(0.0, (current.astimezone(timezone.utc) - parsed).total_seconds())


def make_heartbeat_event(timestamp: str | None = None, payload: dict[str, Any] | None = None) -> LifeSignEvent:
    """Create a read-only heartbeat event."""

    ts = timestamp or utc_now_iso()
    return LifeSignEvent(
        event_id=f"heartbeat-{ts.replace(':', '').replace('.', '').replace('Z', '')}",
        timestamp=ts,
        event_type="heartbeat",
        summary="Monitor heartbeat observed.",
        payload=dict(payload or {}),
    )


def heartbeat_is_stale(last_heartbeat_at: str | None, threshold_seconds: float, now: datetime | None = None) -> bool:
    """Return true when no heartbeat exists or the heartbeat exceeds the stale threshold."""

    age = seconds_since(last_heartbeat_at, now)
    return age is None or age > threshold_seconds


def classify_alive_status(snapshot: LifeSignsSnapshot, now: datetime | None = None, stale_threshold_seconds: float = 120.0) -> str:
    """Classify a snapshot without claiming consciousness."""

    if snapshot.alive_status == "stopped":
        return "stopped"
    if snapshot.rhythm_mode == "resting" or snapshot.alive_status == "resting":
        return "resting"
    if snapshot.tick_count <= 0 and snapshot.heartbeat_age_seconds is None:
        return "unknown"
    latest_time = None
    if snapshot.latest_tick:
        latest_time = str(snapshot.latest_tick.get("timestamp") or "")
    if latest_time and heartbeat_is_stale(latest_time, stale_threshold_seconds, now):
        return "stalled"
    if snapshot.heartbeat_age_seconds is not None and snapshot.heartbeat_age_seconds > stale_threshold_seconds:
        return "stalled"
    if snapshot.heartbeat_age_seconds is not None and snapshot.heartbeat_age_seconds <= stale_threshold_seconds:
        return "alive" if snapshot.latest_tick or snapshot.pending_approvals else "idle"
    if snapshot.pending_approvals:
        return "alive"
    if snapshot.tick_count > 0:
        return "alive" if snapshot.latest_need or snapshot.latest_action or snapshot.latest_spark else "idle"
    return "unknown"
