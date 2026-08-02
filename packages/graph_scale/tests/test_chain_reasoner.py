# -*- coding: utf-8 -*-
"""Multi-hop chain reasoning: energy-descent settles at the most general ancestor over
stored transitive edges, terminates without a hop cap, cannot loop, and verbalizes the
exact chain — no invented links."""
from __future__ import annotations

from packages.graph_scale.chain_reasoner import answer_relationship, reason_chain


def _store(edges):
    by_s: dict[str, list[tuple[str, str, str]]] = {}
    for s, p, o in edges:
        by_s.setdefault(s, []).append((s, p, o))
    return lambda subj: by_s.get(subj, [])


def test_climbs_multi_hop_is_a_chain():
    fa = _store([("참새", "is_a", "새"), ("새", "is_a", "동물"), ("동물", "is_a", "생물")])
    r = reason_chain("참새", fa, "is_a")
    assert r is not None
    assert r.conclusion == "생물"
    assert [o for _s, _p, o in r.chain] == ["새", "동물", "생물"]
    assert r.local_minimum is False


def test_verbalizes_chain_with_conclusion():
    fa = _store([("참새", "is_a", "새"), ("새", "is_a", "동물")])
    r = reason_chain("참새", fa, "is_a")
    ans = r.to_answer_ko()
    assert "참새는 새의 일종이고" in ans  # topic particle, nominal chain
    assert "새는 동물의 일종입니다" in ans
    assert "따라서 참새는 동물의 일종입니다" in ans


def test_cycle_cannot_loop_terminates():
    # a wrongly-stored cycle A->B->A must not hang: energy strictly decreases,
    # so a revisit is impossible; it settles at the first hop.
    fa = _store([("A", "is_a", "B"), ("B", "is_a", "A")])
    r = reason_chain("A", fa, "is_a")
    assert r is not None and r.conclusion == "B"  # B is visited once; A already seen


def test_no_outgoing_edge_returns_none():
    fa = _store([("고립개념", "defined_as", "설명")])  # no is_a edge
    assert reason_chain("고립개념", fa, "is_a") is None


def test_relationship_question_gated_on_cue_and_depth():
    fa = _store([("참새", "is_a", "새"), ("새", "is_a", "동물")])
    # cue present + 2-hop chain -> answered
    r = answer_relationship("참새는 결국 무엇인가?", fa, ["참새"])
    assert r is not None and r["answer_kind"] == "multi_hop_chain"
    assert len(r["reasoning_certificate"]["steps"]) == 2
    # no cue -> not this path's job
    assert answer_relationship("참새란?", fa, ["참새"]) is None


# --------------------------------------------------- generalized shapes (A1/A2/A3)

def test_verify_yes_with_multi_hop_path():
    fa = _store([("참새", "is_a", "새"), ("새", "is_a", "동물"), ("동물", "is_a", "생물")])
    r = answer_relationship("참새는 생물인가?", fa, ["참새", "생물"])
    assert r is not None
    assert r["answer"].startswith("네 — ")
    assert "따라서 참새는 생물의 일종입니다" in r["answer"]
    assert r["reasoning_certificate"]["question_kind"] == "verify"
    assert len(r["reasoning_certificate"]["steps"]) == 3


def test_verify_no_path_stays_silent():
    fa = _store([("참새", "is_a", "새")])

    assert answer_relationship("참새는 돌인가?", fa, ["참새", "돌"]) is None


def test_verify_ignores_question_words():
    fa = _store([("참새", "is_a", "새"), ("새", "is_a", "동물")])

    assert answer_relationship("참새는 무엇인가?", fa, ["참새"]) is None


def test_property_inheritance_down_the_ladder():
    fa = _store([("참새", "is_a", "새"), ("새", "capable_of", "날다")])
    r = answer_relationship("참새는 날 수 있어?", fa, ["참새"])
    assert r is not None
    assert r["answer"].startswith("네 — ")
    assert "'날다'" in r["answer"]
    assert "따라서 참새도" in r["answer"]
    assert r["reasoning_certificate"]["question_kind"] == "property_inheritance"
    assert r["reasoning_certificate"]["composition"] == "capable_of"


def test_property_direct_needs_no_inference():
    fa = _store([("새", "capable_of", "날다")])
    r = answer_relationship("새는 날 수 있나?", fa, ["새"])
    assert r is not None and r["reasoning_certificate"]["question_kind"] == "property_direct"


def test_property_unknown_stays_silent():
    fa = _store([("참새", "is_a", "새")])
    assert answer_relationship("참새는 수영할 수 있어?", fa, ["참새"]) is None


def test_relation_path_between_two_concepts():
    fa = _store([("서울", "located_in", "한국"), ("한국", "located_in", "아시아")])
    r = answer_relationship("서울과 아시아의 관계는?", fa, ["서울", "아시아"])
    assert r is not None
    assert "서울은 한국에 있고" in r["answer"]
    assert "따라서 서울은 아시아에 있습니다" in r["answer"]
    assert r["reasoning_certificate"]["question_kind"] == "relation_path"


def test_unsound_composition_prunes_no_conclusion():
    # part_of after has_property is NOT in the algebra — the walk must prune,
    # never compose an unsound conclusion
    fa = _store([("A", "has_property", "B"), ("B", "part_of", "C")])
    assert answer_relationship("A와 C의 관계는?", fa, ["A", "C"]) is None


def test_mixed_taxonomy_mereology_composes_soundly():
    fa = _store([("참새", "is_a", "새"), ("새", "part_of", "생태계")])
    r = answer_relationship("참새와 생태계의 관계는?", fa, ["참새", "생태계"])
    assert r is not None
    assert "따라서 참새는 생태계의 일부입니다" in r["answer"]
    assert r["reasoning_certificate"]["composition"] == "part_of"


def test_chatter_never_triggers_chain_shapes():
    from packages.graph_scale.chain_reasoner import has_chain_intent
    for chatter in ("안녕하세요", "고마워", "오늘 기분 어때", "참새란?", "그거 좋네"):
        assert has_chain_intent(chatter) is False, chatter


# ------------------------------------------------ cross-language gloss hops

_CROSS = [
    ("참새", "defined_as", "sparrow"),
    ("sparrow", "is_a", "bird"),
    ("bird", "is_a", "animal"),
    ("동물", "defined_as", "animal"),
]


def test_verify_rides_the_english_ladder_via_gloss():
    fa = _store(_CROSS)
    r = answer_relationship("참새는 동물인가?", fa, ["참새", "동물"])
    assert r is not None
    assert r["answer"].startswith("네 — ")
    assert "'sparrow'" in r["answer"]              # the identity hop is SHOWN
    assert "동물(animal)의 일종입니다" in r["answer"]  # asked label leads, graph label audits
    assert r["reasoning_certificate"]["question_kind"] == "verify"


def test_ultimate_rides_the_english_ladder_via_gloss():
    fa = _store(_CROSS)
    r = answer_relationship("참새는 결국 무엇인가?", fa, ["참새"])
    assert r is not None
    assert "'sparrow'" in r["answer"]
    assert "animal" in r["answer"]


def test_phrase_gloss_is_not_an_identity():
    # a phrase is a description, not a translation — must not hop
    fa = _store([("참새", "defined_as", "a small brown bird"), ("bird", "is_a", "animal")])
    assert answer_relationship("참새는 동물인가?", fa, ["참새", "동물"]) is None
