"""Corpus quality helpers for English-first CGSR benchmarks."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EnglishCorpusQuality:
    """Quality result for one English benchmark row."""

    usable: bool
    reasons: tuple[str, ...]


def validate_english_example(text: str) -> EnglishCorpusQuality:
    """Reject empty, markup-heavy, or non-English benchmark examples."""

    value = str(text or "").strip()
    reasons: list[str] = []
    if not value:
        reasons.append("empty")
    if len(value) < 8:
        reasons.append("too_short")
    latin = len(re.findall(r"[A-Za-z]", value))
    if latin / max(1, len(value)) < 0.35:
        reasons.append("low_latin_ratio")
    if re.search(r"<[^>]+>|\{\{|\}\}", value):
        reasons.append("markup_residue")
    return EnglishCorpusQuality(usable=not reasons, reasons=tuple(reasons))
