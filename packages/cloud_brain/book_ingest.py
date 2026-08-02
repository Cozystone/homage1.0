# -*- coding: utf-8 -*-
"""Book ingestion — feed ATANOR a PDF and let it READ, like a person.

Owner's vision (2026-07-09): once the engine is mature enough, you should be
able to hand it a book or document and it reads on its own — 'Thinking, Fast
and Slow' so it learns about thinking about thinking. Human-like learning: not
only Wikidata dumps, but real books.

This is the front door. A PDF becomes sentences, sentences enter the SAME
learning pipeline as the web firehose (relation checking behind the consensus /
quality gate), so nothing bypasses the truth gates — a book is a high-quality
CORPUS, not an override. Two extraction paths, auto-selected per page:
  * TEXT layer (fitz/PyMuPDF) for born-digital PDFs — fast, exact;
  * OCR (pytesseract on a rendered page image) for scanned pages with no text
    layer — so a photographed book still reads.

The output is a corpus .txt in the firehose's corpus dir; the running learner
picks it up. Honest scope: today's relation extraction is co-occurrence-level
(gated), so a book surfaces its CONCEPTS and their associations as candidates —
the deep argument structure needs richer extraction (a named next step)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

_SENT_SPLIT = re.compile(r"(?<=[.!?。！？])\s+|\n{2,}")

# every format we can read today; a book/doc is just a text source, and the
# door is one dispatcher so adding a format later is one branch.
_TEXT_EXT = {".txt", ".md", ".markdown", ".text", ".rst"}
_HTML_EXT = {".html", ".htm", ".xhtml"}


@dataclass
class IngestResult:
    source: str
    pages: int
    pages_ocr: int
    sentences: int
    corpus_file: str
    chars: int
    ocr_available: bool
    note: str = ""
    region_id: str = ""
    region_color: str = ""
    relation_candidates: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "pages": self.pages, "pages_ocr": self.pages_ocr,
                "sentences": self.sentences, "corpus_file": self.corpus_file,
                "chars": self.chars, "ocr_available": self.ocr_available, "note": self.note,
                "region_id": self.region_id, "region_color": self.region_color,
                "relation_candidates": self.relation_candidates}


def _ocr_available() -> bool:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_pdf_text(path: str | Path, *, ocr_scanned: bool = True,
                     max_pages: int | None = None,
                     log: Any = print) -> tuple[str, int, int]:
    """Extract text from a PDF. Per page: use the text layer; if it's empty
    (scanned) and OCR is available, render the page and OCR it. Returns
    (text, pages_read, pages_ocr)."""
    import fitz  # PyMuPDF

    doc = fitz.open(str(path))
    n = doc.page_count if max_pages is None else min(doc.page_count, max_pages)
    have_ocr = ocr_scanned and _ocr_available()
    parts: list[str] = []
    pages_ocr = 0
    for i in range(n):
        page = doc.load_page(i)
        txt = page.get_text("text").strip()
        if len(txt) < 40 and have_ocr:            # likely a scanned/image page
            try:
                import io

                import pytesseract
                from PIL import Image
                pix = page.get_pixmap(dpi=200)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                txt = pytesseract.image_to_string(img).strip()
                pages_ocr += 1
            except Exception:
                pass
        if txt:
            parts.append(txt)
        if i and i % 25 == 0:
            log(f"  ...{i}/{n} pages")
    doc.close()
    return "\n\n".join(parts), n, pages_ocr


class _HTMLText(HTMLParser):
    """Minimal, dependency-free HTML/XHTML -> text (drops script/style, keeps
    block boundaries so sentence splitting works)."""
    _SKIP = {"script", "style", "head"}
    _BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6",
              "tr", "section", "article"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def _html_to_text(html: str) -> str:
    p = _HTMLText()
    try:
        p.feed(html)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)   # last-resort tag strip
    return p.text()


def extract_epub_text(path: str | Path, *, max_pages: int | None = None,
                      log: Any = print) -> tuple[str, int]:
    """EPUB = a zip of (X)HTML documents. Read the spine in reading order (fall
    back to sorted content docs), strip tags. Returns (text, docs_read). Pure
    stdlib — no ebooklib needed."""
    import zipfile

    with zipfile.ZipFile(str(path)) as zf:
        names = zf.namelist()
        order = _epub_spine_order(zf, names)
        if max_pages is not None:
            order = order[:max_pages]
        parts: list[str] = []
        for i, name in enumerate(order):
            try:
                raw = zf.read(name).decode("utf-8", "ignore")
            except Exception:
                continue
            parts.append(_html_to_text(raw))
            if i and i % 25 == 0:
                log(f"  ...{i}/{len(order)} docs")
    return "\n\n".join(parts), len(order)


def _epub_spine_order(zf: Any, names: list[str]) -> list[str]:
    """Reading order from the OPF spine; fall back to every content doc sorted."""
    content = [n for n in names if n.lower().endswith((".xhtml", ".html", ".htm"))]
    try:
        opf = next((n for n in names if n.lower().endswith(".opf")), None)
        if not opf:
            return sorted(content)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(zf.read(opf))
        ns = {"o": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
        base = opf.rsplit("/", 1)[0] if "/" in opf else ""
        idref_href: dict[str, str] = {}
        man = root.find("o:manifest", ns) if ns else root.find("manifest")
        for item in (man or []):
            iid = item.get("id"); href = item.get("href")
            if iid and href:
                idref_href[iid] = (base + "/" + href) if base else href
        spine = root.find("o:spine", ns) if ns else root.find("spine")
        ordered = [idref_href[it.get("idref")] for it in (spine or [])
                   if it.get("idref") in idref_href]
        ordered = [n for n in ordered if n in names]
        return ordered or sorted(content)
    except Exception:
        return sorted(content)


def extract_text_any(path: str | Path, *, ocr_scanned: bool = True,
                     max_pages: int | None = None,
                     log: Any = print) -> tuple[str, int, int, str]:
    """One door for every format. Returns (text, units_read, units_ocr, kind).
    'units' are pages (PDF) or documents (EPUB/HTML) or 1 (plain text)."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        text, pages, ocr = extract_pdf_text(
            path, ocr_scanned=ocr_scanned, max_pages=max_pages, log=log)
        return text, pages, ocr, "pdf"
    if ext == ".epub":
        text, docs = extract_epub_text(path, max_pages=max_pages, log=log)
        return text, docs, 0, "epub"
    if ext in _HTML_EXT:
        return _html_to_text(path.read_text("utf-8", "ignore")), 1, 0, "html"
    if ext in _TEXT_EXT or ext == "":
        return path.read_text("utf-8", "ignore"), 1, 0, "text"
    # unknown extension: try text, then give an honest note
    try:
        return path.read_text("utf-8", "ignore"), 1, 0, "text?"
    except Exception:
        return "", 0, 0, "unsupported"


