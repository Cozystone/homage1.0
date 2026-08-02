from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SelfhoodEvent:
    event_id: str
    event_type: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InMemorySelfhoodEventStream:
    """Small in-memory event stream; it writes no runtime state to disk."""

    def __init__(self) -> None:
        self._events: list[SelfhoodEvent] = []

    def append(self, event_type: str, message: str, metadata: dict[str, Any] | None = None) -> SelfhoodEvent:
        event = SelfhoodEvent(f"selfhood_event_{len(self._events) + 1}", event_type, message, metadata or {})
        self._events.append(event)
        return event

    def list_events(self) -> list[SelfhoodEvent]:
        return list(self._events)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self._events]
