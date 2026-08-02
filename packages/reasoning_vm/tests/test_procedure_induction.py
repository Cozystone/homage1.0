# -*- coding: utf-8 -*-
"""The system induces its OWN algorithms from examples, verification-gated — no hand-written algo."""
import random

from packages.reasoning_vm.procedure_induction import induce, grow_basis, seed_basis


def test_induces_addition_from_examples_only():
    ex = [((a, b), a + b) for a, b in [(2, 3), (10, 7), (1, 1), (0, 5), (6, 6),
                                       (4, 9), (8, 2), (3, 0), (12, 5), (7, 7)]]
    ind = induce("add", ex)
    assert ind is not None and ind.n_verified >= 1
    rng = random.Random(1)
    assert all(ind.fn(a, b) == a + b
               for a, b in [(rng.randint(0, 999), rng.randint(0, 999)) for _ in range(150)])


def test_compositional_growth_multiplication_on_induced_addition():
    add = induce("add", [((a, b), a + b) for a, b in
                         [(2, 3), (10, 7), (1, 1), (0, 5), (6, 6), (4, 9), (8, 2), (3, 0)]])
    assert add is not None
    basis = grow_basis(seed_basis(), add)          # induced add becomes a primitive
    mul = induce("mul", [((a, b), a * b) for a, b in
                         [(2, 3), (4, 5), (1, 7), (0, 9), (6, 6), (3, 8), (9, 2), (5, 5)]], basis)
    assert mul is not None and "add" in mul.basis_used   # built ON the induced addition
    rng = random.Random(2)
    assert all(mul.fn(a, b) == a * b
               for a, b in [(rng.randint(0, 300), rng.randint(0, 300)) for _ in range(150)])


def test_refuses_when_no_program_reproduces_examples():
    # an arbitrary/inconsistent map has no program in the bounded space → honest None
    assert induce("nonsense", [((1, 1), 7), ((2, 2), 3), ((3, 1), 99), ((0, 4), 42)]) is None


def test_certificate_records_verification():
    ind = induce("add", [((a, b), a + b) for a, b in
                         [(2, 3), (10, 7), (1, 1), (0, 5), (6, 6), (4, 9)]])
    c = ind.certificate()
    assert c["verified_held_out"] >= 1 and "add" in c["induced_procedure"]


def test_induces_disjunctive_syllogism_logic():
    """The elimination logic Cesana-Arlotti (Science 2018) found in 12-month-olds — induced,
    verify-gated, from examples over the domain-general engine (not just arithmetic)."""
    from packages.reasoning_vm.procedure_induction import induce_general
    ex = [(("cat", "dog"), "cat") and (("cat", "dog"), "cat")]  # placeholder replaced below
    ex = [((("cat", "dog"), "cat"), "dog"), ((("red", "blue"), "blue"), "red"),
          ((("A", "B"), "A"), "B"), ((("x", "y"), "y"), "x"),
          ((("moon", "sun"), "sun"), "moon"), ((("1", "2"), "1"), "2")]
    ind = induce_general("disjunctive_syllogism", ex)
    assert ind is not None and ind.rule.startswith("disjunctive")
    assert ind.fn(("apple", "pear"), "apple") == "pear"          # unseen
    assert ind.fn(("on", "off"), "off") == "on"


def test_occam_prefers_reused_primitive_for_multiplication():
    """With induced add in the basis, multiplication is expressed via add (shorter concept-length)
    rather than a raw-successor construction."""
    add = induce("add", [((a, b), a + b) for a, b in
                         [(2, 3), (10, 7), (1, 1), (0, 5), (6, 6), (4, 9), (8, 2), (3, 0)]])
    basis = grow_basis(seed_basis(), add)
    mul = induce("mul", [((a, b), a * b) for a, b in
                         [(2, 3), (4, 5), (1, 7), (0, 9), (6, 6), (3, 8), (9, 2), (5, 5)]], basis)
    assert mul is not None and mul.program.op == "add"          # reuses the induced primitive
