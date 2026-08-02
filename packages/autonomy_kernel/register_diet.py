# -*- coding: utf-8 -*-
"""Register-balanced diet (owner 2026-07-13: "···, ").

MEASURED PROBLEM (corpus-composition-is-the-bottleneck): the 30k voice corpus is 52% encyclopedic
knowledge, only 2% conversational, 0% questions — so the voice recites Wikipedia stubs, and scaling
the corpus does NOT raise speaking quality (500→6000 lines flat at ~0.60). The bottleneck is
REGISTER, not size.

THE FIX — balance by register, not by source. This module:
 • classify_register(text) → one of {dialogue, commonsense, knowledge, english} (No-LLM, feature-based)
 • register_mix(lines) → the current distribution (the honest scoreboard)
 • balanced_draw(lines, k) → a training sample with EQUAL parts per register, so the voice trains on
 all four evenly instead of drowning in Wikipedia (the immediate lever, works on existing data)
 • under_registers(lines) → which registers are below the even floor, to STEER mining/sourcing there

Balanced drawing is the fast lever; the bulk fix is SOURCING the scarce registers (dialogue / English
datasets) — this module tells the miner where the gaps are. Nothing fabricated; pure classification.
"""
from __future__ import annotations

import random
import re
from typing import Any

REGISTERS = ("dialogue", "commonsense", "knowledge", "english")



# laughter/emoticon, and 2nd-person address are register-independent dialogue tells.
_DIALOGUE_END_RE = re.compile(
    r"(거든|잖아|는데|은데|던데|구나|군요|네요|더라|더라고|을까|ㄹ까|나요|까요|드릴게|할게|"
    r"해\s?줘|해\s?봐|하자|이야|거야|을래|ㄹ래|아|어|지|야|네|자|냐)$")
_LAUGH_RE = re.compile(r"[ㅋㅎ]{2}|:\)|:\(|ㅠ|ㅜ|😊|😂")
_SECOND_PERSON_RE = re.compile(r"(^|\s)(너|넌|니가|네가|당신|너희|자네)([\s은는이가을를도야]|$)")


def _is_dialogue(t: str) -> bool:
    if "?" in t or "？" in t:
        return True                                        # a question is aimed at someone
    if _LAUGH_RE.search(t) or _SECOND_PERSON_RE.search(t):
        return True
    core = re.sub(r"[\s\d.!?~…]+$", "", t)                 # strip trailing digits/punct before anchoring
    return bool(_DIALOGUE_END_RE.search(core))
# encyclopedic knowledge = SPECIFICITY (what separates it from general commonsense): a date/year, an


_KNOWLEDGE_RE = re.compile(
    r"(18|19|20)\d\d"                                       # a 4-digit year anywhere
    r"|\d+\s*(년|월|일)"                                     # date components
    r"|(특별시|광역시|특별자치|자치도|자치시|시청|도청|군청)"     # administrative places
    r"|(에\s*위치|출신|에\s*설치|소재|본사|에\s*본부|일대에|에\s*있는)"   # location / origin phrases
    r"|(촌|선수|가수|배우|감독|음반|싱글|앨범|밴드|대학교|고등학교|중학교|초등학교|팀|별|원소|행성|"
    r"은하|섬|강|산|왕|여왕|황제|장군|박사|뉴타운|리|읍|면|현|주|국|시|군|구|동)이다[\s.]*$")


def _ratios(text: str) -> tuple[float, float]:
    latin = sum(1 for c in text if "a" <= c.lower() <= "z")
    hangul = sum(1 for c in text if "가" <= c <= "힣")
    letters = latin + hangul
    if letters == 0:
        return 0.0, 0.0
    return latin / letters, hangul / letters


def classify_register(text: str) -> str:
    """One of REGISTERS. Order matters: English by script, then conversation by interactive grammar,
    then encyclopedic by date/stub markers, else general commonsense (the default declarative)."""
    t = " ".join(str(text or "").split())
    latin_r, hangul_r = _ratios(t)
    alpha = sum(1 for c in t if c.isalpha())
    if hangul_r < 0.15 and latin_r >= 0.5 and alpha >= 6:
        return "english"
    if _is_dialogue(t):
        return "dialogue"
    if _KNOWLEDGE_RE.search(t):
        return "knowledge"
    return "commonsense"


def register_mix(lines: list[str]) -> dict[str, Any]:
    """The honest scoreboard: counts + fractions per register over a set of lines."""
    counts = {r: 0 for r in REGISTERS}
    for ln in lines:
        counts[classify_register(ln)] += 1
    n = max(1, len(lines))
    return {"total": len(lines), "counts": counts,
            "fractions": {r: round(counts[r] / n, 4) for r in REGISTERS}}


def bucketize(lines: list[str]) -> dict[str, list[str]]:
    b: dict[str, list[str]] = {r: [] for r in REGISTERS}
    for ln in lines:
        b[classify_register(ln)].append(ln)
    return b


def balanced_draw(lines: list[str], k: int, rng: random.Random | None = None) -> list[str]:
    """Draw ~k lines with EQUAL representation per register (round-robin over shuffled buckets). A
    scarce register contributes all it has; the remainder is spread over the registers that still have
    material — so the sample is as balanced as the data allows, never Wikipedia-dominated. This is the
    immediate lever: even on today's 52%-knowledge corpus, the voice now trains on the four registers
    evenly."""
    rng = rng or random.Random()
    buckets = bucketize(lines)
    for r in REGISTERS:
        rng.shuffle(buckets[r])
    cursors = {r: 0 for r in REGISTERS}
    out: list[str] = []
    order = list(REGISTERS)
    while len(out) < k:
        progressed = False
        for r in order:
            if len(out) >= k:
                break
            if cursors[r] < len(buckets[r]):
                out.append(buckets[r][cursors[r]])
                cursors[r] += 1
                progressed = True
        if not progressed:
            break                                          # every bucket exhausted
    return out


def under_registers(lines: list[str], floor: float = 0.20) -> list[str]:
    """Registers whose share is below the even floor (1/len = 0.25 target; default 0.20) — the gaps to
    STEER mining/sourcing toward, so the diet fills what the voice is starved of (dialogue, English)."""
    frac = register_mix(lines)["fractions"]
    return [r for r in REGISTERS if frac[r] < floor]
