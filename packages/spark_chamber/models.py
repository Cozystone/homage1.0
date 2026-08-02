from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


SparkSource = Literal["deficit_signal", "contradiction", "low_confidence_path", "stale_memory", "proof_fixture"]
MutationType = Literal[
    "phase_jitter",
    "relation_swap",
    "priority_jitter",
    "symbolic_gap",
    "contradiction_probe",
    "virtual_bit_flip",
]


def _required(name: str, value: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _unit(name: str, value: float) -> float:
    numeric = float(value)
    if numeric < 0.0 or numeric > 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return numeric


@dataclass(frozen=True)
class SparkInput:
    input_id: str
    source: SparkSource
    content: dict[str, Any]
    deterministic_seed: int | None = None
    allow_stochastic: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required("input_id", self.input_id)
        if not isinstance(self.content, dict):
            raise ValueError("content must be a dict")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChaosBudget:
    max_mutation_rate: float
    max_mutated_fields: int
    allow_bit_flip: bool = False
    allow_relation_swap: bool = True
    allow_phase_jitter: bool = True
    allow_priority_jitter: bool = True
    max_risk_score: float = 0.25
    production_mutation_allowed: bool = False
    local_brain_mutation_allowed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_mutation_rate", _unit("max_mutation_rate", self.max_mutation_rate))
        object.__setattr__(self, "max_risk_score", _unit("max_risk_score", self.max_risk_score))
        if self.max_mutated_fields < 0:
            raise ValueError("max_mutated_fields must be non-negative")
        if self.production_mutation_allowed:
            raise ValueError("Spark Chamber proof cannot allow production mutation")
        if self.local_brain_mutation_allowed:
            raise ValueError("Spark Chamber proof cannot allow Local Brain mutation")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MutationEvent:
    event_id: str
    mutation_type: MutationType
    before: dict[str, Any]
    after: dict[str, Any]
    risk_score: float
    reversible: bool
    applied_to_production: bool = False
    applied_to_local_brain: bool = False

    def __post_init__(self) -> None:
        _required("event_id", self.event_id)
        object.__setattr__(self, "risk_score", _unit("risk_score", self.risk_score))
        if self.applied_to_production:
            raise ValueError("mutation event must not apply to production")
        if self.applied_to_local_brain:
            raise ValueError("mutation event must not apply to Local Brain")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SparkInsight:
    insight_id: str
    source_input_id: str
    summary: str
    novelty_score: float
    coherence_score: float
    usefulness_score: float
    risk_score: float
    candidate_only: bool = True
    requires_review: bool = True
    mutates_production: bool = False
    mutates_local_brain: bool = False
    evidence: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _required("insight_id", self.insight_id)
        _required("source_input_id", self.source_input_id)
        _required("summary", self.summary)
        for name in ("novelty_score", "coherence_score", "usefulness_score", "risk_score"):
            object.__setattr__(self, name, _unit(name, getattr(self, name)))
        if not self.candidate_only:
            raise ValueError("spark insights must be candidate-only")
        if not self.requires_review:
            raise ValueError("spark insights must require review")
        if self.mutates_production:
            raise ValueError("spark insights must not mutate production")
        if self.mutates_local_brain:
            raise ValueError("spark insights must not mutate Local Brain")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SparkChamberReport:
    report_id: str
    total_mutations: int
    accepted_insights: int
    rejected_mutations: int
    chaos_budget: dict[str, Any]
    insights: list[SparkInsight]
    invariants: dict[str, Any]
    passed: bool

    def __post_init__(self) -> None:
        _required("report_id", self.report_id)
        if self.total_mutations < 0 or self.accepted_insights < 0 or self.rejected_mutations < 0:
            raise ValueError("report counts must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["insights"] = [insight.to_dict() for insight in self.insights]
        return data
