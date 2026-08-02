# -*- coding: utf-8 -*-
"""X4.3 meta-basis — fast unit tests (sealed gate a: the substrate is CORRECT and SAFE, and it is
purely ADDITIVE so the live loop is byte-identical). The heavy self-invention A/B measurement lives in
scratchpad/x43; these lock the substrate's invariants."""
from __future__ import annotations

import random
import time

from packages.evolution import meta_basis as mb
from packages.evolution import open_domain as od


# --- ordering ------------------------------------------------------------------------------------
def test_min2_max2():
    assert od.evaluate(("max2", ("int", 3), ("int", 7)), {}) == 7
    assert od.evaluate(("min2", ("int", 3), ("int", 7)), {}) == 3
    assert od.evaluate(("max2", ("var", "a"), ("var", "b")), {"a": 2, "b": 9}) == 9
    # max-of-list via reduce+max2 (a program the search composes)
    maxl = ("reduce", ("max2", ("var", "_acc"), ("var", "_x")), ("int", 0), ("var", "xs"))
    for xs in [(3, 1, 2), (5,), (), (7, 2, 7)]:
        assert od.evaluate(maxl, {"xs": xs}) == (max(xs) if xs else 0)


# --- bounded recursion / fixpoint ----------------------------------------------------------------
def test_fix_tail_recursion_factorial():
    fac = ("fix",
           ("if", ("cmp", "<=", ("var", "_r"), ("int", 1)),
            ("int", 1),
            ("mul", ("var", "_r"), ("rec", ("sub", ("var", "_r"), ("int", 1))))),
           ("var", "a"))
    for n in range(0, 9):
        exp = 1
        for i in range(1, n + 1):
            exp *= i
        assert od.evaluate(fac, {"a": n}) == exp


def test_fix_fresh_param_breaks_nested_comparison_ceiling():
    """The crux: second-largest needs to compare an INNER-loop element to an OUTER value. The base
    grammar cannot (one shared bound-var name); the fix parameter _r carries the outer max inward."""
    maxl = ("reduce", ("max2", ("var", "_acc"), ("var", "_x")), ("int", 0), ("var", "xs"))
    second = ("fix",
              ("reduce", ("max2", ("var", "_acc"), ("var", "_x")), ("int", 0),
               ("filter", ("cmp", "<", ("var", "_x"), ("var", "_r")), ("var", "xs"))),
              maxl)
    for xs in [(3, 1, 2), (5, 5, 4), (1,), (), (7, 2, 7, 3), (4, 4)]:
        m = max(xs) if xs else 0
        below = [x for x in xs if x < m]
        exp = max(below) if below else 0
        assert od.evaluate(second, {"xs": xs}) == exp


def test_fix_terminates_on_pathological_nonterminating_recursion():
    """SAFETY: f(r) = rec(r) has no base case. It MUST terminate (fuel + depth caps), never hang."""
    bad = ("fix", ("rec", ("var", "_r")), ("int", 5))
    t0 = time.time()
    v = od.evaluate(bad, {})
    assert time.time() - t0 < 1.0                             # bounded, no hang
    assert isinstance(v, int)                                 # total: returns a value, never raises
    # a rec OUTSIDE any fix is inert (returns 0), never crashes
    assert od.evaluate(("rec", ("int", 1)), {}) == 0


def test_fix_depth_is_bounded():
    assert od.MAX_REC <= 256                                  # a real, small cap
    # deep-but-terminating recursion within the cap still computes (sum 1..r)
    s = ("fix", ("if", ("cmp", "<=", ("var", "_r"), ("int", 0)), ("int", 0),
                 ("add", ("var", "_r"), ("rec", ("sub", ("var", "_r"), ("int", 1))))),
         ("var", "a"))
    assert od.evaluate(s, {"a": 10}) == 55


# --- relational / graph ops ----------------------------------------------------------------------
def test_grid_adjacency_reach_closure():
    # 3x3 grid: L-shape object of colour 1 at {0,1,3}, isolated colour-1 cell at {8}
    g = (1, 1, 0, 1, 0, 0, 0, 0, 1)
    w = 3
    adj = od.evaluate(("edges", ("var", "xs"), ("var", "n")), {"xs": g, "n": w})
    assert adj[0] == (0, 1, 3) and adj[8] == (8,) and adj[2] == ()
    # reach from cell 0 = the whole L-shape (size 3); transitive closure
    size0 = od.evaluate(("len", ("reach", ("edges", ("var", "xs"), ("var", "n")), ("int", 0))),
                        {"xs": g, "n": w})
    assert size0 == 3
    # closure labels + number-of-objects = filter(_x == _i) count
    ncomp = od.evaluate(("len", ("filter", ("cmp", "==", ("var", "_x"), ("var", "_i")),
                                 ("closure", ("edges", ("var", "xs"), ("var", "n"))))),
                        {"xs": g, "n": w})
    assert ncomp == 2                                         # the L-shape and the singleton
    # colour separates components. (1,2,1,2) with width 2 is two vertical single-colour columns:
    #   row0: 1 2   row1: 1 2   -> {0,2} colour-1 column and {1,3} colour-2 column = 2 objects
    cols = od.evaluate(("len", ("filter", ("cmp", "==", ("var", "_x"), ("var", "_i")),
                                ("closure", ("edges", ("var", "xs"), ("var", "n"))))),
                       {"xs": (1, 2, 1, 2), "n": 2})
    assert cols == 2
    # a true 2x2 checkerboard (1,2,2,1) -> every cell colour-isolated -> 4 singleton objects
    check = od.evaluate(("len", ("filter", ("cmp", "==", ("var", "_x"), ("var", "_i")),
                                 ("closure", ("edges", ("var", "xs"), ("var", "n"))))),
                        {"xs": (1, 2, 2, 1), "n": 2})
    assert check == 4


