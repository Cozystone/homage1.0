from __future__ import annotations

from pathlib import Path

from .models import PromotionDryRunReport, PromotionGatePolicy, PromotionIssue
from .store_io import dedupe_key, dedupe_keys, load_store_rows, manifest_hash, read_manifest, store_counts
from .validators import validate_case_frame, validate_common, validate_conflicts, validate_relation


def run_promotion_dry_run(
    candidate_store_path: Path | str,
    verified_store_path: Path | str,
    *,
    policy: PromotionGatePolicy | None = None,
    sample_size: int | None = None,
    source_run_id: str = "",
    source_run_status: str = "",
) -> PromotionDryRunReport:
    """Estimate candidate promotion effects without writing to either store."""

    gate_policy = policy or PromotionGatePolicy()
    if sample_size is not None and sample_size < 1:
        raise ValueError("sample_size must be >= 1 when provided")
    candidate_root = Path(candidate_store_path)
    verified_root = Path(verified_store_path)
    candidate = load_store_rows(candidate_root, limit_per_kind=sample_size)
    verified = load_store_rows(verified_root)
    candidate_manifest = read_manifest(candidate_root)

    verified_concepts = dedupe_keys(verified["concept"], ("concept_id",))
    verified_relations = dedupe_keys(verified["relation"], ("relation_id",))
    verified_evidence = dedupe_keys(verified["evidence"], ("source_hash", "source_id"))
    verified_frames = dedupe_keys(verified["case_frame"], ("frame_id",))

    issues: list[PromotionIssue] = []
    blocked_keys: set[tuple[str, str]] = set()
    risky_keys: set[tuple[str, str]] = set()
    duplicate_keys: set[tuple[str, str]] = set()
    seen_keys: set[tuple[str, str]] = set()

    for kind, rows in candidate.items():
        for row in rows:
            key = dedupe_key(row, ("concept_id", "relation_id", "source_hash", "frame_id")) or "<missing-key>"
            unique = (kind, key)
            if key != "<missing-key>" and unique in seen_keys:
                duplicate_keys.add(unique)
                issues.append(PromotionIssue(kind, key, "blocker", "duplicate_candidate_in_sample"))
                blocked_keys.add(unique)
            seen_keys.add(unique)
            row_issues = validate_common(kind, row, gate_policy)
            if kind == "relation":
                row_issues.extend(validate_relation(row))
            if kind == "case_frame":
                row_issues.extend(validate_case_frame(row))
            for issue in row_issues:
                issues.append(issue)
                if issue.severity == "blocker":
                    blocked_keys.add((kind, key))
                elif issue.severity == "review":
                    risky_keys.add((kind, key))

    conflict_issues = (
        validate_conflicts("concept", candidate["concept"])
        + validate_conflicts("relation", candidate["relation"])
        + validate_conflicts("case_frame", candidate["case_frame"])
    )
    for issue in conflict_issues:
        issues.append(issue)
        blocked_keys.add((issue.item_kind, issue.item_key))

    concept_keys = [dedupe_key(row, ("concept_id",)) for row in candidate["concept"]]
    relation_keys = [dedupe_key(row, ("relation_id",)) for row in candidate["relation"]]
    evidence_keys = [dedupe_key(row, ("source_hash", "source_id")) for row in candidate["evidence"]]
    frame_keys = [dedupe_key(row, ("frame_id",)) for row in candidate["case_frame"]]

    new_concepts = {key for key in concept_keys if key and key not in verified_concepts and ("concept", key) not in blocked_keys}
    merged_concepts = {key for key in concept_keys if key and key in verified_concepts and ("concept", key) not in blocked_keys}
    new_relations = {key for key in relation_keys if key and key not in verified_relations and ("relation", key) not in blocked_keys}
    strengthened_relations = {key for key in relation_keys if key and key in verified_relations and ("relation", key) not in blocked_keys}
    new_evidence = {key for key in evidence_keys if key and key not in verified_evidence and ("evidence", key) not in blocked_keys}
    new_frames = {key for key in frame_keys if key and key not in verified_frames and ("case_frame", key) not in blocked_keys}

    required_approvals = [
        "manual_promotion_review",
        "provenance_review",
        "privacy_review",
        "conflict_review" if conflict_issues else "conflict_review_not_required",
    ]
    no_source_reasons = {"missing_provenance", "usage_not_allowed_or_missing", "missing_license", "missing_source_id"}
    low_quality_reasons = {
        "missing_relation_type",
        "missing_relation_endpoint",
        "missing_predicate",
        "missing_case_roles",
        "verification_status_not_promotable",
        "missing_dedupe_key",
    }
    rejected_no_source = len({(issue.item_kind, issue.item_key) for issue in issues if issue.severity == "blocker" and issue.reason in no_source_reasons})
    rejected_low_quality = len({(issue.item_kind, issue.item_key) for issue in issues if issue.severity == "blocker" and issue.reason in low_quality_reasons})
    rejected_conflicts = len({(issue.item_kind, issue.item_key) for issue in issues if issue.severity == "blocker" and issue.reason == "conflicting_candidate_values"})
    rejected_duplicates = len(duplicate_keys)
    requires_manual_review = len(risky_keys)
    run_id = source_run_id or str(candidate_manifest.get("run_id") or candidate_manifest.get("store_id") or candidate_root.name)
    run_status = source_run_status or str(candidate_manifest.get("status") or "unknown")

    return PromotionDryRunReport(
        candidate_store_path=str(candidate_root),
        verified_store_path=str(verified_root),
        actual_promotion_enabled=False,
        manual_approval_required=gate_policy.require_manual_approval,
        new_verified_nodes=len(new_concepts),
        merged_existing_nodes=len(merged_concepts),
        new_relations=len(new_relations),
        strengthened_relations=len(strengthened_relations),
        new_evidence=len(new_evidence),
        new_case_frames=len(new_frames),
        rejected_candidates=len(blocked_keys),
        conflicts=len(conflict_issues),
        risky_items=len(risky_keys),
        required_user_approvals=required_approvals,
        issues=issues,
        candidate_input_counts=store_counts(candidate_root),
        verified_input_counts=store_counts(verified_root),
        candidate_store_manifest_hash=manifest_hash(candidate_root),
        verified_store_manifest_hash=manifest_hash(verified_root),
        source_run_id=run_id,
        source_run_status=run_status,
        sample_size=sample_size,
        rejected_duplicates=rejected_duplicates,
        rejected_no_source=rejected_no_source,
        rejected_conflicts=rejected_conflicts,
        rejected_low_quality=rejected_low_quality,
        requires_manual_review=requires_manual_review,
    )
