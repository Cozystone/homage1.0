"""Graph-native transitive comparison reasoning: compose stated relations, no per-Q rule."""
from __future__ import annotations

from app.services.transitive_reasoner import solve_transitive
from app.services.reasoning_vm import solve_reasoning


def _a(q):
    return (solve_transitive(q) or {}).get("answer")


def test_three_item_chain_max():
    assert "철수" in _a("철수는 영희보다 크고 영희는 민수보다 크다. 가장 키 큰 사람은?")


def test_three_item_chain_min_via_antonym():
    assert "개" in _a("기린은 말보다 크고 말은 개보다 크다. 가장 작은 동물은?")


def test_pairwise_non_adjacent_via_reachability():

    assert "철수" in _a("철수는 영희보다 키가 크고 영희는 민수보다 키가 크다. 민수와 철수 중 누가 더 커?")


def test_dimension_noun_construction():

    assert "지호" in _a("민지는 수아보다 나이가 많고 수아는 지호보다 나이가 많다. 가장 어린 사람은?")


def test_speed_scale_min():
    assert "달팽이" in _a("토끼는 거북이보다 빠르고 거북이는 달팽이보다 빠르다. 가장 느린 것은?")


def test_contradictory_chain_abstains():
    # A>B and C>B leave A vs C unordered → must not guess a maximum.
    assert solve_transitive("A는 B보다 크고 C는 B보다 크다. 가장 큰 것은?") is None


def test_single_comparison_is_left_alone():
    # One comparison has nothing to compose; defer to the pairwise/web reasoner.
    assert solve_transitive("철수는 영희보다 크다. 누가 더 커?") is None


def test_wired_into_solve_reasoning_before_numeric_gate():
    # The chat path calls solve_reasoning; a digit-less ordering question must still route here.
    out = solve_reasoning("철수는 영희보다 크고 영희는 민수보다 크다. 가장 키 큰 사람은?")
    assert out and "철수" in out["answer"]
    assert out["reasoning_certificate"]["derivation_kind"] == "deterministic_transitive_order"
