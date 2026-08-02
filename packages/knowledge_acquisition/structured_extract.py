# -*- coding: utf-8 -*-
"""Facts the page already published for machines — typed, exact, and often LIVE.

    from packages.knowledge_acquisition.structured_extract import extract_structured
    extract_structured(html, url)   # -> [Fact(subject, predicate, object, kind, volatile), ...]

THE THROUGHPUT WALL AND WHERE IT ACTUALLY WAS. Turning the web into a fact graph looked impossible from
one machine: at the 0.6 facts per page our sentence extractor gets, a trillion facts needs 1.6 trillion
page reads. But 0.6 is a property of OUR EXTRACTOR, not of the web. Measured 2026-07-31 on pages the
crawler can already reach:

    rottentomatoes.com   48 structured fields   actor, aggregateRating, contentRating, director
    arstechnica.com      27
    en.wikipedia.org     14                     author, mainEntity, publisher, sameAs
    dictionary.com       10
    bbc.com               9                     publisher, mainEntityOfPage
    news.ycombinator.com  0

Fifteen to eighty times what regexing prose gets, and it is not guessed: schema.org JSON-LD is what the
publisher deliberately put there FOR MACHINES. Same bandwidth, same politeness, one to two orders of
magnitude more knowledge per fetch. That is the architectural answer to the wall -- not crawling more
pages, extracting more from each.

AND THE SAME MECHANISM IS THE REAL-TIME ANSWER, which is the part that surprised me. The live values of
the web live in exactly these blocks: price, availability, startDate, datePublished, aggregateRating,
eventStatus. A prose extractor cannot see them and a search API charges for them. They are sitting in the
HTML, typed and dated.

So every fact carries `volatile`: whether this predicate is one the world changes. That is what lets the
graph know which of its own branches are rotting -- a stable fact is fetched once, a volatile one is
scheduled by its own rate of change. A general engine cannot do this because it never knew what it
extracted.

WHAT THIS IS NOT. It is not more trustworthy because it is structured: a publisher writes its own
schema.org, so a price is a claim by a seller. Structured facts enter the SAME consensus gate as mined
ones and carry their domain with them. Exactness is not truthfulness.
"""
from __future__ import annotations

import html as _html
import json
import re
import urllib.parse
from dataclasses import dataclass

_JSONLD = re.compile(rb'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                     re.I | re.S)
_OG = re.compile(rb'<meta[^>]+(?:property|name)=["\'](og:[a-z:]+|article:[a-z_]+)["\'][^>]*'
                 rb'content=["\']([^"\']{1,300})["\']', re.I)
_OG_REV = re.compile(rb'<meta[^>]+content=["\']([^"\']{1,300})["\'][^>]*'
                     rb'(?:property|name)=["\'](og:[a-z:]+|article:[a-z_]+)["\']', re.I)

# Predicates whose value the WORLD changes. This is the volatility prior; measured drift refines it
# per fact later, but a first schedule has to come from somewhere and the schema name is a good guess.
VOLATILE = {
    "price", "lowprice", "highprice", "availability", "inventorylevel", "pricecurrency",
    "aggregaterating", "ratingvalue", "reviewcount", "ratingcount",
    "startdate", "enddate", "eventstatus", "previousstartdate", "doortime",
    "datepublished", "datemodified", "uploaddate", "expires", "validthrough",
    "temperature", "score", "position", "interactioncount", "userinteractioncount",
}
# Structural noise: present on every page, says nothing about the thing.
SKIP_KEY = {"@context", "@type", "@id", "url", "image", "logo", "thumbnailurl", "contenturl",
            "potentialaction", "breadcrumb", "isaccessibleforfree", "inlanguage", "mainentityofpage",
            "sameas", "identifier", "width", "height", "encodingformat"}
MAX_FACTS = 200
MAX_VALUE = 200


@dataclass(frozen=True)
class Fact:
    subject: str
    predicate: str
    object: str
    kind: str            # jsonld | opengraph
    volatile: bool
    source: str          # url

    def as_triple(self) -> tuple[str, str, str]:
        return (self.subject, self.predicate, self.object)


def _text(v) -> str | None:
    """A scalar the graph can hold. Nested objects are followed elsewhere; this only flattens leaves."""
    if isinstance(v, (str, int, float)):
        s = str(v).strip()
    elif isinstance(v, dict):
        s = str(v.get("name") or v.get("@id") or v.get("value") or "").strip()
    else:
        return None
    s = re.sub(r"\s+", " ", _html.unescape(s))
    return s[:MAX_VALUE] if 1 <= len(s) <= MAX_VALUE else None


def _subject_of(node: dict, url: str) -> str:
    name = _text(node.get("name")) or _text(node.get("headline"))
    if name:
        return name.lower()
    slug = urllib.parse.urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[_\-]+", " ", urllib.parse.unquote(slug)).strip().lower() or url


def _walk(node, url: str, out: list, depth: int = 0) -> None:
    if depth > 4 or len(out) >= MAX_FACTS:
        return
    if isinstance(node, list):
        for item in node:
            _walk(item, url, out, depth)
        return
    if not isinstance(node, dict):
        return
    subject = _subject_of(node, url)
    for key, value in node.items():
        if len(out) >= MAX_FACTS:
            return
        k = key.lower()
        if k in SKIP_KEY or k.startswith("@"):
            if isinstance(value, (dict, list)):
                _walk(value, url, out, depth + 1)
            continue
        if isinstance(value, (dict, list)):
            _walk(value, url, out, depth + 1)
            v = _text(value) if isinstance(value, dict) else None
        else:
            v = _text(value)
        if v and subject and v.lower() != subject:
            out.append(Fact(subject, k, v, "jsonld", k in VOLATILE, url))


def extract_structured(body: bytes, url: str) -> list[Fact]:
    """Every machine-published fact on the page. Empty is a perfectly normal answer."""
    out: list[Fact] = []
    for block in _JSONLD.findall(body):
        try:
            data = json.loads(block.decode("utf-8", "ignore"))
        except Exception:
            continue                       # a malformed block is not an error, it is a bad page
        _walk(data, url, out)
    if len(out) < MAX_FACTS:
        og: dict[str, str] = {}
        for m in _OG.finditer(body):
            og.setdefault(m.group(1).decode("ascii", "ignore").lower(),
                          m.group(2).decode("utf-8", "ignore"))
        for m in _OG_REV.finditer(body):
            og.setdefault(m.group(2).decode("ascii", "ignore").lower(),
                          m.group(1).decode("utf-8", "ignore"))
        title = og.get("og:title") or ""
        subject = re.sub(r"\s+", " ", _html.unescape(title)).strip().lower()
        if not subject:
            slug = urllib.parse.urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
            subject = re.sub(r"[_\-]+", " ", urllib.parse.unquote(slug)).strip().lower()
        for key, value in og.items():
            if key in ("og:title", "og:image", "og:url"):
                continue
            v = _text(value)
            pred = key.split(":", 1)[-1]
            if v and subject and v.lower() != subject:
                out.append(Fact(subject, pred, v, "opengraph", pred in VOLATILE, url))
    seen = set()
    uniq = []
    for f in out:
        t = f.as_triple()
        if t not in seen:
            seen.add(t)
            uniq.append(f)
    return uniq[:MAX_FACTS]


def volatility_split(facts: list[Fact]) -> tuple[list[Fact], list[Fact]]:
    """(stable, volatile). The graph fetches the first once and schedules the second by its own rate."""
    return [f for f in facts if not f.volatile], [f for f in facts if f.volatile]
