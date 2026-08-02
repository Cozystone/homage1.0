from __future__ import annotations

from typing import Any

from packages.promotion_review.models import PromotionReviewSession

from .hashing import manifest_id_for_hash, sha256_hex
from .models import PromotionManifest, PromotionManifestItem, PromotionManifestValidation, utc_now_iso


NO_SOURCE_FLAGS = {"no_source", "missing_source", "missing_provenance", "missing_license", "usage_not_allowed_or_missing"}
CONFLICT_FLAGS = {"conflict", "conflicting_candidate_values"}
GENERIC_FLAGS = {"generic_predicate", "generic_predicate_requires_review", "weak_case_role_structure"}

REQUIRED_GATES_V0 = {
    "cryptographic_signature_verified": False,
    "human_review_complete": False,
    "conflict_review_complete": False,
    "rollback_plan_exists": False,
    "production_apply_dry_run_passed": False,
    "backup_snapshot_exists": False,
}


def _source_ref_dicts(source_refs: list[object]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in source_refs:
        if isinstance(ref, dict):
            refs.append(dict(ref))
        else:
            refs.append({"ref": str(ref)})
    return refs


def build_manifest_from_review_session(
    session: PromotionReviewSession,
    verified_store_hash: str | None = None,
    candidate_store_hash: str | None = None,
    *,
    created_at: str | None = None,
) -> PromotionManifest:
    verified_hash = session.verified_store_hash if verified_store_hash is None else verified_store_hash
    candidate_hash = session.candidate_store_hash if candidate_store_hash is None else candidate_store_hash
    decisions_by_item = {decision.item_id: decision for decision in session.decisions}
    items: list[PromotionManifestItem] = []
    for review_item in sorted(session.items, key=lambda item: (item.item_type, item.candidate_id, item.item_id)):
        decision = decisions_by_item.get(review_item.item_id)
        if decision is None:
            continue
        approved = decision.decision == "approve_for_future_manifest"
        items.append(
            PromotionManifestItem(
                item_id=review_item.item_id,
                candidate_id=review_item.candidate_id,
                item_type=review_item.item_type,
                review_decision_id=decision.decision_id,
                dry_run_effect=review_item.dry_run_effect,
                approved_for_manifest=approved,
                source_refs=_source_ref_dicts(review_item.source_refs),
                quality_score=review_item.quality_score,
                risk_flags=list(review_item.risk_flags),
                review_notes=decision.notes,
            )
        )
    approved_count = sum(1 for item in items if item.approved_for_manifest)
    rejected_count = sum(1 for decision in session.decisions if decision.decision == "reject")
    deferred_count = sum(1 for decision in session.decisions if decision.decision in {"defer", "needs_more_evidence", "conflict_review"})
    base_payload: dict[str, Any] = {
        "manifest_version": "promotion_manifest_v0",
        "source_review_session_id": session.session_id,
        "source_candidate_run_id": session.source_run_id,
        "verified_store_hash_before": verified_hash,
        "candidate_store_hash": candidate_hash,
        "items": [item.to_dict() for item in items],
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "deferred_count": deferred_count,
        "ready_for_real_promotion": False,
        "apply_enabled": False,
        "production_store_mutated": False,
        "local_brain_write": False,
    }
    canonical_hash = sha256_hex(base_payload)
    return PromotionManifest(
        manifest_id=manifest_id_for_hash(canonical_hash),
        source_review_session_id=session.session_id,
        source_candidate_run_id=session.source_run_id,
        verified_store_hash_before=verified_hash,
        candidate_store_hash=candidate_hash,
        created_at=created_at or utc_now_iso(),
        items=items,
        approved_count=approved_count,
        rejected_count=rejected_count,
        deferred_count=deferred_count,
        canonical_hash=canonical_hash,
    )


def validate_manifest(manifest: PromotionManifest) -> PromotionManifestValidation:
    errors: list[str] = []
    warnings: list[str] = []
    if not manifest.verified_store_hash_before:
        errors.append("missing_verified_store_hash_before")
    if not manifest.candidate_store_hash:
        errors.append("missing_candidate_store_hash")
    if manifest.apply_enabled:
        errors.append("apply_enabled_must_be_false_in_v0")
    if manifest.production_store_mutated:
        errors.append("production_store_mutated_must_be_false")
    if manifest.local_brain_write:
        errors.append("local_brain_write_must_be_false")
    if manifest.ready_for_real_promotion:
        errors.append("ready_for_real_promotion_must_be_false_in_v0")

    for item in manifest.items:
        flags = set(item.risk_flags)
        if item.approved_for_manifest and not item.review_decision_id:
            errors.append(f"{item.item_id}:missing_review_decision_id")
        if item.approved_for_manifest and not item.source_refs:
            errors.append(f"{item.item_id}:approved_missing_source_refs")
        if item.approved_for_manifest and flags & NO_SOURCE_FLAGS:
            errors.append(f"{item.item_id}:approved_no_source")
        if item.approved_for_manifest and flags & CONFLICT_FLAGS:
            errors.append(f"{item.item_id}:approved_conflict")
        if item.approved_for_manifest and flags & GENERIC_FLAGS and "explicit_reviewed_note" not in item.review_notes:
            errors.append(f"{item.item_id}:approved_generic_predicate_without_explicit_note")
        if not item.source_refs:
            warnings.append(f"{item.item_id}:missing_source_refs")

    recomputed_payload = manifest.to_dict()
    recomputed_payload.pop("created_at", None)
    recomputed_payload["canonical_hash"] = manifest.canonical_hash
    if not manifest.canonical_hash:
        errors.append("missing_canonical_hash")
    return PromotionManifestValidation(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        ready_for_real_promotion=False,
        apply_enabled=False,
        required_gates=dict(REQUIRED_GATES_V0),
    )
