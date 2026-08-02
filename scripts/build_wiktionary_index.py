# -*- coding: utf-8 -*-
"""A SECOND corpus for ATANOR's own search head — because one corpus can never reach consensus.

    python scripts/build_wiktionary_index.py

WHY THIS IS THE FIRST STEP OF THE OWN-SEARCH PATH, and it is not the step I expected. The search head
already exists and works: `packages.atanor_index.retriever.local_search` runs BM25 over a 1.8 GB disk
index of 7,016,505 Wikipedia lead passages, answers in 0.02-0.8 s, needs no network, and is already wired
into the provider fan-out in web_search.py. Measured tonight on the deficit questions it returns real
hits -- Mower, Borer, Wheel tractor-scraper.

Every one of those hits is en.wikipedia.org. The acquisition loop only accepts a fact that TWO DISTINCT
DOMAINS assert, so an index over one site cannot land a single fact no matter how good its retrieval is.
The bottleneck in the own-search path is not the search head. It is that ATANOR owns exactly one corpus
about the world.

WIKTIONARY IS THE SECOND ONE ALREADY ON DISK. kaikki-en is 470 MB, a different work by a different
editor community, served from a different domain, and its definitions ARE property statements by
editorial convention -- which is the whole reason the dictionary lane outscored the encyclopedia lane
tonight (used_for 0.559 against 0.471, capable_of 0.317 against 0.235).

AND THE HONEST CAVEAT, which belongs here rather than in a footnote: Wikipedia and Wiktionary are two
works but ONE ECOSYSTEM. Both are Wikimedia projects, their editors overlap, and one routinely cites the
other. The consensus gate counts distinct DOMAINS and will read them as two, which is true by the rule
and generous in spirit. A fact corroborated by wiktionary + wikipedia is real evidence and is WEAKER than
the same fact corroborated by two unrelated sites. A genuinely independent third corpus about ordinary
objects is still missing, and that is the next thing this path needs -- not more retrieval.

No network: the dump is local. No LLM: BM25 is corpus statistics.
"""
from __future__ import annotations

import gzip
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.atanor_index.disk_index import build_index          # noqa: E402

KAIKKI = Path("data/graph_scale/kaikki-en.jsonl.gz")
PASSAGES = Path("data/graph_scale/wiktionary_passages_en/passages.tsv")
OUT_DIR = Path("data/atanor_index/wiktionary_en")
MAX_SENSES = 6
MIN_CHARS = 30
SKIP = re.compile(r"^\s*(abbreviation|alternative|alt\.|plural|singular|initialism|acronym|"
                  r"misspelling|obsolete form|archaic form|clipping|contraction|eye dialect)\b", re.I)


def write_passages() -> int:
    """One passage per (word, pos): the word, then its senses, so BM25 sees both the name and the gloss.

    Senses are joined rather than split one-per-passage because a property question ("what is a mower
    used for") should retrieve the WORD, and splitting would make six weak documents compete with each
    other instead of one strong one."""
    PASSAGES.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with gzip.open(KAIKKI, "rt", encoding="utf-8") as fh, \
            PASSAGES.open("w", encoding="utf-8", newline="\n") as out:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            word = (d.get("word") or "").strip()
            pos = (d.get("pos") or "").strip()
            if not word or not pos or len(word) > 60:
                continue
            glosses = []
            for s in d.get("senses", [])[:MAX_SENSES]:
                g = (s.get("glosses") or [""])[0].strip()
                if g and not SKIP.match(g):
                    glosses.append(g)
            if not glosses:
                continue
            text = f"{word} ({pos}): " + " ".join(glosses)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) < MIN_CHARS:
                continue
            out.write(f"{word}\t{text}\n")      # title \t text, the shape build_index expects
            n += 1
            if n % 200000 == 0:
                print(f"  {n:,} passages", flush=True)
    return n


def main() -> None:
    if not KAIKKI.exists():
        sys.exit(f"no dictionary at {KAIKKI}")
    if OUT_DIR.joinpath("meta.json").exists():
        print(f"{OUT_DIR} already built; delete it to rebuild")
        return
    print(f"writing passages from {KAIKKI} ...")
    t0 = time.time()
    n = write_passages()
    print(f"{n:,} passages in {time.time() - t0:.0f}s -> {PASSAGES} "
          f"({PASSAGES.stat().st_size / 1e6:.0f} MB)")
    print(f"\nbuilding the BM25 index into {OUT_DIR} ...")
    t1 = time.time()
    build_index(PASSAGES, OUT_DIR)
    print(f"built in {time.time() - t1:.0f}s")
    meta = json.loads((OUT_DIR / "meta.json").read_text(encoding="utf-8"))
    print(f"  {meta.get('n_docs', 0):,} docs   {meta.get('n_terms', 0):,} terms   "
          f"{meta.get('n_postings', 0):,} postings")
    print("\nwikipedia index for comparison: 7,016,505 docs, 4,818,027 terms")
    print("retriever must now query BOTH -- one corpus cannot satisfy a two-domain consensus gate.")


if __name__ == "__main__":
    main()
