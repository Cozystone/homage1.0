# -*- coding: utf-8 -*-
"""Arithmetic is DERIVED with a proof, never looked up — and never guessed."""
import random

from packages.reasoning_vm.arithmetic import evaluate, has_arithmetic_intent


def test_addition_matches_truth_with_trace():
    r = evaluate("348 더하기 1275")
    assert r is not None and r.value == 348 + 1275
    assert r.method == "long_addition" and len(r.steps) >= 4  # per-column proof


def test_small_addition_uses_peano_axioms():
    r = evaluate("3 + 4")
    assert r is not None and r.value == 7 and r.method == "peano"
    assert any("axiom" in s for s in r.steps)          # proof from axioms, not a table


def test_multiplication_and_square():
    assert evaluate("348 곱하기 27").value == 348 * 27
    r = evaluate("12의 제곱")
    assert r is not None and r.value == 144


def test_division_exact_and_remainder():
    assert evaluate("36 나누기 6").value == 6
    r = evaluate("37 나누기 6")
    assert r.value == 6 and getattr(r, "remainder", None) == 1


def test_divide_by_zero_abstains():
    assert evaluate("5 나누기 0") is None          # undefined -> abstain, never invent


def test_random_sweep_never_wrong():
    """The verifier guarantees: whatever it returns is correct (or it returns
    None). Sweep random ops and assert every emitted value is exactly right."""
    rng = random.Random(11)
    for _ in range(400):
        a, b = rng.randint(0, 99999), rng.randint(1, 9999)
        for op, truth in (("+", a + b), ("*", a * b), ("나누기", a // b)):
            r = evaluate(f"{a} {op} {b}")
            assert r is None or r.value == truth


def test_intent_gate():
    assert has_arithmetic_intent("2 + 2 는?") and not has_arithmetic_intent("서울의 수도는?")


def test_multi_term_precedence_and_parens():
    from packages.reasoning_vm.arithmetic import evaluate
    assert evaluate("2+3*4").value == 14              # precedence
    assert evaluate("(2+3)*4").value == 20            # parentheses override
    assert evaluate("2+3*4^2").value == 50            # power > *
    assert evaluate("100 - 37 + 5").value == 68       # left assoc
    r = evaluate("(2 더하기 3) 곱하기 4")               # korean words in an expression
    assert r is not None and r.value == 20 and r.method == "expression"


def test_expression_sweep_never_wrong():
    import random
    from packages.reasoning_vm.arithmetic import evaluate
    rng = random.Random(5)
    for _ in range(300):
        a, b, c = rng.randint(1, 99), rng.randint(1, 99), rng.randint(1, 30)
        for q, truth in ((f"({a}+{b})*{c}", (a + b) * c),
                         (f"{a}*{b}-{c}", a * b - c),
                         (f"{a}+{b}*{c}", a + b * c)):
            r = evaluate(q)
            assert r is None or r.value == truth
