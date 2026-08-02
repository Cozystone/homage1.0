"""ATANOR Index retriever — self-owned passages in the web-result shape ( §4 - ).

Bridges the disk-backed BM25 index into the existing web pipeline: local_search() returns the SAME
dict shape as tavily_search/searxng_search, so ATANOR's own index joins the provider fan-out (and, at
V3, precedes external providers). No network — this is the offline "search head" that makes the SAGE
tier partly self-sufficient. Lazy singleton; ATANOR_DISABLE_LOCAL_INDEX=1 disables it entirely.
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
# Prefer the full 7M index; fall back to the 278k while the full one is still building.
_CANDIDATE_DIRS = (
    _REPO / "data" / "atanor_index" / "wiki_en_full",
    _REPO / "data" / "atanor_index" / "wiki_en_278k",
)
_LOCK = threading.Lock()
_STATE: dict[str, Any] = {"idx": None, "tried_dir": None}


def _built(d: Path) -> bool:
    return (d / "meta.json").exists() and (d / "term_hashes.npy").exists()


def _pick_dir() -> Path | None:
    # env override wins; else the first candidate that is fully built (largest corpus first)
    ov = os.environ.get("ATANOR_INDEX_DIR")
    if ov and _built(Path(ov)):
        return Path(ov)
    for d in _CANDIDATE_DIRS:
        if _built(d):
            return d
    return None


def _get_index():
    """Open (or re-open, if a bigger corpus finished building) the DiskIndex. None if unavailable."""
    if os.environ.get("ATANOR_DISABLE_LOCAL_INDEX") == "1":
        return None
    want = _pick_dir()
    if want is None:
        return None
    with _LOCK:
        if _STATE["idx"] is not None and _STATE["tried_dir"] == str(want):
            return _STATE["idx"]
        try:
            from packages.atanor_index.disk_index import DiskIndex
            _STATE["idx"] = DiskIndex(want)
            _STATE["tried_dir"] = str(want)
        except Exception:
            _STATE["idx"] = None
            _STATE["tried_dir"] = str(want)
        return _STATE["idx"]


def _wiki_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + re.sub(r"\s+", "_", title.strip())


def _wiktionary_url(title: str) -> str:
    return "https://en.wiktionary.org/wiki/" + re.sub(r"\s+", "_", title.strip())


def _wordnet_url(title: str) -> str:
    return "http://wordnetweb.princeton.edu/perl/webwn?s=" + re.sub(r"\s+", "+", title.strip())


def _gcide_url(title: str) -> str:
    return "https://gcide.gnu.org.ua/?q=" + re.sub(r"\s+", "+", title.strip())


# EVERY CORPUS ATANOR OWNS, because one corpus can never reach consensus. The acquisition loop accepts
# a fact only when TWO DISTINCT DOMAINS assert it, so a search head over a single site cannot land one
# no matter how good its retrieval is -- measured 2026-07-31, when local_search answered every deficit
# question and returned en.wikipedia.org for every hit.
#
# HONEST CAVEAT, kept here rather than in a footnote: Wikipedia and Wiktionary are two works but ONE
# ECOSYSTEM. Both are Wikimedia projects, their editors overlap, and each cites the other. The gate
# counts distinct domains and will read them as two, which is true by the rule and generous in spirit.
# A fact these two agree on is real evidence and is WEAKER than one two unrelated sites agree on. A
# genuinely independent third corpus about ordinary objects is still missing.
_CORPORA = (
    ("wiki", _REPO / "data" / "atanor_index" / "wiki_en_full", _wiki_url, "reference_only"),
    ("wiki", _REPO / "data" / "atanor_index" / "wiki_en_278k", _wiki_url, "reference_only"),
    ("wiktionary", _REPO / "data" / "atanor_index" / "wiktionary_en", _wiktionary_url,
     "reference_only"),
    # THREE traditions, not four sources. wiki and wiktionary are both Wikimedia; wordnet is
    # Princeton's own lexicographic database; gcide is Webster's 1913 Revised Unabridged with
    # volunteer correction. Open English WordNet was rejected despite being newer and easy to fetch,
    # because it descends from Princeton WordNet -- counting it would repeat the Simple-English-
    # Wikipedia mistake of reading a derivative as an independent witness.
    ("wordnet", _REPO / "data" / "atanor_index" / "wordnet_en", _wordnet_url, "reference_only"),
    ("gcide", _REPO / "data" / "atanor_index" / "gcide_en", _gcide_url, "reference_only"),
)
_CORPUS_STATE: dict[str, Any] = {}


def corpus_url(corpus: str, title: str) -> str:
    """The url a corpus name maps to. ONE definition, because two would break the consensus floor.

    `packages.knowledge_acquisition.loop` feeds the property table's precomputed sightings into the
    same ConsensusTally as the mined ones, and the tally counts DISTINCT DOMAINS. If the table said
    a fact came from "wiki" and this file called that something other than en.wikipedia.org, a fact
    the table read out of Wikipedia and a fact fetched from a Wikipedia page would look like two
    independent sources and reach a two-source floor on their own. So the mapping lives here, beside
    _CORPORA, and the loop imports it rather than keeping its own copy."""
    for name, _dir, url_fn, _lic in _CORPORA:
        if name == corpus:
            return url_fn(title)
    return ""


def _corpus_indexes():
    """(name, DiskIndex, url_fn, license) for every built corpus. At most one index per corpus name,
    so the 7M wiki index shadows the 278k fallback rather than both answering."""
    if os.environ.get("ATANOR_DISABLE_LOCAL_INDEX") == "1":
        return []
    out, seen = [], set()
    with _LOCK:
        for name, d, url_fn, lic in _CORPORA:
            if name in seen or not _built(d):
                continue
            seen.add(name)
            key = str(d)
            if key not in _CORPUS_STATE:
                try:
                    from packages.atanor_index.disk_index import DiskIndex
                    _CORPUS_STATE[key] = DiskIndex(d)
                except Exception:
                    _CORPUS_STATE[key] = None
            if _CORPUS_STATE[key] is not None:
                out.append((name, _CORPUS_STATE[key], url_fn, lic))
    return out


def local_search(query: str, count: int = 6) -> list[dict[str, Any]]:
    """BM25 over EVERY corpus ATANOR owns → web-result dicts. Empty if no index or no match.

    The dominance filter runs PER CORPUS, not over the merged list. Applied across corpora it would
    delete exactly what makes a second corpus worth having: BM25 scores are not comparable between
    indexes with different avgdl and different term statistics, so the shorter dictionary passages
    would be cut against long encyclopedia leads and the result would be single-domain again."""
    query = (query or "").strip()
    corpora = _corpus_indexes()
    if not corpora or not query:
        return []
    per = max(1, min(count, 12))
    rows: list[dict[str, Any]] = []
    for name, idx, url_fn, lic in corpora:
        try:
            hits = idx.search_topk(query, k=per)
        except Exception:
            continue
        # Dominance filter: when the top hit clearly wins (e.g. "Capital of Korea" 56 vs "Capital
        # punishment in South Korea" 21), inject ONLY the winner(s). Feeding the whole shortlist let
        # the downstream composer anchor on a plausible-looking distractor and regress the answer
        # (measured live: capital-of-Korea → "Capital punishment"). Within half the top score; ≥1.
        if hits:
            floor = 0.5 * float(hits[0].get("score") or 0.0)
            hits = [hits[0]] + [h for h in hits[1:] if float(h.get("score") or 0.0) >= floor]
        for i, h in enumerate(hits, start=1):
            text = str(h.get("text") or "").strip()
            if not text:
                continue
            title = str(h.get("title") or "").strip()
            rows.append({
                "id": f"atanor-{name}-{i}",
                "title": title,
                "url": url_fn(title),
                "snippet": text[:600],
                "provider": f"atanor_index:{name}",
                "source_type": "atanor_index",
                "license_status": lic,              # EN-wiki lead / Wiktionary = CC-BY-SA
                "search_score": float(h.get("score") or 0.0),
                "normalized_query": query,
            })
    return rows


def index_status() -> dict[str, Any]:
    """Ops snapshot: which corpus is live + its size."""
    d = _pick_dir()
    if d is None:
        return {"available": False, "dir": None}
    idx = _get_index()
    meta = getattr(idx, "meta", {}) if idx is not None else {}
    return {
        "available": idx is not None,
        "dir": str(d),
        "n_docs": meta.get("n_docs"),
        "n_terms": meta.get("n_terms"),
        "n_postings": meta.get("n_postings"),
        "built_at": meta.get("built_at"),
    }
