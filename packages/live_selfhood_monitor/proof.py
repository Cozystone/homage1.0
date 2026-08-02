from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from packages.live_selfhood_cycle.clock import make_tick
from packages.live_selfhood_cycle.lifecycle import run_life_cycle_tick
from packages.live_selfhood_cycle.models import LifeCycleConfig
from packages.live_selfhood_cycle.scheduler_config import LiveSelfhoodSchedulerConfig
from packages.live_selfhood_cycle.scheduler_service import create_stop_marker

from .heartbeat import make_heartbeat_event, utc_now_iso
from .models import LifeSignEvent, LifeSignsWatchConfig, default_actual_mutations
from .monitor import build_snapshot_from_events, build_snapshot_from_lifecycle_result, events_from_lifecycle_result
from .narrator import narrate_snapshot
from .watch_session import run_watch_session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "live_selfhood_monitor"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _tick(context: dict[str, Any] | None = None, tick_type: str = "manual_ping") -> Any:
    tick = make_tick(tick_type=tick_type, reason=f"life signs proof {tick_type}", autonomy_level="LEVEL_3_SANDBOX_PLANNER")
    return run_life_cycle_tick(LifeCycleConfig(), tick, context or {})


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """Run proof-only life signs scenarios and write ignored audit outputs."""

    disabled = run_watch_session(LifeSignsWatchConfig(enabled=False))
    alive_result = _tick({"candidate_backlog": 4, "entropy_seed": "life-signs-alive"})
    alive_snapshot = build_snapshot_from_lifecycle_result(alive_result)
    resting_result = _tick({"disk_free_gib": 1, "entropy_seed": "life-signs-rest"})
    resting_snapshot = build_snapshot_from_lifecycle_result(resting_result)
    stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat().replace("+00:00", "Z")
    stalled_snapshot = build_snapshot_from_events([make_heartbeat_event(stale_ts)])
    pending_events = events_from_lifecycle_result(_tick({"approved_write_plan_waiting": True}, "manual_ping"))
    pending_snapshot = build_snapshot_from_events(pending_events)
    safety_event = LifeSignEvent(
        event_id="proof-safety-block",
        timestamp=utc_now_iso(),
        event_type="safety_blocked",
        summary="Unsafe local write remains blocked.",
        payload={"blocked": ["real_local_brain_write", "candidate_promotion", "real_p2p"]},
        severity="blocked",
    )
    safety_snapshot = build_snapshot_from_events([make_heartbeat_event(), safety_event])
    bounded = run_watch_session(
        LifeSignsWatchConfig(enabled=True, max_ticks=2),
        LiveSelfhoodSchedulerConfig(enabled=True, max_ticks_per_session=2, max_runtime_seconds=10_000),
        {"candidate_backlog": 4},
    )
    stop_marker = output_dir / "life_signs_stop.marker"
    output_dir.mkdir(parents=True, exist_ok=True)
    create_stop_marker(stop_marker)
    stopped = run_watch_session(
        LifeSignsWatchConfig(enabled=True, max_ticks=3),
        LiveSelfhoodSchedulerConfig(enabled=True, stop_marker_path=str(stop_marker)),
        {"candidate_backlog": 4},
    )
    if stop_marker.exists():
        stop_marker.unlink()
    scenarios = {
        "disabled": disabled.enabled is False and disabled.stopped_reason == "disabled" and disabled.final_snapshot.alive_status == "stopped",
        "alive": alive_snapshot.alive_status == "alive" and _no_mutation(alive_snapshot.actual_mutations),
        "resting": resting_snapshot.alive_status in {"resting", "alive"} and resting_snapshot.rhythm_mode in {"resting", "observing", "curious", "briefing", "waiting_user", "deliberating"},
        "stalled": stalled_snapshot.alive_status == "stalled",
        "pending_approval": len(pending_snapshot.pending_approvals) > 0 and _no_mutation(pending_snapshot.actual_mutations),
        "safety_blocked": len(safety_snapshot.safety_blocks) > 0 and bool(safety_snapshot.safety_blocks[0]["blocked"]),
        "bounded": bounded.enabled is True and bounded.stopped_reason in {"max_ticks", "completed"} and len(bounded.snapshots) <= 2,
        "stop_marker": stopped.stopped_reason == "stop_marker" and stopped.final_snapshot.tick_count == 0,
    }
    samples = {
        "disabled": disabled.to_dict(),
        "alive": alive_snapshot.to_dict(),
        "resting": resting_snapshot.to_dict(),
        "stalled": stalled_snapshot.to_dict(),
        "pending_approval": pending_snapshot.to_dict(),
        "safety_blocked": safety_snapshot.to_dict(),
        "bounded": bounded.to_dict(),
        "stop_marker": stopped.to_dict(),
        "narration": {
            "alive": narrate_snapshot(alive_snapshot),
            "resting": narrate_snapshot(resting_snapshot),
            "stalled": narrate_snapshot(stalled_snapshot),
            "pending_approval": narrate_snapshot(pending_snapshot),
        },
    }
    payload = {
        "verdict": "PASS" if all(scenarios.values()) else "FAIL",
        "scenarios": scenarios,
        "invariants": default_actual_mutations(),
        "samples": samples,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    json_path = output_dir / f"life_signs_monitor_proof_{ts}.json"
    md_path = output_dir / f"life_signs_monitor_proof_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return payload


def _no_mutation(flags: dict[str, Any]) -> bool:
    allowed_true = {"requires_user_approval", "text_input_supported", "voice_optional", "monitor_read_only", "can_stop", "bounded_runtime"}
    return not any(bool(value) for key, value in flags.items() if key not in allowed_true)


def _markdown(payload: dict[str, Any]) -> str:
    lines = ["# Live Selfhood Life Signs Monitor Proof", "", f"- verdict: `{payload['verdict']}`", ""]
    for key, value in payload["scenarios"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "This proof-only monitor reports functional heartbeat, rhythm, spark, proposals, briefs, pending approvals, and safety blocks. It does not prove real consciousness or AGI, and it does not mutate memory, production stores, candidate stores, or runtime services.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    result = run_proof()
    print(json.dumps({"verdict": result["verdict"], "scenarios": result["scenarios"], "outputs": result["outputs"]}, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
