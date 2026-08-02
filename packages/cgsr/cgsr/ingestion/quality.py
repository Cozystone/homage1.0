"""Quality, duplicate, and corroboration checks for verified ingestion."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from .korean_text_quality import validate_korean_sentence
from .verification_gate import has_mock_signal, normalize_for_dedupe


CORE_ROLES = {"TOPIC", "SUBJ"}
DEPENDENT_ROLES = {"OBJ", "ADVL"}
GENERIC_HEADS = {"것", "수", "등", "때", "곳", "년", "일", "내", "차", "말"}


@dataclass(frozen=True)
class QualityDecision:
    """Human-readable quality label for one case frame."""

    label: str
    reasons: tuple[str, ...]
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "reasons": list(self.reasons), "score": round(self.score, 4)}


def normalized_frame_signature(frame: dict[str, Any], *, mask_heads: bool = False) -> str:
    """Return a stable signature used for duplicate/corroboration checks."""

    predicate = normalize_for_dedupe(str(frame.get("predicate") or ""))
    roles = []
    for role in frame.get("case_roles") or []:
        if not isinstance(role, dict):
            continue
        role_name = str(role.get("role") or "")
        marker = str(role.get("marker") or "")
        head = "*" if mask_heads else normalize_for_dedupe(str(role.get("head") or ""))
        roles.append(f"{role_name}:{marker}:{head}")
    roles.sort()
    return f"{predicate}|{'|'.join(roles)}"


def frame_hash(frame: dict[str, Any], *, mask_heads: bool = False) -> str:
    """Return a compact hash for a normalized frame signature."""

    return hashlib.sha256(normalized_frame_signature(frame, mask_heads=mask_heads).encode("utf-8")).hexdigest()[:20]


def quality_decision(frame: dict[str, Any]) -> QualityDecision:
    """Classify whether a case frame is reusable Korean construction material."""

    reasons: list[str] = []
    score = 1.0
    canonical = str(frame.get("canonical_form") or "")
    predicate = str(frame.get("predicate") or "")
    language = str(frame.get("language") or "")
    roles = [row for row in frame.get("case_roles") or [] if isinstance(row, dict)]
    provenance = frame.get("provenance") or {}
    verification = frame.get("verification") or {}

    if has_mock_signal(json.dumps(frame, ensure_ascii=False)):
        return QualityDecision("No", ("mock_signal",), 0.0)
    if language != "ko":
        reasons.append("language_not_ko")
        score -= 0.35
    if verification.get("status") != "verified":
        reasons.append("not_verified")
        score -= 0.5
    if not provenance.get("license") or not provenance.get("source_hash"):
        reasons.append("incomplete_provenance")
        score -= 0.5
    if not predicate or not re.search(r"[가-힣]", predicate):
        reasons.append("missing_korean_predicate")
        score -= 0.45
    if predicate:
        predicate_quality = validate_korean_sentence(predicate, expect_korean=True)
        if not predicate_quality.is_valid:
            reasons.append(f"predicate_text_quality:{predicate_quality.issues[0]}")
            score -= 0.45
    if predicate and not predicate.endswith("다"):
        reasons.append("predicate_not_lemma")
        score -= 0.15
    if not roles:
        reasons.append("missing_case_roles")
        score -= 0.5
    if len(roles) == 1:
        reasons.append("single_case_role")
        score -= 0.2
    if len(roles) > 8:
        reasons.append("overlong_case_frame")
        score -= 0.2
    role_names = {str(row.get("role") or "") for row in roles}
    if not (role_names & CORE_ROLES):
        reasons.append("no_topic_or_subject")
        score -= 0.15
    if not (role_names & DEPENDENT_ROLES):
        reasons.append("no_object_or_adverbial")
        score -= 0.15
    generic_count = sum(1 for row in roles if str(row.get("head") or "") in GENERIC_HEADS)
    if roles and generic_count / len(roles) > 0.5:
        reasons.append("mostly_generic_heads")
        score -= 0.25
    if len(re.findall(r"\d", canonical)) / max(1, len(canonical)) > 0.25:
        reasons.append("numeric_heavy_frame")
        score -= 0.25
    if any(token in canonical for token in ("섬네일", "대체글", "...", "파일:")):
        reasons.append("markup_residue")
        score -= 0.35
    canonical_quality = validate_korean_sentence(canonical, expect_korean=False)
    if not canonical_quality.is_valid:
        reasons.append(f"canonical_text_quality:{canonical_quality.issues[0]}")
        score -= 0.35
    for role in roles:
        marker_quality = validate_korean_sentence(str(role.get("marker") or ""), expect_korean=True)
        if not marker_quality.is_valid:
            reasons.append(f"marker_text_quality:{marker_quality.issues[0]}")
            score -= 0.25
            break
        head_quality = validate_korean_sentence(str(role.get("head") or ""), expect_korean=False)
        if not head_quality.is_valid:
            reasons.append(f"head_text_quality:{head_quality.issues[0]}")
            score -= 0.25
            break

    if score >= 0.72:
        label = "Yes"
    elif score >= 0.45:
        label = "Ambiguous"
    else:
        label = "No"
    return QualityDecision(label, tuple(reasons or ["reusable_case_frame"]), max(0.0, score))


def quality_audit(frames: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate every frame and summarize quality labels/reasons."""

    rows = []
    counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for index, frame in enumerate(frames):
        decision = quality_decision(frame)
        counts[decision.label] += 1
        reasons.update(decision.reasons)
        rows.append(
            {
                "index": index,
                "frame_id": frame.get("frame_id"),
                "predicate": frame.get("predicate"),
                "language": frame.get("language"),
                "canonical_form": frame.get("canonical_form"),
                "quality": decision.to_dict(),
            }
        )
    total = len(rows)
    return {
        "total": total,
        "counts": dict(counts),
        "ratios": {key: round(value / max(1, total), 4) for key, value in counts.items()},
        "reason_counts": dict(reasons),
        "rows": rows,
        "samples": {
            "yes": [row for row in rows if row["quality"]["label"] == "Yes"][:10],
            "ambiguous": [row for row in rows if row["quality"]["label"] == "Ambiguous"][:10],
            "no": [row for row in rows if row["quality"]["label"] == "No"][:10],
        },
    }


