# -*- coding: utf-8 -*-
"""Free-text MCQ → answer: parse a pasted 4 into (stem, choices) and route through the
verify-gated discriminator, so the deployed AI can actually crush a multiple-choice question a user
types — un-hallucinatable (answers only what the graph backs, else ABSTAIN).

The parser is pure SURFACE structure (which markers, where the choices split) — LAD, never a fact.
Supported choice markers: circled ①②③④, 'A)'/'A.'/'(A)', '1)'/'1.', and ///. Choices are
keyed by POSITION (A,B,C,D…) regardless of the original marker; the original label is kept for the
reply. If the text isn't clearly an MCQ (fewer than 3 sequential markers), parse_mcq returns None and
the normal answer path is untouched — so this only ever fires on a real MCQ."""
from __future__ import annotations

import re
from typing import Callable

from .discrimination import discriminate

_LETTERS = "ABCDEFGH"
_CIRCLED = "①②③④⑤⑥⑦⑧⑨"
_HANGUL = "가나다라마바사아"

# each style: a finditer pattern capturing (label) and its ordinal position in the style's alphabet
_STYLES = [
    ("circled", re.compile(r"([①②③④⑤⑥⑦⑧⑨])"), lambda m: _CIRCLED.index(m.group(1))),
    ("paren_num", re.compile(r"(?<![0-9.])([1-9])\s*[)．.]"), lambda m: int(m.group(1)) - 1),
    ("paren_alpha", re.compile(r"(?<![A-Za-z])\(?([A-Ha-h])\s*[)．.]"), lambda m: _LETTERS.index(m.group(1).upper())),
    ("hangul", re.compile(r"([가-사])\s*[)．.]"), lambda m: _HANGUL.index(m.group(1)) if m.group(1) in _HANGUL else -1),
]


def parse_mcq(text: str) -> tuple[str, dict[str, str], dict[str, str]] | None:
    """text → (stem, choices{A:…}, labels{A:orig}) or None if it isn't clearly a multiple-choice item.
    Picks the marker style whose markers form the longest strictly-increasing run (≥3)."""
    s = str(text or "").strip()
    if not s:
        return None
    best: tuple[int, list] | None = None
    for _name, pat, ordf in _STYLES:
        hits = []
        for m in pat.finditer(s):
            o = ordf(m)
            if o < 0:
                continue
            hits.append((m.start(), m.end(), o, m.group(1)))
        # keep the longest prefix that starts at ordinal 0 and increases by 1 (0,1,2,3…)
        run: list = []
        for h in hits:
            if h[2] == len(run):                 # next expected ordinal
                run.append(h)
        if len(run) >= 3 and (best is None or len(run) > len(best[1])):
            best = (len(run), run)
    if best is None:
        return None
    run = best[1]
    stem = s[: run[0][0]].strip().rstrip(":：").strip()
    choices: dict[str, str] = {}
    labels: dict[str, str] = {}
    for i, (_st, en, _o, orig) in enumerate(run):
        nxt = run[i + 1][0] if i + 1 < len(run) else len(s)
        key = _LETTERS[i]
        choices[key] = s[en:nxt].strip().strip(".．)]").strip()
        labels[key] = orig
    if not stem or any(not v for v in choices.values()):
        return None
    return stem, choices, labels


def answer_mcq(text: str, facts_about: Callable[[str], list[tuple[str, str, str]]]) -> dict | None:
    """Parse a free-text MCQ and answer it via the verify-gated discriminator. Returns a result dict
    (grounded pick + original label + basis) or an ABSTAIN dict; None if the text isn't an MCQ."""
    parsed = parse_mcq(text)
    if parsed is None:
        return None
    stem, choices, labels = parsed
    v = discriminate(stem, choices, facts_about)
    return {
        "is_mcq": True,
        "status": v.status,                                   # GROUNDED | ABSTAIN
        "choice_key": v.choice_key,                           # 'A'… (positional) or None
        "choice_label": labels.get(v.choice_key) if v.choice_key else None,
        "answer_text": choices.get(v.choice_key) if v.choice_key else None,
        "confidence": v.confidence,
        "basis": v.basis,
        "supported": v.supported,
    }
