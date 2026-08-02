from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


IssueSeverity = Literal["info", "review", "blocker"]
CandidateKind = Literal["concept", "relation", "evidence", "case_frame"]


@dataclass(frozen=True)
class PromotionGatePolicy:
    """Dry-run-only policy for candidate promotion review."""

    min_evidence_per_source: int = 1
    require_provenance: bool = True
    require_usage_allowed: bool = True
    require_license: bool = True
    require_manual_approval: bool = True
    actual_promotion_enabled: bool = False

    def __post_init__(self) -> None:
        if self.min_evidence_per_source < 1:
            raise ValueError("min_evidence_per_source must be >= 1")
        if self.actual_promotion_enabled:
            raise ValueError("promotion gate is dry-run only; actual promotion must remain disabled")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionIssue:
    item_kind: CandidateKind
    item_key: str
    severity: IssueSeverity
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionDryRunReport:
    candidate_store_path: str
    verified_store_path: str
    actual_promotion_enabled: bool
    manual_approval_required: bool
    new_verified_nodes: int
    merged_existing_nodes: int
    new_relations: int
    strengthened_relations: int
    new_evidence: int
    new_case_frames: int
    rejected_candidates: int
    conflicts: int
    risky_items: int
    required_user_approvals: list[str]
    issues: list[PromotionIssue]
    candidate_input_counts: dict[str, int] = field(default_factory=dict)
    verified_input_counts: dict[str, int] = field(default_factory=dict)
    candidate_store_manifest_hash: str = ""
    verified_store_manifest_hash: str = ""
    source_run_id: str = ""
    source_run_status: str = ""
    sample_size: int | None = None
    rejected_duplicates: int = 0
    rejected_no_source: int = 0
    rejected_conflicts: int = 0
    rejected_low_quality: int = 0
    requires_manual_review: int = 0
    actual_promotion_performed: bool = False
    dry_run_only: bool = True
    production_store_mutated: bool = False
    local_brain_write: bool = False
    candidate_promotion: bool = False
    external_llm_used: bool = False
    real_p2p_used: bool = False
    generated_code_executed: bool = False
    mock_growth: bool = False

    def __post_init__(self) -> None:
        if self.actual_promotion_enabled or self.actual_promotion_performed or not self.dry_run_only:
            raise ValueError("dry-run report cannot enable actual promotion")
        if self.production_store_mutated or self.local_brain_write or self.candidate_promotion:
            raise ValueError("dry-run report cannot mutate stores or promote candidates")
        if self.external_llm_used or self.real_p2p_used or self.generated_code_executed:
            raise ValueError("dry-run report cannot use external LLMs, real P2P, or generated code execution")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = [issue.to_dict() for issue in self.issues]
        return payload
