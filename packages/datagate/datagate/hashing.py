"""Deterministic text normalization and hashing.

Determinism is the prime invariant of DataGate: the same input text must
always produce the same normalized form, the same content hash, and the same
``doc_id``. No randomness, no timestamps, no locale-dependent behavior.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")

# Length of the doc_id prefix taken from the full content hash.
DOC_ID_LENGTH = 16


def normalize_text(text: str) -> str:
    """Normalize text for hashing/dedup.

    Steps (order matters and is fixed for determinism):
      1. Unicode NFC normalization (so visually identical text hashes equal).
      2. ``strip()`` leading/trailing whitespace.
      3. Collapse every internal whitespace run to a single space.
    """
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.strip()
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized


def content_hash(normalized_text: str) -> str:
    """Full SHA-256 hex digest of already-normalized text."""
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def doc_id_for(normalized_text: str) -> str:
    """Deterministic short document id: first 16 hex chars of the content hash."""
    return content_hash(normalized_text)[:DOC_ID_LENGTH]
