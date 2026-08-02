from __future__ import annotations

from typing import Any

from .models import CandidateKind, PromotionGatePolicy, PromotionIssue
from .store_io import dedupe_key


GENERIC_PREDICATES = {"be", "have", "do", "make", "get", "use"}


def _provenance_view(row: dict[str, Any]) -> dict[str, Any]:
    """Return provenance fields from nested or flat candidate rows."""

    provenance = row.get("provenance")
    if isinstance(provenance, dict) and provenance:
        return provenance
    return row


def validate_common(
    kind: CandidateKind,
    row: dict[str, Any],
    policy: PromotionGatePolicy,
) -> list[PromotionIssue]:
    issues: list[PromotionIssue] = []
    key = dedupe_key(row, ("concept_id", "relation_id", "source_hash", "frame_id")) or "<missing-key>"
    provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
    source_view = _provenance_view(row)
    verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}

    if not row.get("dedupe_key"):
        issues.append(PromotionIssue(kind, key, "blocker", "missing_dedupe_key"))
    if policy.require_provenance and not provenance:
        if not (source_view.get("source_id") and source_view.get("license") and source_view.get("usage_allowed") is True):
            issues.append(PromotionIssue(kind, key, "blocker", "missing_provenance"))
    if policy.require_usage_allowed and source_view.get("usage_allowed") is not True:
        issues.append(PromotionIssue(kind, key, "blocker", "usage_not_allowed_or_missing"))
    if policy.require_license and not source_view.get("license"):
        issues.append(PromotionIssue(kind, key, "blocker", "missing_license"))
    if not source_view.get("source_id"):
        issues.append(PromotionIssue(kind, key, "blocker", "missing_source_id"))
    if verification.get("status") not in {"verified", "pending"}:
        issues.append(PromotionIssue(kind, key, "blocker", "verification_status_not_promotable", {"status": verification.get("status")}))
    return issues


def validate_relation(row: dict[str, Any]) -> list[PromotionIssue]:
    key = dedupe_key(row, ("relation_id",)) or "<missing-key>"
    issues: list[PromotionIssue] = []
    if not row.get("relation"):
        issues.append(PromotionIssue("relation", key, "blocker", "missing_relation_type"))
    if not row.get("source_concept_id") or not row.get("target_concept_id"):
        issues.append(PromotionIssue("relation", key, "blocker", "missing_relation_endpoint"))
    if row.get("source_concept_id") == row.get("target_concept_id"):
        issues.append(PromotionIssue("relation", key, "review", "self_relation_requires_review"))
    return issues


def validate_case_frame(row: dict[str, Any]) -> list[PromotionIssue]:
    key = dedupe_key(row, ("frame_id",)) or "<missing-key>"
    issues: list[PromotionIssue] = []
    predicate = str(row.get("predicate") or "")
    case_roles = row.get("case_roles")
    if not predicate:
        issues.append(PromotionIssue("case_frame", key, "blocker", "missing_predicate"))
    if predicate in GENERIC_PREDICATES:
        issues.append(PromotionIssue("case_frame", key, "review", "generic_predicate_requires_review", {"predicate": predicate}))
    if not isinstance(case_roles, list) or not case_roles:
        issues.append(PromotionIssue("case_frame", key, "blocker", "missing_case_roles"))
    else:
        roles = {str(role.get("role") or "") for role in case_roles if isinstance(role, dict)}
        if not roles.intersection({"SUBJ", "TOPIC", "OBJ", "ADVL"}):
            issues.append(PromotionIssue("case_frame", key, "review", "weak_case_role_structure", {"roles": sorted(roles)}))
    return issues


def validate_conflicts(kind: CandidateKind, candidate_rows: list[dict[str, Any]]) -> list[PromotionIssue]:
    by_key: dict[str, set[str]] = {}
    for row in candidate_rows:
        key = dedupe_key(row, ("concept_id", "relation_id", "frame_id"))
        if not key:
            continue
        label = str(row.get("canonical_name") or row.get("canonical_form") or row.get("relation") or "")
        by_key.setdefault(key, set()).add(label)
    return [
        PromotionIssue(kind, key, "blocker", "conflicting_candidate_values", {"values": sorted(values)})
        for key, values in by_key.items()
        if len(values) > 1
    ]
