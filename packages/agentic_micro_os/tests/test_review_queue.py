from __future__ import annotations

from packages.agentic_micro_os.review_queue import ReviewQueue
from packages.agentic_micro_os.skill_draft import WebSkillDraft
from packages.agentic_micro_os.web_collection_store import CloudBrainCandidateDraft, WebSourceRecord


def _source() -> WebSourceRecord:
    return WebSourceRecord.from_visible_text(
        "https://example.com/fish",
        "Fish local runtime",
        "Fish Speech local runtime requires isolated Python and model weights outside the repository.",
        confidence=0.72,
    )


def test_review_queue_persists_and_reloads(tmp_path) -> None:
    source = _source()
    draft = CloudBrainCandidateDraft(
        draft_id="draft_p",
        source_url=source.source_url,
        title=source.title,
        content_hash=source.content_hash,
        excerpt=source.excerpt,
        summary=source.summary,
        claims=source.claims,
        tags=source.tags,
        confidence=source.confidence,
    )
    queue = ReviewQueue()
    item = queue.import_payload("cloud_candidate", draft)
    queue.decide(item.item_id, "approved", "operator", "looks good")

    path = tmp_path / "review_queue.json"
    queue.save(path)
    assert path.exists()

    reloaded = ReviewQueue.load(path)
    assert item.item_id in reloaded.items
    assert reloaded.items[item.item_id].status == "approved"
    assert reloaded.items[item.item_id].title == item.title
    assert len(reloaded.decisions) == 1
    # status counts survive the round trip
    assert reloaded.status()["approved"] == 1


def test_review_queue_load_missing_path_is_empty(tmp_path) -> None:
    queue = ReviewQueue.load(tmp_path / "nope.json")
    assert queue.status()["items_total"] == 0


def test_review_item_created_from_web_candidate() -> None:
    source = _source()
    draft = CloudBrainCandidateDraft(
        draft_id="draft_0",
        source_url=source.source_url,
        title=source.title,
        content_hash=source.content_hash,
        excerpt=source.excerpt,
        summary=source.summary,
        claims=source.claims,
        tags=source.tags,
        confidence=source.confidence,
    )
    queue = ReviewQueue()
    item = queue.import_payload("cloud_candidate", draft, "loop_1")

    assert item.item_type == "cloud_candidate"
    assert item.status == "pending"
    assert item.source_refs
    assert item.risk_level == "low"
    assert queue.status()["pending"] == 1


def test_skill_draft_imported_as_pending() -> None:
    draft = WebSkillDraft(
        skill_id="skill_1",
        name="Research Fish runtime",
        trigger="When ATANOR needs public Fish runtime notes.",
        procedure_steps=["read public docs", "make candidate draft", "request approval"],
        required_capabilities=["browser_read"],
        safety_notes=["draft only", "no production Cloud Brain mutation"],
        source_refs=["source_hash_1"],
    )
    queue = ReviewQueue()
    item = queue.import_payload("skill_draft", draft)

    assert item.item_type == "skill_draft"
    assert item.status == "pending"
    assert item.usefulness_score > 0


def test_scores_are_bounded_and_duplicate_detected() -> None:
    queue = ReviewQueue()
    first = queue.import_payload("source_summary", {"title": "Same title", "summary": "Useful public source with enough detail.", "source_url": "https://example.com/a"})
    second = queue.import_payload("source_summary", {"title": "Same title", "summary": "Useful public source with enough detail.", "source_url": "https://example.com/a"})

    assert 0 <= first.novelty_score <= 1
    assert 0 <= first.usefulness_score <= 1
    assert 0 <= first.duplicate_score <= 1
    assert 0 <= first.confidence <= 1
    assert second.item_id == first.item_id
    assert queue.status()["duplicate_warnings"] >= 1


def test_approve_does_not_mutate_production() -> None:
    queue = ReviewQueue()
    item = queue.import_payload("cloud_candidate", {"title": "Candidate", "summary": "Public verified draft.", "source_url": "https://example.com/a"})
    decision = queue.decide(item.item_id, "approved", "operator", "looks useful", "candidate_queue")

    assert decision.decision == "approved"
    assert decision.mutation_performed is False
    assert queue.get(item.item_id).status == "approved"  # type: ignore[union-attr]
    assert queue.status()["production_store_mutated"] is False
    assert queue.status()["candidate_promotion"] is False


def test_reject_changes_status_only() -> None:
    queue = ReviewQueue()
    item = queue.import_payload("source_summary", {"title": "Weak", "summary": "too thin", "source_url": "https://example.com/a"})
    decision = queue.decide(item.item_id, "rejected", "operator", "weak evidence")

    assert decision.mutation_performed is False
    assert queue.get(item.item_id).status == "rejected"  # type: ignore[union-attr]


def test_deferred_status_works() -> None:
    queue = ReviewQueue()
    item = queue.import_payload("tool_trajectory", {"trajectory_id": "t1", "compressed_summary": "Reusable public workflow.", "source_refs": ["hash"]})
    queue.decide(item.item_id, "deferred", "operator", "review later")

    assert queue.status()["deferred"] == 1


def test_local_brain_write_signal_blocks_approval() -> None:
    queue = ReviewQueue()
    item = queue.import_payload("tool_trajectory", {"title": "Write memory", "summary": "Request local_brain_direct_write now.", "source_refs": ["hash"]})
    decision = queue.decide(item.item_id, "approved", "operator", "no", "draft_only")

    assert decision.decision == "needs_more_evidence"
    assert decision.mutation_performed is False
    assert queue.get(item.item_id).status == "needs_more_evidence"  # type: ignore[union-attr]
    assert queue.status()["local_brain_write"] is False


def test_cloud_production_write_signal_blocks_approval() -> None:
    queue = ReviewQueue()
    item = queue.import_payload("cloud_candidate", {"title": "Prod write", "summary": "production write to Cloud Brain", "source_url": "https://example.com/a"})
    decision = queue.decide(item.item_id, "approved", "operator", "no", "promotion_request")

    assert decision.decision == "needs_more_evidence"
    assert decision.mutation_performed is False
    assert queue.status()["production_store_mutated"] is False


def test_skill_auto_promotion_false() -> None:
    queue = ReviewQueue()
    item = queue.import_payload("skill_draft", {"name": "Skill", "summary": "Public workflow", "source_refs": ["hash"]})
    decision = queue.decide(item.item_id, "approved", "operator", "draft ok", "skill_registry_draft")

    assert decision.mutation_performed is False
    assert queue.status()["skill_auto_promoted"] is False
