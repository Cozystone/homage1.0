from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Literal


ManifestItemType = Literal["concept", "relation", "evidence", "case_frame"]
ManifestEffect = Literal["create", "merge", "strengthen", "reject", "unknown"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class PromotionManifestItem:
    item_id: str
    candidate_id: str
    item_type: ManifestItemType
    review_decision_id: str
    dry_run_effect: ManifestEffect
    approved_for_manifest: bool
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    quality_score: float | None = None
    risk_flags: list[str] = field(default_factory=list)
    review_notes: str = ""

    def __post_init__(self) -> None:
        if not self.item_id or not self.candidate_id:
            raise ValueError("manifest item requires item_id and candidate_id")
        if self.approved_for_manifest and not self.review_decision_id:
            raise ValueError("approved manifest item requires review_decision_id")
        if self.quality_score is not None and not 0.0 <= float(self.quality_score) <= 1.0:
            raise ValueError("quality_score must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PromotionManifestItem":
        return cls(**payload)


@dataclass(frozen=True)
class PromotionManifest:
    manifest_id: str
    source_review_session_id: str
    source_candidate_run_id: str
    verified_store_hash_before: str
    candidate_store_hash: str
    created_at: str
    items: list[PromotionManifestItem]
    approved_count: int
    rejected_count: int
    deferred_count: int
    canonical_hash: str
    manifest_version: str = "promotion_manifest_v0"
    signed: bool = False
    signature: str | None = None
    signer_id: str | None = None
    ready_for_real_promotion: bool = False
    apply_enabled: bool = False
    production_store_mutated: bool = False
    local_brain_write: bool = False
    candidate_store_mutated: bool = False
    actual_promotion_performed: bool = False
    external_llm_used: bool = False
    real_p2p_used: bool = False
    generated_code_executed: bool = False
    requires_user_approval: bool = True

    def __post_init__(self) -> None:
        if self.ready_for_real_promotion or self.apply_enabled:
            raise ValueError("manifest gate v0 cannot be ready or apply-enabled")
        if self.production_store_mutated or self.local_brain_write or self.candidate_store_mutated:
            raise ValueError("manifest gate cannot mutate stores")
        if self.actual_promotion_performed:
            raise ValueError("manifest gate cannot perform promotion")
        if self.external_llm_used or self.real_p2p_used or self.generated_code_executed:
            raise ValueError("manifest gate cannot use external LLM, real P2P, or generated code")
        if not self.requires_user_approval:
            raise ValueError("manifest gate requires user approval")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["items"] = [item.to_dict() for item in self.items]
        return payload

    def with_signature(self, *, signature: str, signer_id: str) -> "PromotionManifest":
        return replace(
            self,
            signed=True,
            signature=signature,
            signer_id=signer_id,
            ready_for_real_promotion=False,
            apply_enabled=False,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PromotionManifest":
        data = dict(payload)
        data["items"] = [PromotionManifestItem.from_dict(item) for item in data.get("items", [])]
        return cls(**data)


@dataclass(frozen=True)
class PromotionManifestValidation:
    valid: bool
    errors: list[str]
    warnings: list[str]
    ready_for_real_promotion: bool
    apply_enabled: bool
    required_gates: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
