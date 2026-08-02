from __future__ import annotations

import hashlib
import re
from typing import Any

from .models import MemoryCandidate, MemoryDecision, SourceType, utc_now_iso


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
IDLIKE_RE = re.compile(r"\b(?:ssn|passport|resident|id(?:entifier)?|token|api[_-]?key)\b", re.IGNORECASE)
ADDRESS_RE = re.compile(r"\b\d{1,6}\s+[A-Za-z0-9 .'-]+(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr)\b", re.IGNORECASE)
UNCERTAIN_RE = re.compile(r"\b(?:noise|background|uncertain|inaudible|garbled|not sure|maybe)\b", re.IGNORECASE)


def _stable_id(prefix: str, payload: object) -> str:
    encoded = repr(payload).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:16]}"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _source_refs(source_type: SourceType) -> list[dict[str, Any]]:
    return [{"source_type": source_type, "provenance": "local_user_interaction", "local_only": True}]


def _has_sensitive_marker(text: str) -> bool:
    return bool(EMAIL_RE.search(text) or PHONE_RE.search(text) or IDLIKE_RE.search(text) or ADDRESS_RE.search(text))


def classify_memory_candidate(text: str, source_type: SourceType = "user_text") -> MemoryCandidate:
    """Classify a proposed memory without writing Local Brain or calling models."""

    normalized = _normalize_text(text)
    lowered = normalized.lower()
    memory_type = "unknown"
    sensitivity = "personal"
    confidence = 0.55

    if _has_sensitive_marker(normalized):
        memory_type = "sensitive"
        sensitivity = "sensitive"
        confidence = 0.92
    elif source_type == "correction" or "correction" in lowered or "remember instead" in lowered or "not that" in lowered:
        memory_type = "correction"
        sensitivity = "personal"
        confidence = 0.84
    elif source_type == "preference" or "i like" in lowered or "i prefer" in lowered or "favorite" in lowered:
        memory_type = "preference"
        sensitivity = "personal"
        confidence = 0.86
    elif source_type == "project_fact" or "atanor" in lowered or "project" in lowered or "local brain" in lowered or "cloud brain" in lowered:
        memory_type = "project_context"
        sensitivity = "public"
        confidence = 0.82
    elif "my name is" in lowered or "call me" in lowered:
        memory_type = "personal_fact"
        sensitivity = "personal"
        confidence = 0.86
    elif "goal" in lowered or "todo" in lowered or "task" in lowered:
        memory_type = "task_goal"
        sensitivity = "personal"
        confidence = 0.76

    if source_type == "voice_transcript":
        confidence = min(confidence, 0.72)
        if UNCERTAIN_RE.search(normalized):
            memory_type = "unknown"
            confidence = 0.25

    summary = normalized
    if len(summary) > 160:
        summary = summary[:157].rstrip() + "..."

    return MemoryCandidate(
        candidate_id=_stable_id("memory_candidate", {"source_type": source_type, "text": normalized}),
        source_type=source_type,
        raw_text=normalized,
        normalized_summary=summary,
        memory_type=memory_type,  # type: ignore[arg-type]
        sensitivity=sensitivity,  # type: ignore[arg-type]
        confidence=confidence,
        source_refs=_source_refs(source_type),
        created_at=utc_now_iso(),
        requires_user_approval=True,
        local_brain_write=False,
    )


def recommend_memory_decision(candidate: MemoryCandidate) -> MemoryDecision:
    """Recommend a review decision while keeping automatic memory disabled."""

    if candidate.sensitivity in {"sensitive", "secret"}:
        return "edit_required"
    if candidate.source_type == "voice_transcript":
        if candidate.confidence < 0.4 or candidate.memory_type == "unknown":
            return "defer"
        return "edit_required"
    if candidate.confidence < 0.4:
        return "defer"
    if candidate.memory_type == "unknown":
        return "defer"
    return "approve_for_future_memory_manifest"
