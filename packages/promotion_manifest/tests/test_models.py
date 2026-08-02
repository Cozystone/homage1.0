from __future__ import annotations

import pytest

from packages.promotion_manifest.models import PromotionManifest, PromotionManifestItem


def test_manifest_rejects_apply_enabled() -> None:
    item = PromotionManifestItem(
        item_id="item-1",
        candidate_id="candidate-1",
        item_type="concept",
        review_decision_id="decision-1",
        dry_run_effect="create",
        approved_for_manifest=True,
        source_refs=[{"ref": "wiki:test"}],
        quality_score=0.9,
        risk_flags=[],
    )

    with pytest.raises(ValueError, match="ready or apply-enabled"):
        PromotionManifest(
            manifest_id="promotion-manifest:test",
            source_review_session_id="review-1",
            source_candidate_run_id="run-1",
            verified_store_hash_before="verified-hash",
            candidate_store_hash="candidate-hash",
            created_at="2026-01-01T00:00:00Z",
            items=[item],
            approved_count=1,
            rejected_count=0,
            deferred_count=0,
            canonical_hash="hash",
            apply_enabled=True,
        )


def test_item_requires_decision_when_approved() -> None:
    with pytest.raises(ValueError, match="review_decision_id"):
        PromotionManifestItem(
            item_id="item-1",
            candidate_id="candidate-1",
            item_type="concept",
            review_decision_id="",
            dry_run_effect="create",
            approved_for_manifest=True,
        )
