from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


EVENT_TYPES = {
    "ego.checkout_predicted",
    "ego.checkout_blocked",
    "ego.checked_out_dry_run",
    "ego.midnight_congress_started",
    "ego.midnight_congress_synthesized",
    "ego.checkin_available",
    "ego.sync_conflict",
    "ego.morning_gift",
    "ego.user_approval_required",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class EgoEvent:
    event_id: str
    event_type: str
    created_at: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    requires_user_action: bool = False

    def __post_init__(self) -> None:
        if self.event_type not in EVENT_TYPES:
            raise ValueError(f"unknown ego event type: {self.event_type}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InMemoryEgoEventStream:
    """Local event stream for proof-only ego sync scenarios."""

    def __init__(self) -> None:
        self._events: list[EgoEvent] = []

    def append_event(self, event: EgoEvent) -> EgoEvent:
        self._events.append(event)
        return event

    def list_events(self, event_type: str | None = None) -> list[EgoEvent]:
        if event_type is None:
            return list(self._events)
        return [event for event in self._events if event.event_type == event_type]

    def consume_events(self, event_type: str | None = None) -> list[EgoEvent]:
        selected = self.list_events(event_type)
        if event_type is None:
            self._events.clear()
        else:
            self._events = [event for event in self._events if event.event_type != event_type]
        return selected


def append_event(stream: InMemoryEgoEventStream, event: EgoEvent) -> EgoEvent:
    return stream.append_event(event)


def list_events(stream: InMemoryEgoEventStream, event_type: str | None = None) -> list[EgoEvent]:
    return stream.list_events(event_type)


def consume_events(stream: InMemoryEgoEventStream, event_type: str | None = None) -> list[EgoEvent]:
    return stream.consume_events(event_type)
