# -*- coding: utf-8 -*-
"""Run the extractor once over every corpus and store the answers — then measure the throughput.

    python scripts/build_property_table.py                 # dictionaries only (fast)
    python scripts/build_property_table.py --with-wiki     # + 7M Wikipedia leads (slow build)
    python scripts/build_property_table.py --bench-only    # just re-measure the existing table

THE OWNER ASKED FOR THOUSANDS TO TENS OF THOUSANDS OF SEARCHES PER SECOND. That is not reachable by
making BM25 faster and it is easy once the question changes shape. A person types ambiguous language and
needs ranking, so a search engine must tokenize, score thousands of postings and sort; ATANOR's shape
parser has already produced (entity, relation) before it asks, so ranking is work nobody reads.

A human search engine cannot precompute its answers because it does not know the question in advance.
ATANOR does: the relations are a small closed set. So the extraction that used to run per query runs once
here, over every passage in every corpus, and the result is a memmapped table.

WHAT IS MEASURED AT THE END is queries per second on real deficit questions, against the BM25 path on the
same questions, single process, no warm cache tricks beyond what a normal run gets. If the number is not
what this docstring claims, the number is what gets reported.

WHAT THIS DOES NOT BUY, said plainly: recall. The table can only answer what the extractor could see, so
its coverage equals the extractor's coverage. This makes retrieval free; it does not make extraction
smarter, and the consensus floor is untouched -- the table stores which corpus said what precisely so the
same rule can be applied to it.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np                                                        # noqa: E402

from packages.atanor_index.property_table import (PropertyTable,          # noqa: E402
                                                  PropertyTableBuilder)
from packages.graph_scale.property_extraction import extract              # noqa: E402

OUT = Path("data/atanor_index/property_table")
REPORT = Path("data/perception/property_table_bench.json")
QUESTIONS = Path("data/acquisition_daemon/deficit_questions.txt")
RELATIONS = ["used_for", "capable_of", "made_of"]
CORPORA = [
    ("wiktionary", Path("data/graph_scale/wiktionary_passages_en/passages.tsv")),
    ("wordnet", Path("data/graph_scale/wordnet_passages_en/passages.tsv")),
    ("gcide", Path("data/graph_scale/gcide_passages_en/passages.tsv")),
]
WIKI = ("wiki", Path("data/graph_scale/wiki_passages_en_full/passages.tsv"))


def build(with_wiki: bool) -> dict:
    b = PropertyTableBuilder()
    corpora = list(CORPORA) + ([WIKI] if with_wiki else [])
    for name, tsv in corpora:
        if not tsv.exists():
            print(f"  {name}: no passages at {tsv} -- skipped")
            continue
        t0 = time.time()
        rows = kept = 0
        with tsv.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                title, _, text = line.partition("\t")
                title = title.strip().lower()
                if not title or not text:
                    continue
                rows += 1
                for rel, obj in extract(title, text):
                    b.add(title, rel, obj, name)
                    kept += 1
                if rows % 1000000 == 0:
                    print(f"    {name}: {rows:,} passages, {kept:,} facts", flush=True)
        print(f"  {name}: {rows:,} passages -> {kept:,} facts in {time.time() - t0:.0f}s")
    print(f"\nwriting the table: {len(b):,} distinct (entity, relation) keys")
    meta = b.write(OUT, RELATIONS)
    print(f"  {meta['n_keys']:,} keys   {meta['n_values']:,} values   "
          f"{meta['n_objects']:,} distinct objects   corpora {meta['corpora']}")
    size = sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())
    print(f"  {size / 1e6:.1f} MB on disk")
    return meta


def bench() -> dict:
    """Queries per second on real questions. The comparison is the BM25 path on the same questions."""
    from packages.base_brain.relational_lookup import parse_relational_shape

    t = PropertyTable(OUT)
    lines = [ln.strip() for ln in QUESTIONS.read_text(encoding="utf-8").splitlines() if ln.strip()]
    ents, rels = [], []
    ASK = {"used for": "used_for", "capable of": "capable_of", "made of": "made_of"}
    for q in lines:
        sh = parse_relational_shape(q)
        if not sh:
            continue
        e = str(sh.get("entity") or "").strip().lower()
        r = ASK.get(str(sh.get("rel_norm") or "").strip().lower())
        if e and r:
            ents.append(e)
            rels.append(r)
    n = len(ents)
    print(f"\n{n:,} real deficit questions, {len(t):,} keys in the table")

    t0 = time.time()
    counts = t.count_many(ents, rels)
    el_batch = time.time() - t0
    hits = int((counts > 0).sum())
    two = int((counts >= 2).sum())

    t0 = time.time()
    for e, r in zip(ents[:2000], rels[:2000]):
        t.lookup(e, r)
    el_single = time.time() - t0

    from packages.atanor_index.retriever import local_search
    t0 = time.time()
    for q in lines[:200]:
        local_search(q, 8)
    el_bm25 = time.time() - t0

    qps_batch = n / max(el_batch, 1e-9)
    qps_single = 2000 / max(el_single, 1e-9)
    qps_bm25 = 200 / max(el_bm25, 1e-9)
    print()
    print(f"{'path':<34}{'queries':>10}{'seconds':>10}{'QPS':>14}")
    print(f"{'property table, batch':<34}{n:>10,}{el_batch:>10.3f}{qps_batch:>14,.0f}")
    print(f"{'property table, one at a time':<34}{2000:>10,}{el_single:>10.3f}{qps_single:>14,.0f}")
    print(f"{'BM25 over 4 corpora':<34}{200:>10,}{el_bm25:>10.3f}{qps_bm25:>14,.0f}")
    print()
    print(f"speedup, batch vs BM25: {qps_batch / max(qps_bm25, 1e-9):,.0f}x")
    print(f"answered: {hits:,} of {n:,} questions   reaching 2 corpora: {two:,}")
    print("the consensus floor is UNCHANGED; the table stores which corpus said what so the same "
          "rule applies to it.")

    rep = {"n_questions": n, "n_keys": len(t), "qps_batch": qps_batch,
           "qps_single": qps_single, "qps_bm25": qps_bm25,
           "answered": hits, "reaching_two_corpora": two,
           "corpora": t.corpora, "relations": t.meta.get("relations")}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(f"wrote {REPORT}")
    return rep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-wiki", action="store_true")
    ap.add_argument("--bench-only", action="store_true")
    args = ap.parse_args()
    if not args.bench_only:
        print("extracting every fact from every corpus, once ...")
        build(args.with_wiki)
    bench()


if __name__ == "__main__":
    main()
