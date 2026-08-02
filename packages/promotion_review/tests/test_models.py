from __future__ import annotations

import pytest

from packages.promotion_review.models import PromotionReviewDecision, PromotionReviewItem, PromotionReviewSession


def test_review_item_requires_manual_review() -> None:
    item = PromotionReviewItem(
        item_id="item_1",
        candidate_id="concept:1",
        item_type="concept",
        summary="source grounded concept",
        source_refs=["wiki:1"],
        dry_run_effect="create",
        quality_score=0.9,
    )
    assert item.requires_manual_review is True

    with pytest.raises(ValueError):
        PromotionReviewItem(
            item_id="item_2",
            candidate_id="concept:2",
            item_type="concept",
            summary="bad",
            quality_score=1.2,
        )


def test_decision_cannot_be_applied_to_production() -> None:
    with pytest.raises(ValueError):
        PromotionReviewDecision(
            decision_id="decision_1",
            item_id="item_1",
            reviewer="user",
            decision="approve_for_future_manifest",
            applied_to_production=True,
        )


def test_session_invariants_block_mutation() -> None:
    with pytest.raises(ValueError):
        PromotionReviewSession(
            session_id="session_1",
            source_run_id="run",
            dry_run_report_id="report",
            verified_store_hash="verified",
            candidate_store_hash="candidate",
            production_store_mutated=True,
        )
