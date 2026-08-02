# -*- coding: utf-8 -*-
"""Wire the roamer's harvest into ATANOR's OWN search index (the self-search engine).

Owner vision: build an AI-friendly search engine ATANOR grows by roaming, instead of leaning on an
external SERP. This is the seam: what autonomous_surf reads on the open web is written to a plain
title<TAB>text corpus, and packages/atanor_index (our own disk-backed BM25) indexes it. Then
local_search over the roamed corpus replaces the external engine for anything ATANOR has already
seen. No new index engine -- it reuses the existing atanor_index build/search verbatim.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

_DIR = Path(__file__).resolve().parents[2] / "data" / "atanor_browser"
_CORPUS = _DIR / "roam_corpus.tsv"          # title<TAB>text, one roamed page per line (append-only)
_INDEX = _DIR / "roam_index"

_WS = re.compile(r"\s+")


def _clean(s: str) -> str:
    return _WS.sub(" ", (s or "").replace("\t", " ").replace("\n", " ")).strip()


def append_pages(pages: Iterable) -> int:
    """Append roamed PagePerception objects (or {title,text,url} dicts) to the corpus tsv. Returns
    how many non-empty pages were written. Deduped by URL within this call."""
    _DIR.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    n = 0
    with open(_CORPUS, "a", encoding="utf-8") as f:
        for p in pages:
            url = getattr(p, "url", None) or (p.get("url") if isinstance(p, dict) else "")
            title = getattr(p, "title", None) or (p.get("title") if isinstance(p, dict) else "") or url
            text = (p.main_text() if hasattr(p, "main_text")
                    else (p.get("text", "") if isinstance(p, dict) else ""))
            title, text = _clean(title), _clean(text)
            if not text or len(text) < 80 or url in seen:
                continue
            seen.add(url)
            f.write(f"{title}\t{text}\n")
            n += 1
    return n


def rebuild_index() -> dict:
    """(Re)build the disk BM25 index over the roamed corpus. Returns the index meta."""
    from packages.atanor_index.disk_index import build_index
    if not _CORPUS.exists():
        return {"error": "no roam corpus yet"}
    _INDEX.mkdir(parents=True, exist_ok=True)
    return build_index(_CORPUS, _INDEX)


def search(query: str, k: int = 6) -> list[dict]:
    """Search ATANOR's OWN roamed corpus (no external engine). Returns [] until the index is built."""
    from packages.atanor_index.disk_index import DiskIndex
    if not (_INDEX / "meta.json").exists():
        return []
    return DiskIndex(_INDEX).search_topk(query, k=k)


def corpus_size() -> int:
    if not _CORPUS.exists():
        return 0
    return sum(1 for _ in open(_CORPUS, encoding="utf-8"))
