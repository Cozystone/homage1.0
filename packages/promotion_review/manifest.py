from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any

from .models import PromotionReviewSession, utc_now_iso


@dataclass(frozen=True)
class PromotionManifestDraft:
    manifest_id: str
    source_review_session_id: str
    approved_item_ids: list[str]
    rejected_item_ids: list[str]
    deferred_item_ids: list[str]
    verified_store_hash_before: str
    candidate_store_hash: str
    created_at: str
    signed: bool = False
    signature: str | None = None
    ready_for_real_promotion: bool = False
    actual_promotion_performed: bool = False
    production_store_mutated: bool = False
    local_brain_write: bool = False

    def __post_init__(self) -> None:
        if self.ready_for_real_promotion:
            raise ValueError("manifest draft cannot be ready for real promotion before a future signature gate")
        if self.signed or self.signature:
            raise ValueError("manifest draft is unsigned in v0")
        if self.actual_promotion_performed or self.production_store_mutated or self.local_brain_write:
            raise ValueError("manifest draft cannot mutate stores")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _manifest_id(session: PromotionReviewSession) -> str:
    payload = {
        "session_id": session.session_id,
        "decisions": [decision.to_dict() for decision in session.decisions],
    }
    digest = hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()[:16]
    return f"promotion_manifest_draft_{digest}"


def create_manifest_draft(session: PromotionReviewSession) -> PromotionManifestDraft:
    approved = [decision.item_id for decision in session.decisions if decision.decision == "approve_for_future_manifest"]
    rejected = [decision.item_id for decision in session.decisions if decision.decision == "reject"]
    deferred = [
        decision.item_id
        for decision in session.decisions
        if decision.decision in {"defer", "needs_more_evidence", "conflict_review"}
    ]
    return PromotionManifestDraft(
        manifest_id=_manifest_id(session),
        source_review_session_id=session.session_id,
        approved_item_ids=approved,
        rejected_item_ids=rejected,
        deferred_item_ids=deferred,
        verified_store_hash_before=session.verified_store_hash,
        candidate_store_hash=session.candidate_store_hash,
        created_at=utc_now_iso(),
        signed=False,
        signature=None,
        ready_for_real_promotion=False,
    )
