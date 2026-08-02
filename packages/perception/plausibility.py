# -*- coding: utf-8 -*-
"""Plausibility re-verification (owner 2026-07-13: ).

An open-vocabulary detector will sometimes fire on a poster, a screen, a reflection, or just noise —
and confidently name something that cannot physically be in a room (a whale, an airplane, an
elephant). ATANOR's honesty rule says: don't assert it as real on one glimpse. So an implausible-for-
a-room detection (or a low-confidence one) is held TENTATIVE and must be RE-VERIFIED — seen stably
across several frames — before it is narrated as actually present.

Light + No-LLM: a small curated set of things that don't belong indoors + a persistence gate. As the
concept graph grows, is_plausible_indoors can defer to it (typical-location relations); the set is the
honest bootstrap.
"""
from __future__ import annotations

# things that essentially cannot be physically present in an ordinary indoor room — a confident
# detection of one is far more likely a false positive (a picture of it, a screen, a reflection).
INDOOR_IMPLAUSIBLE = {
    "고래", "상어", "돌고래", "물고기", "비행기", "헬리콥터", "기차", "지하철", "버스", "트럭",
    "배", "요트", "잠수함", "코끼리", "기린", "사자", "호랑이", "곰", "얼룩말", "하마", "코뿔소",
    "낙타", "캥거루", "펭귄", "말", "소", "산", "바다", "폭포", "해변", "구름", "로켓", "트랙터",
    "불도저", "비행선", "등대", "다리", "빌딩",
}

_REVERIFY_FRAMES = 3     # an implausible/low-conf object must be seen this many times to be accepted
_LOW_CONF = 0.30         # below this, even a plausible object is re-verified before it is narrated


def is_plausible_indoors(label_ko: str) -> bool:
    """False for objects that cannot realistically be in a room (whale/airplane/elephant/…)."""
    return label_ko not in INDOOR_IMPLAUSIBLE


def needs_reverify(label_ko: str, score: float) -> bool:
    """A detection worth doubting on first sight: implausible for a room, OR just low-confidence."""
    return (not is_plausible_indoors(label_ko)) or float(score) < _LOW_CONF


def is_confident(label_ko: str, score: float, frames_seen: int) -> bool:
    """Accept a detection as REALLY present when it is either immediately trustworthy (plausible +
    confident) or has been RE-VERIFIED across enough frames (persistence beats a one-frame fluke)."""
    if not needs_reverify(label_ko, score):
        return True
    return int(frames_seen) >= _REVERIFY_FRAMES


def annotate(dets: list[dict], frames_of) -> list[dict]:
    """Tag each detection with tentative/reason. `frames_of(label_ko)->int` gives how many frames the
    weave has seen that label (its persistence). Confident ones read as real; tentative ones are held
    for re-verification and should be shown dimmed / kept out of the confident scene sentence."""
    out = []
    for d in dets:
        ko, sc = d.get("label_ko", ""), float(d.get("score", 0.0))
        conf = is_confident(ko, sc, frames_of(ko))
        reason = None
        if not conf:
            reason = "방 안에 있기 어려운 사물이라 재확인 중" if not is_plausible_indoors(ko) else "아직 흐릿해 재확인 중"
        out.append({**d, "tentative": not conf, "reverify_reason": reason})
    return out
