from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


AutonomyLevelName = Literal[
    "LEVEL_0_OFF",
    "LEVEL_1_OBSERVE",
    "LEVEL_2_PROACTIVE_BRIEF",
    "LEVEL_3_SANDBOX_PLANNER",
    "LEVEL_4_GATED_OPERATOR",
]
TickType = Literal[
    "startup",
    "periodic_tick",
    "morning",
    "afternoon",
    "evening",
    "idle_timeout",
    "user_returned",
    "pre_sleep",
    "post_sleep",
    "manual_ping",
]
Severity = Literal["info", "notice", "warning", "blocked"]
NeedType = Literal[
    "memory_review_needed",
    "promotion_review_needed",
    "repo_hygiene_needed",
    "morning_brief_needed",
    "quality_audit_needed",
    "voice_setup_needed",
    "p2p_blocked_by_gate",
    "local_brain_write_blocked",
    "operator_confirmation_needed",
    "user_attention_needed",
    "do_nothing",
]
ActionType = Literal[
    "observe_status",
    "prepare_morning_brief",
    "prepare_evening_brief",
    "run_mirofish_deliberation",
    "prepare_memory_review",
    "prepare_promotion_review",
    "prepare_operator_confirmation_request",
    "recommend_repo_hygiene",
    "ask_user_attention",
    "do_nothing",
]
ActionStatus = Literal["proposed", "waiting_user", "approved_for_future_gate", "rejected", "deferred", "blocked"]
RhythmMode = Literal["dormant", "observing", "curious", "deliberating", "briefing", "waiting_user", "resting", "blocked"]
SparkType = Literal[
    "revisit_stale_candidate",
    "inspect_low_quality_answer",
    "propose_memory_review",
    "propose_promotion_review",
    "start_mirofish_topic",
    "prepare_status_brief",
    "ask_user_attention",
    "do_nothing",
]


def _require_text(name: str, value: str) -> None:
    if not value:
        raise ValueError(f"{name} is required")


def default_safety() -> dict[str, Any]:
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
        "real_hot_swap_performed": False,
        "always_listening_enabled": False,
        "raw_voice_saved": False,
        "memory_apply_enabled": False,
        "requires_user_approval": True,
        "text_input_supported": True,
        "voice_optional": True,
    }


def assert_safe(safety: dict[str, Any]) -> None:
    unsafe_true = [
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
        "real_hot_swap_performed",
        "always_listening_enabled",
        "raw_voice_saved",
        "memory_apply_enabled",
    ]
    bad = {key: safety.get(key) for key in unsafe_true if bool(safety.get(key))}
    if bad:
        raise ValueError(f"Live Selfhood Cycle cannot mutate or use unsafe capabilities: {bad}")
    if safety.get("requires_user_approval") is not True:
        raise ValueError("requires_user_approval must remain true")
    if safety.get("text_input_supported") is not True:
        raise ValueError("text_input_supported must remain true")
    if safety.get("voice_optional") is not True:
        raise ValueError("voice_optional must remain true")


