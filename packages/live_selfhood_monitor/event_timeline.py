from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .heartbeat import parse_timestamp
from .models import LifeSignEvent


def append_life_event(events: Iterable[LifeSignEvent], event: LifeSignEvent) -> list[LifeSignEvent]:
    """Return a new timeline with one event appended."""

    return [*events, event]


def sort_events(events: Iterable[LifeSignEvent]) -> list[LifeSignEvent]:
    """Sort events by timestamp while keeping unparsable timestamps stable at the end."""

    fallback = parse_timestamp("9999-12-31T00:00:00Z")
    return sorted(events, key=lambda item: parse_timestamp(item.timestamp) or fallback)


def group_events_by_type(events: Iterable[LifeSignEvent]) -> dict[str, list[LifeSignEvent]]:
    """Group a timeline by life sign event type."""

    grouped: dict[str, list[LifeSignEvent]] = defaultdict(list)
    for event in events:
        grouped[event.event_type].append(event)
    return dict(grouped)


def last_event_of_type(events: Iterable[LifeSignEvent], event_type: str) -> LifeSignEvent | None:
    """Return the last event of a given type, if any."""

    matches = [event for event in sort_events(events) if event.event_type == event_type]
    return matches[-1] if matches else None


def timeline_summary(events: Iterable[LifeSignEvent]) -> dict[str, object]:
    """Summarize heartbeat, spark, proposal, brief, and safety history."""

    ordered = sort_events(events)
    grouped = group_events_by_type(ordered)
    return {
        "event_count": len(ordered),
        "tick_count": len(grouped.get("tick", [])),
        "spark_count": len(grouped.get("spark_generated", [])),
        "proposal_count": len(grouped.get("action_proposed", [])),
        "brief_count": len(grouped.get("brief_ready", [])),
        "safety_block_count": len(grouped.get("safety_blocked", [])),
        "last_event": ordered[-1].to_dict() if ordered else None,
    }
