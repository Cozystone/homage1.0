"""MinLengthFilter: reject documents that are too short."""

from __future__ import annotations

from typing import ClassVar

from ..config import DataGateConfig
from ..models import Document, FilterResult
from .base import BaseFilter


class MinLengthFilter(BaseFilter):
    name: ClassVar[str] = "min_length"

    def __init__(self, config: DataGateConfig) -> None:
        self.min_chars = config.min_chars

    def apply(self, doc: Document) -> FilterResult:
        char_count = len(doc.text.strip())
        metrics: dict[str, float | int] = {
            "char_count": char_count,
            "threshold": self.min_chars,
        }
        if char_count < self.min_chars:
            return FilterResult(
                filter_name=self.name,
                passed=False,
                reason=f"char_count {char_count} < min {self.min_chars}",
                metrics=metrics,
            )
        return FilterResult(filter_name=self.name, passed=True, metrics=metrics)
