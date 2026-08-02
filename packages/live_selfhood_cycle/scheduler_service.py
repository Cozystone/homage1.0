from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from .clock import SimulatedLifeClock
from .lifecycle import run_life_cycle_tick
from .models import LifeCycleConfig, LifeCycleResult, RhythmPolicy, default_safety
from .scheduler_config import LiveSelfhoodSchedulerConfig


StoppedReason = Literal[
    "disabled",
    "max_ticks_reached",
    "max_runtime_reached",
    "stop_marker",
    "safety_stop",
    "error",
]


def _safe_actual_mutations() -> dict[str, bool]:
    return {
        "local_brain_write": False,
        "real_local_brain_write": False,
        "real_local_brain_mutated": False,
        "production_store_mutated": False,
        "candidate_store_mutated": False,
        "candidate_promotion": False,
        "actual_promotion_performed": False,
        "real_p2p": False,
        "real_p2p_used": False,
        "real_cloud_upload": False,
        "generated_code_executed": False,
        "always_listening": False,
        "always_listening_enabled": False,
        "raw_voice_saved": False,
    }


@dataclass(frozen=True)
class SchedulerSessionState:
    """Mutable-loop-free snapshot used by should_stop."""

    ticks_run: int = 0
    simulated_elapsed_seconds: float = 0.0
    error: str | None = None


@dataclass(frozen=True)
class SchedulerSessionResult:
    """Result of one bounded, in-process scheduler proof session."""

    session_id: str
    enabled: bool
    ticks_run: int
    stopped_reason: StoppedReason
    results: list[LifeCycleResult]
    actual_mutations: dict[str, bool]
    safety: dict[str, Any]
    simulated_elapsed_seconds: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "enabled": self.enabled,
            "ticks_run": self.ticks_run,
            "stopped_reason": self.stopped_reason,
            "results": [item.to_dict() for item in self.results],
            "actual_mutations": dict(self.actual_mutations),
            "safety": dict(self.safety),
            "simulated_elapsed_seconds": self.simulated_elapsed_seconds,
            "error": self.error,
        }


def create_stop_marker(path: str | Path) -> Path:
    """Create a local proof-only stop marker file."""

    marker = Path(path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("stop\n", encoding="utf-8")
    return marker


def read_stop_marker(path: str | Path | None) -> bool:
    """Return true when a local stop marker exists."""

    return bool(path) and Path(path).exists()


def clear_stop_marker(path: str | Path | None) -> None:
    """Remove a local proof-only stop marker if it exists."""

    if not path:
        return
    marker = Path(path)
    if marker.exists():
        marker.unlink()


def should_stop(config: LiveSelfhoodSchedulerConfig, state: SchedulerSessionState) -> StoppedReason | None:
    """Check bounded-session stop conditions without sleeping or mutating stores."""

    if not config.enabled:
        return "disabled"
    if state.error:
        return "error"
    if read_stop_marker(config.stop_marker_path):
        return "stop_marker"
    if state.ticks_run >= config.max_ticks_per_session:
        return "max_ticks_reached"
    if state.simulated_elapsed_seconds >= config.max_runtime_seconds:
        return "max_runtime_reached"
    return None


def run_one_tick(config: LiveSelfhoodSchedulerConfig, context: dict[str, Any] | None = None) -> LifeCycleResult:
    """Run one proof-only Live Selfhood tick under scheduler bounds."""

    cfg = LifeCycleConfig(
        autonomy_level=config.autonomy_level,
        voice_optional=not config.allow_voice_events,
        text_input_supported=True,
    )
    tick_index = int((context or {}).get("scheduler_tick_index", 1) or 1)
    clock = (context or {}).get("clock")
    if not isinstance(clock, SimulatedLifeClock):
        clock = SimulatedLifeClock()
    tick = clock.tick(
        tick_type="periodic_tick",
        reason="opt-in proof scheduler tick",
        autonomy_level=config.autonomy_level,
    )
    rhythm_policy = RhythmPolicy(
        min_delay_seconds=config.min_delay_seconds,
        max_delay_seconds=config.max_delay_seconds,
        entropy_seed=f"{config.deterministic_seed}:{tick_index}",
    )
    ctx = dict(context or {})
    ctx["rhythm_policy"] = rhythm_policy
    ctx["entropy_seed"] = rhythm_policy.entropy_seed
    return run_life_cycle_tick(cfg, tick, ctx)


def run_scheduler_session(
    config: LiveSelfhoodSchedulerConfig,
    context: dict[str, Any] | None = None,
) -> SchedulerSessionResult:
    """Run a bounded opt-in scheduler session without creating a daemon."""

    session_id = f"live-selfhood-session-{uuid4().hex[:12]}"
    safety = {
        **default_safety(),
        "scheduler_enabled_by_default": False,
        "bounded_runtime": True,
        "can_stop": True,
        "os_service": False,
        "daemon_started": False,
    }
    results: list[LifeCycleResult] = []
    state = SchedulerSessionState()
    first_stop = should_stop(config, state)
    if first_stop:
        return SchedulerSessionResult(
            session_id=session_id,
            enabled=config.enabled,
            ticks_run=0,
            stopped_reason=first_stop,
            results=[],
            actual_mutations=_safe_actual_mutations(),
            safety=safety,
        )

    clock = SimulatedLifeClock()
    ctx = dict(context or {})
    try:
        while True:
            stop = should_stop(config, state)
            if stop:
                return SchedulerSessionResult(
                    session_id=session_id,
                    enabled=config.enabled,
                    ticks_run=state.ticks_run,
                    stopped_reason=stop,
                    results=results,
                    actual_mutations=_safe_actual_mutations(),
                    safety=safety,
                    simulated_elapsed_seconds=state.simulated_elapsed_seconds,
                )
            tick_context = {
                **ctx,
                "clock": clock,
                "scheduler_tick_index": state.ticks_run + 1,
                "last_tick_at": results[-1].tick.timestamp if results else None,
            }
            result = run_one_tick(config, tick_context)
            if any(result.actual_mutations.values()):
                return SchedulerSessionResult(
                    session_id=session_id,
                    enabled=config.enabled,
                    ticks_run=state.ticks_run,
                    stopped_reason="safety_stop",
                    results=results,
                    actual_mutations=_safe_actual_mutations(),
                    safety=safety,
                    simulated_elapsed_seconds=state.simulated_elapsed_seconds,
                )
            results.append(result)
            simulated_delay = float(result.next_tick_delay_seconds or config.min_delay_seconds)
            simulated_delay = max(config.min_delay_seconds, min(config.max_delay_seconds, simulated_delay))
            state = SchedulerSessionState(
                ticks_run=state.ticks_run + 1,
                simulated_elapsed_seconds=state.simulated_elapsed_seconds + simulated_delay,
            )
    except Exception as exc:
        return SchedulerSessionResult(
            session_id=session_id,
            enabled=config.enabled,
            ticks_run=state.ticks_run,
            stopped_reason="error",
            results=results,
            actual_mutations=_safe_actual_mutations(),
            safety=safety,
            simulated_elapsed_seconds=state.simulated_elapsed_seconds,
            error=str(exc),
        )
