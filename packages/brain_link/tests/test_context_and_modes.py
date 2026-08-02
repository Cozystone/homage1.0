# -*- coding: utf-8 -*-
"""Context disambiguation + discourse modes — the Chinese-room 맥락 결여 fix, tested:
(1) an ambiguous term is resolved by the DISCOURSE context (query variants + result boost),
(2) the conversation grows modes (share / compare) from state, deterministically,
(3) the context actually flows from the dialogue into the web lane."""
from __future__ import annotations

from collections import Counter

import packages.brain_link.web_knowledge as wk
from packages.brain_link.conversation import Agent, Turn, converse, step


# ---------- web lane: context picks the sense ----------

def test_context_variant_leads_queries():
    qs = wk._query_variants("United", context=["states", "country"])
    assert qs[0] == "United states country"          # context-anchored variant leads
    assert '"United" definition' in qs               # generic variants still follow


def test_context_boost_beats_wrong_sense(monkeypatch):
    """The overnight failure: 'what is United?' -> airline deals. With discourse context
    ['states','country'], the polity result must win even from a lower base weight."""
    airline = {"url": "https://united.com", "title": "United Airlines",
               "content": "Find the latest travel deals on flights, hotels and rental cars united.",
               "domain": "united.com", "weight": 1.0}
    polity = {"url": "https://example.org/us", "title": "United States",
              "content": "The United States is a country of fifty states in North America.",
              "domain": "example.org", "weight": 0.6}
    monkeypatch.setattr(wk, "searxng_ranked",
                        lambda q, base, used, timeout=8.0: [dict(airline), dict(polity)])
    got = wk.learn_from_web("United", "http://x", Counter(), context=["states", "country"])
    assert got is not None and got[2] == "example.org", got   # context boosted the right sense
    # without context, the airline (higher base weight, definitional-ish shape absent) is NOT
    # accepted as a definition — the lane falls back rather than embrace the wrong sense
    monkeypatch.setattr(wk, "_wiki_fallback", lambda term, timeout=8.0: None)
    got2 = wk.learn_from_web("United", "http://x", Counter())
    assert got2 is None or got2[2] != "united.com" or "country" in got2[0].lower() \
        or "travel" not in got2[0].lower()


# ---------- conversation: modes emerge from state ----------

def _teacher() -> Agent:
    return Agent("edge", knowledge={
        "bird": [["bird", "is_a", "animal"], ["bird", "capable_of", "fly"]],
        "fish": [["fish", "is_a", "animal"]],
        "rock": [["rock", "is_a", "mineral"]],
        "rain": [["rain", "is_a", "weather"]],
    }, web=False)


def test_share_fires_after_three_learnings(monkeypatch):
    # hermetic: the teacher voices is_a-only bones (fish/rock/rain), which lever 2 would try to
    # enrich from the live 3GB store — stub the graph read so the unit test needs no store.
    monkeypatch.setattr("packages.brain_link.conversation._graph_facts", lambda *a, **k: [])
    a = Agent("pc", curiosity=["bird", "fish", "rock", "rain"], web=False)
    b = _teacher()
    out = converse(a, b, max_turns=16)
    acts = [t["act"] for t in out["transcript"]]
    assert "share" in acts, acts                      # small talk emerged from learning pressure
    share = next(t for t in out["transcript"] if t["act"] == "share")
    assert share["payload"]                           # the peer gets a CLEAN gloss to learn
    assert share["concept"].lower() in a.knowledge    # it shared something it truly holds


def test_compare_debate_fires_on_conflicting_bones_and_web_resolves(monkeypatch):
    """I hold bones that differ from your account of the SAME concept -> debate, then evidence."""
    # hermetic: stub the graph read so lever-2 enrichment of the thin 'bird is_a reptile' belief
    # does not open the live store (the agent's OWN classification is preserved either way).
    monkeypatch.setattr("packages.brain_link.conversation._graph_facts", lambda *a, **k: [])
    a = Agent("pc", knowledge={"bird": [["bird", "is_a", "reptile"]]}, curiosity=["bird"], web=False)
    b = Agent("edge", knowledge={"bird": [["bird", "is_a", "animal"]]}, web=True)
    monkeypatch.setattr("packages.brain_link.conversation.learn_from_web",
                        lambda c, s, u, context=None: ("A bird is a warm-blooded animal.",
                                                       "https://ex.org/bird", "ex.org"))
    t1 = step(a, None)                                # pc: what is bird?
    t2 = step(b, t1)                                  # edge: bird is an animal (bones voiced)
    t3 = step(a, t2)                                  # pc holds DIFFERENT bones -> compare
    assert t3.act == "compare" and "reptile" in t3.text and t3.concept == "bird"
    t4 = step(b, t3)                                  # edge checks the web -> evidence answers
    assert t4.act == "answer_web" and t4.source == "https://ex.org/bird"
    assert "warm-blooded" in t4.payload
    # bones are never clobbered by prose: pc keeps its structured belief storage type
    t5 = step(a, t4)
    assert isinstance(a.knows("bird"), list)          # structure preserved; debate journaled in text


def test_discourse_context_flows_into_web_search(monkeypatch):
    """The conversation's recent topics must reach learn_from_web as context (맥락 배선 증명)."""
    seen = {}

    def _fake_web(concept, searx, used, context=None):
        seen[concept] = list(context or [])
        return (f"{concept} is a thing.", "https://ex.org", "ex.org")

    monkeypatch.setattr("packages.brain_link.conversation.learn_from_web", _fake_web)
    asker = Agent("pc", curiosity=["state"], web=False)
    answerer = Agent("edge", web=True)
    answerer.touch("country"); answerer.touch("geography")   # what the talk has been about
    t1 = step(asker, None)
    t2 = step(answerer, t1)
    assert t2.act == "answer_web"
    assert "country" in seen["state"] and "geography" in seen["state"]


def test_turn_payload_backward_compatible():
    """Old daemon JSON without 'payload' must still deserialize (drop files in flight)."""
    t = Turn(**{"speaker": "x", "text": "hi", "act": "ask", "concept": "c",
                "source": "", "endogenous": True, "references_prev": False})
    assert t.payload == ""


def test_contractions_never_become_concepts():
    """Overnight defect: 'what is you're?' was really asked (answered with a YouTube ad). A
    contraction or possessive names nothing in the world, so it must never enter curiosity."""
    from packages.brain_link.conversation import _key_concepts
    got = _key_concepts("Whatever you're into, it's on YouTube and they're waiting")
    assert not any("'" in w for w in got), got
    assert "YouTube" in got                            # real content words still survive
    # lever 1 (2026-07-24): 'large' is a bare adjective and is now rejected; noun content survives.
    assert _key_concepts("A city is a large human settlement")[:2] == ["city", "human"]
