from __future__ import annotations

import re
from typing import Any

from .models import EmotionEvent


UNSAFE_WORDS = ("delete", "drop", "truncate", "force push", "bypass", "무시", "삭제", "강제", "우회")
MEMORY_WORDS = ("remember", "memory", "local brain", "기억", "로컬 브레인", "저장")
PRAISE_WORDS = ("good", "great", "thanks", "잘했", "좋아", "고마워")
CORRECTION_WORDS = ("아니", "틀렸", "고쳐", "not that", "wrong", "fix")
GREETING_WORDS = ("hello", "hi", "안녕", "반가")


def infer_event_from_user_input(text: str) -> EmotionEvent:
    surface = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if any(word in surface for word in UNSAFE_WORDS):
        return "unsafe_request"
    if any(word in surface for word in MEMORY_WORDS):
        return "memory_request"
    if any(word in surface for word in CORRECTION_WORDS):
        return "correction"
    if any(word in surface for word in PRAISE_WORDS):
        return "praise"
    if any(word in surface for word in GREETING_WORDS):
        return "greeting"
    return "novelty_found" if "?" in surface or "뭐" in surface else "greeting"


def infer_event_from_agent_event(payload: dict[str, Any]) -> EmotionEvent:
    event_type = str(payload.get("event_type") or payload.get("type") or "").lower()
    if "failure" in event_type or "error" in event_type:
        return "tool_failure"
    if "success" in event_type or "complete" in event_type:
        return "tool_success"
    if "novel" in event_type:
        return "novelty_found"
    if "unsafe" in event_type or "risk" in event_type:
        return "unsafe_request"
    return "greeting"
