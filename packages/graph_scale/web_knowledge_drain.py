# -*- coding: utf-8 -*-
"""Web knowledge drain v2 — a KNOWLEDGE learner, not a vocabulary learner.

v1 treated the web like a dictionary: term -> one definitional sentence.
v2 (owner directive) works at the QUESTION level against the WHOLE web:

 question -> search-API cascade (Tavily -> self-hosted SearXNG metasearch:
 Google/Bing/Naver/news/anything indexed) -> candidate claims extracted from
 EVERY result -> k-DOMAIN consensus (the P1 principle: a claim asserted by
 one page is a rumor; by >=2 independent domains, evidence) -> judge gate ->
 stored WITH the actual page URL as provenance.

Consensus key is structural, not string-exact: two sources rarely word a
definition identically, but they agree on the HEAD ( -> from both
namu.wiki and a news page). The stored object is the best (longest clean)
agreeing sentence; the cited source is that sentence's page. Bias/:
single-outlet claims never reach the store — cross-domain interference is
today's stand-in for the PHFE wave filter, and the quarantine ledger keeps
the audit trail.
"""
from __future__ import annotations

import re
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

from .corpus_adapters import extract_definition_triple  # noqa: E402
from .curated_judge import filter_candidates  # noqa: E402
from .graph_paths import (
    SHIPPED_GRAPH_ROOT,
    WEB_KNOWLEDGE_PROPOSAL_FRAGMENT_ROOT,
)
from .triple_store import TripleStore  # noqa: E402


def _search_rows(query: str, count: int = 8) -> list[dict[str, Any]]:
    api_dir = str(REPO / "apps" / "api")
    if api_dir not in sys.path:
        sys.path.insert(0, api_dir)
    from app.services.web_search import searxng_search, tavily_search

    return tavily_search(query, count=count) or searxng_search(query, count=count)


def _domain(url: str) -> str:
    return re.sub(r"^www\.", "", urllib.parse.urlparse(url).netloc.lower())


def _page_text(url: str, limit: int = 20000) -> str:
    """REAL web exploration: read the page body, not just the search snippet.
    Bounded fetch, tags stripped — enough sentences for cross-domain consensus."""
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ATANOR-KG/2.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read(400_000).decode("utf-8", "ignore")
    except Exception:
        return ""
    raw = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"&[a-z#0-9]+;", " ", raw)
    return re.sub(r"\s+", " ", raw)[:limit]


def _head_noun(text: str) -> str | None:
    """Consensus head: the last content noun of the claim object (the same
    structural rule the taxonomy backbone uses)."""
    t = re.sub(r"\([^)]*\)", "", text).strip().rstrip(".。 ")
    try:
        from packages.base_brain.neighborhood import _kiwi

        kw = _kiwi()
        if kw is not None:
            nouns = [tok.form for tok in kw.tokenize(t) if tok.tag in ("NNG", "NNP")]
            if nouns:
                return nouns[-1]
    except Exception:
        pass
    m = re.search(r"([가-힣A-Za-z]{2,})\s*$", t)
    return m.group(1) if m else None


