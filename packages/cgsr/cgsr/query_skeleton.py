"""Case-role preserving query skeleton helpers for CGSR/RHFC retrieval."""

from __future__ import annotations

from typing import Any

from .induction import extract_headed_valency_frames
from .morphology import lemmatize_predicate


CaseRole = dict[str, str]


def normalize_query_predicate(predicate: str) -> str:
    """Normalize a query predicate without importing the RHFC bridge."""

    return lemmatize_predicate(str(predicate or "").strip())


def canonical_case_token(role: str, marker: str = "") -> str:
    """Return the same case-role token shape used by valency constructions."""

    if role in {"SUBJ", "TOPIC", "OBJ"}:
        return role
    if role == "ADVL":
        return f"ADVL:{marker}" if marker else "ADVL"
    return role


def case_roles_to_tokens(case_roles: list[CaseRole]) -> list[str]:
    """Convert query case-role rows to construction-compatible tokens."""

    tokens: list[str] = []
    for row in case_roles:
        role = str(row.get("role") or "")
        marker = str(row.get("marker") or "")
        if not role:
            continue
        token = canonical_case_token(role, marker)
        if token not in tokens:
            tokens.append(token)
    head = next(
        (
            str(row.get("head") or "")
            for row in case_roles
            if row.get("role") == "OBJ" and str(row.get("head") or "").strip()
        ),
        "",
    )
    if not head:
        head = next(
            (
                str(row.get("head") or "")
                for row in case_roles
                if row.get("role") in {"SUBJ", "TOPIC"} and str(row.get("head") or "").strip()
            ),
            "",
        )
    if head:
        tokens.append(f"HEAD:{head}")
    return tokens


def default_case_roles_from_flat_skeleton(skeleton: dict[str, Any]) -> list[CaseRole]:
    """Map a flat manual skeleton to explicit default case roles.

    This is intentionally simple and documented: without source particles, CGSR
    treats the concept as TOPIC and the object as OBJ.  Stage 3.2 measures how
    much this fallback limits the 24 hand-authored cases.
    """

    rows: list[CaseRole] = []
    concept = str(skeleton.get("concept") or "").strip()
    obj = str(skeleton.get("object") or "").strip()
    if concept:
        rows.append({"role": "TOPIC", "marker": "", "head": concept, "source": "manual_default"})
    if obj:
        rows.append({"role": "OBJ", "marker": "", "head": obj, "source": "manual_default"})
    return rows


def extract_case_roles_from_sentence(sentence: str, predicate: str = "") -> list[CaseRole]:
    """Extract case roles from a source sentence using valency-frame extraction."""

    normalized = normalize_query_predicate(predicate)
    frames = extract_headed_valency_frames(sentence)
    if not frames:
        return []
    selected = None
    for cases, raw_predicate in frames:
        if normalized and normalize_query_predicate(raw_predicate) == normalized:
            selected = cases
            break
    if selected is None:
        selected = frames[0][0]
    return [
        {
            "role": role,
            "marker": marker,
            "head": head,
            "source": "source_sentence_valency",
        }
        for role, marker, head in selected
    ]


def enrich_query_skeleton(
    skeleton: dict[str, Any],
    *,
    source_sentence: str | None = None,
) -> dict[str, Any]:
    """Return a query skeleton with case-role rows preserved when possible."""

    enriched = dict(skeleton)
    existing = enriched.get("case_roles")
    if isinstance(existing, list) and existing:
        enriched["case_roles"] = [
            {
                "role": str(row.get("role") or ""),
                "marker": str(row.get("marker") or ""),
                "head": str(row.get("head") or ""),
                "source": str(row.get("source") or "provided"),
            }
            for row in existing
            if isinstance(row, dict)
        ]
        return enriched
    extracted = extract_case_roles_from_sentence(source_sentence or "", str(enriched.get("predicate") or "")) if source_sentence else []
    enriched["case_roles"] = extracted or default_case_roles_from_flat_skeleton(enriched)
    enriched["case_role_source"] = "source_sentence_valency" if extracted else "manual_default"
    return enriched


def canonical_query_tokens(skeleton: dict[str, Any]) -> list[str]:
    """Return canonical query tokens aligned with construction canonical forms."""

    roles = skeleton.get("case_roles")
    if isinstance(roles, list) and roles:
        return case_roles_to_tokens([row for row in roles if isinstance(row, dict)])
    return ["TOPIC", "OBJ"]
