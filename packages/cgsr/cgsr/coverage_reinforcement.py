"""Fixture-only predicate-coverage diagnostics for CGSR Stage 2.4.

This module does not relax the global storage policy.  It builds a separate
diagnostic track from observed query cases that passed the bounded deterministic
grammar checks but were absent from the strict RHFC construction store.

Stage 2.5 proved that this case-derived track does not generalize.  New coverage
reinforcement must use corpus-wide statistics instead of evaluation rows.  The
functions in this module are kept only for reproducing the Stage 2.4 leakage
diagnostic and must not be used for production coverage promotion.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

from .rhfc_bridge import normalize_predicate


def predicate_from_canonical(canonical_form: str) -> str:
    """Extract a normalized predicate token from a canonical form."""

    for token in str(canonical_form or "").split():
        if token.startswith("PREDICATE:"):
            return normalize_predicate(token.removeprefix("PREDICATE:"))
    return ""


def strict_predicate_inventory(candidates: Iterable[dict[str, Any]]) -> set[str]:
    """Return normalized predicate coverage from strict RHFC candidates."""

    predicates: set[str] = set()
    for item in candidates:
        canonical = str((item.get("row") or {}).get("canonical_form") or "")
        predicate = predicate_from_canonical(canonical)
        if predicate:
            predicates.add(predicate)
    return predicates


def _head(text: str) -> str:
    tokens = [token for token in str(text or "").split() if token.strip()]
    return tokens[-1] if tokens else ""


def _candidate_id(case: dict[str, str]) -> str:
    payload = "|".join(
        [
            str(case.get("concept") or ""),
            normalize_predicate(str(case.get("predicate") or "")),
            str(case.get("object") or ""),
        ]
    )
    return "domain_cxf_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def make_domain_relevant_candidate(case: dict[str, str], *, source: str) -> dict[str, Any]:
    """Create one diagnostic construction candidate from an observed query."""

    predicate = normalize_predicate(str(case.get("predicate") or ""))
    obj_head = _head(str(case.get("object") or ""))
    tokens = ["TOPIC", "OBJ"]
    if obj_head:
        tokens.append(f"HEAD:{obj_head}")
    tokens.append(f"PREDICATE:{predicate}")
    family_id = _candidate_id(case)
    canonical_form = " ".join(tokens)
    example = f"{case.get('concept', 'X')} / {case.get('object', 'Y')} / {case.get('predicate', predicate)}"
    return {
        "family_id": family_id,
        "destination": "diagnostic_only",
        "priority_score": 76.0,
        "reason": f"domain_relevant_predicate_track_fixture_only_diagnostic, {source}",
        "diagnostic_only": True,
        "not_for_production": True,
        "row": {
            "family_id": family_id,
            "classification": "domain_relevant_valency_frame",
            "canonical_form": canonical_form,
            "member_count": 1,
            "reduction_contribution": 0,
            "fixed_token_count": len(tokens),
            "surface_diversity": 1.0,
            "sample_surfaces": [canonical_form],
            "sample_examples": [example],
        },
    }


def build_domain_relevant_candidates_fixture_only_diagnostic(
    case_rows: list[dict[str, Any]],
    strict_candidates: list[dict[str, Any]],
    *,
    source: str = "stage24_observed_case",
) -> list[dict[str, Any]]:
    """Build fixture-only diagnostic candidates for ok cases whose predicates are absent.

    The source rows are expected to come from the fixed 24-case benchmark.  Rows
    flagged as lexicalization issues are not promoted because they are exactly
    the class of false success Stage 2.4 is trying to avoid.

    This function intentionally consumes evaluation rows, so its output is a
    diagnostic artifact only.  It is not a valid coverage policy for CGSR.
    """

    covered = strict_predicate_inventory(strict_candidates)
    unsafe_predicates = {
        normalize_predicate(str((row.get("case") or {}).get("predicate") or ""))
        for row in case_rows
        if row.get("awkwardness_bucket") != "ok"
    }
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in case_rows:
        if row.get("awkwardness_bucket") != "ok":
            continue
        case = dict(row.get("case") or {})
        predicate = normalize_predicate(str(case.get("predicate") or ""))
        if not predicate or predicate in covered or predicate in unsafe_predicates or predicate in seen:
            continue
        rows.append(make_domain_relevant_candidate(case, source=source))
        seen.add(predicate)
    return rows


def build_domain_relevant_candidates(
    case_rows: list[dict[str, Any]],
    strict_candidates: list[dict[str, Any]],
    *,
    source: str = "stage24_observed_case",
) -> list[dict[str, Any]]:
    """Backward-compatible alias for the fixture-only diagnostic builder."""

    return build_domain_relevant_candidates_fixture_only_diagnostic(
        case_rows,
        strict_candidates,
        source=source,
    )
