from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


EventType = Literal[
    "autonomy.insight",
    "autonomy.warning",
    "autonomy.proposal",
    "autonomy.blocked",
    "autonomy.morning_brief",
    "autonomy.deficit_detected",
    "autonomy.congress_summary",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AutonomyEvent:
    event_id: str
    timestamp: str
    source: str
    event_type: EventType
    priority: int
    title: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    requires_user_action: bool = False
    expires_at: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id is required")
        if self.priority < 0:
            raise ValueError("priority must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InMemoryEventStream:
    def __init__(self) -> None:
        self._events: list[AutonomyEvent] = []

    def append_event(self, event: AutonomyEvent) -> None:
        self._events.append(event)

    def list_events(self) -> list[AutonomyEvent]:
        return list(self._events)

    def consume_events(self) -> list[AutonomyEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def clear_expired(self, now: str | None = None) -> int:
        active_now = now or utc_now()
        before = len(self._events)
        self._events = [event for event in self._events if event.expires_at is None or event.expires_at > active_now]
        return before - len(self._events)

