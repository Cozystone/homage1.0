# -*- coding: utf-8 -*-
"""C3 discrimination: verify each MCQ choice against the graph, pick the supported one, ABSTAIN
when the graph can't isolate one (the un-hallucinatable MCQ path; never guesses)."""
from packages.reasoning_vm.discrimination import discriminate, discriminate_factual


_KG = {
    "프랑스": [("프랑스", "capital", "파리"), ("프랑스", "country", "유럽")],
    "대한민국": [("대한민국", "capital", "서울"), ("대한민국", "is_a", "국가")],
}


def _fa(subject):
    return _KG.get(subject, [])


def test_picks_the_graph_verified_choice():
    v = discriminate_factual("프랑스", "capital",
                             {"A": "런던", "B": "파리", "C": "베를린", "D": "로마"}, _fa)
    assert v.status == "GROUNDED" and v.choice_key == "B"
    assert v.supported == {"A": False, "B": True, "C": False, "D": False}


def test_loose_match_ignores_parenthetical():
    v = discriminate_factual("대한민국", "capital",
                             {"A": "서울 (대한민국)", "B": "부산", "C": "도쿄", "D": "베이징"}, _fa)
    assert v.status == "GROUNDED" and v.choice_key == "A"


def test_abstains_when_no_choice_supported():
    """The right answer isn't among the choices / not in the graph → ABSTAIN, never guess."""
    v = discriminate_factual("프랑스", "capital",
                             {"A": "런던", "B": "베를린", "C": "로마", "D": "마드리드"}, _fa)
    assert v.status == "ABSTAIN" and v.choice_key is None


def test_abstains_when_relation_unknown():
    v = discriminate_factual("프랑스", "population",
                             {"A": "6700만", "B": "1억", "C": "300만", "D": "5억"}, _fa)
    assert v.status == "ABSTAIN"                             # no population fact → honest silence


def test_negated_picks_the_odd_one_out():
    """' ?': the answer is the single choice the graph does NOT verify, when the rest
 are all verified. Here A/B/C are real relations of , D is false → D is the odd one out."""
    kg2 = {"대한민국": [("대한민국", "capital", "서울"), ("대한민국", "is_a", "국가"),
                     ("대한민국", "continent", "아시아")]}
    v = discriminate_factual("대한민국", "capital",
                             {"A": "서울", "B": "서울", "C": "서울", "D": "부산"}, lambda s: kg2.get(s, []),
                             negated=True)
    assert v.status == "GROUNDED" and v.choice_key == "D"


def test_never_fabricates_confidence_on_abstain():
    v = discriminate_factual("화성", "capital", {"A": "x", "B": "y", "C": "z", "D": "w"}, _fa)
    assert v.status == "ABSTAIN" and v.confidence == 0.0


# ── end-to-end: stem → (subject, relation) → discriminate ─────────────────────────────────────
def test_endtoend_factual_stem_picks_verified():
    """A whole factual stem — subject+relation inferred from cues (josa stripped) — resolves."""
    v = discriminate("프랑스의 수도는 무엇인가?",
                     {"A": "런던", "B": "파리", "C": "베를린", "D": "로마"}, _fa)
    assert v.status == "GROUNDED" and v.choice_key == "B"


def test_endtoend_negated_stem_odd_one_out():
    kg = {"대한민국": [("대한민국", "capital", "서울")]}
    v = discriminate("다음 중 대한민국의 수도로 옳지 않은 것은?",
                     {"A": "서울", "B": "서울", "C": "서울", "D": "부산"}, lambda s: kg.get(s, []))
    assert v.status == "GROUNDED" and v.choice_key == "D"


def test_endtoend_conceptual_stem_abstains():
    """No factual relation cue (' ') → abstain, never bluff (honesty contract)."""
    v = discriminate("광합성에 대한 설명으로 옳은 것은?",
                     {"A": "a", "B": "b", "C": "c", "D": "d"}, _fa)
    assert v.status == "ABSTAIN"


# ── multi-hop (backward chaining) + multi-word subject span ───────────────────────────────────
_CHAIN_KG = {
    "북클럽": [("북클럽", "author", "홍길동")],
    "홍길동": [("홍길동", "born_in", "서울")],
    "서울": [("서울", "country", "대한민국")],
    "San Isidro Canton": [("San Isidro Canton", "capital", "San Isidro")],
}


def _fc(subject):
    return _CHAIN_KG.get(subject, [])


def test_multihop_chain_resolves_two_hops():
    """A 2-cue stem is a 2-HOP question: -author-> -born_in-> . Each hop is a graph
 lookup; the single-hop path would have answered 'author' (the wrong relation)."""
    v = discriminate("북클럽의 저자가 태어난 곳은?",
                     {"A": "부산", "B": "서울", "C": "도쿄", "D": "파리"}, _fc)
    assert v.status == "GROUNDED" and v.choice_key == "B"


def test_threehop_chain_resolves():
    """3 cues → 3 hops: -author-> -born_in-> -country-> . Each hop a lookup."""
    v = discriminate("북클럽의 저자가 태어난 곳의 국가는?",
                     {"A": "일본", "B": "대한민국", "C": "중국", "D": "미국"}, _fc)
    assert v.status == "GROUNDED" and v.choice_key == "B"


def test_multihop_abstains_when_bridge_ambiguous():
    """Two authors → no single bridge to chain from → ABSTAIN (the honesty gate, one hop deeper)."""
    kg = {"책": [("책", "author", "갑"), ("책", "author", "을")],
          "갑": [("갑", "born_in", "서울")], "을": [("을", "born_in", "부산")]}
    v = discriminate("책의 저자가 태어난 곳은?",
                     {"A": "서울", "B": "부산", "C": "도쿄", "D": "파리"}, lambda s: kg.get(s, []))
    assert v.status == "ABSTAIN"


def test_multiword_subject_matched_as_span():
    """A multi-word entity must match as a contiguous SPAN — testing single tokens ('Canton', 'San')
    abstained on every multi-word subject (measured C3 coverage 0.11 → 0.99 once spans were tried)."""
    v = discriminate("San Isidro Canton의 수도는?",
                     {"A": "San Isidro", "B": "런던", "C": "파리", "D": "도쿄"}, _fc)
    assert v.status == "GROUNDED" and v.choice_key == "A"
