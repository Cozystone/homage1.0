from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


ReviewItemType = Literal["concept", "relation", "evidence", "case_frame"]
DryRunEffect = Literal["create", "merge", "strengthen", "reject", "unknown"]
Reviewer = Literal["user", "system_suggestion"]
ReviewDecision = Literal[
    "approve_for_future_manifest",
    "reject",
    "defer",
    "needs_more_evidence",
    "conflict_review",
]
ReviewStatus = Literal["draft", "in_review", "completed", "blocked"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class PromotionReviewItem:
    item_id: str
    candidate_id: str
    item_type: ReviewItemType
    summary: str
    source_refs: list[str] = field(default_factory=list)
    dry_run_effect: DryRunEffect = "unknown"
    risk_flags: list[str] = field(default_factory=list)
    quality_score: float = 0.0
    requires_manual_review: bool = True

    def __post_init__(self) -> None:
        if not self.item_id or not self.candidate_id:
            raise ValueError("review items require item_id and candidate_id")
        if not 0.0 <= float(self.quality_score) <= 1.0:
            raise ValueError("quality_score must be between 0 and 1")
        if self.requires_manual_review is not True:
            raise ValueError("promotion review items must require manual review")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PromotionReviewItem":
        return cls(**payload)


@dataclass(frozen=True)
class PromotionReviewDecision:
    decision_id: str
    item_id: str
    reviewer: Reviewer
    decision: ReviewDecision
    notes: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    applied_to_production: bool = False

    def __post_init__(self) -> None:
        if not self.decision_id or not self.item_id:
            raise ValueError("review decisions require decision_id and item_id")
        if self.applied_to_production:
            raise ValueError("promotion review decisions cannot be applied to production")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PromotionReviewDecision":
        return cls(**payload)


@dataclass(frozen=True)
class PromotionReviewSession:
    session_id: str
    source_run_id: str
    dry_run_report_id: str
    verified_store_hash: str
    candidate_store_hash: str
    items: list[PromotionReviewItem] = field(default_factory=list)
    decisions: list[PromotionReviewDecision] = field(default_factory=list)
    status: ReviewStatus = "draft"
    actual_promotion_performed: bool = False
    production_store_mutated: bool = False
    local_brain_write: bool = False
    candidate_store_mutated: bool = False
    external_llm_used: bool = False
    real_p2p_used: bool = False
    generated_code_executed: bool = False
    requires_user_approval: bool = True

    def __post_init__(self) -> None:
        if not self.session_id:
            raise ValueError("review session requires session_id")
        if self.actual_promotion_performed or self.production_store_mutated or self.local_brain_write:
            raise ValueError("review session cannot mutate production or Local Brain")
        if self.candidate_store_mutated:
            raise ValueError("review session cannot mutate candidate store")
        if self.external_llm_used or self.real_p2p_used or self.generated_code_executed:
            raise ValueError("review session cannot use external LLMs, real P2P, or generated code")
        if not self.requires_user_approval:
            raise ValueError("review session must require user approval")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["items"] = [item.to_dict() for item in self.items]
        payload["decisions"] = [decision.to_dict() for decision in self.decisions]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PromotionReviewSession":
        data = dict(payload)
        data["items"] = [PromotionReviewItem.from_dict(item) for item in data.get("items", [])]
        data["decisions"] = [PromotionReviewDecision.from_dict(decision) for decision in data.get("decisions", [])]
        return cls(**data)
