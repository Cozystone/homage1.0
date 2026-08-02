from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from packages.cgsr.cgsr.conversation_constructions import ConstructionFrame
from packages.cgsr.cgsr.korean_discourse import detect_awkward_korean_markers, score_korean_naturalness


INTERNAL_TRACE_PATTERNS: tuple[str, ...] = (
    "먼저 의도와 경계를",
    "내부적으로 점검",
    "내적 독백",
    "숨겨진 사고",
    "chain of thought",
    "scratchpad",
)

OVERCLAIM_PATTERNS: tuple[str, ...] = (
    "나는 의식을 가졌다",
    "진짜 의식",
    "AGI를 달성했다",
    "완전한 자율",
    "인간과 같은 의식",
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


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9가-힣]+", str(text or ""))


def _has_repetition(text: str) -> bool:
    tokens = _tokens(text)
    if len(tokens) < 5:
        return False
    repeated_count = len(tokens) - len(set(tokens))
    repeated_key_nouns = [token for token in tokens if token in {"상태", "기억", "후보", "대화", "경계"} and tokens.count(token) >= 2]
    return repeated_count >= max(3, len(tokens) // 3) or bool(repeated_key_nouns)


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
    token_count = len(_tokens(stripped))
    naturalness = score_korean_naturalness(stripped)

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
    awkward_markers = detect_awkward_korean_markers(stripped)
    if awkward_markers:
        reasons.extend(awkward_markers)
        score -= min(0.7, len(awkward_markers) * 0.16)
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
    score += naturalness * 0.36
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