def near_duplicate_report(frames: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Estimate exact and template-like duplicate rates for case frames."""

    rows = list(frames)
    exact = Counter(frame_hash(frame, mask_heads=False) for frame in rows)
    structural = Counter(frame_hash(frame, mask_heads=True) for frame in rows)
    exact_duplicates = sum(count - 1 for count in exact.values() if count > 1)
    structural_duplicates = sum(count - 1 for count in structural.values() if count > 1)
    total = len(rows)
    return {
        "total": total,
        "exact_duplicate_count": exact_duplicates,
        "exact_duplicate_rate": round(exact_duplicates / max(1, total), 4),
        "structural_duplicate_count": structural_duplicates,
        "structural_duplicate_rate": round(structural_duplicates / max(1, total), 4),
        "top_structural_duplicates": structural.most_common(10),
    }


def corroboration_report(frames: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Compute deterministic multi-source support counts for similar frames."""

    rows = list(frames)
    support: dict[str, set[str]] = defaultdict(set)
    exact_support: dict[str, set[str]] = defaultdict(set)
    for frame in rows:
        provenance = frame.get("provenance") or {}
        source_hash = str(frame.get("source_hash") or provenance.get("source_hash") or "")
        source_id = str(provenance.get("source_id") or source_hash)
        if not source_hash:
            continue
        support[normalized_frame_signature(frame, mask_heads=True)].add(source_id)
        exact_support[normalized_frame_signature(frame, mask_heads=False)].add(source_id)
    counts = [len(values) for values in support.values()]
    exact_counts = [len(values) for values in exact_support.values()]
    bucket = Counter(counts)
    exact_bucket = Counter(exact_counts)
    return {
        "structural_signature_count": len(support),
        "exact_signature_count": len(exact_support),
        "corroboration_count_distribution": dict(sorted(bucket.items())),
        "exact_corroboration_count_distribution": dict(sorted(exact_bucket.items())),
        "multi_source_structural_ratio": round(sum(1 for value in counts if value >= 2) / max(1, len(counts)), 4),
        "multi_source_exact_ratio": round(sum(1 for value in exact_counts if value >= 2) / max(1, len(exact_counts)), 4),
    }


def quality_gate(
    frames: Iterable[dict[str, Any]],
    *,
    min_yes_ratio: float = 0.5,
    max_structural_duplicate_rate: float = 0.65,
) -> dict[str, Any]:
    """Return whether a batch is safe to commit."""

    frame_rows = list(frames)
    quality = quality_audit(frame_rows)
    duplicates = near_duplicate_report(frame_rows)
    yes_ratio = quality["ratios"].get("Yes", 0.0)
    passed = yes_ratio >= min_yes_ratio and duplicates["structural_duplicate_rate"] <= max_structural_duplicate_rate
    reasons = []
    if yes_ratio < min_yes_ratio:
        reasons.append("quality_yes_ratio_below_threshold")
    if duplicates["structural_duplicate_rate"] > max_structural_duplicate_rate:
        reasons.append("structural_duplicate_rate_above_threshold")
    return {
        "passed": passed,
        "reasons": reasons or ["quality_and_duplicate_gate_passed"],
        "quality": {k: v for k, v in quality.items() if k != "rows"},
        "duplicates": duplicates,
    }
