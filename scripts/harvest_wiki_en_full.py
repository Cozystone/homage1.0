# -*- coding: utf-8 -*-
"""SINGLE-PASS English Wikipedia harvester → passages + is_a taxonomy in one stream over the 23 GB dump.

Overall growth (owner 2026-07-15): build the full English knowledge core. Two passes over 23 GB is
wasteful; this streams once and emits BOTH halves per article:
  • data/graph_scale/wiki_passages_en_full/passages.tsv   (title<TAB>lead prose, the open-book corpus)
  • data/graph_scale/wiki_kg_en/                           (title, is_a, head-noun — the taxonomy)

  python scripts/harvest_wiki_en_full.py --dump data/knowledge_sources/enwiki-full.xml.bz2
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
from scripts.harvest_wiki_passages import _lead_text, _SCRIPT          # noqa: E402
from scripts.harvest_wiki_isa_en import _ISA, _head_noun, _STOPHEAD, _lead_sentence  # noqa: E402

_PMAX = 700


def build(dump: Path, limit: int | None) -> dict:
    from packages.graph_scale.triple_store import TripleStore
    pdir = REPO / "data" / "graph_scale" / "wiki_passages_en_full"
    pdir.mkdir(parents=True, exist_ok=True)
    fout = open(pdir / "passages.tsv", "w", encoding="utf-8")
    kg = TripleStore(REPO / "data" / "graph_scale" / "wiki_kg_en", dict_backend="sharded", write_src=True)
    try:
        src = kg.intern_source("enwiki", "https://en.wikipedia.org/wiki/{}")
    except Exception:
        src = 0
    try:
        import indexed_bzip2 as _ibz2
        raw = _ibz2.open(str(dump), parallelization=4)
    except Exception:
        raw = bz2.BZ2File(str(dump), "rb")

    t0 = time.time()
    seen = kept_p = kept_i = 0
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
        if ":" in title or not title or title.endswith("(disambiguation)"):
            continue
        body = b"".join(buf).replace(b"</text>", b"").decode("utf-8", "ignore")
        if body.lstrip()[:12].lower().startswith("#redirect"):
            continue
        # (a) passage
        text = _lead_text(body, _PMAX, _SCRIPT["en"])
        if len(text) >= 24:
            fout.write(title.replace("\t", " ") + "\t" + text + "\n")
            kept_p += 1
        # (b) is_a — reuse the same lead
        mm = _ISA.match(_lead_sentence(body))
        if mm:
            head = _head_noun(mm.group(2))
            if head and 3 <= len(head) <= 30 and head not in _STOPHEAD:
                kg.add(title, "is_a", head, source=src)
                kept_i += 1
        if seen % 100000 == 0:
            fout.flush()
            kg.flush()
            print(f'{{"seen": {seen}, "passages": {kept_p}, "isa": {kept_i}, '
                  f'"rate_s": {round(seen/max(1e-9,time.time()-t0),1)}}}', flush=True)
    fout.close()
    kg.flush()
    try:
        n = kg.rebuild_index()
    except Exception:
        n = 0
    rep = {"seen": seen, "passages": kept_p, "isa": kept_i, "isa_indexed": int(n),
           "elapsed_s": round(time.time() - t0, 1)}
    print("\nDONE", rep)
    return rep


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    args = sys.argv[1:]

    def _get(flag, default=None):
        return args[args.index(flag) + 1] if flag in args else default
    dump = Path(_get("--dump", "data/knowledge_sources/enwiki-full.xml.bz2"))
    limit = _get("--limit")
    if not dump.exists():
        print("dump not found:", dump)
        raise SystemExit(1)
    build(dump, int(limit) if limit else None)
