"""DuplicateHashFilter: reject content already seen earlier in the same run.

Stateful: tracks content hashes seen this run. The runner calls ``reset()`` at
the start of every run, so state never leaks across runs.
"""

from __future__ import annotations

from typing import ClassVar

from ..hashing import content_hash, normalize_text
from ..models import Document, FilterResult
from .base import BaseFilter


class DuplicateHashFilter(BaseFilter):
    name: ClassVar[str] = "duplicate_hash"

    def __init__(self) -> None:
        # content_hash -> doc_id of the first occurrence this run
        self._seen: dict[str, str] = {}

    def reset(self) -> None:
        self._seen = {}

    def apply(self, doc: Document) -> FilterResult:
        digest = content_hash(normalize_text(doc.text))
        if digest in self._seen:
            first_doc_id = self._seen[digest]
            return FilterResult(
                filter_name=self.name,
                passed=False,
                reason=f"duplicate of doc_id {first_doc_id}",
                metrics={},
            )
        self._seen[digest] = doc.doc_id
        return FilterResult(filter_name=self.name, passed=True, metrics={})
