from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .heartbeat import utc_now_iso
from .models import LifeSignEvent, LifeSignsSnapshot, LifeSignsWatchConfig, LifeSignsWatchResult, default_actual_mutations
from .monitor import build_snapshot_from_events, events_from_lifecycle_result


def _disabled_snapshot(now: str) -> LifeSignsSnapshot:
    return LifeSignsSnapshot(
        snapshot_id=f"life-signs-disabled-{uuid4().hex[:8]}",
        generated_at=now,
        alive_status="stopped",
        heartbeat_age_seconds=None,
        tick_count=0,
        actual_mutations=default_actual_mutations(),
    )


def run_watch_session(
    config: LifeSignsWatchConfig,
    scheduler_config: Any | None = None,
    context: dict[str, Any] | None = None,
    provided_events: list[LifeSignEvent] | None = None,
) -> LifeSignsWatchResult:
    """Run a bounded opt-in watch session without creating a daemon or mutating stores."""

    started = utc_now_iso()
    if not config.enabled:
        final = _disabled_snapshot(started)
        result = LifeSignsWatchResult(
            session_id=f"life-signs-watch-{uuid4().hex[:12]}",
            started_at=started,
            ended_at=utc_now_iso(),
            enabled=False,
            stopped_reason="disabled",
            events=[],
            snapshots=[final],
            final_snapshot=final,
            actual_mutations=default_actual_mutations(),
        )
        _write_runtime_log_if_requested(config, result)
        return result

    events = list(provided_events or [])
    snapshots: list[LifeSignsSnapshot] = []
    stopped_reason = "completed"
    if scheduler_config is not None:
        from packages.live_selfhood_cycle.scheduler_service import run_scheduler_session

        session = run_scheduler_session(scheduler_config, context or {})
        for lifecycle_result in session.results[: config.max_ticks]:
            events.extend(events_from_lifecycle_result(lifecycle_result))
            snapshots.append(build_snapshot_from_events(events))
        if session.stopped_reason == "stop_marker":
            stopped_reason = "stop_marker"
        elif session.stopped_reason == "safety_stop":
            stopped_reason = "safety_stop"
        elif session.stopped_reason == "max_runtime_reached":
            stopped_reason = "max_watch_seconds"
        elif session.stopped_reason == "max_ticks_reached":
            stopped_reason = "max_ticks"
        else:
            stopped_reason = "completed"
    else:
        limited = events[: max(0, config.max_ticks)]
        events = limited
        snapshots.append(build_snapshot_from_events(events))
        stopped_reason = "max_ticks" if len(provided_events or []) > len(events) else "completed"

    final = snapshots[-1] if snapshots else build_snapshot_from_events(events)
    result = LifeSignsWatchResult(
        session_id=f"life-signs-watch-{uuid4().hex[:12]}",
        started_at=started,
        ended_at=utc_now_iso(),
        enabled=True,
        stopped_reason=stopped_reason,  # type: ignore[arg-type]
        events=events,
        snapshots=snapshots or [final],
        final_snapshot=final,
        actual_mutations=default_actual_mutations(),
    )
    _write_runtime_log_if_requested(config, result)
    return result


def _write_runtime_log_if_requested(config: LifeSignsWatchConfig, result: LifeSignsWatchResult) -> None:
    """Write an optional local runtime log only when the caller supplies an explicit path."""

    if not config.write_runtime_log:
        return
    if not config.runtime_log_path:
        raise ValueError("runtime_log_path is required when write_runtime_log is true")
    path = Path(config.runtime_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
