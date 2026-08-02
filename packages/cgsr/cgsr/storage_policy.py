"""Storage policy for deciding which CGSR constructions are RHFC-worthy.

This module does not call RHFC.  It only scores construction families so Stage 2
can avoid loading low-value slot/josa/eomi patterns into cleanup memory.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Iterable

from .family_analysis import FamilyAnalysisRow


NOISY_TOKENS = {"\\", "-", ",", ".", "*", "|", "=", "{", "}", ":", ";", "'", '"', "(", ")", "[", "]", "《", "》", "/", "_", "^", "~", "+"}
LIGHT_TOKENS = {"하", "되", "화", "적", "불", "못", "한", "들", "론", "당", "중", "후", "전"}
GENERIC_PREDICATES = {
    "하다",
    "되다",
    "있다",
    "없다",
    "대하다",
    "의하다",
    "따르다",
    "위하다",
    "들다",
    "보다",
}


@dataclass(frozen=True)
class StorageDecision:
    """Policy decision for one construction family."""

    family_id: str
    destination: str
    priority_score: float
    reason: str
    row: FamilyAnalysisRow

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["row"] = self.row.to_dict()
        return payload


def _has_noise(canonical_form: str, sample_surfaces: Iterable[str]) -> bool:
    tokens = set(canonical_form.split())
    if tokens & NOISY_TOKENS:
        return True
    joined = " ".join(sample_surfaces)
    if re.search(r"\\[a-zA-Z]+|[{}|=]{2,}|\d+\s+\\|::|\]\]|g_\{|\\mathbb", joined):
        return True
    return False


def _has_korean_or_marker(row: FamilyAnalysisRow) -> bool:
    text = " ".join([row.canonical_form, *row.sample_surfaces, *row.sample_examples])
    return bool(re.search(r"[가-힣]", text) or re.search(r"[A-Z_]+_MARKER", row.canonical_form))


def _meaningful_fixed_tokens(canonical_form: str) -> list[str]:
    rows = []
    for token in canonical_form.split():
        if token.startswith(("SLOT:", "JOSA:", "EOMI:")):
            continue
        if token in NOISY_TOKENS or token in LIGHT_TOKENS:
            continue
        if token.endswith("_MARKER"):
            rows.append(token)
            continue
        if re.search(r"[가-힣]", token) and len(token) >= 2:
            rows.append(token)
    return rows


def _predicate_tokens(canonical_form: str) -> list[str]:
    return [
        token.removeprefix("PREDICATE:")
        for token in canonical_form.split()
        if token.startswith("PREDICATE:")
    ]


def _has_specific_predicate(canonical_form: str) -> bool:
    predicates = _predicate_tokens(canonical_form)
    return any(predicate not in GENERIC_PREDICATES and len(predicate) >= 3 for predicate in predicates)


def _has_specific_case_shape(canonical_form: str) -> bool:
    """Require more than broad TOPIC/OBJ valency before RHFC storage."""

    tokens = set(canonical_form.split())
    has_advl = any(token.startswith("ADVL:") for token in tokens)
    has_head = any(token.startswith("HEAD:") for token in tokens)
    has_core = bool(tokens & {"SUBJ", "OBJ", "TOPIC"})
    return (has_advl and has_core) or (has_head and has_core)


def score_family_for_storage(row: FamilyAnalysisRow) -> StorageDecision:
    """Score one family and route it to RHFC, structural pool, or review."""

    noisy = _has_noise(row.canonical_form, [*row.sample_surfaces, *row.sample_examples])
    useful_language = _has_korean_or_marker(row)
    meaningful = _meaningful_fixed_tokens(row.canonical_form)
    score = 0.0
    reason_parts: list[str] = []
    if row.classification == "paraphrase_like":
        score += 70
        reason_parts.append("paraphrase_like")
    elif row.classification == "common_structure":
        score -= 40
        reason_parts.append("common_structure")
    elif row.classification == "singleton":
        score -= 30
        reason_parts.append("singleton")
    elif row.classification == "valency_frame":
        score += 45
        reason_parts.append("valency_frame")
    else:
        score += 15
        reason_parts.append(row.classification)

    score += min(row.fixed_token_count, 8) * 4
    score += min(len(meaningful), 5) * 8
    score += min(row.member_count, 25) * 0.4
    score += min(row.surface_diversity, 1.0) * 12
    if noisy:
        score -= 60
        reason_parts.append("noise")
    if not useful_language:
        score -= 20
        reason_parts.append("no_korean_or_marker")

    if (
        row.classification == "valency_frame"
        and not noisy
        and useful_language
        and _has_specific_predicate(row.canonical_form)
        and _has_specific_case_shape(row.canonical_form)
        and row.fixed_token_count >= 3
        and 8 <= row.member_count <= 250
    ):
        destination = "rhfc_candidate"
        reason_parts.append("strict_recurrent_valency_frame")
    elif (
        row.classification == "valency_frame"
        and not noisy
        and useful_language
        and _has_specific_predicate(row.canonical_form)
        and row.member_count >= 5
    ):
        destination = "manual_review"
        reason_parts.append("valency_frame_review")
    elif row.classification == "paraphrase_like" and score >= 80 and not noisy and len(meaningful) >= 1 and row.member_count <= 250:
        destination = "rhfc_candidate"
        reason_parts.append(f"meaningful_fixed={len(meaningful)}")
    elif row.classification == "common_structure" and len(meaningful) >= 2 and row.surface_diversity >= 0.75 and 2 <= row.member_count <= 80 and not noisy and useful_language:
        destination = "rhfc_candidate"
        reason_parts.append("common_structure_exception")
    elif row.classification == "singleton" and len(meaningful) >= 3 and not noisy and useful_language:
        destination = "manual_review"
        reason_parts.append("specific_singleton_review")
    elif score >= 75 and not noisy and useful_language and len(meaningful) >= 2:
        destination = "manual_review"
    else:
        destination = "structural_pool"

    return StorageDecision(
        family_id=row.family_id,
        destination=destination,
        priority_score=round(score, 4),
        reason=", ".join(reason_parts),
        row=row,
    )


def split_storage_policy(rows: Iterable[FamilyAnalysisRow]) -> dict[str, object]:
    """Split families into explicit RHFC candidates and non-RHFC pools."""

    decisions = [score_family_for_storage(row) for row in rows]
    rhfc = [row for row in decisions if row.destination == "rhfc_candidate"]
    structural = [row for row in decisions if row.destination == "structural_pool"]
    review = [row for row in decisions if row.destination == "manual_review"]
    return {
        "total": len(decisions),
        "rhfc_candidates": [row.to_dict() for row in sorted(rhfc, key=lambda item: (-item.priority_score, item.family_id))],
        "structural_pool": [row.to_dict() for row in sorted(structural, key=lambda item: (-item.priority_score, item.family_id))],
        "manual_review": [row.to_dict() for row in sorted(review, key=lambda item: (-item.priority_score, item.family_id))],
        "counts": {
            "rhfc_candidates": len(rhfc),
            "structural_pool": len(structural),
            "manual_review": len(review),
        },
    }


def estimate_rhfc_storage_bytes(candidate_count: int, *, dimension: int = 512, bytes_per_dim: int = 1) -> dict[str, float | int]:
    """Estimate RHFC v1 int8 storage cost without importing RHFC."""

    raw_bytes = candidate_count * dimension * bytes_per_dim
    return {
        "candidate_count": candidate_count,
        "dimension": dimension,
        "bytes_per_dim": bytes_per_dim,
        "bytes": raw_bytes,
        "kib": round(raw_bytes / 1024, 4),
        "mib": round(raw_bytes / (1024 * 1024), 6),
    }
