from __future__ import annotations

from dataclasses import asdict, dataclass
import bz2
import gzip
from pathlib import Path
import re
from typing import IO, Iterable
import xml.etree.ElementTree as ET


WIKIPEDIA_LICENSE = "CC BY-SA 4.0"
_TAG_RE = re.compile(r"<[^>]+>")
_REF_RE = re.compile(r"<ref\b[^>/]*?(?:/>|>.*?</ref>)", re.IGNORECASE | re.DOTALL)
_TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
_TABLE_RE = re.compile(r"\{\|.*?\|\}", re.DOTALL)
_FILE_LINK_RE = re.compile(r"\[\[(?:File|Image|Category):[^\]]+\]\]", re.IGNORECASE)
_WIKI_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")
_EXTERNAL_LINK_RE = re.compile(r"\[https?://[^\s\]]+(?:\s+([^\]]+))?\]")
_HEADING_RE = re.compile(r"^=+[^=]+=+$")
_URL_ONLY_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


@dataclass(frozen=True)
class WikipediaSentence:
    """One sentence extracted from a local Wikipedia dump page."""

    text: str
    title: str
    page_id: str | None
    revision_id: str | None
    revision_timestamp: str | None
    sentence_index: int
    language: str = "en"
    license: str = WIKIPEDIA_LICENSE
    source_url: str = ""

    def to_record(self) -> dict[str, object]:
        """Return a record compatible with the public corpus shard builder."""

        return asdict(self) | {
            "source_id": f"wikipedia:{self.page_id or self.title}:{self.revision_id or 'unknown'}:{self.sentence_index}",
        }


def _strip_namespace(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _child_text(element: ET.Element, name: str) -> str:
    for child in element:
        if _strip_namespace(child.tag) == name:
            return child.text or ""
    return ""


def _find_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if _strip_namespace(child.tag) == name:
            return child
    return None


def _open_dump(path: Path) -> IO[str]:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if suffixes[-2:] == [".xml", ".bz2"] or path.suffix.lower() == ".bz2":
        return bz2.open(path, "rt", encoding="utf-8", errors="strict")
    if suffixes[-2:] == [".xml", ".gz"] or path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="strict")
    return path.open("r", encoding="utf-8", errors="strict")


def clean_wikitext(text: str) -> str:
    """Return a conservative plain-text approximation of Wikipedia wikitext."""

    value = str(text or "")
    previous = None
    while previous != value:
        previous = value
        value = _REF_RE.sub(" ", value)
        value = _TABLE_RE.sub(" ", value)
        value = _TEMPLATE_RE.sub(" ", value)
    value = _FILE_LINK_RE.sub(" ", value)
    value = _WIKI_LINK_RE.sub(lambda match: match.group(2) or match.group(1), value)
    value = _EXTERNAL_LINK_RE.sub(lambda match: match.group(1) or " ", value)
    value = _TAG_RE.sub(" ", value)
    value = re.sub(r"'{2,}", "", value)
    value = re.sub(r"__[^_]+__", " ", value)
    cleaned_lines: list[str] = []
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _HEADING_RE.match(line):
            continue
        if line.startswith(("*", "#", ";", ":", "{|", "|", "!")):
            continue
        if _URL_ONLY_RE.match(line):
            continue
        cleaned_lines.append(line)
    return re.sub(r"\s+", " ", " ".join(cleaned_lines)).strip()


def split_english_sentences(text: str, *, min_chars: int = 40, max_chars: int = 700) -> list[str]:
    """Split cleaned English text into bounded sentence candidates."""

    cleaned = clean_wikitext(text)
    rows: list[str] = []
    for part in _SENTENCE_RE.split(cleaned):
        sentence = part.strip(" \t\r\n")
        if not sentence:
            continue
        if len(sentence) < min_chars or len(sentence) > max_chars:
            continue
        if not re.search(r"[A-Za-z]", sentence):
            continue
        rows.append(sentence)
    return rows


def _is_allowed_namespace(ns: str, allowed: set[str]) -> bool:
    return str(ns or "0") in allowed


def iter_wikipedia_sentences(
    path: str | Path,
    *,
    language: str = "en",
    max_rows: int | None = None,
    max_pages: int | None = None,
    include_namespaces: Iterable[str] | None = None,
    min_chars: int = 40,
    max_chars: int = 700,
) -> Iterable[WikipediaSentence]:
    """Stream sentence records from a local Wikipedia XML dump.

    The reader does not download data. It only parses a local dump or compressed
    local dump file, skips redirects, and defaults to the main namespace.
    """

    input_path = Path(path)
    allowed_namespaces = {str(value) for value in (include_namespaces or ["0"])}
    emitted = 0
    pages_seen = 0
    with _open_dump(input_path) as handle:
        context = ET.iterparse(handle, events=("end",))
        for _event, element in context:
            if _strip_namespace(element.tag) != "page":
                continue
            title = _child_text(element, "title").strip()
            ns = _child_text(element, "ns").strip() or "0"
            page_id = _child_text(element, "id").strip() or None
            if not _is_allowed_namespace(ns, allowed_namespaces):
                element.clear()
                continue
            if _find_child(element, "redirect") is not None:
                element.clear()
                continue
            revision = _find_child(element, "revision")
            revision_id: str | None = None
            revision_timestamp: str | None = None
            body = ""
            if revision is not None:
                revision_id = _child_text(revision, "id").strip() or None
                revision_timestamp = _child_text(revision, "timestamp").strip() or None
                text_element = _find_child(revision, "text")
                body = text_element.text or "" if text_element is not None else ""
            pages_seen += 1
            for index, sentence in enumerate(
                split_english_sentences(body, min_chars=min_chars, max_chars=max_chars),
                start=1,
            ):
                yield WikipediaSentence(
                    text=sentence,
                    title=title,
                    page_id=page_id,
                    revision_id=revision_id,
                    revision_timestamp=revision_timestamp,
                    sentence_index=index,
                    language=language,
                    source_url=f"https://{language}.wikipedia.org/wiki/{title.replace(' ', '_')}" if title else "",
                )
                emitted += 1
                if max_rows is not None and emitted >= int(max_rows):
                    element.clear()
                    return
            element.clear()
            if max_pages is not None and pages_seen >= int(max_pages):
                return
