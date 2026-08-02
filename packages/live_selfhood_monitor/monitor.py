from __future__ import annotations

from typing import Any, Iterable
from uuid import uuid4

from .event_timeline import last_event_of_type, sort_events
from .heartbeat import parse_timestamp, seconds_since, utc_now_iso
from .models import LifeSignEvent, LifeSignsSnapshot, default_actual_mutations


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return dict(getattr(value, "__dict__", {}))


def _make_event(event_type: str, timestamp: str, summary: str, payload: dict[str, Any], severity: str = "info") -> LifeSignEvent:
    return LifeSignEvent(
        event_id=f"life-sign-{event_type}-{uuid4().hex[:10]}",
        timestamp=timestamp,
        event_type=event_type,  # type: ignore[arg-type]
        summary=summary,
        payload=payload,
        severity=severity,  # type: ignore[arg-type]
    )


def events_from_lifecycle_result(result: Any) -> list[LifeSignEvent]:
    """Translate a proof-only LifeCycleResult into monitor life sign events."""

    payload = _as_dict(result)
    tick = payload.get("tick") or {}
    timestamp = str(tick.get("timestamp") or utc_now_iso())
    events: list[LifeSignEvent] = [
        _make_event("heartbeat", timestamp, "Lifecycle heartbeat recorded.", {"tick_id": tick.get("tick_id")}),
        _make_event("tick", timestamp, str(tick.get("reason") or "Lifecycle tick."), tick),
    ]
    rhythm_state = payload.get("rhythm_state") or {}
    rhythm_decision = payload.get("rhythm_decision") or {}
    if rhythm_state or rhythm_decision:
        mode = rhythm_decision.get("next_mode") or rhythm_state.get("mode")
        events.append(
            _make_event(
                "rhythm_changed",
                timestamp,
                f"Rhythm mode is {mode}.",
                {"rhythm_state": rhythm_state, "rhythm_decision": rhythm_decision},
                "notice",
            )
        )
        if mode == "resting":
            events.append(_make_event("resting", timestamp, str(rhythm_decision.get("explanation") or rhythm_state.get("reason") or "Resting."), rhythm_decision, "notice"))
    for observation in payload.get("observations") or []:
        events.append(_make_event("observation", timestamp, str(observation.get("summary") or "Observation."), observation, observation.get("severity", "info")))
    for need in payload.get("needs") or []:
        events.append(_make_event("need_detected", timestamp, str(need.get("summary") or need.get("need_type") or "Need detected."), need, need.get("severity", "info")))
    for impulse in payload.get("impulses") or []:
        events.append(_make_event("impulse_ranked", timestamp, str(impulse.get("reason") or "Impulse ranked."), impulse, "notice"))
    spark = payload.get("spark")
    if spark:
        events.append(_make_event("spark_generated", timestamp, str(spark.get("trigger_reason") or spark.get("spark_type") or "Spark generated."), spark, "notice"))
    for action in payload.get("scheduled_actions") or []:
        events.append(_make_event("action_proposed", timestamp, str(action.get("summary") or action.get("title") or "Action proposed."), action, "notice"))
        if action.get("requires_user_approval"):
            events.append(
                _make_event(
                    "user_attention_requested",
                    timestamp,
                    f"User approval is required for {action.get('action_type')}.",
                    {"action_id": action.get("action_id"), "action_type": action.get("action_type"), "title": action.get("title")},
                    "notice",
                )
            )
    for deliberation in payload.get("deliberations") or []:
        events.append(_make_event("deliberation_completed", timestamp, str(deliberation.get("summary") or "Deliberation completed."), deliberation, "notice"))
    brief = payload.get("brief")
    if brief:
        events.append(_make_event("brief_ready", timestamp, str(brief.get("title") or "Brief ready."), brief, "notice"))
    safety_blocks = ["Local Brain write locked", "production mutation locked", "candidate promotion locked", "real P2P locked", "generated code locked", "always listening locked"]
    events.append(_make_event("safety_blocked", timestamp, "Irreversible capabilities remain locked.", {"blocked": safety_blocks}, "blocked"))
    return events


def collect_pending_approvals(events: Iterable[LifeSignEvent]) -> list[dict[str, Any]]:
    """Collect user attention requests and approval-required proposed actions."""

    approvals: list[dict[str, Any]] = []
    for event in events:
        if event.event_type == "user_attention_requested":
            approvals.append(event.payload)
        if event.event_type == "action_proposed" and event.payload.get("requires_user_approval"):
            approvals.append(
                {
                    "action_id": event.payload.get("action_id"),
                    "action_type": event.payload.get("action_type"),
                    "title": event.payload.get("title"),
                    "source_event": event.event_id,
                }
            )
    return approvals


