# -*- coding: utf-8 -*-
"""Harvest English is_a triples from a Wikipedia dump — the taxonomy half of the English knowledge core.

Overall growth (owner 2026-07-15): build the English brain properly, not a benchmark hack. Passages
(open-book) are one half; the is_a TAXONOMY is the other — 'X is a Y' categorization that powers
type-checking, the discovery engine, and grounded reasoning. English extraction is clean and No-LLM:
the lead sentence 'TITLE is/was a/an HEAD …' yields (TITLE, is_a, HEAD) with near-0 loss (no morphology).

  python scripts/harvest_wiki_isa_en.py --dump data/knowledge_sources/enwiki-full.xml.bz2 --out wiki_kg_en
"""
from __future__ import annotations

import bz2
import io
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.harvest_wikipedia import _clean            # noqa: E402  reuse the wikimarkup cleaner

# 'Photosynthesis is a process …' / 'Aristotle was an ancient Greek philosopher …' → the noun-phrase
# HEAD after the copula+article. Capture broadly, then walk words until a phrase-ending function word;
# the head is the last content word of that run (adjectives before it are fine).
_ISA = re.compile(r"^\s*(?:The\s+|An?\s+)?(.{2,60}?)\s+(?:is|was|are|were)\s+(?:an?|the)\s+(.{2,80})", re.I)
_NPSTOP = {"of", "in", "on", "at", "with", "for", "and", "or", "by", "to", "from", "as", "that",
           "which", "who", "whose", "used", "made", "known", "called", "this", "these", "those",
           "located", "found", "born", "consisting", "comprising", "having", "containing", "also",
           "was", "is", "are", "were", "belonging", "based", "developed", "created", "written"}
_STOPHEAD = {"one", "kind", "type", "form", "member", "part", "name", "term", "group", "series",
             "number", "set", "collection", "way", "result", "example", "variety", "sort"}


def _head_noun(tail: str) -> str | None:
    run: list[str] = []
    for w in re.findall(r"[a-z]+", tail.lower()):
        if w in _NPSTOP:
            break
        run.append(w)
    return run[-1] if run else None


def _lead_sentence(body: str) -> str:
    for line in _clean(body).splitlines():
        line = line.strip()
        if not line or line.startswith(("=", "*", "#", "|", "!", "{", ":", ";", "'")):
            continue
        if re.match(r"[A-Z]", line) and len(line) >= 15:
            m = re.split(r"(?<=[.!?])\s", line)
            return m[0] if m else line
    return ""


def build(dump: Path, out_name: str, limit: int | None) -> dict:
    from packages.graph_scale.triple_store import TripleStore
    out = REPO / "data" / "graph_scale" / out_name
    out.mkdir(parents=True, exist_ok=True)
    st = TripleStore(out, dict_backend="sharded", write_src=True)
    try:
        src = st.intern_source("enwiki", "https://en.wikipedia.org/wiki/{}")
    except Exception:
        src = 0
    try:
        import indexed_bzip2 as _ibz2
        raw = _ibz2.open(str(dump), parallelization=4)
    except Exception:
        raw = bz2.BZ2File(str(dump), "rb")

    t0 = time.time()
    seen = kept = triples = 0
    title = ""
    in_text = False
    buf: list[bytes] = []
    _title_re = re.compile(rb"<title>(.*?)</title>")
    for line in raw:
        if limit and seen >= limit:
            break
        m = _title_re.search(line)
        if m:
            title = m.group(1).decode("utf-8", "ignore").strip()
        if b"<text" in line:
            in_text = True
            buf = [line.split(b">", 1)[1] if b">" in line else b""]
            if b"</text>" in line:
                in_text = False
            else:
                continue
        elif in_text:
            buf.append(line)
            if b"</text>" not in line:
                continue
            in_text = False
        else:
            continue
        seen += 1
        if ":" in title or not title or title.endswith(("(disambiguation)",)):
            continue
        body = b"".join(buf).replace(b"</text>", b"").decode("utf-8", "ignore")
        if body.lstrip()[:12].lower().startswith("#redirect"):
            continue
        sent = _lead_sentence(body)
        m = _ISA.match(sent)
        if m:
            head = _head_noun(m.group(2))                          # noun-phrase head
            if head and 3 <= len(head) <= 30 and head not in _STOPHEAD:
                st.add(title, "is_a", head, source=src)
                triples += 1
                kept += 1
        if seen % 50000 == 0:
            st.flush()
            print(f'{{"seen": {seen}, "kept": {kept}, "triples": {triples}, '
                  f'"rate_s": {round(seen/max(1e-9,time.time()-t0),1)}}}', flush=True)
    st.flush()
    try:
        n = st.rebuild_index()
    except Exception:
        n = 0
    rep = {"seen": seen, "kept": kept, "triples": triples, "indexed_rows": int(n),
           "elapsed_s": round(time.time() - t0, 1), "out": str(out)}
    print("\nDONE", rep)
    return rep


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    args = sys.argv[1:]

    def _get(flag, default=None):
        return args[args.index(flag) + 1] if flag in args else default
    dump = Path(_get("--dump", "data/knowledge_sources/enwiki-full.xml.bz2"))
    out_name = _get("--out", "wiki_kg_en")
    limit = _get("--limit")
    if not dump.exists():
        print("dump not found:", dump)
        raise SystemExit(1)
    build(dump, out_name, int(limit) if limit else None)
