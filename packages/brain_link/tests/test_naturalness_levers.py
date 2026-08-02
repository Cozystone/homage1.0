# -*- coding: utf-8 -*-
"""The three v3 'stop-looking-rule-based' levers (2026-07-24), tested hermetically (the graph read
is stubbed, so no test needs the live 3GB store):

  1. POS-aware _key_concepts — adjectives / adverbs / comparatives / function words never become
     concepts to go and learn ('closer', 'another', 'when', 'large' are dropped; real nouns survive).
  2. Richer abstract substance — a thin lexical bone ('ability antonym disability') is graph-enriched
     into a substantive point; if the graph is dry AND the agent can't web, it ABSTAINS honestly
     rather than voice a weak non-point; the agent's own belief is never overwritten.
  3. Diversified surface — compare / share / connect each sample several faithful frames, salted by
     concept, so no single line repeats every turn.
"""
from __future__ import annotations

import packages.brain_link.conversation as C
from packages.brain_link.conversation import Agent, Turn, _key_concepts, step


# ------------------------------- lever 1: POS-aware _key_concepts -------------------------------

def test_lever1_rejects_adjectives_adverbs_comparatives_function_words():
    text = ("This is closer and another when large quickly various possible dangerous useful "
            "endless closely simplest happily")
    got = [w.lower() for w in _key_concepts(text)]
    for bad in ("closer", "another", "when", "large", "quickly", "various", "possible",
                "dangerous", "useful", "endless", "closely", "simplest", "happily"):
        assert bad not in got, (bad, got)


def test_lever1_owner_reported_four_are_gone():
    # the exact non-nouns the owner watched v2 drill
    for phrase, bad in (("Which is closer to it", "closer"), ("Try another one", "another"),
                        ("Tell me when it happens", "when"), ("It is very large indeed", "large")):
        got = [w.lower() for w in _key_concepts(phrase)]
        assert bad not in got, (bad, got)


def test_lever1_keeps_real_nouns():
    keep = {w.lower() for w in _key_concepts("intelligence consciousness freedom settlement family city")}
    assert keep == {"intelligence", "consciousness", "freedom", "settlement", "family", "city"}
    keep2 = {w.lower() for w in _key_concepts("knowledge table human philosophy")}
    assert keep2 == {"knowledge", "table", "human", "philosophy"}


# ------------------------------ lever 2: richer abstract substance ------------------------------

_ABILITY_FACTS = [
    ["ability", "defined_as", "The quality or state of being able; capacity to do something"],
    ["ability", "is_a", "quality"],
    ["ability", "antonym", "disability"],
    ["ability", "alias", "capability"],
]


def test_lever2_thin_antonym_becomes_substantive(monkeypatch):
    monkeypatch.setattr(C, "_graph_facts",
                        lambda concept, limit=30: _ABILITY_FACTS if concept.lower() == "ability" else [])
    prose = C._voice_substantive("ability", [["ability", "antonym", "disability"]])
    assert prose                                     # a real point, not silence
    assert "antonym" not in prose.lower()            # the ugly relation word is gone
    assert "disability" not in prose.lower()         # the lexical-only bone is dropped
    assert "quality" in prose.lower()                # substance pulled from the graph


def test_lever2_abstains_when_graph_and_web_dry(monkeypatch):
    monkeypatch.setattr(C, "_graph_facts", lambda *a, **k: [])
    a = Agent("A", knowledge={"ability": [["ability", "antonym", "disability"]]}, web=False)
    out = step(a, Turn("B", "what is ability?", "ask", "ability"))
    assert out.act == "reflect_unknown"              # did NOT voice a weak point
    assert "hold little" in out.text.lower()         # honest admission instead
    assert "antonym" not in out.text.lower()


def test_lever2_own_substantive_bones_are_not_touched(monkeypatch):
    called = []
    monkeypatch.setattr(C, "_graph_facts", lambda *a, **k: called.append(1) or [])
    prose = C._voice_substantive("bird", [["bird", "is_a", "animal"], ["bird", "capable_of", "fly"]])
    assert "animal" in prose and "fly" in prose
    assert not called                                # already substantive -> no graph read at all


