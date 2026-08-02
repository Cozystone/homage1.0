from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


SignalType = Literal[
    "knowledge_gap",
    "resource_pressure",
    "promotion_candidate",
    "privacy_risk",
    "stale_goal",
    "social_congress_ready",
    "voice_event",
    "sync_conflict",
]

ActionType = Literal[
    "run_quality_audit",
    "propose_promotion_review",
    "prepare_morning_brief",
    "open_atlas_congress_thread",
    "request_user_approval",
    "route_public_fragment",
    "privacy_review",
    "do_nothing",
]

RiskLevel = Literal["low", "medium", "high", "blocked"]

KernelStateName = Literal[
    "idle",
    "observing",
    "planning",
    "sandboxing",
    "awaiting_review",
    "presenting",
    "blocked",
    "safety_stop",
]


def _require_text(name: str, value: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _unit_interval(name: str, value: float) -> float:
    numeric = float(value)
    if numeric < 0.0 or numeric > 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return numeric


@dataclass(frozen=True)
class LifeSignal:
    signal_id: str
    signal_type: SignalType
    severity: float
    evidence: list[dict[str, Any]]
    source: str

    def __post_init__(self) -> None:
        _require_text("signal_id", self.signal_id)
        _require_text("source", self.source)
        object.__setattr__(self, "severity", _unit_interval("severity", self.severity))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LifeActionProposal:
    action_id: str
    action_type: ActionType
    title: str
    summary: str
    risk_level: RiskLevel
    requires_user_approval: bool = True
    mutates_production: bool = False
    mutates_local_brain: bool = False
    uses_real_p2p: bool = False
    generated_code_executed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("action_id", self.action_id)
        _require_text("title", self.title)
        _require_text("summary", self.summary)

    @property
    def safe_by_default(self) -> bool:
        return (
            self.requires_user_approval
            and not self.mutates_production
            and not self.mutates_local_brain
            and not self.uses_real_p2p
            and not self.generated_code_executed
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LifeKernelState:
    state: KernelStateName
    active_signals: list[LifeSignal] = field(default_factory=list)
    active_proposals: list[LifeActionProposal] = field(default_factory=list)
    last_event_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["active_signals"] = [signal.to_dict() for signal in self.active_signals]
        payload["active_proposals"] = [proposal.to_dict() for proposal in self.active_proposals]
        return payload
