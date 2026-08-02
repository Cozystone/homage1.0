from __future__ import annotations

from packages.promotion_review.review_store import PromotionReviewStore


def _report() -> dict[str, object]:
    return {
        "report_id": "report_1",
        "source_run_id": "run_1",
        "verified_store_manifest_hash": "verified_hash",
        "candidate_store_manifest_hash": "candidate_hash",
        "review_items": [
            {
                "candidate_id": "concept:alpha",
                "item_type": "concept",
                "summary": "Alpha concept",
                "source_refs": ["wiki:alpha"],
                "dry_run_effect": "create",
                "risk_flags": [],
                "quality_score": 0.9,
            },
            {
                "candidate_id": "relation:beta",
                "item_type": "relation",
                "summary": "Beta relation",
                "source_refs": [],
                "dry_run_effect": "unknown",
                "risk_flags": ["no_source"],
                "quality_score": 0.2,
            },
        ],
    }


def test_store_creates_and_summarizes_review_session(tmp_path) -> None:
    store = PromotionReviewStore(tmp_path)
    session = store.create_review_session(_report())

    assert session.production_store_mutated is False
    assert session.local_brain_write is False
    assert session.candidate_store_mutated is False
    assert len(session.items) == 2
    assert store.list_review_sessions()[0].session_id == session.session_id

    updated = store.add_decision(session.session_id, session.items[0].item_id, "approve_for_future_manifest", notes="ok")
    assert len(updated.decisions) == 1
    summary = store.summarize_review_session(session.session_id)
    assert summary["decisions"] == 1
    assert summary["production_store_mutated"] is False


def test_store_rejects_unknown_item_decision(tmp_path) -> None:
    store = PromotionReviewStore(tmp_path)
    session = store.create_review_session(_report())

    try:
        store.add_decision(session.session_id, "missing", "reject")
    except KeyError as exc:
        assert "unknown review item" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected unknown item to fail")
