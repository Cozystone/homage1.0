# -*- coding: utf-8 -*-
"""Tier B / B2 lever i — build a FULL-ARTICLE passage corpus from the enwiki dump.

The measured B2 root cause is evidence starvation: MCQ-distinguishing evidence ("directional vs
stabilizing selection") sits in article BODIES, but the shipped corpus is LEAD paragraphs only
(wiki_passages_en_full, 7M leads). gold-option lexical presence is 28.5% there. This streams the
same dump once and emits EVERY body paragraph (not just the lead), reusing the proven wiki cleaner:

  data/graph_scale/wiki_passages_en_body/passages.tsv   (title<TAB>paragraph, one row per paragraph)

Then scripts/build_ring1_index.py rebuilds the disk BM25 over it, and the pre-declared gate is
re-measured: gold lexical presence 28.5% -> >=60% on the fresh slice. RED there = "the evidence is
absent even in the body", which seals B2 lever i honestly and hands the wall to representation (E9).

  python scripts/b2_build_fullarticle_corpus.py --dump D:/atanor_corpus/enwiki-latest-pages-articles.xml.bz2
"""
from __future__ import annotations

import argparse
import bz2
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.harvest_wiki_passages import _clean, _SCRIPT             # noqa: E402  (proven cleaner)

_EN = _SCRIPT["en"]
_MARKUP_PREFIX = ("=", "*", "#", "|", "!", "{", ":", ";", "}")
OUT = REPO / "data" / "graph_scale" / "wiki_passages_en_body"

# body prose leaks residue the lead never showed (spaced self-closing refs, stray brackets): a light
# post-clean pass over each candidate line on top of the proven _clean(), so the BM25 corpus stays prose.
_RE_REF = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/?>", re.I | re.S)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_BRACKET = re.compile(r"\[\[|\]\]|\{\{|\}\}")


def _extra_clean(line: str) -> str:
    line = _RE_REF.sub("", line)
    line = _RE_TAG.sub("", line)
    line = _RE_BRACKET.sub("", line)
    return line.strip()


def _paragraphs(body: str, target: int = 600, min_para: int = 120) -> list[str]:
    """Full-body prose split into paragraphs. Reuses the wiki cleaner, keeps English prose lines,
    breaks on section headers (a '=' line) and once a paragraph reaches ~`target` chars. Pure and
    unit-testable without the dump."""
    paras: list[str] = []
    cur: list[str] = []
    cur_len = 0

    def flush():
        nonlocal cur, cur_len
        if cur:
            text = re.sub(r"\s+", " ", " ".join(cur)).strip()
            if len(text) >= min_para:
                paras.append(text)
        cur, cur_len = [], 0

    for line in _clean(body).splitlines():
        line = line.strip()
        if not line:
            continue
        if line[:1] in _MARKUP_PREFIX:          # section header / list / table / template -> boundary
            flush()
            continue
        line = _extra_clean(line)               # strip residual refs / tags / stray brackets
        if not _EN.search(line) or len(line) < 12:
            continue
        cur.append(line)
        cur_len += len(line)
        if cur_len >= target:
            flush()
    flush()
    return paras


def build(dump: Path, limit: int | None, max_para: int = 12) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    fout = open(OUT / "passages.tsv", "w", encoding="utf-8")
    try:
        import indexed_bzip2 as _ibz2
        raw = _ibz2.open(str(dump), parallelization=4)
    except Exception:
        raw = bz2.BZ2File(str(dump), "rb")

    t0 = time.time()
    seen = kept_para = kept_art = 0
    title, in_text, buf = "", False, []
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
        paras = _paragraphs(body)[:max_para]        # cap per article -> tractable corpus + index size
        if paras:
            kept_art += 1
        for p in paras:
            fout.write(title.replace("\t", " ") + "\t" + p + "\n")
            kept_para += 1
        if seen % 100000 == 0:
            fout.flush()
            print(f'{{"seen": {seen}, "articles": {kept_art}, "paragraphs": {kept_para}, '
                  f'"rate_s": {round(seen/max(1e-9,time.time()-t0),1)}}}', flush=True)
    fout.close()
    return {"seen": seen, "articles": kept_art, "paragraphs": kept_para,
            "elapsed_s": round(time.time() - t0, 1), "out": str(OUT / "passages.tsv")}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default="D:/atanor_corpus/enwiki-latest-pages-articles.xml.bz2")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-para", type=int, default=12)
    args = ap.parse_args()
    dump = Path(args.dump)
    if not dump.exists():
        print(f"dump not found: {dump} (waiting on the background download to finish)")
        return 1
    rep = build(dump, args.limit, args.max_para)
    print(f'RESULT b2_body_corpus {rep}')
    print("next: python scripts/build_ring1_index.py over wiki_passages_en_body, then re-measure the "
          "gold lexical-presence gate (28.5% -> >=60%).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
