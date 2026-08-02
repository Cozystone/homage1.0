from __future__ import annotations

from packages.promotion_review.models import PromotionReviewItem
from packages.promotion_review.review_policy import recommend_decision


def _item(**kwargs: object) -> PromotionReviewItem:
    return PromotionReviewItem(
        item_id=str(kwargs.pop("item_id", "item")),
        candidate_id=str(kwargs.pop("candidate_id", "candidate")),
        item_type=kwargs.pop("item_type", "case_frame"),  # type: ignore[arg-type]
        summary=str(kwargs.pop("summary", "summary")),
        source_refs=list(kwargs.pop("source_refs", ["wiki:1"])),  # type: ignore[arg-type]
        dry_run_effect=kwargs.pop("dry_run_effect", "create"),  # type: ignore[arg-type]
        risk_flags=list(kwargs.pop("risk_flags", [])),  # type: ignore[arg-type]
        quality_score=float(kwargs.pop("quality_score", 0.9)),
    )


def test_policy_recommendations_are_deterministic() -> None:
    assert recommend_decision(_item(source_refs=[], risk_flags=["no_source"], quality_score=0.1)) == "reject"
    assert recommend_decision(_item(risk_flags=["conflict"], quality_score=0.8)) == "conflict_review"
    assert recommend_decision(_item(risk_flags=["low_quality"], quality_score=0.8)) == "needs_more_evidence"
    assert recommend_decision(_item(risk_flags=["generic_predicate"], quality_score=0.8)) == "defer"
    assert recommend_decision(_item(risk_flags=[], quality_score=0.91)) == "approve_for_future_manifest"
