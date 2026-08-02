from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


DeliberationRole = Literal[
    "skeptic",
    "builder",
    "domain_expert",
    "privacy_guard",
    "router",
    "synthesis_chair",
    "promotion_judge",
]
Recommendation = Literal["approve_for_review", "needs_more_evidence", "blocked"]


@dataclass(frozen=True)
class DeliberationInput:
    """Local proof-only deliberation input with no private raw payloads."""

    topic: str
    evidence_refs: list[str]
    contradictions: list[str] = field(default_factory=list)
    privacy_report: dict[str, Any] = field(default_factory=dict)
    router_report: dict[str, Any] = field(default_factory=dict)
    candidate_metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.topic:
            raise ValueError("topic is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RoleStatement:
    role: DeliberationRole
    stance: str
    findings: list[str]
    blocks_promotion: bool = False

    def __post_init__(self) -> None:
        if not self.stance:
            raise ValueError("stance is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeliberationResult:
    topic: str
    transcript: list[RoleStatement]
    objections: list[str]
    synthesis: str
    promotion_recommendation: Recommendation
    requires_manual_approval: bool
    morning_brief_candidate: str
    production_store_mutated: bool = False
    local_brain_write: bool = False
    external_llm_used: bool = False
    real_p2p_used: bool = False
    candidate_promotion: bool = False

    def __post_init__(self) -> None:
        if self.production_store_mutated or self.local_brain_write or self.external_llm_used:
            raise ValueError("proof deliberation cannot mutate stores or use external LLMs")
        if self.real_p2p_used or self.candidate_promotion:
            raise ValueError("proof deliberation cannot use real P2P or promote candidates")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["transcript"] = [statement.to_dict() for statement in self.transcript]
        return payload
