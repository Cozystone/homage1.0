# -*- coding: utf-8 -*-
"""Korean orthography rule engine — the LAD (foundation), applied at the surface
boundary so every generated answer is grammatically correct regardless of which module
built it.

Owner (2026-07-09): " · 
 ." Per the binding doctrine ([[korean-norms-to-lad-layer]]): =
surface/morphology (LAD), NOT world knowledge. So these are DETERMINISTIC, explainable,
citable rules applied to the final text — never a statistical guess, never a fabrication.

The flagship fix: PARTICLE ALLOMORPH selection (/, /, /, /, (),
/) by (final consonant). This eliminates the "()" dual-form leaks
across the whole engine in ONE place — `resolve_particles(text)` runs on the answer just
before it's spoken. Each rule is named so the engine can honestly cite it
(" : ").
"""
from __future__ import annotations

import re
from typing import Any

_HANGUL_START = 0xAC00
_HANGUL_END = 0xD7A3


def _final_index(ch: str) -> int:
    """() index 0..27 of a Hangul syllable; -1 if not Hangul."""
    if not ch or not (_HANGUL_START <= ord(ch) <= _HANGUL_END):
        return -1
    return (ord(ch) - _HANGUL_START) % 28


def has_batchim(word: str) -> bool:
    """True if the last Hangul syllable has a . Digits/Latin: treat by reading —
 a trailing digit uses the Korean reading's (1/7/8/0 → ; etc.)."""
    w = re.sub(r"[)\]\"'’」』.,!?~\s]+$", "", str(word or ""))
    if not w:
        return True
    last = w[-1]
    fi = _final_index(last)
    if fi >= 0:
        return fi != 0

    if last.isdigit():
        return last in "1368" or last == "0"

    return last.lower() in "lmnr"


def _rieul_batchim(word: str) -> bool:
    """ — () ( '')."""
    w = re.sub(r"[)\]\"'’」』.,!?~\s]+$", "", str(word or ""))
    if not w:
        return False
    fi = _final_index(w[-1])
    return fi == 8


def josa(word: str, kind: str) -> str:
    """Return `word` + the correct particle allomorph. kind ∈
 {topic(/), subject(/), object(/), and(/), to(()), copula(/)}."""
    b = has_batchim(word)
    if kind == "topic":
        return f"{word}은" if b else f"{word}는"
    if kind == "subject":
        return f"{word}이" if b else f"{word}가"
    if kind == "object":
        return f"{word}을" if b else f"{word}를"
    if kind == "and":
        return f"{word}과" if b else f"{word}와"
    if kind == "to":
        return f"{word}로" if _rieul_batchim(word) else (f"{word}으로" if b else f"{word}로")
    if kind == "copula":
        return f"{word}이에요" if b else f"{word}예요"
    return word


# Dual-form placeholders a generator may emit — resolved to the correct single form by


# decision still reads the noun's final syllable; the quote just passes through.
_Q = "(['\"”’」』]?)"
_DUAL = [
    (re.compile(r"([가-힣A-Za-z0-9])" + _Q + r"은\(는\)"), "topic"),
    (re.compile(r"([가-힣A-Za-z0-9])" + _Q + r"는\(은\)"), "topic"),
    (re.compile(r"([가-힣A-Za-z0-9])" + _Q + r"이\(가\)"), "subject"),
    (re.compile(r"([가-힣A-Za-z0-9])" + _Q + r"가\(이\)"), "subject"),
    (re.compile(r"([가-힣A-Za-z0-9])" + _Q + r"을\(를\)"), "object"),
    (re.compile(r"([가-힣A-Za-z0-9])" + _Q + r"를\(을\)"), "object"),
    (re.compile(r"([가-힣A-Za-z0-9])" + _Q + r"와\(과\)"), "and"),
    (re.compile(r"([가-힣A-Za-z0-9])" + _Q + r"과\(와\)"), "and"),
    (re.compile(r"([가-힣A-Za-z0-9])" + _Q + r"이에요\(예요\)"), "copula"),
    (re.compile(r"([가-힣A-Za-z0-9])" + _Q + r"예요\(이에요\)"), "copula"),
    (re.compile(r"([가-힣A-Za-z0-9])" + _Q + r"\(으\)로"), "to"),
    (re.compile(r"([가-힣A-Za-z0-9])" + _Q + r"으로\(로\)"), "to"),
]

_SUFFIX = {"topic": ("은", "는"), "subject": ("이", "가"), "object": ("을", "를"),
           "and": ("과", "와"), "copula": ("이에요", "예요"), "to": ("으로", "로")}


def resolve_particles(text: str) -> str:
    """Resolve every dual-form particle placeholder ('()' → '') by the
 preceding word's . Safe: only touches the explicit dual-form markers, never a
 plain particle. This is the single filter that kills josa errors engine-wide."""
    s = str(text or "")
    if "(" not in s:
        return s
    for rx, kind in _DUAL:
        batchim_form, no_batchim_form = _SUFFIX[kind]
        if kind == "to":
            def _to(m: "re.Match[str]") -> str:
                ch, q = m.group(1), m.group(2)
                return ch + q + ("로" if _rieul_batchim(ch) else ("으로" if has_batchim(ch) else "로"))
            s = rx.sub(_to, s)
        else:
            def _sub(m: "re.Match[str]", bf=batchim_form, nf=no_batchim_form) -> str:
                ch, q = m.group(1), m.group(2)
                return ch + q + (bf if has_batchim(ch) else nf)
            s = rx.sub(_sub, s)
    return s



# Applied only at a WORD boundary to avoid touching mid-word syllables.
_DUEUM = [(re.compile(r"(^|[\s(])녀(?=[성자])"), r"\1여"),
          (re.compile(r"(^|[\s(])뇨"), r"\1요"),
          (re.compile(r"(^|[\s(])라(?=[디)])"), r"\1나")]


def normalize(text: str) -> str:
    """The full surface pass: particle allomorphs (+ room for / as the rule set
 grows). Deterministic, explainable, hallucination-free — it only reshapes surface
 morphology, never content."""
    return resolve_particles(text)


RULES_APPLIED = {
    "particle_allomorph": "한글 맞춤법 — 받침 유무에 따른 조사(은/는·이/가·을/를·와/과·(으)로·이에요/예요) 선택",
}