@dataclass(frozen=True)
class LifeCycleConfig:
    autonomy_level: AutonomyLevelName = "LEVEL_3_SANDBOX_PLANNER"
    max_actions_per_tick: int = 3
    voice_optional: bool = True
    text_input_supported: bool = True

    def __post_init__(self) -> None:
        if self.max_actions_per_tick < 0:
            raise ValueError("max_actions_per_tick must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LifeCycleTick:
    tick_id: str
    timestamp: str
    tick_type: TickType
    reason: str
    autonomy_level: AutonomyLevelName

    def __post_init__(self) -> None:
        _require_text("tick_id", self.tick_id)
        _require_text("timestamp", self.timestamp)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Observation:
    observation_id: str
    sensor: str
    status: str
    summary: str
    severity: Severity = "info"
    payload: dict[str, Any] = field(default_factory=dict)
    source_refs: list[str] = field(default_factory=list)
    read_only: bool = True

    def __post_init__(self) -> None:
        _require_text("observation_id", self.observation_id)
        _require_text("sensor", self.sensor)
        if self.read_only is not True:
            raise ValueError("observations must remain read_only")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Need:
    need_id: str
    need_type: NeedType
    summary: str
    severity: Severity = "info"
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Impulse:
    impulse_id: str
    need_type: NeedType
    urgency: float
    importance: float
    reversibility: float
    user_value: float
    cost: float
    safety: float
    reason: str
    proposed_next_step: str

    @property
    def score(self) -> float:
        return round(self.urgency + self.importance + self.reversibility + self.user_value + self.safety - self.cost, 6)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["score"] = self.score
        return payload


@dataclass(frozen=True)
class ScheduledAction:
    action_id: str
    action_type: ActionType
    title: str
    summary: str
    requires_user_approval: bool = True
    irreversible: bool = False
    can_apply_now: bool = False
    safety_flags: dict[str, Any] = field(default_factory=default_safety)

    def __post_init__(self) -> None:
        _require_text("action_id", self.action_id)
        if self.can_apply_now:
            raise ValueError("scheduled actions cannot apply in proof-only lifecycle")
        assert_safe(self.safety_flags)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionQueueItem:
    action_id: str
    action_type: ActionType
    title: str
    summary: str
    status: ActionStatus = "proposed"
    requires_user_approval: bool = True
    irreversible: bool = False
    can_apply_now: bool = False
    safety_flags: dict[str, Any] = field(default_factory=default_safety)
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.can_apply_now:
            raise ValueError("action queue items cannot apply now")
        assert_safe(self.safety_flags)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeliberationSummary:
    action_id: str
    summary: str
    objections: list[str]
    safety_notes: list[str]
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Brief:
    brief_id: str
    brief_type: Literal["morning", "evening", "status"]
    title: str
    sections: dict[str, str]
    language: Literal["ko", "en"] = "ko"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RhythmState:
    rhythm_id: str
    mode: RhythmMode
    energy: float
    curiosity: float
    uncertainty: float
    backlog_pressure: float
    user_presence: float
    resource_pressure: float
    last_tick_at: str | None
    next_tick_delay_seconds: float
    reason: str

    def __post_init__(self) -> None:
        _require_text("rhythm_id", self.rhythm_id)
        for name in ["energy", "curiosity", "uncertainty", "backlog_pressure", "user_presence", "resource_pressure"]:
            value = float(getattr(self, name))
            if value < 0.0 or value > 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0")
        if self.next_tick_delay_seconds < 0:
            raise ValueError("next_tick_delay_seconds must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RhythmPolicy:
    min_delay_seconds: float = 30.0
    max_delay_seconds: float = 3600.0
    base_delay_seconds: float = 300.0
    curiosity_weight: float = 0.3
    backlog_weight: float = 0.45
    uncertainty_weight: float = 0.35
    user_presence_weight: float = 0.25
    resource_pressure_weight: float = 0.7
    rest_recovery_rate: float = 0.1
    spark_probability_base: float = 0.05
    spark_probability_max: float = 0.35
    entropy_seed: str | None = None
    deterministic_replay: bool = True

    def __post_init__(self) -> None:
        if self.min_delay_seconds < 0 or self.max_delay_seconds < self.min_delay_seconds:
            raise ValueError("invalid rhythm delay bounds")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Spark:
    spark_id: str
    spark_type: SparkType
    trigger_reason: str
    novelty_score: float
    risk_level: Literal["low", "medium", "high"]
    proposed_action_type: ActionType
    requires_user_approval: bool = True
    can_mutate: bool = False
    can_execute: bool = False

    def __post_init__(self) -> None:
        if self.can_mutate or self.can_execute:
            raise ValueError("spark cannot mutate or execute code")
        if self.requires_user_approval is not True:
            raise ValueError("spark must require user approval")
        if self.novelty_score < 0.0 or self.novelty_score > 1.0:
            raise ValueError("novelty_score must be between 0.0 and 1.0")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RhythmDecision:
    decision_id: str
    next_mode: RhythmMode
    next_tick_delay_seconds: float
    should_observe: bool
    should_deliberate: bool
    should_brief: bool
    should_rest: bool
    spark_generated: bool
    spark: dict[str, Any] | None
    explanation: str
    safety_flags: dict[str, Any] = field(default_factory=default_safety)

    def __post_init__(self) -> None:
        _require_text("decision_id", self.decision_id)
        assert_safe({**default_safety(), **self.safety_flags})
        if self.next_tick_delay_seconds < 0:
            raise ValueError("next_tick_delay_seconds must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FreedomBudget:
    max_internal_actions_per_day: int = 64
    max_sparks_per_day: int = 12
    max_user_attention_requests_per_day: int = 4
    max_deliberations_per_day: int = 8
    max_briefs_per_day: int = 6
    max_sandbox_plans_per_day: int = 6
    current_counts: dict[str, int] = field(default_factory=dict)
    reset_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LifeEvent:
    event_id: str
    event_type: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LifeCycleResult:
    tick: LifeCycleTick
    observations: list[Observation]
    needs: list[Need]
    impulses: list[Impulse]
    scheduled_actions: list[ScheduledAction]
    queued_actions: list[ActionQueueItem]
    deliberations: list[DeliberationSummary]
    brief: Brief | None
    events: list[LifeEvent]
    safety: dict[str, Any]
    actual_mutations: dict[str, Any]
    rhythm_state: RhythmState | None = None
    rhythm_decision: RhythmDecision | None = None
    spark: Spark | None = None
    next_tick_delay_seconds: float | None = None
    freedom_budget_snapshot: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        assert_safe(self.safety)
        assert_safe({**default_safety(), **self.actual_mutations})

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick.to_dict(),
            "observations": [item.to_dict() for item in self.observations],
            "needs": [item.to_dict() for item in self.needs],
            "impulses": [item.to_dict() for item in self.impulses],
            "scheduled_actions": [item.to_dict() for item in self.scheduled_actions],
            "queued_actions": [item.to_dict() for item in self.queued_actions],
            "deliberations": [item.to_dict() for item in self.deliberations],
            "brief": self.brief.to_dict() if self.brief else None,
            "events": [item.to_dict() for item in self.events],
            "safety": dict(self.safety),
            "actual_mutations": dict(self.actual_mutations),
            "rhythm_state": self.rhythm_state.to_dict() if self.rhythm_state else None,
            "rhythm_decision": self.rhythm_decision.to_dict() if self.rhythm_decision else None,
            "spark": self.spark.to_dict() if self.spark else None,
            "next_tick_delay_seconds": self.next_tick_delay_seconds,
            "freedom_budget_snapshot": dict(self.freedom_budget_snapshot),
        }
