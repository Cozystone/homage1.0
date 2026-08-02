"""Minimal English construction induction for Stage E1 benchmarks."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from .canonical_frames import EnglishConstructionFrame
from .construction_patterns import core_english_frames


FAMILY_KEYWORDS = {
    "definition": (" is a ", " is an ", " refers to "),
    "comparison": (" while ", " compared with ", " whereas "),
    "procedure": ("first,", "then,", "finally,"),
    "cause_effect": ("leads to", "because", "therefore"),
    "limitation": ("limitation", "cannot", "risk"),
    "example": ("for example", "such as"),
    "summary": ("in short", "overall"),
    "evidence_based_claim": ("based on", "evidence", "supported by"),
    "abstention": ("not have enough", "insufficient evidence"),
}


def classify_sentence(sentence: str) -> str:
    """Classify an English example into a construction family."""

    lowered = str(sentence or "").casefold()
    for family, keywords in FAMILY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return family
    return "summary"


def induce_english_frames(sentences: Iterable[str], *, min_frequency: int = 1) -> list[EnglishConstructionFrame]:
    """Return core frames whose family appears in the training examples."""

    counts = Counter(classify_sentence(sentence) for sentence in sentences)
    available = {family for family, count in counts.items() if count >= min_frequency}
    return [frame for frame in core_english_frames() if frame.family in available]
