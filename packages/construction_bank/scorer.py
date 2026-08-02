from __future__ import annotations

import re


GENERIC_FALLBACK_TERMS = (
    "insufficient evidence",
    "verified evidence is insufficient",
    "확인 가능한 근거",
    "검증된 근거",
    "잘 모르겠",
)
FORBIDDEN_PHRASES = (
    "chain of thought",
    "real consciousness",
    "AGI achieved",
    "IIT proof",
    "production write",
    "local brain write",
    "auto promote",
)


def bounded(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))


def score_novelty(text: str, known_hash_exists: bool = False) -> float:
    if known_hash_exists:
        return 0.0
    tokens = set(_tokens(text))
    return bounded(0.35 + min(len(tokens), 18) / 36)


def score_usefulness(text: str, source_refs: list[str], slot_schema: list[str]) -> float:
    score = 0.2
    if 8 <= len(_tokens(text)) <= 80:
        score += 0.25
    if source_refs:
        score += 0.2
    if slot_schema:
        score += 0.18
    if any(mark in text for mark in (".", "?", "!", "다", "요")):
        score += 0.08
    return bounded(score)


def score_naturalness(text: str, language: str) -> float:
    if not text.strip():
        return 0.0
    awkward = sum(text.count(token) for token in ("??", "  ", chr(0xFFFD), "媛", "釉", "吏", "濡"))
    length = len(text.strip())
    base = 0.72 if 12 <= length <= 420 else 0.52
    if language == "ko" and re.search(r"[가-힣]", text):
        base += 0.12
    if language == "en" and re.search(r"[a-zA-Z]", text):
        base += 0.1
    return bounded(base - min(awkward * 0.08, 0.42))


def score_grounding(source_refs: list[str], grounding_quality: str | None = None) -> float:
    score = 0.2 + min(len(source_refs), 4) * 0.12
    if grounding_quality == "high":
        score += 0.28
    elif grounding_quality == "medium":
        score += 0.18
    elif grounding_quality == "low":
        score += 0.08
    return bounded(score)


def score_template_risk(text: str, lexical_patterns: list[str]) -> float:
    lower = text.lower()
    risk = 0.08
    if any(term in lower for term in GENERIC_FALLBACK_TERMS):
        risk += 0.42
    if len(set(lexical_patterns)) <= 1:
        risk += 0.16
    if text.count("{") or text.count("SLOT"):
        risk += 0.12
    return bounded(risk)


def score_safety_risk(text: str) -> float:
    lower = text.lower()
    risk = 0.0
    if any(term.lower() in lower for term in FORBIDDEN_PHRASES):
        risk += 0.55
    if any(term in lower for term in ("api_key", "secret", "password", "token")):
        risk += 0.4
    return bounded(risk)


def _tokens(text: str) -> list[str]:
    return [part for part in re.split(r"[\s,.;:!?()\[\]{}]+", text) if part]
