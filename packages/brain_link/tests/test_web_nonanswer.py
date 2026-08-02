# -*- coding: utf-8 -*-
"""Non-answer rejection — the overnight PC↔edge dialogue exposed the web lane accepting snippets that
are English and on-topic but say NOTHING: Wikipedia disambiguation stubs ("Topics referred to by the
same term") and glossary word-lists ("a - accent - acute - all the best - alpha …"). These read as
confident but carry zero meaning, so they must never become an answer — not even as the fallback."""
from __future__ import annotations

from collections import Counter

import packages.brain_link.web_knowledge as wk


def test_disambiguation_stub_is_nonanswer():
    assert wk._is_nonanswer("Topics referred to by the same term")
    assert wk._is_nonanswer("State may refer to: a political division, a condition, ...")
    assert wk._is_nonanswer("Lower (disambiguation)")


def test_wordlist_dump_is_nonanswer():
    assert wk._is_nonanswer("a - accent - acute - all the best - alpha - B - best - beta - bravo")


def test_real_definition_is_not_nonanswer():
    assert not wk._is_nonanswer("A city is a large human settlement with defined boundaries.")
    assert not wk._is_nonanswer("Anarchy is a situation in which a government does not exist.")


def test_learn_from_web_skips_stub_prefers_real_definition(monkeypatch):
    """With a disambiguation stub ranked FIRST and a real definition second, the lane must skip the
    stub and return the definition — the exact overnight 'what is state?' failure, now fixed."""
    ranked = [
        {"url": "https://en.wikipedia.org/wiki/State", "title": "State",
         "content": "Topics referred to by the same term", "domain": "en.wikipedia.org", "weight": 0.4},
        {"url": "https://example.gov/state", "title": "State",
         "content": "A state is an organized political community under one government.",
         "domain": "example.gov", "weight": 1.4},
    ]
    monkeypatch.setattr(wk, "searxng_ranked", lambda q, base, used, timeout=8.0: ranked)
    got = wk.learn_from_web("state", "http://x", Counter())
    assert got is not None
    gloss, url, domain = got
    assert gloss.startswith("A state is an organized political community")
    assert domain == "example.gov"                      # the stub on wikipedia was skipped


def test_pitch_and_incidental_mention_never_become_fallback(monkeypatch):
    """GPT-5.4's game-film coaching, enforced: 'what is parts?' must not accept an auto-parts sales
    pitch, and 'what is letter?' must not accept a CPU article that mentions 'letter' in passing."""
    assert not wk._acceptable_fallback("parts",
        "We present to your attention our wide range of quality auto parts for cars.")
    assert not wk._acceptable_fallback("letter",
        "Another quirk is Intel mobile CPUs where the letter at the end signals power class.")
    assert wk._acceptable_fallback("letter",
        "A letter in an alphabet represents a speech sound in writing.")
    ranked = [{"url": "https://shop.example/parts", "title": "Auto parts",
               "content": "We present to your attention our wide range of quality auto parts.",
               "domain": "shop.example", "weight": 1.2}]
    monkeypatch.setattr(wk, "searxng_ranked", lambda q, base, used, timeout=8.0: ranked)
    monkeypatch.setattr(wk, "_wiki_fallback", lambda term, timeout=8.0: None)
    assert wk.learn_from_web("parts", "http://x", Counter()) is None   # abstain beats an ad


def test_learn_from_web_returns_none_when_only_nonanswers(monkeypatch):
    """If every result is a non-answer, abstain (None) rather than surfacing a meaningless stub.
    Falls through to the wiki REST fallback, which we also stub out to isolate the filter."""
    ranked = [
        {"url": "https://en.wikipedia.org/wiki/United", "title": "United",
         "content": "United may refer to: a football club, an airline, ...",
         "domain": "en.wikipedia.org", "weight": 0.4},
    ]
    monkeypatch.setattr(wk, "searxng_ranked", lambda q, base, used, timeout=8.0: ranked)
    monkeypatch.setattr(wk, "_wiki_fallback", lambda term, timeout=8.0: None)
    assert wk.learn_from_web("United", "http://x", Counter()) is None
