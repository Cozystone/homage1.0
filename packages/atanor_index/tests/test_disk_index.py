"""Correctness of the disk-backed BM25 index: build a tiny corpus, verify retrieval + ranking + SPIMI
multi-run merge give the same answer as an obvious brute-force expectation. No network, no LLM."""
from __future__ import annotations

import numpy as np

from packages.atanor_index.disk_index import DiskIndex, build_index, tokenize


def _corpus(tmp):
    p = tmp / "passages.tsv"
    rows = [
        "Seoul\tSeoul is the capital and largest metropolis of South Korea.",
        "Tokyo\tTokyo is the capital of Japan and its most populous city.",
        "Water\tWater is an inorganic compound with the chemical formula H2O.",
        "Paris\tParis is the capital and most populous city of France.",
        "Penguin\tThe penguin is a flightless aquatic bird living in the southern hemisphere.",
    ]
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return p


def test_build_and_retrieve(tmp_path):
    src = _corpus(tmp_path)
    out = tmp_path / "idx"
    meta = build_index(src, out, progress_every=0)
    assert meta["n_docs"] == 5
    assert meta["n_terms"] > 0

    idx = DiskIndex(out)
    hits = idx.search_topk("what is the capital of South Korea", k=3)
    assert hits, "expected a hit for the Seoul query"
    assert hits[0]["title"] == "Seoul"          # BM25 must rank Seoul first

    h2o = idx.search_topk("chemical formula of water", k=2)
    assert h2o and h2o[0]["title"] == "Water"

    # open-world: a term absent from the corpus returns nothing (no confabulation)
    assert idx.search_topk("zzzznonexistentterm", k=3) == []
    idx.close()


def test_multi_run_merge_matches(tmp_path):
    """Force many tiny SPIMI runs (ram_postings=3) and confirm the merged postings are still correct —
    guards the k-way merge / tf-accumulation path that only triggers when a term spans runs."""
    src = _corpus(tmp_path)
    out = tmp_path / "idx2"
    build_index(src, out, ram_postings=3, progress_every=0)
    idx = DiskIndex(out)
    # "capital" appears in Seoul, Tokyo, Paris — all three must be retrievable
    titles = {h["title"] for h in idx.search_topk("capital", k=5)}
    assert {"Seoul", "Tokyo", "Paris"} <= titles
    idx.close()


def test_tf_accumulates(tmp_path):
    p = tmp_path / "p.tsv"
    p.write_text("Repeat\talpha alpha alpha beta\nOnce\talpha gamma\n", encoding="utf-8")
    out = tmp_path / "idx3"
    build_index(p, out, ram_postings=2, progress_every=0)
    idx = DiskIndex(out)
    hits = idx.search_topk("alpha", k=2)
    # Repeat has tf=3 for alpha but is longer; Once has tf=1. Both retrieved; Repeat ranked >= Once.
    by = {h["title"]: h["score"] for h in hits}
    assert "Repeat" in by and "Once" in by
    assert by["Repeat"] >= by["Once"]
    idx.close()


def test_tokenize_drops_stopwords():
    toks = tokenize("The capital of the South Korea")
    assert "the" not in toks and "of" not in toks
    assert "capital" in toks and "korea" in toks
