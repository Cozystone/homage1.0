# -*- coding: utf-8 -*-
"""Evidence sources for the acquisition loop.

An evidence source answers ONE question: "give me candidate (url, text) documents that might
state ``(entity, relation)``." The loop then extracts + verifies + injects. Two implementations:

  * ``FixtureEvidence`` — a controlled in-memory corpus. This is what the SEALED GATE uses, so the
    loop is deterministic and reproducible (no live-network flakiness). Documents carry a real URL
    (so ``domain_of`` yields distinct domains) and prose text.

  * ``WebEvidence`` — the LIVE lane (opt-in, read-only): reuses ``web_knowledge_drain._search_rows``
    (search-API cascade) + ``_page_text`` (bounded page fetch). Same interface, so a real overnight
    demo swaps the source without touching the loop. NOT used by the sealed gate.

Both hand the loop plain (url, text) pairs; the safety floors (harm/PII/injection) and the
consensus gate live in the loop, so no evidence source can bypass them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _clean_live_document(snippet: str, body: str, entity: str, max_sentences: int = 8) -> str:
    """Shape a raw (snippet, fetched-page) pair into CLEAN extractable text: keep only well-formed
    sentences that actually mention the ENTITY and are not questions. Live pages are ~20KB of nav /
    menu / breadcrumb / echoed-query chrome around a few real sentences — feeding that whole blob to
    the high-precision extractor manufactures noise objects ('what', 'astana astana', menu runs). A
    sentence that (a) names the entity, (b) is declarative (not the query echoed back as a '?'), and
    (c) is a sane length is the real signal. Surface filtering only — no world knowledge."""
    ent = entity.strip().lower()
    if not ent:
        blob = ((snippet or "") + " " + (body or "")).strip()
        return re.sub(r"\s+", " ", blob)[:2000]
    kept: list[str] = []
    for s in _SENT_SPLIT.split(((snippet or "") + " " + (body or "")).strip()):
        s = re.sub(r"\s+", " ", s).strip()
        if not (12 <= len(s) <= 320):
            continue
        if s.rstrip().endswith("?"):                 # an echoed query states no fact
            continue
        if ent not in s.lower():                     # only sentences ABOUT the entity (drops chrome)
            continue
        if s in kept:
            continue
        kept.append(s)
        if len(kept) >= max_sentences:
            break
    return " ".join(kept)


class EvidenceSource(Protocol):
    def documents(self, entity: str, rel_norm: str, query: str = "") -> list[tuple[str, str]]:
        ...


@dataclass
class FixtureEvidence:
    """Deterministic controlled corpus. ``corpus`` is a list of {"url", "text"} dicts. A document
    is returned for an (entity, rel_norm) probe when the entity string occurs in its text (the loop
    then extracts the specific relation). Fully offline, reproducible."""
    corpus: list[dict[str, str]] = field(default_factory=list)

    def documents(self, entity: str, rel_norm: str, query: str = "") -> list[tuple[str, str]]:
        ent = entity.strip().lower()
        return [(d["url"], d["text"]) for d in self.corpus
                if ent in str(d.get("text", "")).lower() and d.get("url")]


@dataclass
class LocalIndexEvidence:
    """Evidence from ATANOR's OWN corpora. No network at all, so no rate limit at all.

    WHY IT EXISTS, measured 2026-07-31. Continuous querying got SearXNG's upstreams to suspend it
    inside an hour -- google CAPTCHA, brave too-many-requests, duckduckgo and mojeek and qwant
    access-denied -- and the acquisition loop went from 8 documents per question to nothing on 35% of
    them. Two-distinct-domain consensus over zero documents is impossible, so the loop pursued 78 gaps
    and landed 0. The ceiling was the search provider, not the loop.

    WHY IT IS NOT JUST WebEvidence WITH A DIFFERENT SEARCH. WebEvidence searches, then FETCHES each
    result page over the network. Pointed at the local index it would take a wikipedia.org URL out of
    a local hit and go download it, which reintroduces exactly the dependency this removes. The index
    already stores the passage, so the snippet IS the document and nothing is fetched.

    WHAT IT CANNOT DO, and this is the honest limit. ATANOR owns two corpora, Wikipedia and Wiktionary,
    which are two works but one ecosystem -- both Wikimedia, overlapping editors, each citing the
    other. The consensus gate counts distinct domains and reads them as two, which is true by the rule
    and generous in spirit. Facts these two agree on are real evidence and weaker than facts two
    unrelated sites agree on. A genuinely independent third corpus about ordinary objects is missing,
    and no amount of retrieval engineering substitutes for it."""

    count: int = 10
    body_sentences: int = 8

    def documents(self, entity: str, rel_norm: str, query: str = "") -> list[tuple[str, str]]:
        from packages.atanor_index.retriever import local_search

        q = query or f"what is the {rel_norm} of {entity}"
        docs: list[tuple[str, str]] = []
        for row in local_search(q, self.count) or []:
            url = str(row.get("url") or "")
            snippet = str(row.get("snippet") or "")
            if not url or not snippet:
                continue
            text = _clean_live_document(snippet, "", entity, self.body_sentences)
            if text:
                docs.append((url, text))
        return docs


@dataclass
class WebEvidence:
    """LIVE, read-only evidence via the existing search-API cascade + page fetch. Opt-in — the
    sealed gate never constructs this. Kept thin: it only gathers documents; all verification stays
    in the loop."""
    count: int = 8
    page_chars: int = 20000
    body_sentences: int = 8

    def documents(self, entity: str, rel_norm: str, query: str = "") -> list[tuple[str, str]]:
        from packages.graph_scale.web_knowledge_drain import _page_text, _search_rows

        q = query or f"what is the {rel_norm} of {entity}"
        rows: list[dict[str, Any]] = _search_rows(q, count=self.count) or []
        docs: list[tuple[str, str]] = []
        for row in rows:
            url = str(row.get("url") or "")
            if not url:
                continue
            snippet = str(row.get("snippet") or row.get("content") or "")
            body = _page_text(url, limit=self.page_chars)
            # shape into clean entity-bearing sentences so the extractor sees signal, not chrome
            text = _clean_live_document(snippet, body, entity, self.body_sentences)
            if text:
                docs.append((url, text))
        return docs
