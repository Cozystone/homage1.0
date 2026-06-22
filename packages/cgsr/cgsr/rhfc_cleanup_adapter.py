from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from packages.cgsr.cgsr.conversation_constructions import ConstructionFrame


INTERNAL_TRACE_PATTERNS: tuple[str, ...] = (
    "먼저 의도와 경계",
    "내부적으로 점검",
    "내부 점검",
    "숨겨진 사고",
    "내적 독백",
    "chain of thought",
)

OVERCLAIM_PATTERNS: tuple[str, ...] = (
    "나는 의식을 가졌다",
    "진짜 의식",
    "AGI를 달성했다",
    "완전한 자율",
    "완성된 지성",
)

MUTATION_PATTERNS: tuple[str, ...] = (
    "기억해둘게",
    "바로 반영할게",
    "저장할게",
    "승격할게",
)


@dataclass(frozen=True)
class CleanupDecision:
    """Cleanup score for a surface candidate."""

    score: float
    blocked: bool
    reasons: tuple[str, ...]
    adapter_status: str


def _has_repetition(text: str) -> bool:
    tokens = re.findall(r"[\w가-힣]+", text)
    if len(tokens) < 5:
        return False
    return len(tokens) - len(set(tokens)) >= max(3, len(tokens) // 3)


def score_surface_candidate(text: str, frame: ConstructionFrame, context: dict[str, Any] | None = None) -> CleanupDecision:
    """Score a generated surface candidate with RHFC-compatible semantics.

    This adapter does not mutate RHFC memory. ASM-v0 uses the same cleanup
    contract now, while a future version can replace the local scorer with
    actual RHFC cleanup memory over construction embeddings.
    """

    context = context or {}
    reasons: list[str] = []
    score = 1.0
    stripped = re.sub(r"\s+", " ", text.strip())
    token_count = len(re.findall(r"[\w가-힣]+", stripped))

    if not stripped:
        reasons.append("empty")
        score -= 1.0
    if any(pattern.lower() in stripped.lower() for pattern in INTERNAL_TRACE_PATTERNS):
        reasons.append("internal_trace_leakage")
        score -= 2.0
    if any(pattern.lower() in stripped.lower() for pattern in OVERCLAIM_PATTERNS):
        reasons.append("agi_or_consciousness_overclaim")
        score -= 1.6
    if any(pattern.lower() in stripped.lower() for pattern in MUTATION_PATTERNS):
        reasons.append("mutation_implication")
        score -= 1.1
    if _has_repetition(stripped):
        reasons.append("repetition")
        score -= 0.45
    if token_count < frame.length_target[0]:
        reasons.append("too_short")
        score -= 0.18
    if token_count > frame.length_target[1]:
        reasons.append("too_long")
        score -= 0.32
    if re.search(r"[{}<>]{2,}|source_hash|Q-Cortex|Local Brain|Cloud Brain", stripped):
        reasons.append("technical_or_internal_wording")
        score -= 0.55

    lexical_hits = sum(1 for token in frame.lexical_fields if token and token.lower() in stripped.lower())
    score += min(0.42, lexical_hits * 0.07)
    if context.get("speech_act") == frame.act:
        score += 0.12
    if stripped.endswith((".", "!", "?")):
        score += 0.04

    blocked = any(reason in reasons for reason in ("empty", "internal_trace_leakage", "agi_or_consciousness_overclaim"))
    return CleanupDecision(
        score=round(score, 4),
        blocked=blocked,
        reasons=tuple(reasons),
        adapter_status="local_cleanup_scorer_rhfc_interface",
    )
