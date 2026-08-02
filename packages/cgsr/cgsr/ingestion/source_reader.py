"""Licensed source reader for verified Cloud Brain ingestion."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import Iterable

from .korean_text_quality import HANGUL_RE, normalize_korean_text


TAG_RE = re.compile(r"<[^>]+>")
TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)\|?([^\]]*)\]\]")


@dataclass(frozen=True)
class SourceSentence:
    """A raw sentence with complete source provenance."""

    text: str
    language: str
    source_id: str
    source_name: str
    source_type: str
    source_hash: str
    document_id: str
    title: str
    url: str
    license: str
    usage_allowed: bool
    collected_at: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable mapping."""

        return asdict(self)

    @property
    def provenance(self) -> dict[str, object]:
        """Return the schema-level provenance block for this sentence."""

        return {
            "source_id": self.source_id,
            "source_hash": self.source_hash,
            "source_type": self.source_type,
            "document_id": self.document_id,
            "title": self.title,
            "url": self.url,
            "license": self.license,
            "usage_allowed": self.usage_allowed,
            "collected_at": self.collected_at,
        }


def utc_now() -> str:
    """Return a stable UTC timestamp string."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(value: str, *, prefix: str = "") -> str:
    """Return a deterministic SHA-256 hash with an optional prefix."""

    digest = hashlib.sha256(normalize_korean_text(str(value)).encode("utf-8")).hexdigest()
    return f"{prefix}{digest}" if prefix else digest


def clean_source_text(text: str) -> str:
    """Remove lightweight wiki/HTML markup while preserving sentence text."""

    value = normalize_korean_text(str(text or ""))
    value = TAG_RE.sub(" ", value)
    value = TEMPLATE_RE.sub(" ", value)
    value = WIKI_LINK_RE.sub(lambda match: match.group(2) or match.group(1), value)
    value = re.sub(r"\[https?://[^\s\]]+\s*([^\]]*)\]", r"\1", value)
    value = re.sub(r"'{2,}", "", value)
    value = re.sub(r"[|=]{2,}", " ", value)
    value = re.sub(r"\s+", " ", value)
    return normalize_korean_text(value)


def read_utf8_text_strict(path: str | Path) -> str:
    """Read a corpus text file as strict UTF-8 and NFC-normalize it.

    Canonical verified ingestion must fail on decode errors rather than using
    ``errors="ignore"`` or ``errors="replace"``.  Audit-only scripts may choose
    a lossy mode, but source ingestion should not.
    """

    return normalize_korean_text(Path(path).read_text(encoding="utf-8", errors="strict"))


def split_sentences(text: str, *, min_len: int = 12, max_len: int = 240) -> list[str]:
    """Split cleaned Korean text into bounded sentence candidates."""

    cleaned = clean_source_text(text)
    parts = re.split(r"(?<=[.!?。！？])\s+|(?<=[다요죠음함됨됨])\s+", cleaned)
    rows: list[str] = []
    for part in parts:
        sentence = part.strip(" \t\r\n-•*")
        if not sentence:
            continue
        if len(sentence) < min_len or len(sentence) > max_len:
            continue
        if not HANGUL_RE.search(sentence):
            continue
        rows.append(sentence)
    return rows


def detect_language(sentence: str) -> str:
    """Return a coarse deterministic language tag."""

    value = str(sentence or "")
    hangul = len(HANGUL_RE.findall(value))
    latin = len(re.findall(r"[A-Za-z]", value))
    if hangul and hangul >= latin:
        return "ko"
    if latin:
        return "en"
    return "unknown"


def make_source_sentences(
    sentences: Iterable[str],
    *,
    source_name: str,
    source_type: str,
    license: str,
    language: str | None = None,
    document_id: str = "sample",
    title: str = "sample",
    url: str = "",
    collected_at: str | None = None,
    max_sentences: int | None = None,
) -> list[SourceSentence]:
    """Attach provenance to already extracted raw sentence strings."""

    collected = collected_at or utc_now()
    rows: list[SourceSentence] = []
    seen: set[str] = set()
    for index, raw in enumerate(sentences):
        for sentence in split_sentences(raw) or [clean_source_text(raw)]:
            sentence = sentence.strip()
            if not sentence:
                continue
            sentence_hash = stable_hash(sentence)
            if sentence_hash in seen:
                continue
            seen.add(sentence_hash)
            source_id = f"{source_type}:{document_id}:{index}"
            rows.append(
                SourceSentence(
                    text=sentence,
                    language=language or detect_language(sentence),
                    source_id=source_id,
                    source_name=source_name,
                    source_type=source_type,
                    source_hash=sentence_hash,
                    document_id=document_id,
                    title=title,
                    url=url,
                    license=license,
                    usage_allowed=bool(license),
                    collected_at=collected,
                )
            )
            if max_sentences is not None and len(rows) >= max_sentences:
                return rows
    return rows
