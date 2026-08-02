"""Graph-native IS-A / property / causal composition: compose stated relations, no per-Q rule."""
from __future__ import annotations

from app.services.entailment_reasoner import solve_entailment
from app.services.reasoning_vm import solve_reasoning


def _a(q):
    return (solve_entailment(q) or {}).get("answer")


def test_isa_transitive_yes():
    assert "네" in _a("참새는 새다. 새는 동물이다. 참새는 동물이야?")


def test_isa_two_hop_yes():
    assert "네" in _a("고래는 포유류다. 포유류는 동물이다. 고래는 동물인가?")


def test_isa_sibling_is_no():

    assert "아니" in _a("사과는 과일이다. 오렌지는 과일이다. 사과는 오렌지야?")


def test_isa_unknown_class_defers():

    assert solve_entailment("참새는 새다. 새는 동물이다. 참새는 식물이야?") is None


def test_property_inheritance_one_hop():
    assert "네" in _a("새는 날 수 있다. 참새는 새다. 참새는 날 수 있어?")


def test_property_inheritance_two_hop():
    assert "네" in _a("개는 포유류다. 포유류는 새끼를 낳는다. 개는 새끼를 낳아?")


def test_causal_chain_yes():
    assert "네" in _a("가뭄은 흉년을 부르고 흉년은 기근을 부른다. 가뭄이 기근을 유발해?")


def test_causal_chain_conjugated_verbs():
    assert "네" in _a("흡연은 폐암을 일으키고 폐암은 사망을 초래한다. 흡연이 사망을 초래해?")


def test_single_isa_edge_is_not_composed():
    # One IS-A edge has nothing to compose; a bare restatement isn't the target — defer.
    assert solve_entailment("참새는 새다. 참새는 동물이야?") is None


def test_wired_into_solve_reasoning():
    out = solve_reasoning("참새는 새다. 새는 동물이다. 참새는 동물이야?")
    assert out and "네" in out["answer"]
    assert out["reasoning_certificate"]["derivation_kind"] == "deterministic_isa_inheritance"
