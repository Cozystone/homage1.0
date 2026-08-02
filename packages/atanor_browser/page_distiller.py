# -*- coding: utf-8 -*-
"""Page distiller — DOM text to subject-anchored knowledge ( P2 core).

The hard part of a graph-native browser is not rendering; it is the honest
real-time conversion of an arbitrary page into graph material WITHOUT letting
the wrong-page/tangential noise class back in. This distiller encodes the
lessons the web learner already paid for:

 * TITLE-ANCHOR GATE — the page's own title names its subject; a sentence
 only yields a triple when its subject matches the title anchor (or an
 explicitly whitelisted secondary subject). The '→Miraculous' class
 dies at the door.
 * BOILERPLATE STRIP — nav/menu/cookie/footer text never reaches extraction
 (short lines, link-dense lines, pipe-chained title bars).
 * CONSERVATIVE EXTRACTION — only the definitional copula class ('X Y')
 and explicit relation cues are lifted; everything else stays prose
 evidence with provenance (the graph decides later, at promotion).
 * PROVENANCE ALWAYS — every output row carries url + title + position.

Outputs are CANDIDATES for the existing quarantine/consensus pipeline —
this module never writes to any store (the browser observes; promotion gates).
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

_SKIP_TAGS = {"script", "style", "nav", "footer", "header", "aside", "form",
              "button", "noscript", "svg", "iframe"}
_BLOCK_TAGS = {"p", "div", "li", "td", "h1", "h2", "h3", "h4", "section", "article", "br"}


# which is a FACT-EVENT, not a definition — those stay evidence for the miner
_COPULA_RE = re.compile(
    r"^(?P<subj>[가-힣A-Za-z0-9·\s]{2,30}?)[은는이가]\s+(?P<body>.{6,160}?)(?:이다|입니다)\.?$")
_MIN_SENTENCE = 12
_MAX_LINK_DENSITY = 0.4


class _TextExtract(HTMLParser):
    """Boilerplate-aware text extraction: block-level text runs with their
    link density, so menu bars (link-dense) can be dropped downstream."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self._in_link = 0
        self.blocks: list[dict[str, Any]] = []
        self._buf: list[str] = []
        self._link_chars = 0

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if text:
            total = max(1, len(text))
            self.blocks.append({"text": text,
                                "link_density": min(1.0, self._link_chars / total)})
        self._buf, self._link_chars = [], 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "title":
            self._in_title = True
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        if tag == "a":
            self._in_link += 1
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "a" and self._in_link > 0:
            self._in_link -= 1
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
            return
        if self._skip_depth:
            return
        self._buf.append(data)
        if self._in_link:
            self._link_chars += len(data)


def _title_anchor(title: str) -> str:
    """The page subject: the title's head segment before separators, trimmed
 of the site name (' - ' -> '')."""
    head = re.split(r"[|\-–—:·]", str(title or ""), maxsplit=1)[0].strip()
    return head[:40]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?다요])\s+", text) if len(s.strip()) >= _MIN_SENTENCE]


def _anchor_match(subj: str, anchor: str) -> bool:
    s, a = subj.strip().lower(), anchor.strip().lower()
    if not s or not a:
        return False
    return s in a or a in s


def distill_page(html: str, url: str = "") -> dict[str, Any]:
    """One page -> {anchor, triples[], evidence[], dropped} — candidates only,
    nothing written anywhere. The relevance gate is structural, not heuristic
    trust: an off-anchor sentence can be perfect prose and still not become a
    triple, because the page never claimed to be about it."""
    parser = _TextExtract()
    try:
        parser.feed(str(html or ""))
        parser._flush()
    except Exception:
        return {"anchor": "", "triples": [], "evidence": [], "dropped": {"parse_error": 1}}

    anchor = _title_anchor(parser.title)
    triples: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    dropped = {"boilerplate": 0, "off_anchor": 0, "short": 0}

    pos = 0
    for block in parser.blocks:
        if block["link_density"] > _MAX_LINK_DENSITY or "|" in block["text"][:80]:
            dropped["boilerplate"] += 1
            continue
        for sent in _sentences(block["text"]):
            pos += 1
            m = _COPULA_RE.match(sent)
            if m:
                subj = re.sub(r"\s+", " ", m.group("subj")).strip()
                if _anchor_match(subj, anchor):
                    triples.append({
                        "subject": anchor, "predicate": "defined_as",
                        "object": m.group("body").strip(),
                        "url": url, "title": parser.title.strip(), "position": pos,
                        "gate": "title_anchor_copula",
                    })
                    continue
                dropped["off_anchor"] += 1
            # anchor-relevant prose stays as evidence (the graph decides later)
            if anchor and _anchor_match_any_token(sent, anchor):
                evidence.append({"sentence": sent, "url": url,
                                 "title": parser.title.strip(), "position": pos})
    return {"anchor": anchor, "triples": triples,
            "evidence": evidence[:20], "dropped": dropped,
            "written_to_store": False}


def _anchor_match_any_token(sentence: str, anchor: str) -> bool:
    a = anchor.strip()
    return bool(a) and a.split()[0] in sentence
