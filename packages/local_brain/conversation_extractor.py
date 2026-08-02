"""Deterministic extraction of user facts from a conversation turn.

No LLM and no canned answers — this is pattern-based *information extraction*
(allowed under the no-rule-based-ANSWERS philosophy: it produces structured data,
not the spoken reply). It is intentionally conservative: it only emits a fact when
a clear self-statement pattern matches, so the Local Brain never accumulates
guesses about the user.

Returns a list of ``(kind, subject, value, confidence)`` tuples.
"""

from __future__ import annotations

import re
from typing import Literal


FactKind = Literal["preference", "identity", "info"]

# Stop at a clause boundary so we capture just the salient span.
_END = r"(?:을|를|이|가|은|는|이라고|라고|에|에서|이야|예요|이에요|야|입니다|이라|\.|,|!|\?|$| and | but |\.)"

_KO_PATTERNS: list[tuple[FactKind, str, re.Pattern[str]]] = [
    ("identity", "name", re.compile(r"(?:내\s*이름은|제\s*이름은|나는|저는)\s*([^\s].{0,30}?)\s*(?:이?라고\s*해|이?야|예요|이에요|입니다|라고\s*불러)")),
    ("preference", "likes", re.compile(r"(?:나는|저는|난|전)\s*([^.!?]{1,20}?)\s*(?:을|를|이|가)\s*(?:정말\s*|진짜\s*)?(?:좋아해|좋아한다|좋아합니다|선호해|선호합니다)")),
    ("preference", "dislikes", re.compile(r"(?:나는|저는|난|전)\s*([^.!?]{1,20}?)\s*(?:을|를|이|가)\s*(?:싫어해|싫어한다|싫어합니다)")),
    ("info", "job", re.compile(r"(?:내\s*직업은|나는|저는|제\s*일은)\s*([^\s].{0,30}?)\s*(?:이?에요|예요|입니다|이야|야|로\s*일해|으로\s*일해|를\s*해)")),
    ("info", "location", re.compile(r"(?:나는|저는|난|전)\s*([^\s].{0,30}?)\s*(?:에|에서)\s*(?:살아|살아요|삽니다|거주해|거주합니다)")),
]

_EN_PATTERNS: list[tuple[FactKind, str, re.Pattern[str]]] = [
    ("identity", "name", re.compile(r"\b(?:my name is|i am called|call me|i'm)\s+([A-Z][\w'-]{1,30})", re.IGNORECASE)),
    ("preference", "likes", re.compile(r"\bi\s+(?:really\s+)?(?:like|love|prefer|enjoy)\s+(.{1,40}?)(?:\.|,|!|\?|$| and | but )", re.IGNORECASE)),
    ("preference", "dislikes", re.compile(r"\bi\s+(?:really\s+)?(?:dislike|hate|don'?t like|do not like)\s+(.{1,40}?)(?:\.|,|!|\?|$| and | but )", re.IGNORECASE)),
    ("info", "job", re.compile(r"\bi\s+(?:work as|am)\s+(?:an?\s+)?([\w '-]{2,30}?)(?:\.|,|!|\?|$| and | but )", re.IGNORECASE)),
    ("info", "location", re.compile(r"\bi\s+live\s+in\s+([\w '-]{2,40}?)(?:\.|,|!|\?|$| and | but )", re.IGNORECASE)),
]

# Never accumulate sensitive identifiers even if a pattern catches them.
_SENSITIVE = re.compile(r"\b(?:password|api[_ ]?key|secret|token|ssn|card number|주민등록|비밀번호|카드번호)\b", re.IGNORECASE)


def _clean(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" .,!?;:\"'~…")
    return value


def extract_user_facts(user_text: str, language: str = "ko") -> list[tuple[FactKind, str, str, float]]:
    text = str(user_text or "").strip()
    if not text or _SENSITIVE.search(text):
        return []
    # A question is not a self-statement — never accumulate from it. Facts are

    if "?" in text or "？" in text:
        return []
    patterns = _KO_PATTERNS if re.search(r"[가-힣]", text) else _EN_PATTERNS
    facts: list[tuple[FactKind, str, str, float]] = []
    seen: set[tuple[str, str]] = set()
    for kind, subject, pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        value = _clean(match.group(1))
        # reject too-short / pronoun-only / question captures
        low = value.lower()
        if len(value) < 2 or low in {"i", "me", "my", "나", "저", "너", "뭐", "what", "who"}:
            continue

        # question turn never pollutes memory
        if re.search(r"(뭐|뭘|뭣|무엇|뭔|누구|어디|언제|어떻)", value) or low.startswith(("what ", "who ", "where ", "내가", "제가", "너가", "네가")):
            continue
        if _SENSITIVE.search(value):
            continue
        key = (subject, value.lower())
        if key in seen:
            continue
        seen.add(key)
        facts.append((kind, subject, value, 0.75))
    return facts
