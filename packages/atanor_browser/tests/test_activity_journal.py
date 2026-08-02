# -*- coding: utf-8 -*-
"""Personal browsing activity journal — local, PII-gated, interest-deriving."""

from __future__ import annotations

import importlib

import packages.atanor_browser.activity_journal as aj


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(aj, "JOURNAL", tmp_path / "j.jsonl")
    # isolate the episodic mirror too (the package __init__ shadows the submodule
    # with a re-exported function -> import the real module via importlib)
    tl = importlib.import_module("packages.episodic_memory.timeline")
    monkeypatch.setattr(tl, "EVENTS_PATH", tmp_path / "ev.jsonl")


def test_visit_and_search_are_journaled_locally(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    out = aj.record_activity("visit", url="https://news.ycombinator.com/item?id=1", title="HN")
    assert out["recorded"] and out["host"] == "news.ycombinator.com"
    aj.record_activity("search", query="파이썬 리스트 정렬", url="https://google.com/search")
    st = aj.status()
    assert st["local_only"] is True and st["events"] == 2

    tl = importlib.import_module("packages.episodic_memory.timeline")
    assert any(r["predicate"] == "검색" for r in tl.timeline("파이썬 리스트 정렬"))


def test_pii_query_is_dropped(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    out = aj.record_activity("search", query="내 번호 010-1234-5678 조회",
                             url="https://google.com/search")
    assert out["pii_dropped"] is True
    # the PII query never lands in recall
    assert all("1234" not in (h.get("query") or "") for h in aj.recall())


def test_interests_exclude_search_engines_and_weight_by_dwell(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    aj.record_activity("visit", url="https://google.com/search")  # the road, not dest
    aj.record_activity("visit", url="https://arxiv.org/abs/1", dwell_s=180)  # long read
    aj.record_activity("visit", url="https://arxiv.org/abs/2", dwell_s=120)
    aj.record_activity("visit", url="https://x.com/a", dwell_s=3)  # bounce
    ints = aj.interests()
    domains = [i["domain"] for i in ints]
    assert "google.com" not in domains          # search engines excluded
    assert domains[0] == "arxiv.org"            # dwell-weighted to the top


def test_recall_matches_term_newest_first(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    aj.record_activity("visit", url="https://arxiv.org/abs/1", title="attention paper")
    aj.record_activity("visit", url="https://wikipedia.org/x", title="바다")
    hits = aj.recall("arxiv")
    assert len(hits) == 1 and hits[0]["host"] == "arxiv.org"
    assert aj.recall()[0]["title"] == "바다"     # no query -> newest first


def test_revisits_flag_habitual_domains(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    for _ in range(4):
        aj.record_activity("visit", url="https://news.ycombinator.com/")
    aj.record_activity("visit", url="https://arxiv.org/abs/1")
    rv = aj.revisits(min_count=3)
    assert len(rv) == 1 and rv[0]["domain"] == "news.ycombinator.com"


def test_sessions_thread_by_time_gap(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    aj.record_activity("visit", url="https://a.com/")
    aj.record_activity("visit", url="https://b.com/")  # same session (no gap)
    sess = aj.sessions_summary()
    assert len(sess) == 1
    assert set(sess[0]["hosts"]) == {"a.com", "b.com"} and sess[0]["events"] == 2
