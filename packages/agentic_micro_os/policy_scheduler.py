from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

from packages.agentic_micro_os.permission_gate import PermissionGate
from packages.agentic_micro_os.policy_loop import LOOP_SAFETY_FLAGS, PolicyDrivenAutonomousLoop, PolicyLoopConfig
from packages.agentic_micro_os.review_queue import ReviewQueue
from packages.neural_emotion.event_bus import NeuralEmotionEventBus


SCHEDULER_SAFETY_FLAGS = {
    **LOOP_SAFETY_FLAGS,
    "scheduler_opt_in": True,
    "scheduler_stoppable": True,
    "no_daemon_autostart": True,
}


@dataclass(frozen=True)
class SchedulerConfig:
    scheduler_id: str = ""
    enabled: bool = False
    max_runtime_sec: int = 600
    max_cycles: int = 5
    min_interval_sec: float = 5.0
    max_interval_sec: float = 120.0
    stop_file: str = "runtime/agentic_micro_os/policy_scheduler.stop"
    emergency_stop_file: str = "runtime/agentic_micro_os/EMERGENCY_STOP"
    run_policy_loop: bool = True
    allow_web_explorer: bool = True
    allow_review_import: bool = True
    allow_splatra_generation: bool = True
    allow_host_executor_status_only: bool = True
    live_web: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "scheduler_id", self.scheduler_id or f"policy_scheduler_{uuid4().hex[:12]}")
        object.__setattr__(self, "max_runtime_sec", max(1, min(int(self.max_runtime_sec), 21_600)))
        object.__setattr__(self, "max_cycles", max(1, min(int(self.max_cycles), 10_000)))
        object.__setattr__(self, "min_interval_sec", max(0.1, min(float(self.min_interval_sec), 3_600.0)))
        object.__setattr__(self, "max_interval_sec", max(float(self.min_interval_sec), min(float(self.max_interval_sec), 7_200.0)))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SchedulerState:
    scheduler_id: str
    enabled: bool
    started_at: str
    stopped_at: str
    cycle_count: int
    next_delay_sec: float
    last_policy: dict[str, Any]
    last_emotion: dict[str, Any]
    last_result: dict[str, Any] | None
    stopped_reason: str
    safety_flags: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PolicyDrivenAutonomousScheduler:
    def __init__(
        self,
        config: SchedulerConfig | None = None,
        *,
        event_bus: NeuralEmotionEventBus | None = None,
        review_queue: ReviewQueue | None = None,
        permission_gate: PermissionGate | None = None,
    ) -> None:
        self.config = config or SchedulerConfig()
        self.event_bus = event_bus or NeuralEmotionEventBus()
        self.review_queue = review_queue or ReviewQueue()
        self.permission_gate = permission_gate or PermissionGate()
        self.started_monotonic: float | None = None
        self.started_at = ""
        self.stopped_at = ""
        self.enabled = bool(self.config.enabled)
        if self.enabled:
            self.started_monotonic = monotonic()
            self.started_at = _now()
        self.cycle_count = 0
        self.last_result: dict[str, Any] | None = None
        self.stopped_reason = "" if self.enabled else "disabled"

    def start(self, *, operator_confirmed: bool = False) -> dict[str, Any]:
        if not operator_confirmed:
            self.enabled = False
            self.stopped_reason = "operator_confirmation_required"
            return {**self.state().to_dict(), "allowed": False, "reason": self.stopped_reason}
        self.enabled = True
        self.started_monotonic = monotonic()
        self.started_at = _now()
        self.stopped_at = ""
        self.cycle_count = 0
        self.stopped_reason = ""
        self._clear_stop_file()
        return {**self.state().to_dict(), "allowed": True, "reason": "scheduler_started"}

    def stop(self, *, reason: str = "operator_stop", create_stop_file: bool = True) -> dict[str, Any]:
        self.enabled = False
        self.stopped_at = _now()
        self.stopped_reason = reason
        if create_stop_file:
            self._write_stop_file(reason)
        return {**self.state().to_dict(), "allowed": True, "reason": reason}

    def tick(self) -> dict[str, Any]:
        if not self.enabled:
            return {**self.state().to_dict(), "ran": False, "reason": self.stopped_reason or "disabled"}
        stop_reason = self._stop_reason()
        if stop_reason:
            self.stop(reason=stop_reason, create_stop_file=False)
            return {**self.state().to_dict(), "ran": False, "reason": stop_reason}

        policy = self._policy()
        if policy["agent_loop"]["should_rest"]:
            self.stop(reason=policy["agent_loop"].get("rest_reason") or "rest_requested", create_stop_file=False)
            return {**self.state().to_dict(), "ran": False, "reason": self.stopped_reason}

        run_config = self._loop_config(policy)
        result: dict[str, Any] | None = None
        if self.config.run_policy_loop:
            result = PolicyDrivenAutonomousLoop(
                run_config,
                event_bus=self.event_bus,
                review_queue=self.review_queue,
                permission_gate=self.permission_gate,
            ).run_once().to_dict()
        self.last_result = result
        self.cycle_count += 1
        if self.cycle_count >= self.config.max_cycles:
            self.enabled = False
            self.stopped_at = _now()
            self.stopped_reason = "max_cycles"
        return {**self.state().to_dict(), "ran": True, "reason": self.stopped_reason or "tick_completed"}

    def state(self) -> SchedulerState:
        policy = self._policy()
        snapshot = self.event_bus.engine.snapshot().to_dict()
        return SchedulerState(
            scheduler_id=self.config.scheduler_id,
            enabled=self.enabled,
            started_at=self.started_at,
            stopped_at=self.stopped_at,
            cycle_count=self.cycle_count,
            next_delay_sec=self._next_delay(policy),
            last_policy=policy,
            last_emotion=snapshot,
            last_result=self.last_result,
            stopped_reason=self.stopped_reason,
            safety_flags=SCHEDULER_SAFETY_FLAGS.copy(),
        )

    def _loop_config(self, policy: dict[str, Any]) -> PolicyLoopConfig:
        review_pressure = self._review_pressure()
        base_web_pages = 0 if review_pressure >= 0.65 or not self.config.allow_web_explorer else 3
        base_review_batch = 0 if not self.config.allow_review_import else 6
        base_splatra_frames = 0 if not self.config.allow_splatra_generation else 1
        allow_host = bool(self.config.allow_host_executor_status_only and policy["review"]["strictness"] < 0.55)
        return PolicyLoopConfig(
            loop_id=f"{self.config.scheduler_id}_cycle_{self.cycle_count + 1}",
            max_cycles=1,
            max_runtime_sec=min(30, self.config.max_runtime_sec),
            base_web_pages=base_web_pages,
            base_review_batch=base_review_batch,
            base_splatra_frames=base_splatra_frames,
            allow_host_executor=allow_host,
            review_queue_pressure=review_pressure,
            recent_failures=0,
            unsafe_request=False,
            voice_available=False,
            live_web=bool(self.config.live_web and self.config.allow_web_explorer),
            allow_review_import=self.config.allow_review_import,
        )

    def _policy(self) -> dict[str, Any]:
        loop = PolicyDrivenAutonomousLoop(
            PolicyLoopConfig(review_queue_pressure=self._review_pressure()),
            event_bus=self.event_bus,
            review_queue=self.review_queue,
            permission_gate=self.permission_gate,
        )
        return loop.status()["policy_decision"]

    def _next_delay(self, policy: dict[str, Any]) -> float:
        vector = self.event_bus.engine.snapshot().vector
        span = self.config.max_interval_sec - self.config.min_interval_sec
        curiosity_pull = vector.curiosity * 0.5
        fatigue_push = vector.fatigue * 0.7
        caution_push = float(policy["review"]["strictness"]) * 0.25
        ratio = max(0.0, min(1.0, 0.5 - curiosity_pull + fatigue_push + caution_push))
        return round(self.config.min_interval_sec + span * ratio, 3)

    def _review_pressure(self) -> float:
        pending = int(self.review_queue.status().get("pending", 0) or 0)
        high_risk = int(self.review_queue.status().get("high_risk", 0) or 0)
        return max(min(pending / 12.0, 1.0), 1.0 if high_risk else 0.0)

    def _stop_reason(self) -> str:
        if self._emergency_path().exists() or self.permission_gate.status().get("emergency_stop_triggered"):
            return "emergency_stop"
        if self._stop_path().exists():
            return "stop_file"
        if self.started_monotonic is not None and monotonic() - self.started_monotonic >= self.config.max_runtime_sec:
            return "max_runtime_sec"
        if self.cycle_count >= self.config.max_cycles:
            return "max_cycles"
        return ""

    def _stop_path(self) -> Path:
        return Path(self.config.stop_file)

    def _emergency_path(self) -> Path:
        return Path(self.config.emergency_stop_file)

    def _write_stop_file(self, reason: str) -> None:
        path = self._stop_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(reason, encoding="utf-8")

    def _clear_stop_file(self) -> None:
        path = self._stop_path()
        if path.exists():
            path.unlink()


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="Run proof-only opt-in policy scheduler ticks.")
    parser.add_argument("--max-runtime-sec", type=int, default=600)
    parser.add_argument("--max-cycles", type=int, default=5)
    parser.add_argument("--start", action="store_true", help="Explicitly opt in. Without this the scheduler stays disabled.")
    args = parser.parse_args()
    scheduler = PolicyDrivenAutonomousScheduler(SchedulerConfig(max_runtime_sec=args.max_runtime_sec, max_cycles=args.max_cycles))
    if args.start:
        scheduler.start(operator_confirmed=True)
        while scheduler.enabled:
            scheduler.tick()
    print(json.dumps(scheduler.state().to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    run_cli()