def learn_from_question(question: str, subject_hint: str | None = None,
                        min_domains: int = 2, dry_run: bool = False,
                        store: Any = None, reference_store: Any = None,
                        log: Any = print) -> dict[str, Any]:
    """Drain one QUESTION through the whole web. Returns counters + what landed.
    Nothing is stored below the k-domain bar — honest gaps stay visible."""
    rows = _search_rows(question)
    # bucket by (normalized subject, predicate); heads cluster by suffix family

    _UI_JUNK = ("편집", "개요", "목차", "각주", "출처", "분류")
    buckets: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        url = str(row.get("url") or "")
        dom = _domain(url)
        if not dom:
            continue
        text = str(row.get("snippet") or row.get("content") or "")
        body = _page_text(url)
        if body:
            text = text + " " + body
        for sent in re.split(r"(?<=다\.)\s+|(?<=[.?!])\s+", text):
            sent = sent.strip()
            if not (10 <= len(sent) <= 280):
                continue
            trip = extract_definition_triple(sent)
            if not trip:
                continue
            subj, pred, obj = trip
            if any(j in subj for j in _UI_JUNK):
                continue
            if subject_hint:
                if subject_hint not in subj and subj not in subject_hint:
                    continue
                norm_subj = subject_hint  # the question's referent IS the subject
            else:
                norm_subj = re.sub(r"\([^)]*\)", "", subj).strip()
            head = _head_noun(obj)
            if not head or head in ("것", "때", "말"):
                continue
            buckets[(norm_subj, pred)].append(
                {"o": obj.strip(), "url": url, "dom": dom, "head": head})

    counters = {"pages": len(rows), "candidates": sum(len(v) for v in buckets.values()),
                "consensus": 0, "stored": 0, "quarantined": 0, "evidence": 0}
    if store is None:
        store = TripleStore(
            SHIPPED_GRAPH_ROOT
            if dry_run
            else WEB_KNOWLEDGE_PROPOSAL_FRAGMENT_ROOT
        )
    if reference_store is None:
        reference_store = (
            store
            if dry_run
            else TripleStore(SHIPPED_GRAPH_ROOT)
        )
    for (subj, pred), hits in buckets.items():

        families: list[list[dict[str, str]]] = []
        for h in hits:
            for fam in families:
                f0 = fam[0]["head"]
                if h["head"].endswith(f0) or f0.endswith(h["head"]):
                    fam.append(h)
                    break
            else:
                families.append([h])
        fam = max(families, key=lambda f: len({x["dom"] for x in f}))
        domains = sorted({x["dom"] for x in fam})
        if len(domains) < min_domains:
            continue
        counters["consensus"] += 1
        best = max(fam, key=lambda x: len(x["o"]))
        verdicts = filter_candidates(
            [(subj, pred, best["o"])],
            reference_store,
        )
        if not verdicts.get("promotable"):
            counters["quarantined"] += 1
            continue
        log(f"  합의 {len(domains)}개 도메인 {domains}: {subj} {pred} {best['o'][:70]}")
        log(f"    근거: {best['url']}")
        if not dry_run:
            sid = store.intern_source(best["dom"], best["url"])
            if store.add(subj, pred, best["o"], source=sid):
                counters["stored"] += 1
    # TIER 2 — attributed evidence: knowledge sentences ABOUT the subject, stored
    # verbatim with the page URL. Not asserted as graph truth (no consensus needed):

    # This is what makes a rich profile answer possible without fabricating anything.
    if subject_hint:
        per_dom: dict[str, int] = defaultdict(int)
        kept_ev: list[tuple[str, str, str]] = []
        seen_norm: set[str] = set()
        for row in rows:
            url = str(row.get("url") or "")
            dom = _domain(url)
            if not dom or per_dom[dom] >= 2:
                continue
            text = str(row.get("snippet") or "") + " " + _page_text(url)
            for sent in re.split(r"(?<=다\.)\s+|(?<=[.?!])\s+", text):
                if per_dom[dom] >= 2:
                    break  # per-domain cap holds INSIDE the sentence loop too
                sent = sent.strip()
                if not (30 <= len(sent) <= 220):
                    continue
                if not sent.startswith(subject_hint):
                    continue
                if any(j in sent for j in _UI_JUNK) or "[" in sent[:20]:
                    continue
                norm = re.sub(r"\s+", "", sent)[:60]
                if norm in seen_norm:
                    continue
                seen_norm.add(norm)
                kept_ev.append((sent, url, dom))
                per_dom[dom] += 1
                if len(kept_ev) >= 6:
                    break
            if len(kept_ev) >= 6:
                break
        for sent, url, dom in kept_ev:
            log(f"  근거문장[{dom}]: {sent[:70]}")
            if not dry_run:
                sid = store.intern_source(dom, url)
                if store.add(subject_hint, "evidence", sent, source=sid):
                    counters["evidence"] += 1
    if not dry_run:
        store.flush()
    return counters
