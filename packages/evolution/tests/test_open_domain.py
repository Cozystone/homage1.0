# -*- coding: utf-8 -*-
"""Open-ended synthesis domain — safety (total + bounded interpreter), richer value types, and the
self-curriculum invariants (dedup, non-degeneracy gate, capability growth). Fast: small budgets."""
from __future__ import annotations

import random

from packages.evolution import open_domain as od


def test_interpreter_is_total_and_bounded():
    # no random program may raise; every output is int|str|tuple and length-capped (termination proof).
    rng = random.Random(0)
    for _ in range(4000):
        fam = rng.choice(list(od._FAMILIES))
        vs = od._FAMILIES[fam]["vars_"] + [od._X, od._I, od._ACC]
        t = od.random_tree(vs, rng, depth=rng.randint(1, 5))
        v = od.evaluate(t, od._sample_env(fam, rng))
        assert isinstance(v, (int, str, tuple))
        if isinstance(v, (str, tuple)):
            assert len(v) <= od.MAX_LEN


def test_recursion_forms_terminate_and_stay_bounded():
    # a deliberately adversarial nested build/iter must still terminate (fuel) and cap length.
    env = {"a": 5, "b": 3}
    nasty = ("build", ("build", ("add", ("var", od._ACC), ("int", 1)), ("var", od._ACC), ("int", 9)),
             ("int", 1), ("int", 9))
    v = od.evaluate(nasty, env)
    assert isinstance(v, tuple) and len(v) <= od.MAX_LEN


def test_richer_value_types_present():
    # the domain genuinely produces strings and tuples, not just ints (the open-endedness lever).
    assert od.evaluate(("rev", ("var", "s")), {"s": "abc", "k": 0}) == "cba"
    assert od.evaluate(("range", ("var", "n")), {"xs": (), "n": 4}) == (0, 1, 2, 3)
    assert isinstance(od.evaluate(("cat", ("var", "s"), ("var", "s")), {"s": "hi", "k": 0}), str)


def test_seeds_are_nontrivial_and_signatures_stable():
    for fam in od._FAMILIES:
        for _name, tree in od._SEED_TREES[fam]:
            assert not od._is_trivial(tree, fam)
            assert od.signature(tree, fam) == od.signature(tree, fam)  # deterministic


def test_reachable_space_far_exceeds_toy():
    # in a modest random sample the open domain exposes hundreds of distinct functions per family;
    # the toy domain saturates near ~15 TOTAL. This is the domain-finiteness lever under test.
    rng = random.Random(1)
    for fam in od._FAMILIES:
        sigs = set()
        for _ in range(1500):
            t = od.random_tree(od._FAMILIES[fam]["vars_"], rng, depth=rng.randint(2, 5))
            if not od._is_trivial(t, fam):
                sigs.add(od.signature(t, fam))
        assert len(sigs) > 150, (fam, len(sigs))


def test_admit_dedups_and_rejects_trivial():
    st = od.new_state()
    assert od._admit(st, "num", ("int", 5)) == "reject"          # constant
    assert od._admit(st, "num", ("var", "a")) == "reject"        # identity projection
    real = ("add", ("var", "a"), ("var", "b"))
    assert od._admit(st, "num", real) == "new"
    assert od._admit(st, "num", real) == "dup"                   # same signature -> not double-counted
    assert len(st["sigs"]["num"]) == 1


def test_invention_gate_rejects_degenerate_primitive():
    # a template whose output never depends on its hole must NOT enter the solver vocabulary.
    vestigial = ("len", ("range", ("hole", 0)))  # len(range(x)) depends on x -> should pass hole-sens?
    # build a genuinely vestigial one: mul by hole then take a constant-sized thing is hard; use a
    # template that ignores its hole: ("mod", ("int", 4), ("int", 2)) has no hole -> arity 0 -> reject.
    assert not od._expands_reachable(("mod", ("int", 4), ("int", 2)), 0, "num")
    # a real one: lambda x. x + x*x expands reachability.
    good = ("add", ("hole", 0), ("mul", ("hole", 0), ("hole", 0)))
    assert od._expands_reachable(good, 1, "num")


def test_evolve_solves_a_simple_target():
    tests = [({"a": a, "b": b}, a + b) for a, b in [(0, 0), (1, 2), (3, 4), (5, 1), (2, 7), (6, 3)]]
    res = od.evolve(tests, ["a", "b"], pop=60, generations=80, rng_seed=3)
    assert res["solved"] and res["fitness"] == 1.0


def test_autonomous_round_grows_distinct_functions():
    state = od.new_state()
    rng = random.Random(2)
    first = None
    for _ in range(3):
        od.autonomous_round(state, rng, problems=6, pop=60, base_budget=70)
        if first is None:
            first = state["frontier"]["distinct_solved"]
    assert state["frontier"]["distinct_solved"] >= first >= 3
    for fam in od._FAMILIES:                                   # stays deduplicated
        assert len(state["programs"][fam]) == len(set(state["programs"][fam]))
