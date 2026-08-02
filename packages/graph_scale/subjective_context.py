# -*- coding: utf-8 -*-
"""Subjective context — the SAME behaviour means different things by valence.

Owner's point (2026-07-09): lingering 20s at the Genesis while saying " 
" (admiration) vs " .. " (skepticism)
are OPPOSITE reads of the same dwell. Interest MAGNITUDE (dwell) and interest
VALENCE (what was felt) are orthogonal; real context integrates every signal into
the person's SUBJECTIVITY. So an observation carries not just 'how long' but 'how
felt', read from the concurrent utterance.

No-LLM, lexicon-based v0 (transparent: the matched cues are stored, so the read is
auditable, never a mind-reading claim). Ambiguous → neutral. This is deliberately
humble: a heuristic valence the AI can voice AS an interpretation, and correct if
the user pushes back. The richer version (subtle human interaction) is what the
director floated learning from movie SCREENPLAYS — noted as a corpus for later.
"""
from __future__ import annotations

import re
from typing import Any

# admiration / positive desire
_POS = ("대박", "멋지", "멋있", "최고", "죽인", "끝내주", "예쁘", "이쁘", "갖고싶", "사고싶",
        "훌륭", "감탄", "우와", "와우", "좋다", "좋네", "좋은데", "마음에", "쩐다", "지린",
        "amazing", "awesome", "wow", "love", "beautiful", "incredible", "stunning",
        "gorgeous", "want", "impressive")
# skepticism / doubt / difficulty (interested but unsure)
_SKEPT = ("쉽지 않", "되겠나", "될까", "가능할까", "글쎄", "과연", "애매", "의문", "무리",
          "힘들", "어렵", "고민", "긴가민가", "잘 모르겠", "괜찮을까", "음…", "음...",
          "hmm", "not sure", "doubt", "tough", "hard to", "risky", "can it", "really work",
          "we'll see", "iffy", "questionable")
# negative / dislike
_NEG = ("별로", "싫", "실망", "아쉽", "그저 그", "그저그", "최악", "구리", "촌스", "노잼",
        "meh", "bad", "disappointing", "worst", "ugly", "boring", "overrated")


_NEGATORS = ("안", "못", "별로", "not", "no ", "n't", "안이", "하나도")


def _hits(text: str, cues: tuple[str, ...], *, drop_negated: bool = False) -> list[str]:
    low = text.lower()
    out = []
    for c in cues:
        i = text.find(c)
        if i < 0:
            i = low.find(c)
        if i < 0:
            continue
        if drop_negated:
            pre = (text[max(0, i - 4):i] + low[max(0, i - 4):i]).lower()
            if any(n in pre for n in _NEGATORS):
                continue
        out.append(c)
    return out


def valence_from_utterance(text: str) -> dict[str, Any]:
    """Read the felt valence of what was said. Returns stance + a [-1,1] valence
 + the matched cues (auditable). Neutral when no cue or a tie. Simple negation
 handling: a positive cue preceded by //not is not counted as positive."""
    text = (text or "").strip()
    pos = _hits(text, _POS, drop_negated=True)
    skept, neg = _hits(text, _SKEPT), _hits(text, _NEG)
    score = len(pos) - len(neg) - 0.5 * len(skept)
    if skept and not neg and len(skept) >= len(pos):
        stance = "skeptical"          # interested but doubtful — the key third read
    elif score > 0:
        stance = "admiring"
    elif score < 0:
        stance = "negative"
    else:
        stance = "neutral"
    valence = max(-1.0, min(1.0, (len(pos) - len(neg) - 0.5 * len(skept)) / 2.0))
    return {"stance": stance, "valence": round(valence, 3),
            "cues": (pos + skept + neg)[:6]}


# how the AI voices the read, per stance — honest to the felt context, not a
# blanket 'impressed'. A skeptical dwell must NOT be read as admiration.
_PHRASE = {
    "admiring": "감탄하며 보셨던",
    "skeptical": "긴가민가하며 오래 보셨던",
    "negative": "탐탁잖아 하셨던",
    "neutral": "한참 보셨던",
}


def interpret(dwell_seconds: float, utterance: str = "") -> dict[str, Any]:
    """Fuse interest MAGNITUDE (dwell) with interest VALENCE (utterance) into a
    subjective read. High dwell + admiring = strong liking; high dwell + skeptical
    = engaged-but-doubtful; these are genuinely different, and the phrasing follows."""
    v = valence_from_utterance(utterance)
    engaged = dwell_seconds >= 5.0
    if not engaged:
        read = "passing"                         # a glance — didn't really land
    elif v["stance"] == "admiring":
        read = "admired"
    elif v["stance"] == "skeptical":
        read = "engaged_but_doubtful"
    elif v["stance"] == "negative":
        read = "disliked_yet_lingered"
    else:
        read = "interested"
    return {"read": read, "stance": v["stance"], "valence": v["valence"],
            "phrase": _PHRASE.get(v["stance"], "한참 보셨던"), "cues": v["cues"],
            "note": "subjective read fused from dwell + utterance valence (heuristic, auditable)"}
