from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal


LifeEventType = Literal[
    "life.signal_detected",
    "life.action_proposed",
    "life.sandbox_passed",
    "life.sandbox_blocked",
    "life.morning_brief_ready",
    "life.user_approval_required",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class LifeEvent:
    event_id: str
    event_type: LifeEventType
    title: str
    payload: dict[str, Any]
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InMemoryLifeEventStream:
    def __init__(self) -> None:
        self._events: list[LifeEvent] = []

    def emit(self, event_type: LifeEventType, title: str, payload: dict[str, Any]) -> LifeEvent:
        event = LifeEvent(f"life_event_{len(self._events) + 1}", event_type, title, payload, utc_now())
        self._events.append(event)
        return event

    def list_events(self) -> list[LifeEvent]:
        return list(self._events)
