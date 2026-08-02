# -*- coding: utf-8 -*-
"""Browser session orchestration — tab lifecycle + two-lane navigation routing."""

from __future__ import annotations

from packages.atanor_browser.browser_session import BrowserSession


class _FakeJournal:
    def __init__(self):
        self.calls = []

    def record_activity(self, kind, url="", query="", title="", dwell_s=0.0):
        self.calls.append({"kind": kind, "url": url, "query": query, "title": title})
        return {"recorded": True, "kind": kind}


def _sess():
    return BrowserSession(journal=_FakeJournal())


def test_tab_lifecycle():
    s = _sess()
    t = s.open_tab("https://arxiv.org/abs/1")
    assert t["active"]
    st = s.state()
    assert st["count"] == 1 and st["active"] == t["tab_id"]
    t2 = s.open_tab("https://news.ycombinator.com/")
    assert s.state()["active"] == t2["tab_id"]  # newest active
    s.close_tab(t2["tab_id"])
    assert s.state()["active"] == t["tab_id"]    # falls back to remaining tab


def test_navigation_always_journals_personal_lane():
    j = _FakeJournal()
    s = BrowserSession(journal=j)
    t = s.open_tab()
    s.navigate(t["tab_id"], "https://arxiv.org/x", title="paper")
    assert any(c["kind"] == "visit" and c["url"] == "https://arxiv.org/x" for c in j.calls)


def test_content_lane_is_opt_in_and_needs_dom():
    j = _FakeJournal()
    s = BrowserSession(journal=j)
    t = s.open_tab()
    # default: private — no content contribution even with DOM present
    r = s.navigate(t["tab_id"], "https://x.com/a", dom_text="<html>...</html>")
    assert r["contributed"] is None
    # opt-in but no DOM -> still nothing to contribute
    r2 = s.navigate(t["tab_id"], "https://x.com/b", contribute_content=True)
    assert r2["contributed"] is None
    # opt-in WITH DOM -> the shared lane runs
    html = ("<html><head><title>바다 - 위키</title></head><body>"
            "<article><p>바다는 소금물이 넓게 고인 곳이다.</p></article></body></html>")
    r3 = s.navigate(t["tab_id"], "https://ko.wikipedia.org/wiki/바다",
                    dom_text=html, contribute_content=True)
    assert r3["contributed"] is not None
    assert r3["contributed"]["written_to_verified_store"] is False


def test_search_routes_to_journal():
    j = _FakeJournal()
    s = BrowserSession(journal=j)
    t = s.open_tab()
    s.search(t["tab_id"], "RotatE 임베딩", engine_url="https://google.com/search")
    assert any(c["kind"] == "search" and c["query"] == "RotatE 임베딩" for c in j.calls)


def test_back_walks_history():
    s = _sess()
    t = s.open_tab("https://a.com/")["tab_id"]
    s.navigate(t, "https://b.com/")
    s.navigate(t, "https://c.com/")
    assert s.back(t)["url"] == "https://b.com/"
    assert s.back(t)["url"] == "https://a.com/"
    assert s.back(t)["ok"] is False  # no more back history
