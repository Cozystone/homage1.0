# -*- coding: utf-8 -*-
"""Self-awareness → answer-depth fusion.

The bridge that turns "the self HAS a state" into "the self's state CHANGES its
behaviour": when a knowledge query is about a topic the self is currently
preoccupied with (its open self-question, its last wonder, its recent insights),
ATANOR weaves MORE of that topic's grounded relations into the answer — it
answers a thing it is thinking about more deeply.

Safe by construction: depth here means MORE GROUNDED relations that already exist
in the graph, never invented content — so hallucination-0 is preserved. When the
self is not engaged with the subject, bias is 0 and nothing changes (the default
answer is untouched).
"""
from __future__ import annotations

import re
from typing import Any

_PARTICLE = re.compile(r"(은|는|이|가|을|를|의|에|에서|으로|로|와|과|도|만|이란|란)$")
_STOP = {"뭐", "뭐야", "무엇", "누구", "언제", "어디", "어떻게", "왜", "그", "저",
         "것", "거", "수", "때", "그리고", "그러나", "the", "a", "an", "of", "is",
         "what", "who", "why", "how", "about", "나", "너", "우리"}


def _tokens(text: str, min_len: int = 2) -> set[str]:
    out: set[str] = set()
    for raw in re.findall(r"[가-힣A-Za-z0-9]+", str(text or "")):
        t = _PARTICLE.sub("", raw).strip().lower()
        if len(t) >= min_len and t not in _STOP:
            out.add(t)
    return out


def _focus_texts(state: dict[str, Any]) -> list[str]:
    parts = [str(state.get("self_question", "") or "")]
    for key in ("last_inquiry_topic", "_last_inquiry_topic", "current_focus"):
        if state.get(key):
            parts.append(str(state[key]))
    for ins in (state.get("recent_insights") or [])[:6]:
        if isinstance(ins, dict) and ins.get("topic"):
            parts.append(str(ins["topic"]))
    return parts


def preoccupation(state: dict[str, Any], min_len: int = 2) -> set[str]:
    """The concepts the self is currently engaged with — drawn from its live
    state (open self-question, last wonder, recent insights)."""
    toks: set[str] = set()
    for text in _focus_texts(state):
        toks |= _tokens(text, min_len=min_len)
    return toks


def depth_bias(subject: str, state: dict[str, Any]) -> float:
    """0..1 resonance between the query subject and what the self is pondering.
    Scaled by how activated the self is (curiosity, open question)."""
    subj = str(subject or "").strip().lower()
    if not subj:
        return 0.0

    # concepts are often one syllable, so the len>=2 rule would miss them.
    pre_all = preoccupation(state, min_len=1)
    if not pre_all:
        return 0.0
    pre = preoccupation(state, min_len=2)
    subj_toks = _tokens(subject, min_len=1)
    hit = 0.0
    if subj in pre_all:
        hit = 1.0
    if hit == 0.0:
        for p in pre:
            if p == subj or p in subj or subj in p:
                hit = max(hit, 1.0)
            elif subj_toks & {p}:
                hit = max(hit, 0.75)
    if hit == 0.0 and subj_toks:
        overlap = len(subj_toks & pre_all) / max(1, len(subj_toks))
        hit = min(0.7, overlap)
    vitals = state.get("vitals") or {}
    curiosity = float(state.get("curiosity", vitals.get("curiosity", 0.5)) or 0.5)
    activation = 1.0 if state.get("self_question_open") else 0.7
    return round(min(1.0, hit * (0.55 + 0.45 * curiosity) * activation), 3)


def extra_relation_budget(bias: float, base: int = 3, cap_extra: int = 4) -> int:
    """How many MORE grounded relations to weave in for an engaged topic."""
    return base + int(round(max(0.0, min(1.0, bias)) * cap_extra))


def engagement_note(subject: str, bias: float) -> str:
    """Honest, human reason the answer went deeper (for the reasoning trace)."""
    if bias <= 0:
        return ""
    if bias >= 0.75:
        return f"지금 '{subject}'와 관련된 것을 스스로 묻고 있어, 아는 것을 더 깊이 풀었습니다."
    return f"'{subject}'가 지금 품고 있는 관심과 닿아 있어 조금 더 깊이 답했습니다."
