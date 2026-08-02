"""Entity and number locks for cross-lingual surface checks."""

from __future__ import annotations

import re


NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)*(?:%|GB|GiB|ms|s)?\b")
ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)*\b")
ENTITY_STOPWORDS = {"I", "First", "Then", "Finally", "The", "In", "Based", "For", "English", "Korean"}


def extract_number_locks(text: str) -> list[str]:
    """Return numbers that must survive surface realization."""

    return NUMBER_RE.findall(str(text or ""))


def extract_entity_locks(text: str) -> list[str]:
    """Return simple proper-noun/entity locks from English text."""

    seen: list[str] = []
    for item in ENTITY_RE.findall(str(text or "")):
        if item in ENTITY_STOPWORDS:
            continue
        if item not in seen:
            seen.append(item)
    return seen


def missing_locks(source: list[str], target_text: str) -> list[str]:
    """Return locks absent from target text."""

    target = str(target_text or "")
    return [item for item in source if item and item not in target]
