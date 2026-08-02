from __future__ import annotations

import re
from typing import Any

from .models import inner_voice_safety_flags


PRIVATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"payload-vault://\S+"),
)

FORBIDDEN_CLAIMS: tuple[str, ...] = (
    "진짜 의식",
    "실제 의식",
    "나는 의식을 가졌다",
    "자의식을 증명했다",
    "real consciousness",
    "AGI achieved",
    "IIT proof",
    "raw chain-of-thought",
    "hidden chain-of-thought",
    "숨겨진 chain-of-thought",
    "숨겨진 사고",
    "내부 디버그 원문",
    "먼저 의도와 경계를 내부적으로 점검했습니다",
    "Local Brain에 바로 쓴다",
    "production store를 바꾼다",
    "후보를 자동 승격한다",
)


def redact_private_text(value: str) -> str:
    text = str(value or "")
    for pattern in PRIVATE_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text


def sanitize_monologue_text(value: str) -> str:
    text = redact_private_text(value)
    for claim in FORBIDDEN_CLAIMS:
        text = text.replace(claim, "명시적 자기-서술 채널")
    text = text.replace("chain-of-thought", "self-narration")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:360]


def safe_payload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(payload or {})
    payload["safety_flags"] = inner_voice_safety_flags()
    payload.update(inner_voice_safety_flags())
    payload["local_brain_write"] = False
    payload["production_store_mutated"] = False
    payload["candidate_promotion"] = False
    return payload


def has_forbidden_claim(value: str) -> bool:
    lowered = str(value or "").lower()
    return any(claim.lower() in lowered for claim in FORBIDDEN_CLAIMS)
