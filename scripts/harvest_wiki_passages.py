# -*- coding: utf-8 -*-
"""Harvest Wikipedia LEAD PARAGRAPHS → an offline passage store (the OPEN-BOOK corpus).

Why (owner 2026-07-15 goal, honest strategy): closed-book graph lookup can't discriminate the
propositional/conceptual MCQ that KMMLU is made of — measured 0.21 (below the 0.25 guess floor),
because is_a/`defined_as` triples don't hold facts like ' ·· '.
That fact lives in the article's LEAD PROSE. The legitimate No-LLM path to MMLU-style parity is
OPEN-BOOK: retrieve the real passage at test time and verify each option against it — grounded in a
real sentence, no fabrication (see [[public-benchmark-open-book-strategy]]).

This streams the same bz2 dump and stores, per article: title -> cleaned lead text (up to ~600 chars).
Output: data/graph_scale/wiki_passages/passages.tsv (title<TAB>text, one per line, deduped).
The retriever (packages/reasoning_vm/openbook.py) loads it into a dict on first use.

 python scripts/harvest_wiki_passages.py --dump data/knowledge_sources/kowiki-latest-pages-articles.xml.bz2
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

# reuse the exact same wikimarkup cleaner as the is_a harvest (one grammar for reading prose)
from scripts.harvest_wikipedia import _clean, _PAREN_HANJA  # noqa: E402

_LEAD_MAX = 600
_SCRIPT = {"ko": re.compile(r"[가-힣]"), "en": re.compile(r"[A-Za-z]")}   # a line must carry the lang's script


def _lead_text(body: str, max_chars: int = _LEAD_MAX, script=_SCRIPT["ko"]) -> str:
    """The first real prose lines of the article, joined — the propositional lead, cleaned. Skips
    headers/lists/templates; drops the '(光合成)' hanja gloss after the title. `max_chars` controls
    lead vs. fuller-section capture; `script` gates lines to the target language (ko Hangul / en Latin)."""
    out: list[str] = []
    for line in _clean(body).splitlines():
        line = line.strip()
        if not line or line.startswith(("=", "*", "#", "|", "!", "{", ":", ";")):
            continue
        line = _PAREN_HANJA.sub("", line)
        if script.search(line) and len(line) >= 12:
            out.append(line)
        if sum(len(x) for x in out) >= max_chars:
            break
    text = " ".join(out)[:max_chars]
    return re.sub(r"\s+", " ", text).strip()


def build(dump: Path, out_name: str, limit: int | None, max_chars: int = _LEAD_MAX,
          lang: str = "ko") -> dict:
    script = _SCRIPT.get(lang, _SCRIPT["ko"])
    out = REPO / "data" / "graph_scale" / out_name
    out.mkdir(parents=True, exist_ok=True)
    fout = open(out / "passages.tsv", "w", encoding="utf-8")

    try:
        import indexed_bzip2 as _ibz2
        raw = _ibz2.open(str(dump), parallelization=4)
    except Exception:
        raw = bz2.BZ2File(str(dump), "rb")

    t0 = time.time()
    seen = kept = 0
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
        if ":" in title or title.endswith("(동음이의)") or not title:      # skip namespaces/disambig
            continue
        body = b"".join(buf).replace(b"</text>", b"").decode("utf-8", "ignore")
        if body.lstrip().startswith(("#넘겨주기", "#redirect", "#REDIRECT")):
            continue
        text = _lead_text(body, max_chars, script)
        if len(text) >= 24:
            fout.write(title.replace("\t", " ") + "\t" + text + "\n")
            kept += 1
        if seen % 50000 == 0:
            fout.flush()
            print(f'{{"seen": {seen}, "kept": {kept}, '
                  f'"rate_s": {round(seen/max(1e-9,time.time()-t0),1)}}}', flush=True)
    fout.close()
    rep = {"seen": seen, "kept": kept, "elapsed_s": round(time.time() - t0, 1), "out": str(out)}
    print("\nDONE", rep)
    return rep


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    args = sys.argv[1:]

    def _get(flag, default=None):
        return args[args.index(flag) + 1] if flag in args else default
    dump = Path(_get("--dump", "data/knowledge_sources/kowiki-latest-pages-articles.xml.bz2"))
    out_name = _get("--out", "wiki_passages")
    limit = _get("--limit")
    max_chars = int(_get("--maxchars", str(_LEAD_MAX)))
    lang = _get("--lang", "ko")
    if not dump.exists():
        print("dump not found:", dump)
        raise SystemExit(1)
    build(dump, out_name, int(limit) if limit else None, max_chars, lang)
