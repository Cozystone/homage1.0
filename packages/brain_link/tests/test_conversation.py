# -*- coding: utf-8 -*-
"""Autonomous conversation engine: agents ask from their own curiosity, teach what they know,
bounce back what neither knows, and derive NEW curiosity from what they learn. Offline (web=False)
so the test is deterministic. Correlates are counts, never a claim of experience."""
from packages.brain_link.conversation import Agent, converse, step, Turn


def test_agents_teach_and_derive_new_curiosity(monkeypatch):
    # hermetic: 'beans' is an is_a-only bone that lever 2 would try to enrich from the live store;
    # stub the graph read so this unit test stays offline (assertions unchanged).
    monkeypatch.setattr("packages.brain_link.conversation._graph_facts", lambda *a, **k: [])
    a = Agent("A", knowledge={"coffee": [["coffee", "is_a", "beverage"], ["coffee", "made_of", "beans"]],
                              "beans": [["beans", "is_a", "seed"]]},
              curiosity=["beans"], web=False)
    b = Agent("B", knowledge={}, curiosity=[], web=False)
    r = converse(a, b, max_turns=6)
    acts = [t["act"] for t in r["transcript"]]
    assert "ask" in acts and "answer_known" in acts        # asking and teaching both happen
    # B learned something from A (concepts flowed between the two selves)
    assert r["correlates"]["single_owner"] == 2            # each stayed itself
    assert r["correlates"]["binding"] > 0.5                # turns integrate the peer's prior turn


def test_unknown_without_web_bounces_back_not_fabricates():
    a = Agent("A", knowledge={}, curiosity=["quasar"], web=False)
    b = Agent("B", knowledge={}, curiosity=[], web=False)
    t1 = step(a, None)                                      # A asks about quasar
    t2 = step(b, t1)                                        # B doesn't know, no web
    assert t2.act == "reflect_unknown"                     # bounces the thought back
    assert "quasar" in t2.text.lower() and "?" in t2.text  # never invents an answer


def test_curiosity_is_endogenous_from_own_state():
    a = Agent("A", knowledge={"x": [["x", "is_a", "thing"]]}, curiosity=["y"], web=False)
    t = step(a, None)
    assert t.act == "ask" and t.endogenous and t.concept == "y"   # arose from its own queue
