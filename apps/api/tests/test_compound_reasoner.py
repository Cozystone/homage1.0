"""Compound relational-quantity word problems: decompose to equations, compose, solve."""
from __future__ import annotations

from app.services.compound_reasoner import solve_compound
from app.services.reasoning_vm import solve_reasoning


def _a(q):
    return (solve_compound(q) or {}).get("answer")


def test_relational_more():
    assert "8" in _a("철수는 사과 5개를 가지고 있고 영희는 철수보다 3개 더 많아. 영희는 몇 개?")


def test_relational_less():
    assert "6" in _a("철수는 10개 있고 영희는 철수보다 4개 적어. 영희는 몇 개?")


def test_factor_and_sum_three_actors():
    q = "철수는 사과 5개를 가지고 있고 영희는 철수보다 3개 많고 민수는 영희의 2배를 가지고 있어. 세 명의 사과는 모두 몇 개?"
    assert "29" in _a(q)  # 5 + 8 + 16


def test_who_has_most():
    assert "영희" in _a("철수는 5개, 영희는 철수보다 3개 많아. 누가 제일 많아?")


def test_correct_josa_in_answer():

    ans = _a("철수는 10개 있고 영희는 철수보다 4개 적어. 영희는 몇 개?")
    assert "영희는" in ans and "은(는)" not in ans


def test_single_actor_defers_to_vm():
    # nothing to compose across actors → this reasoner abstains (the VM handles it)
    assert solve_compound("철수는 사과 5개를 가지고 있어. 철수는 몇 개?") is None


def test_unresolved_reference_abstains():

    assert solve_compound("영희는 철수보다 3개 많아. 민수는 영희보다 2개 많아. 민수는 몇 개?") is None


def test_wired_into_solve_reasoning():
    out = solve_reasoning("철수는 사과 5개를 가지고 있고 영희는 철수보다 3개 더 많아. 영희는 몇 개?")
    assert out and "8" in out["answer"]
    assert out["reasoning_certificate"]["derivation_kind"] == "deterministic_compound_word_problem"
