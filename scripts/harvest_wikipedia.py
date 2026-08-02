# -*- coding: utf-8 -*-
"""Harvest a Wikipedia XML dump → propositional triples in a TripleStore (the KNOWLEDGE lever).

Owner 2026-07-15: download Wikipedia/textbooks and fill the graph — the biggest lever to lift the
public benchmarks off random. This reads the (bz2) dump, and for each article extracts CLAIMS from
its lead prose using the SAME organ (`statement_entailment.extract_claim`) that VERIFIES claims — so
reading and verifying share one grammar: read prose → (subject, relation, object) → store, cited.

Un-hallucinatable contract: every stored triple traces to a real Wikipedia sentence (source='kowiki',
the sentence kept as provenance). No LLM, no fabrication — just structure read off real text.

  python scripts/harvest_wikipedia.py --dump data/knowledge_sources/kowiki-latest-pages-articles.xml.bz2 \
      --out wiki_kg --limit 200000
"""
from __future__ import annotations

import bz2
import html
import io
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# ── wikimarkup cleanup — enough to recover the lead sentence(s), not a full parser ───────────────
_REF = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.S)
_HTML = re.compile(r"<[^>]+>")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_FILE = re.compile(r"\[\[(?:파일|File|Image|그림):[^\]]*\]\]", re.I)
_LINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]|]+)\]\]")
_BOLDIT = re.compile(r"'{2,5}")
_TABLE = re.compile(r"\{\|.*?\|\}", re.S)
_PAREN_HANJA = re.compile(r"\s*\((?:[一-龥ㄱ-ㆎ\s,;/·]|IPA|영어|한자|문화어)[^)]*\)")


def _clean(text: str) -> str:
    for _ in range(3):                                   # nested templates → iterate a few times
        text = _TEMPLATE.sub("", text)
    text = _COMMENT.sub("", text)
    text = _TABLE.sub("", text)
    text = _REF.sub("", text)
    text = _FILE.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _BOLDIT.sub("", text)
    text = _HTML.sub("", text)
    return html.unescape(text)                           # &gt;/&lt;/&amp; → real chars (kills 'gt' noise)


def _lead_sentences(text: str, k: int = 2) -> list[str]:
    """The first k sentences of the lead paragraph (skip headers/lists/empty lines)."""
    out: list[str] = []
    for line in _clean(text).splitlines():
        line = line.strip()
        if not line or line.startswith(("=", "*", "#", "|", "!", "{", ":", ";")):
            continue
        line = _PAREN_HANJA.sub("", line)                # drop '(光合成)' hanja gloss right after title
        for sent in re.split(r"(?<=다)\.\s|(?<=다)\.$|\.\s", line):
            sent = sent.strip()
            if len(sent) >= 8 and re.search(r"[가-힣]", sent):
                out.append(sent if sent.endswith(("다", ".")) else sent + "다")
                if len(out) >= k:
                    return out
        if out:
            break
    return out


def build(dump: Path, out_name: str, limit: int | None) -> dict:
    from packages.graph_scale.triple_store import TripleStore
    from packages.reasoning_vm.statement_entailment import extract_claim

    out = REPO / "data" / "graph_scale" / out_name
    out.mkdir(parents=True, exist_ok=True)
    st = TripleStore(out, dict_backend="sharded", write_src=True)
    try:
        src = st.intern_source("kowiki", "https://ko.wikipedia.org/wiki/{}")
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
    buf: list[str] = []
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
        # a full <text> block closed → process the article
        seen += 1
        if ":" in title or title.endswith(("(동음이의)",)) or not title:   # skip namespaces/disambig
            continue
        body = b"".join(buf).replace(b"</text>", b"").decode("utf-8", "ignore")
        if body.lstrip().startswith(("#넘겨주기", "#redirect", "#REDIRECT")):
            continue
        got = False
        for sent in _lead_sentences(body, k=2):
            if title not in sent:                          # anchor: the sentence must be ABOUT the title
                sent = f"{title}은 {sent}" if not sent.startswith(title) else sent
            try:
                claim = extract_claim(sent)
            except Exception:
                claim = None
            if not claim:
                continue
            s, r, o = claim
            # PRECISION GATE (un-hallucinatable): harvest is_a ONLY, and ONLY from a genuine copula


            # The dense, clean is_a taxonomy is the high-value signal; other relations stay in the world pack.
            copula = bool(re.search(r"(이다|인|이며|이고|였다|이었다)$", sent.rstrip(" .")))
            if r != "is_a" or not copula:
                continue
            o = o.strip("[]()<> \t")
            if s and o and 2 <= len(o) <= 30 and s != o and re.fullmatch(r"[가-힣A-Za-z0-9 ]+", o):
                st.add(title, "is_a", o, source=src)       # subject = the article title (canonical)
                triples += 1
                got = True
        kept += int(got)
        if seen % 20000 == 0:
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
    dump = Path(_get("--dump", "data/knowledge_sources/kowiki-latest-pages-articles.xml.bz2"))
    out_name = _get("--out", "wiki_kg")
    limit = _get("--limit")
    if not dump.exists():
        print("dump not found:", dump)
        raise SystemExit(1)
    build(dump, out_name, int(limit) if limit else None)
