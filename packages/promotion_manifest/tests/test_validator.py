from __future__ import annotations

from dataclasses import replace

from packages.promotion_manifest.proof import _reviewed_session
from packages.promotion_manifest.validator import build_manifest_from_review_session, validate_manifest


def test_build_manifest_counts_review_decisions(tmp_path) -> None:
    session = _reviewed_session(str(tmp_path))
    manifest = build_manifest_from_review_session(session, created_at="2026-01-01T00:00:00Z")

    assert manifest.approved_count == 1
    assert manifest.rejected_count == 1
    assert manifest.deferred_count == 2
    assert manifest.ready_for_real_promotion is False
    assert manifest.apply_enabled is False
    assert manifest.production_store_mutated is False
    assert manifest.local_brain_write is False
    assert manifest.candidate_store_mutated is False
    assert validate_manifest(manifest).valid is True


def test_no_source_conflict_and_generic_items_are_blocked_when_approved(tmp_path) -> None:
    session = _reviewed_session(str(tmp_path))
    manifest = build_manifest_from_review_session(session, created_at="2026-01-01T00:00:00Z")

    forced = replace(
        manifest,
        items=[
            replace(item, approved_for_manifest=True)
            if item.candidate_id in {"evidence:no_source", "relation:conflict", "case_frame:generic"}
            else item
            for item in manifest.items
        ],
    )
    errors = validate_manifest(forced).errors

    assert any("approved_no_source" in error for error in errors)
    assert any("approved_conflict" in error for error in errors)
    assert any("approved_generic_predicate_without_explicit_note" in error for error in errors)


def test_generic_predicate_can_only_pass_with_explicit_reviewed_note(tmp_path) -> None:
    session = _reviewed_session(str(tmp_path))
    manifest = build_manifest_from_review_session(session, created_at="2026-01-01T00:00:00Z")
    forced = replace(
        manifest,
        items=[
            replace(item, approved_for_manifest=True, review_notes="explicit_reviewed_note: manually checked")
            if item.candidate_id == "case_frame:generic"
            else item
            for item in manifest.items
        ],
    )

    errors = validate_manifest(forced).errors
    assert not any("approved_generic_predicate_without_explicit_note" in error for error in errors)


def test_missing_hashes_are_invalid(tmp_path) -> None:
    session = _reviewed_session(str(tmp_path))
    manifest = build_manifest_from_review_session(
        session,
        verified_store_hash="",
        candidate_store_hash="",
        created_at="2026-01-01T00:00:00Z",
    )

    assert {"missing_verified_store_hash_before", "missing_candidate_store_hash"} <= set(validate_manifest(manifest).errors)
