from __future__ import annotations

from .models import LifeEvent


class InMemoryLifeEventStream:
    def __init__(self) -> None:
        self._events: list[LifeEvent] = []

    def emit(self, event_type: str, payload: dict) -> LifeEvent:
        event = LifeEvent(event_id=f"life-event-{len(self._events) + 1:04d}", event_type=event_type, payload=payload)
        self._events.append(event)
        return event

    def list_events(self) -> list[LifeEvent]:
        return list(self._events)


def build_events(result_payload: dict) -> list[LifeEvent]:
    stream = InMemoryLifeEventStream()
    tick = result_payload["tick"]
    stream.emit("life.tick", tick)
    for observation in result_payload["observations"]:
        stream.emit("life.observation", observation)
    for need in result_payload["needs"]:
        stream.emit("life.need_detected", need)
    for impulse in result_payload["impulses"]:
        stream.emit("life.impulse_ranked", impulse)
    for action in result_payload["scheduled_actions"]:
        stream.emit("life.action_proposed", action)
        if action.get("requires_user_approval"):
            stream.emit("life.user_attention_requested", {"action_id": action["action_id"]})
    for deliberation in result_payload["deliberations"]:
        stream.emit("life.deliberation_completed", deliberation)
    if result_payload.get("brief"):
        stream.emit("life.brief_ready", result_payload["brief"])
    stream.emit("life.safety_blocked", {"blocked": ["real writes", "promotion apply", "real P2P", "always-on microphone"]})
    return stream.list_events()
