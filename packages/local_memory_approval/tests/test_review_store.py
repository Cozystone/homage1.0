from __future__ import annotations

from packages.local_memory_approval.policy import classify_memory_candidate
from packages.local_memory_approval.review_store import MemoryApprovalReviewStore


def test_review_store_records_metadata_only(tmp_path) -> None:
    candidate = classify_memory_candidate("I prefer short answers.", "preference")
    store = MemoryApprovalReviewStore(tmp_path)
    session = store.create_memory_review_session([candidate])
    session = store.add_memory_decision(session.session_id, candidate.candidate_id, "approve_for_future_memory_manifest")
    loaded = store.load_memory_review_session(session.session_id)
    summary = store.summarize_memory_review_session(session.session_id)

    assert loaded.local_brain_mutated is False
    assert loaded.production_store_mutated is False
    assert loaded.decisions[0].applied_to_local_brain is False
    assert summary["local_brain_mutated"] is False
    assert summary["decision_counts"] == {"approve_for_future_memory_manifest": 1}
