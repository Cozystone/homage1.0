# -*- coding: utf-8 -*-
"""Roamed harvest -> ATANOR's own BM25 index -> self-search (no external SERP)."""
import packages.atanor_browser.roam_to_index as r2i


def test_roam_corpus_to_self_search(tmp_path, monkeypatch):
    monkeypatch.setattr(r2i, "_DIR", tmp_path)
    monkeypatch.setattr(r2i, "_CORPUS", tmp_path / "roam_corpus.tsv")
    monkeypatch.setattr(r2i, "_INDEX", tmp_path / "roam_index")
    pages = [
        {"url": "a", "title": "Recall process", "text": "A recall is issued after a defect is reported. " * 12},
        {"url": "b", "title": "Launch sequence", "text": "The rocket ignites then an abort may follow if telemetry fails. " * 12},
    ]
    assert r2i.append_pages(pages) == 2
    assert r2i.corpus_size() == 2
    r2i.rebuild_index()
    hits = r2i.search("abort telemetry rocket", k=2)
    assert hits and hits[0]["title"] == "Launch sequence"     # self-search finds the right doc


def test_search_empty_before_index(tmp_path, monkeypatch):
    monkeypatch.setattr(r2i, "_INDEX", tmp_path / "nope")
    assert r2i.search("anything") == []                        # honest: nothing until built


def test_thin_pages_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(r2i, "_DIR", tmp_path)
    monkeypatch.setattr(r2i, "_CORPUS", tmp_path / "c.tsv")
    assert r2i.append_pages([{"url": "x", "title": "t", "text": "too short"}]) == 0
