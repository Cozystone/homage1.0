"""SpecialCharRatioFilter: reject documents dominated by non-text symbols.

A character is "ordinary" if it is alphanumeric (``str.isalnum`` — Unicode
letters including Korean count), whitespace, or basic punctuation. Everything
else (control glyphs, box-drawing, emoji, dense symbol soup) is "special".
"""

from __future__ import annotations

from typing import ClassVar

from ..config import DataGateConfig
from ..models import Document, FilterResult
from .base import BaseFilter

# Basic punctuation that should NOT be treated as a special character.
BASIC_PUNCT = set(".,!?;:'\"()-")


def compute_special_char_ratio(text: str) -> float:
    """Fraction of characters that are neither alnum, whitespace, nor basic punct.

    Returns ``0.0`` for empty text. Deterministic and locale-independent.
    """
    if not text:
        return 0.0
    special = 0
    for ch in text:
        if ch.isalnum() or ch.isspace() or ch in BASIC_PUNCT:
            continue
        special += 1
    return special / len(text)


class SpecialCharRatioFilter(BaseFilter):
    name: ClassVar[str] = "special_char_ratio"

    def __init__(self, config: DataGateConfig) -> None:
        self.max_ratio = config.max_special_char_ratio

    def apply(self, doc: Document) -> FilterResult:
        ratio = compute_special_char_ratio(doc.text)
        metrics: dict[str, float | int] = {
            "special_char_ratio": round(ratio, 6),
            "threshold": self.max_ratio,
        }
        # Boundary at exactly max_ratio passes; only strictly-greater rejects.
        if ratio > self.max_ratio:
            return FilterResult(
                filter_name=self.name,
                passed=False,
                reason=f"special_char_ratio {ratio:.2f} > max {self.max_ratio:.2f}",
                metrics=metrics,
            )
        return FilterResult(filter_name=self.name, passed=True, metrics=metrics)