_LINGUISTIC = re.compile(r"[A-Za-z가-힣0-9 .,;:'\"()\-?!…’“”—]")


def _looks_linguistic(s: str) -> bool:
    """Reject non-prose noise that survives tag stripping: base64 blobs, embedded
    binary/typography (GEB's encoded figures decoded as mojibake), symbol soup.
    Real sentences are overwhelmingly letters/spaces/basic punctuation."""
    if not s:
        return False
    good = sum(1 for c in s if _LINGUISTIC.match(c))
    if good / len(s) < 0.85:               # <85% ordinary chars -> not prose
        return False
    letters = sum(1 for c in s if c.isalpha())
    if letters / len(s) < 0.55:            # mostly digits/punct -> not a sentence
        return False
    # a real sentence has whitespace between words; a base64/hash run has none
    if len(s) > 30 and s.count(" ") < len(s) / 25:
        return False
    return True


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    for chunk in _SENT_SPLIT.split(text):
        s = re.sub(r"\s+", " ", chunk).strip()
        # keep real sentences: length-bounded, has letters, not a page header/number
        if 20 <= len(s) <= 600 and re.search(r"[A-Za-z가-힣]", s) \
                and not s.isupper() and _looks_linguistic(s):
            out.append(s)
    return out


def ingest_book(path: str | Path, *, corpus_dir: str | Path | None = None,
                title: str | None = None, region_kind: str = "book",
                extract_relations: bool = False, lang: str = "en",
                ocr_scanned: bool = True, max_pages: int | None = None,
                log: Any = print) -> IngestResult:
    """Read a document into the firehose corpus so the running learner ingests it
    behind the same truth gates. The book becomes its own colored REGION (a named
    bundle in the graph), not dissolved into the mass. Returns stats. Does NOT
    bypass promotion — the book is a corpus, its facts still pass every gate."""
    path = Path(path)
    if not path.exists():
        return IngestResult(str(path), 0, 0, 0, "", 0, _ocr_available(),
                            note="file not found")
    if corpus_dir is None:
        corpus_dir = Path(__file__).resolve().parent / "seed_corpus"
    corpus_dir = Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)

    text, pages, pages_ocr, kind = extract_text_any(
        path, ocr_scanned=ocr_scanned, max_pages=max_pages, log=log)
    sents = _sentences(text)
    label = title or path.stem
    slug = re.sub(r"[^\w가-힣]+", "_", label).strip("_").lower()[:60]
    out = corpus_dir / f"book_{slug}.txt"
    out.write_text("\n".join(sents), encoding="utf-8")
    # register the book as its own colored district in the graph
    region_id, region_color = f"book_{slug}", ""
    try:
        from packages.graph_scale.graph_regions import register_region
        reg = register_region(region_id, label=label, kind=region_kind,
                              source=str(path), sentences=len(sents))
        region_id, region_color = reg["region_id"], reg["color"]
    except Exception:
        pass
    # optional v3 pass: rule×topology relation extraction -> gated candidates
    rel_cands = 0
    if extract_relations:
        try:
            from packages.graph_scale.relation_extractor import extract_from_sentences
            er = extract_from_sentences(sents, lang=lang, store=None)
            rel_cands = int(er.get("candidates_written") or 0)
        except Exception:
            pass
    how = {"pdf": ("read via OCR on scanned pages" if pages_ocr else "read PDF text layer"),
           "epub": "read EPUB spine (stdlib)", "html": "read HTML",
           "text": "read plain text"}.get(kind, f"read as {kind}")
    return IngestResult(
        source=str(path), pages=pages, pages_ocr=pages_ocr, sentences=len(sents),
        corpus_file=str(out), chars=len(text), ocr_available=_ocr_available(),
        note=how + f" — its own region '{region_id}'; the learner ingests it behind the truth gates",
        region_id=region_id, region_color=region_color, relation_candidates=rel_cands)
