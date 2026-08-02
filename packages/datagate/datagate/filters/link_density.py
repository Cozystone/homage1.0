"""LinkDensityFilter: reject documents that are mostly URLs / link lists.

Link density is the fraction of characters that belong to a URL. Both bare
URLs (``https?://...``) and markdown link targets (``[text](url)``) count.
Overlapping matches are unioned via a coverage mask so characters are never
double-counted.
"""

from __future__ import annotations

import re
from typing import ClassVar

from ..config import DataGateConfig
from ..models import Document, FilterResult
from .base import BaseFilter

_URL_RE = re.compile(r"https?://\S+")
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def compute_link_density(text: str) -> float:
    """Fraction of characters covered by a URL or markdown link target.

    Returns ``0.0`` for empty text. Deterministic.
    """
    if not text:
        return 0.0
    covered = bytearray(len(text))
    for match in _URL_RE.finditer(text):
        for i in range(match.start(), match.end()):
            covered[i] = 1
    for match in _MD_LINK_RE.finditer(text):
        # group(1) is the URL inside the parentheses
        for i in range(match.start(1), match.end(1)):
            covered[i] = 1
    return sum(covered) / len(text)


class LinkDensityFilter(BaseFilter):
    name: ClassVar[str] = "link_density"

    def __init__(self, config: DataGateConfig) -> None:
        self.max_ratio = config.max_link_density

    def apply(self, doc: Document) -> FilterResult:
        ratio = compute_link_density(doc.text)
        metrics: dict[str, float | int] = {
            "link_density": round(ratio, 6),
            "threshold": self.max_ratio,
        }
        if ratio > self.max_ratio:
            return FilterResult(
                filter_name=self.name,
                passed=False,
                reason=f"link_density {ratio:.2f} > max {self.max_ratio:.2f}",
                metrics=metrics,
            )
        return FilterResult(filter_name=self.name, passed=True, metrics=metrics)