def collect_safety_blocks(events: Iterable[LifeSignEvent]) -> list[dict[str, Any]]:
    """Collect blocked safety gates from a timeline."""

    return [event.payload for event in events if event.event_type == "safety_blocked"]


def build_snapshot_from_events(events: Iterable[LifeSignEvent], generated_at: str | None = None) -> LifeSignsSnapshot:
    """Build a LifeSignsSnapshot from read-only timeline events."""

    ordered = sort_events(events)
    now = generated_at or utc_now_iso()
    tick_events = [event for event in ordered if event.event_type == "tick"]
    latest_tick = tick_events[-1].payload if tick_events else None
    latest_heartbeat = last_event_of_type(ordered, "heartbeat")
    heartbeat_age = seconds_since(latest_heartbeat.timestamp if latest_heartbeat else None, parse_timestamp(now))
    latest_rhythm = last_event_of_type(ordered, "rhythm_changed")
    latest_rest = last_event_of_type(ordered, "resting")
    rhythm_payload = latest_rhythm.payload if latest_rhythm else {}
    rhythm_decision = rhythm_payload.get("rhythm_decision") or {}
    rhythm_state = rhythm_payload.get("rhythm_state") or {}
    status = "unknown"
    if latest_rest:
        status = "resting"
    elif last_event_of_type(ordered, "stopped"):
        status = "stopped"
    elif latest_heartbeat and heartbeat_age is not None and heartbeat_age <= 120:
        status = "alive"
    elif latest_heartbeat:
        status = "stalled"
    elif tick_events:
        status = "idle"
    latest_spark = last_event_of_type(ordered, "spark_generated")
    latest_observation = last_event_of_type(ordered, "observation")
    latest_need = last_event_of_type(ordered, "need_detected")
    latest_impulse = last_event_of_type(ordered, "impulse_ranked")
    latest_action = last_event_of_type(ordered, "action_proposed")
    latest_brief = last_event_of_type(ordered, "brief_ready")
    return LifeSignsSnapshot(
        snapshot_id=f"life-signs-{uuid4().hex[:12]}",
        generated_at=now,
        alive_status=status,  # type: ignore[arg-type]
        heartbeat_age_seconds=heartbeat_age,
        tick_count=len(tick_events),
        latest_tick=latest_tick,
        rhythm_mode=rhythm_decision.get("next_mode") or rhythm_state.get("mode"),
        latest_wake_reason=str(latest_tick.get("reason")) if latest_tick else None,
        latest_spark=latest_spark.payload if latest_spark else None,
        latest_observation=latest_observation.payload if latest_observation else None,
        latest_need=latest_need.payload if latest_need else None,
        latest_impulse=latest_impulse.payload if latest_impulse else None,
        latest_action=latest_action.payload if latest_action else None,
        latest_brief=latest_brief.payload if latest_brief else None,
        pending_approvals=collect_pending_approvals(ordered),
        safety_blocks=collect_safety_blocks(ordered),
        next_tick_delay_seconds=rhythm_decision.get("next_tick_delay_seconds") or rhythm_state.get("next_tick_delay_seconds"),
        actual_mutations=default_actual_mutations(),
    )


def build_snapshot_from_lifecycle_result(result: Any) -> LifeSignsSnapshot:
    """Build a snapshot from one LifeCycleResult without applying actions."""

    return build_snapshot_from_events(events_from_lifecycle_result(result))


def summarize_life_signs(snapshot: LifeSignsSnapshot) -> dict[str, Any]:
    """Return a compact machine-readable status summary."""

    return {
        "alive_status": snapshot.alive_status,
        "heartbeat_age_seconds": snapshot.heartbeat_age_seconds,
        "tick_count": snapshot.tick_count,
        "rhythm_mode": snapshot.rhythm_mode,
        "latest_wake_reason": snapshot.latest_wake_reason,
        "pending_approval_count": len(snapshot.pending_approvals),
        "safety_block_count": len(snapshot.safety_blocks),
        "next_tick_delay_seconds": snapshot.next_tick_delay_seconds,
        "actual_mutations": dict(snapshot.actual_mutations),
    }
