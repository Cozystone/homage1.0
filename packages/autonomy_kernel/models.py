from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


DeficitType = Literal[
    "knowledge_gap",
    "contradiction",
    "low_confidence",
    "resource_pressure",
    "stale_memory",
    "missing_skill",
    "unresolved_user_goal",
    "promotion_needed",
]

ProposalType = Literal[
    "documentation",
    "code_patch_proposal",
    "graph_promotion_proposal",
    "research_question",
    "visualization_idea",
    "privacy_review",
    "routing_request",
]

MorningBriefType = Literal[
    "insight",
    "warning",
    "proposal",
    "completed_background_analysis",
    "blocked_need_user",
]


def _required(name: str, value: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _unit_interval(name: str, value: float) -> float:
    numeric = float(value)
    if numeric < 0.0 or numeric > 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return numeric


@dataclass(frozen=True)
class WorldModelSnapshot:
    snapshot_id: str
    concepts: int
    relations: int
    evidence: int
    unresolved_questions: list[str]
    contradictions: list[dict[str, Any]]
    confidence_gaps: list[dict[str, Any]]
    timestamp: str

    def __post_init__(self) -> None:
        _required("snapshot_id", self.snapshot_id)
        _required("timestamp", self.timestamp)
        for name in ("concepts", "relations", "evidence"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelfModelSnapshot:
    snapshot_id: str
    local_memory_count: int
    user_goals: list[str]
    recent_runs: list[dict[str, Any]]
    resource_state: dict[str, Any]
    known_limits: list[str]
    active_projects: list[str]
    timestamp: str

    def __post_init__(self) -> None:
        _required("snapshot_id", self.snapshot_id)
        _required("timestamp", self.timestamp)
        if self.local_memory_count < 0:
            raise ValueError("local_memory_count must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeficitSignal:
    signal_id: str
    deficit_type: DeficitType
    severity: float
    energy: float
    source: str
    evidence: list[dict[str, Any]]
    proposed_action: str | None = None

    def __post_init__(self) -> None:
        _required("signal_id", self.signal_id)
        _required("source", self.source)
        object.__setattr__(self, "severity", _unit_interval("severity", self.severity))
        object.__setattr__(self, "energy", _unit_interval("energy", self.energy))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AutonomyProposal:
    proposal_id: str
    proposal_type: ProposalType
    title: str
    summary: str
    rationale: str
    required_approval: bool = True
    generated_code_executed: bool = False
    mutates_production: bool = False
    mutates_local_brain: bool = False
    safety_notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _required("proposal_id", self.proposal_id)
        _required("title", self.title)
        _required("summary", self.summary)
        _required("rationale", self.rationale)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MorningBriefEvent:
    event_id: str
    title: str
    summary: str
    event_type: MorningBriefType
    priority: int
    payload: dict[str, Any]
    requires_user_action: bool

    def __post_init__(self) -> None:
        _required("event_id", self.event_id)
        _required("title", self.title)
        if self.priority < 0:
            raise ValueError("priority must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

