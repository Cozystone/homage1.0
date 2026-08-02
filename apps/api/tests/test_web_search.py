from __future__ import annotations

import asyncio
import urllib.error

import app.services.web_search as ws


# ---- pure helpers (no network) ----------------------------------------------

def test_wiki_host_matches_query_language():
    assert ws._wiki_host_for_query("Eiffel Tower") == "en.wikipedia.org"
    assert ws._wiki_host_for_query("에펠탑이 뭐야") == "ko.wikipedia.org"


def test_normalize_strips_question_scaffolding():
    assert ws._normalize_lookup_query("Who invented the telephone?") == "the telephone"
    assert ws._normalize_lookup_query("광합성이 뭐야?") == "광합성"
    assert ws._normalize_lookup_query("마리 퀴리가 누구야?") == "마리 퀴리"
    assert ws._normalize_lookup_query("What is the Eiffel Tower?") == "the Eiffel Tower"


def test_is_knowledge_lookup_query_recognizes_factual_forms():
    for q in ("Who invented the telephone?", "What is the Eiffel Tower?", "광합성이 뭐야?", "마리 퀴리가 누구야?", "When was Rome founded?"):
        assert ws.is_knowledge_lookup_query(q), q
    assert not ws.is_knowledge_lookup_query("안녕")
    assert not ws.is_knowledge_lookup_query("ㅋㅋ")


# ---- offline / cache behavior (monkeypatched network) ------------------------

def _offline(monkeypatch):
    def boom(*a, **k):
        raise urllib.error.URLError("offline: no network")
    monkeypatch.setattr(ws.urllib.request, "urlopen", boom)
    ws._WIKI_CACHE.clear()


def test_wiki_get_json_returns_empty_offline(monkeypatch):
    _offline(monkeypatch)
    assert ws._wiki_get_json("https://en.wikipedia.org/w/api.php?x=1") == {}


def test_wikipedia_search_returns_empty_offline(monkeypatch):
    _offline(monkeypatch)
    assert ws.wikipedia_search("Eiffel Tower", 3) == []


def test_search_web_offline_falls_back_to_static_without_crashing(monkeypatch):
    _offline(monkeypatch)
    result = asyncio.run(ws.search_web("What is the Eiffel Tower?", 4))
    assert result["provider"] == "static"  # never the live providers when offline
    assert isinstance(result.get("results"), list)


def test_wiki_get_json_uses_cache(monkeypatch):
    calls = {"n": 0}

    class _Resp:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(*a, **k):
        calls["n"] += 1
        return _Resp()

    ws._WIKI_CACHE.clear()
    monkeypatch.setattr(ws.urllib.request, "urlopen", fake_urlopen)
    url = "https://en.wikipedia.org/w/api.php?cache-test=1"
    first = ws._wiki_get_json(url)
    second = ws._wiki_get_json(url)
    assert first == second == {"ok": True}
    assert calls["n"] == 1  # second call served from cache


def test_wiki_get_json_retries_then_gives_up_on_429(monkeypatch):
    calls = {"n": 0}

    def always_429(*a, **k):
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(ws.urllib.request, "urlopen", always_429)
    monkeypatch.setattr(ws.time, "sleep", lambda *_: None)  # don't actually wait
    ws._WIKI_CACHE.clear()
    assert ws._wiki_get_json("https://en.wikipedia.org/w/api.php?rl=1", retries=1) == {}
    assert calls["n"] == 2  # initial try + one retry