def test_grid_reference_functions_match_interpreter():
    rng = random.Random(0)
    for env, out in mb.sample_grid_io(mb._ref_obj_size0, 8, rng, plant_corner=True):
        prog = ("len", ("reach", ("edges", ("var", "xs"), ("var", "n")), ("int", 0)))
        assert od.evaluate(prog, env) == out                 # a correct program reproduces the I/O exactly


# --- ADDITIVITY: the live loop is byte-identical (this block is dead for base programs) -----------
def test_live_grammar_never_emits_meta_ops():
    """od.random_tree (the LIVE autonomous-loop generator) must NEVER emit a meta-basis key — the
    interpreter only gained dead branches. Sample widely across families."""
    meta_keys = set(mb.ALL_META) | {"rec"}
    rng = random.Random(7)

    def keys(t, acc):
        if isinstance(t, tuple) and t:
            acc.add(t[0])
            for c in t[1:]:
                keys(c, acc)
        return acc

    seen: set = set()
    for fam in od._FAMILIES:
        v = od._FAMILIES[fam]["vars_"]
        for _ in range(400):
            keys(od.random_tree(v, rng, 4), seen)
    assert not (seen & meta_keys), f"live grammar leaked meta ops: {seen & meta_keys}"


def test_base_evaluate_unchanged_by_meta_branches():
    # a battery of base programs still evaluate to the same values (additivity sanity)
    cases = [
        (("add", ("var", "a"), ("int", 1)), {"a": 4}, 5),
        (("reduce", ("add", ("var", "_acc"), ("var", "_x")), ("int", 0), ("var", "xs")), {"xs": (1, 2, 3)}, 6),
        (("rev", ("var", "s")), {"s": "abc"}, "cba"),
        (("map", ("mul", ("var", "_x"), ("int", 2)), ("var", "xs")), {"xs": (1, 2)}, (2, 4)),
    ]
    for tree, env, want in cases:
        assert od.evaluate(tree, env) == want


# --- the search integrates the meta ops (sanity) + the headline self-invention (bounded) ---------
def test_evolve_meta_integrates_the_meta_ops():
    # num_min == min2(a,b): once the ordering op is available the search integrates the substrate and
    # rediscovers it. (This is the CHEAP integration proof; the deep-KIND wall lives in scratchpad/x43.)
    import packages.evolution.external_corpus as ec
    task = next(t for t in ec.TASKS if t.name == "num_min")
    tr = ec.sample_io(task, 12, random.Random(1))
    ho = ec.sample_io(task, 8, random.Random(2))
    r = mb.evolve_meta(tr, ["a", "b"], ops=mb.REC_OPS, pop=100, generations=80, rng_seed=1, depth=2)
    assert r["solved"] and od.fitness(r["tree"], ho) >= 1.0
    assert "min2" in r["program"]


def test_self_invents_segmentation_primitive_from_io():
    """SEALED GATE (b), bounded: the engine self-generates a segmentation/reachability primitive from I/O
    using only the meta-basis (edges/reach/closure), WITHOUT it handed in."""
    vars_ = ["xs", "n"]
    tr = mb.sample_grid_io(mb._ref_obj_size0, 16, random.Random(1), plant_corner=True)
    ho = mb.sample_grid_io(mb._ref_obj_size0, 12, random.Random(99), plant_corner=True)
    res = mb.discover(tr, vars_, ops=mb.GRAPH_OPS, seeds=[1, 2], pop=150, generations=250, depth=4,
                      holdout=ho)
    assert res["discovered"] is True
    win = res["winner"]
    assert "reach" in win["program"] and "edges" in win["program"]   # a genuine transitive-closure program
    # and it PROMOTES into a named primitive (the compounding channel)
    state = od.new_state()
    assert mb.promote_discovered(state, "seq", win["tree"]) is True
    assert len(state["promoted"]["seq"]) == 1


def test_discovered_primitive_is_not_base_reachable():
    """The invented KIND strictly EXPANDS reach: the base grammar (no meta-basis) cannot solve the
    object-size task within a generous budget — so the win is a new KIND, not a lateral re-spelling."""
    vars_ = ["xs", "n"]
    tr = mb.sample_grid_io(mb._ref_obj_size0, 14, random.Random(3), plant_corner=True)
    ho = mb.sample_grid_io(mb._ref_obj_size0, 10, random.Random(4), plant_corner=True)
    base = od.evolve(tr, vars_, library=(), primitives=(), pop=80, generations=120, rng_seed=5)
    ok = bool(base["solved"] and (od.fitness(base["tree"], ho) >= 1.0 if base["tree"] else False))
    assert ok is False                                        # unreachable without the meta-basis
