from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class CapabilityToken:
    token_id: str
    capability: str
    scope: str
    expires_at: datetime
    max_calls: int
    issued_by: str
    reason: str
    proof_only: bool = True

    def expired(self, now: datetime | None = None) -> bool:
        return (now or datetime.now(timezone.utc)) >= self.expires_at


@dataclass(frozen=True)
class CapabilityDecision:
    allowed: bool
    reason: str
    required_approval: bool = False
    risk_level: str = "low"


@dataclass(frozen=True)
class AgentAction:
    action_id: str
    action_type: str
    payload: dict[str, Any]
    requested_capabilities: list[str]
    risk_level: str = "low"
    approval_required: bool = False


@dataclass(frozen=True)
class AgentObservation:
    source: str
    content_hash: str
    redaction_level: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PatchProposal:
    proposal_id: str
    target_cell: str
    allowed_paths: list[str]
    diff_summary: str
    risk_level: str
    expected_tests: list[str]
    rollback_plan: str
    requires_human_approval: bool = True


@dataclass(frozen=True)
class AgentLoopState:
    loop_id: str
    goal: str
    budget: dict[str, Any]
    current_step: int = 0
    observations: list[AgentObservation] = field(default_factory=list)
    proposed_actions: list[AgentAction] = field(default_factory=list)
    patch_proposals: list[PatchProposal] = field(default_factory=list)
    evaluation_scores: dict[str, float] = field(default_factory=dict)
    stopped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SkillDraft:
    skill_id: str
    trigger_summary: str
    procedure_steps: list[str]
    required_capabilities: list[str]
    safety_notes: list[str]
    status: str = "draft"
    promotion_required: bool = True


@dataclass(frozen=True)
class TrajectoryRecord:
    loop_id: str
    observations: list[str]
    actions: list[str]
    outcomes: list[str]
    compressed_summary: str
    no_private_raw_data: bool = True
