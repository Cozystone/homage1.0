from __future__ import annotations

from .models import PromotionReviewItem, ReviewDecision


GENERIC_PREDICATE_FLAGS = {"generic_predicate", "generic_predicate_requires_review", "weak_case_role_structure"}
NO_SOURCE_FLAGS = {"no_source", "missing_source", "missing_provenance", "missing_license", "usage_not_allowed_or_missing"}
CONFLICT_FLAGS = {"conflict", "conflicting_candidate_values"}
LOW_QUALITY_FLAGS = {"low_quality", "missing_predicate", "missing_case_roles", "missing_relation_endpoint"}


def recommend_decision(item: PromotionReviewItem) -> ReviewDecision:
    """Return a deterministic recommendation only; never auto-apply it."""

    flags = set(item.risk_flags)
    if flags & NO_SOURCE_FLAGS or not item.source_refs:
        return "reject"
    if flags & CONFLICT_FLAGS:
        return "conflict_review"
    if flags & LOW_QUALITY_FLAGS or item.quality_score < 0.45:
        return "needs_more_evidence"
    if flags & GENERIC_PREDICATE_FLAGS:
        return "defer"
    if item.quality_score >= 0.82 and item.source_refs:
        return "approve_for_future_manifest"
    return "needs_more_evidence"
