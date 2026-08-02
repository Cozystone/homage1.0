from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


LifeSignEventType = Literal[
    "heartbeat",
    "tick",
    "observation",
    "need_detected",
    "impulse_ranked",
    "rhythm_changed",
    "spark_generated",
    "action_proposed",
    "deliberation_started",
    "deliberation_completed",
    "brief_ready",
    "user_attention_requested",
    "safety_blocked",
    "resting",
    "stopped",
]
LifeSignSeverity = Literal["info", "notice", "warning", "blocked"]
AliveStatus = Literal["alive", "idle", "resting", "stalled", "stopped", "unknown"]
StoppedReason = Literal["disabled", "max_watch_seconds", "max_ticks", "stop_marker", "safety_stop", "completed"]


def default_actual_mutations() -> dict[str, bool]:
    """Return the non-mutating invariant set required by the life signs monitor."""

    return {
        "real_local_brain_write": False,
        "real_local_brain_mutated": False,
        "production_store_mutated": False,
        "candidate_store_mutated": False,
        "candidate_promotion": False,
        "actual_promotion_performed": False,
        "external_llm_used": False,
        "real_p2p_used": False,
        "real_cloud_upload": False,
        "generated_code_executed": False,
        "always_listening_enabled": False,
        "raw_voice_saved": False,
        "requires_user_approval": True,
        "text_input_supported": True,
        "voice_optional": True,
        "monitor_read_only": True,
        "can_stop": True,
        "bounded_runtime": True,
    }


def assert_monitor_safe(actual_mutations: dict[str, Any]) -> None:
    """Reject snapshots or events that claim real mutation or unsafe capabilities."""

    merged = {**default_actual_mutations(), **actual_mutations}
    must_be_false = [
        "real_local_brain_write",
        "real_local_brain_mutated",
        "production_store_mutated",
        "candidate_store_mutated",
        "candidate_promotion",
        "actual_promotion_performed",
        "external_llm_used",
        "real_p2p_used",
        "real_cloud_upload",
        "generated_code_executed",
        "always_listening_enabled",
        "raw_voice_saved",
    ]
    bad = {key: merged.get(key) for key in must_be_false if bool(merged.get(key))}
    if bad:
        raise ValueError(f"life signs monitor is read-only; unsafe mutation flags set: {bad}")
    for key in ["requires_user_approval", "text_input_supported", "voice_optional", "monitor_read_only", "can_stop", "bounded_runtime"]:
        if merged.get(key) is not True:
            raise ValueError(f"{key} must remain true")


@dataclass(frozen=True)
class LifeSignEvent:
    """One read-only observation emitted by the life signs monitor."""

    event_id: str
    timestamp: str
    event_type: LifeSignEventType
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    severity: LifeSignSeverity = "info"
    mutating: bool = False

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id is required")
        if not self.timestamp:
            raise ValueError("timestamp is required")
        if self.mutating:
            raise ValueError("life sign events cannot be mutating")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LifeSignsSnapshot:
    """Current functional life-sign state for a proof-only ATANOR selfhood loop."""

    snapshot_id: str
    generated_at: str
    alive_status: AliveStatus
    heartbeat_age_seconds: float | None
    tick_count: int
    latest_tick: dict[str, Any] | None = None
    rhythm_mode: str | None = None
    latest_wake_reason: str | None = None
    latest_spark: dict[str, Any] | None = None
    latest_observation: dict[str, Any] | None = None
    latest_need: dict[str, Any] | None = None
    latest_impulse: dict[str, Any] | None = None
    latest_action: dict[str, Any] | None = None
    latest_brief: dict[str, Any] | None = None
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    safety_blocks: list[dict[str, Any]] = field(default_factory=list)
    next_tick_delay_seconds: float | None = None
    actual_mutations: dict[str, Any] = field(default_factory=default_actual_mutations)

    def __post_init__(self) -> None:
        if not self.snapshot_id:
            raise ValueError("snapshot_id is required")
        if not self.generated_at:
            raise ValueError("generated_at is required")
        if self.tick_count < 0:
            raise ValueError("tick_count must be non-negative")
        assert_monitor_safe(self.actual_mutations)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LifeSignsWatchConfig:
    """Bounds for an explicit, proof-only monitor watch session."""

    enabled: bool = False
    max_watch_seconds: int = 60
    max_ticks: int = 10
    poll_interval_seconds: float = 1.0
    include_briefs: bool = True
    include_sparks: bool = True
    include_safety: bool = True
    write_runtime_log: bool = False
    runtime_log_path: str | None = None
    require_user_opt_in: bool = True

    def __post_init__(self) -> None:
        if self.max_watch_seconds < 0 or self.max_watch_seconds > 86_400:
            raise ValueError("max_watch_seconds must be between 0 and 86400")
        if self.max_ticks < 0 or self.max_ticks > 100:
            raise ValueError("max_ticks must be between 0 and 100")
        if self.poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must be non-negative")
        if self.require_user_opt_in is not True:
            raise ValueError("watch sessions require explicit user opt-in")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LifeSignsWatchResult:
    """Result of a bounded life signs watch session."""

    session_id: str
    started_at: str
    ended_at: str
    enabled: bool
    stopped_reason: StoppedReason
    events: list[LifeSignEvent]
    snapshots: list[LifeSignsSnapshot]
    final_snapshot: LifeSignsSnapshot
    actual_mutations: dict[str, Any] = field(default_factory=default_actual_mutations)

    def __post_init__(self) -> None:
        assert_monitor_safe(self.actual_mutations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "enabled": self.enabled,
            "stopped_reason": self.stopped_reason,
            "events": [item.to_dict() for item in self.events],
            "snapshots": [item.to_dict() for item in self.snapshots],
            "final_snapshot": self.final_snapshot.to_dict(),
            "actual_mutations": dict(self.actual_mutations),
        }
