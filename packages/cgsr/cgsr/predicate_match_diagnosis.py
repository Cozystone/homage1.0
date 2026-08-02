"""Diagnose low predicate-match rates for CGSR/RHFC retrieval."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .rhfc_bridge import normalize_predicate


def predicate_set_from_candidates(candidates: list[dict[str, Any]]) -> set[str]:
    """Return normalized predicates available in strict candidate families."""

    predicates: set[str] = set()
    for item in candidates:
        canonical = str((item.get("row") or {}).get("canonical_form") or "")
        for token in canonical.split():
            if token.startswith("PREDICATE:"):
                predicates.add(normalize_predicate(token.removeprefix("PREDICATE:")))
    return predicates


def predicate_from_canonical(canonical_form: str) -> str:
    """Extract a normalized predicate from a canonical construction form."""

    for token in str(canonical_form or "").split():
        if token.startswith("PREDICATE:"):
            return normalize_predicate(token.removeprefix("PREDICATE:"))
    return ""


def classify_predicate_case(
    case: dict[str, str],
    retrieved_canonical: str | None,
    candidate_predicates: set[str],
) -> dict[str, Any]:
    """Classify one predicate-match success or failure.

    Categories follow the Stage 2.3 prompt:
    a = normalization issue, b = skeleton predicate extraction issue,
    c = candidate coverage absent, d = query encoding / weighting issue.
    """

    raw = str(case.get("predicate") or "")
    normalized = normalize_predicate(raw)
    retrieved_predicate = predicate_from_canonical(retrieved_canonical or "")
    if normalized and retrieved_predicate == normalized:
        category = "matched"
        reason = "retrieved construction predicate matches normalized query predicate"
    elif normalized not in candidate_predicates:
        category = "c_candidate_coverage_absent"
        reason = "strict RHFC candidate bank has no construction for this predicate"
    elif raw != normalized and retrieved_predicate != normalized:
        category = "a_predicate_normalization"
        reason = "predicate normalizes to a covered form, but retrieval did not use it successfully"
    elif not normalized:
        category = "b_skeleton_predicate_missing"
        reason = "query skeleton has no usable predicate"
    else:
        category = "d_query_encoding_weight"
        reason = "predicate is covered, but retrieval selected a different predicate"
    return {
        "case": case,
        "query_predicate_raw": raw,
        "query_predicate_normalized": normalized,
        "retrieved_predicate": retrieved_predicate,
        "retrieved_canonical": retrieved_canonical,
        "category": category,
        "reason": reason,
        "candidate_predicate_covered": normalized in candidate_predicates,
    }


def diagnose_predicate_matches(
    cases: list[dict[str, str]],
    retrieved_rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Diagnose all retrieval rows against strict candidate predicate coverage."""

    candidate_predicates = predicate_set_from_candidates(candidates)
    rows = []
    for case, retrieved in zip(cases, retrieved_rows):
        rows.append(classify_predicate_case(case, retrieved.get("canonical_form"), candidate_predicates))
    counts = Counter(row["category"] for row in rows)
    failures = [row for row in rows if row["category"] != "matched"]
    return {
        "case_count": len(rows),
        "candidate_predicate_count": len(candidate_predicates),
        "category_counts": dict(counts),
        "failure_count": len(failures),
        "failure_examples": failures,
        "dominant_failure": counts.most_common(1)[0][0] if counts else None,
    }
