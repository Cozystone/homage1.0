from __future__ import annotations

import pytest

from packages.promotion_review.manifest import PromotionManifestDraft, create_manifest_draft
from packages.promotion_review.review_store import PromotionReviewStore


def test_manifest_draft_is_never_ready_for_real_promotion(tmp_path) -> None:
    store = PromotionReviewStore(tmp_path)
    session = store.create_review_session(
        {
            "report_id": "report",
            "source_run_id": "run",
            "verified_store_manifest_hash": "verified",
            "candidate_store_manifest_hash": "candidate",
            "review_items": [
                {
                    "candidate_id": "concept:alpha",
                    "item_type": "concept",
                    "summary": "Alpha",
                    "source_refs": ["wiki:alpha"],
                    "dry_run_effect": "create",
                    "quality_score": 0.9,
                }
            ],
        }
    )
    reviewed = store.add_decision(session.session_id, session.items[0].item_id, "approve_for_future_manifest")
    manifest = create_manifest_draft(reviewed)

    assert manifest.approved_item_ids == [session.items[0].item_id]
    assert manifest.ready_for_real_promotion is False
    assert manifest.signed is False
    assert manifest.production_store_mutated is False

    with pytest.raises(ValueError):
        PromotionManifestDraft(
            manifest_id="manifest",
            source_review_session_id=session.session_id,
            approved_item_ids=[],
            rejected_item_ids=[],
            deferred_item_ids=[],
            verified_store_hash_before="verified",
            candidate_store_hash="candidate",
            created_at="now",
            ready_for_real_promotion=True,
        )