def test_lever2_enrichment_preserves_own_classification(monkeypatch):
    facts = [["bird", "is_a", "animal"], ["bird", "capable_of", "fly"]]
    monkeypatch.setattr(C, "_graph_facts", lambda *a, **k: facts)
    enriched = C._enrich("bird", [["bird", "is_a", "reptile"]])
    isa = [b[2] for b in enriched if b[1] == "is_a"]
    assert "reptile" in isa and "animal" not in isa  # the agent's OWN belief is kept, not overwritten
    assert any(b[1] == "capable_of" for b in enriched)  # but real relations are still added


def test_lever2_wrong_sense_definition_is_coherence_filtered(monkeypatch):
    # the live store is dictionary-polluted: 'reasoning' -> 'A Rastafari meeting' is a real row.
    facts = [["reasoning", "is_a", "thinking"],
             ["reasoning", "defined_as", "A Rastafari meeting held for chanting and prayer"]]
    monkeypatch.setattr(C, "_graph_facts", lambda *a, **k: facts)
    enriched = C._enrich("reasoning", [["reasoning", "alias", "logic"]])
    assert [b for b in enriched if b[1] == "defined_as"] == []   # incoherent sense dropped
    assert any(b[1] == "is_a" and b[2] == "thinking" for b in enriched)  # clean is_a survives


def test_lever2_never_enriches_a_non_noun(monkeypatch):
    # belt+braces: even if a bare adjective slipped through lever 1, lever 2 refuses to flesh it out
    monkeypatch.setattr(C, "_graph_facts", lambda *a, **k: _ABILITY_FACTS)
    assert C._enrich("large", [["large", "antonym", "small"]]) == [["large", "antonym", "small"]]


# ------------------------------- lever 3: diversified surface -------------------------------

def test_lever3_compare_frames_vary_by_concept():
    # across a handful of concepts at the same running index, the salt spreads the choice over
    # several frames (occasional mod-collisions are fine — the point is it is not ONE fixed line).
    outs = {C._pick(C._COMPARE, 1, c=c, mine="A.", yours="B.")
            for c in ("ability", "freedom", "justice", "energy", "truth", "mind", "atom")}
    assert len(outs) >= 3, outs


def test_lever3_all_compare_frames_are_faithful():
    for fr in C._COMPARE:
        s = fr.format(mine="MINEBONE", yours="YOURGLOSS")
        assert "MINEBONE" in s and "YOURGLOSS" in s  # every frame states the real bone + contrast
    assert len(set(C._COMPARE)) >= 5                 # genuinely several, not one stock line
    stock = "Which is closer to the world? Check, if you can."
    assert sum(stock in fr for fr in C._COMPARE) <= 1  # the old single line no longer dominates


def test_lever3_two_live_debates_do_not_repeat_one_frame(monkeypatch):
    monkeypatch.setattr(C, "_graph_facts", lambda *a, **k: [])
    a = Agent("A", knowledge={"bird": [["bird", "is_a", "reptile"]],
                              "atom": [["atom", "is_a", "planet"]]}, web=False)
    texts = []
    for concept, peer in (("bird", "A bird is an animal."), ("atom", "An atom is a particle.")):
        t = step(a, Turn("B", peer, "answer_known", concept, payload=peer))
        assert t.act == "compare" and concept in t.text.lower()
        texts.append(t.text)
    assert texts[0] != texts[1]                      # the debate opener is not one repeated line


def test_lever3_share_and_connect_frames_have_variety():
    assert len(set(C._SHARE)) >= 4 and len(set(C._CONNECT)) >= 4
    shares = {C._pick(C._SHARE, 0, c=c, g="G.")
              for c in ("ability", "freedom", "justice", "energy", "truth", "mind")}
    assert len(shares) >= 3, shares
