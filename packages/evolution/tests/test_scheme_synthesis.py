# -*- coding: utf-8 -*-
"""X4.4 scheme synthesis — fast unit tests (sealed gate a: schemes CORRECT + SAFE, lambda^2 deduction is
consistent with re-execution, and the registration is purely ADDITIVE so the live loop is byte-identical).
The heavy wall A/B measurement lives in scratchpad/x44/gate_harness.py; these lock the invariants."""
from __future__ import annotations

import random
import time

from packages.evolution import open_domain as od
from packages.evolution import external_corpus as ec
from packages.evolution import scheme_synthesis as ss


# --- LEVER A: the recursion schemes evaluate correctly -------------------------------------------
def test_fold_s_left_fold():
    prog = ("fold_s", ("add", ("var", "_a"), ("var", "_e")), ("int", 0), ("var", "xs"))
    for xs in [(), (5,), (1, 2, 3, 4), (7, 7, 7)]:
        assert od.evaluate(prog, {"xs": xs}) == sum(xs)


def test_para_s_sees_rest():
    """para_s exposes the remaining suffix _rest (lookahead a plain fold cannot): sum of suffix-lengths."""
    prog = ("para_s", ("add", ("var", "_a"), ("len", ("var", "_rest"))), ("int", 0), ("var", "xs"))
    assert od.evaluate(prog, {"xs": (5, 5, 5, 5)}) == 6            # 3+2+1+0
    assert od.evaluate(prog, {"xs": ()}) == 0


def test_unfold_s_grows_list():
    prog = ("unfold_s", ("mul", ("var", "_a"), ("int", 2)), ("int", 1), ("int", 5))
    assert od.evaluate(prog, {}) == (1, 2, 4, 8, 16)


def test_unit_singleton_constructor():
    assert od.evaluate(("unit", ("var", "_e")), {"_e": 9}) == (9,)
    assert od.evaluate(("cat", ("unit", ("int", 3)), ("var", "xs")), {"xs": (1, 2)}) == (3, 1, 2)


def test_fresh_vars_no_shadow_of_nested_body():
    """The structural key: a base filter nested inside a fold_s step binds _x/_i but must NOT shadow the
    scheme element _e — so `insert` (filter the accumulator, compared to the fold element) is expressible."""
    insert = ("cat", ("filter", ("cmp", "<", ("var", "_x"), ("var", "_e")), ("var", "_a")),
              ("filter", ("cmp", ">=", ("var", "_x"), ("var", "_e")),
               ("cat", ("unit", ("var", "_e")), ("var", "_a"))))
    sort_prog = ("fold_s", insert, ("range", ("int", 0)), ("var", "xs"))
    for xs in [(3, 1, 2), (5, 5, 4), (), (7, 2, 7, 3), (9,), (4, 3, 2, 1, 0)]:
        assert od.evaluate(sort_prog, {"xs": xs}) == tuple(sorted(xs))


def test_pair_product_state_accumulator():
    """A fold_s carrying a 2-tuple product state (max, second_max) — the pair-accumulator capability."""
    m = ("get", ("var", "_a"), ("int", 0)); s = ("get", ("var", "_a"), ("int", 1))
    step = ("cat", ("unit", ("max2", m, ("var", "_e"))),
            ("unit", ("max2", s, ("min2", m, ("var", "_e")))))
    init = ("cat", ("unit", ("int", -1)), ("unit", ("int", -1)))
    for xs in [(3, 1, 2), (5, 5, 4), (7, 2, 7, 3), (9, 8)]:
        got = od.evaluate(("fold_s", step, init, ("var", "xs")), {"xs": xs})
        a = sorted(xs, reverse=True)
        assert got == (a[0], a[1])


# --- SAFETY: fuel/depth bounded, total, no exec/eval ---------------------------------------------
def test_schemes_terminate_on_pathological_growth():
    t0 = time.time()
    v = od.evaluate(("fold_s", ("cat", ("var", "_a"), ("var", "_a")), ("range", ("int", 0)),
                     ("range", ("int", 30))), {})
    assert time.time() - t0 < 1.0 and isinstance(v, tuple)
    t0 = time.time()
    v = od.evaluate(("unfold_s", ("cat", ("var", "_a"), ("var", "_a")), ("range", ("int", 1)),
                     ("int", 99)), {})
    assert time.time() - t0 < 1.0 and isinstance(v, tuple) and len(v) <= od.MAX_LEN


def test_no_exec_or_eval_in_module():
    import packages.evolution.scheme_synthesis as _m
    src = open(_m.__file__, encoding="utf-8").read()
    assert "exec(" not in src and "eval(" not in src


# --- LEVER B: lambda^2 deduction is consistent with re-execution (the verification anchor) --------
def test_fold_deduction_matches_reexecution():
    sort_task = next(t for t in ec.TASKS if t.name == "seq_sort")
    outer = ss.prefix_closed_io(sort_task.ref, "xs", n_lists=8, max_len=5, rng=random.Random(2))
    insert = ("cat", ("filter", ("cmp", "<", ("var", "_x"), ("var", "_e")), ("var", "_a")),
              ("filter", ("cmp", ">=", ("var", "_x"), ("var", "_e")),
               ("cat", ("unit", ("var", "_e")), ("var", "_a"))))
    derived = ss.derive_fold_step_examples(outer, "xs", ())
    assert derived, "prefix-closed examples must yield derived step I/O"
    # every derived (acc, elem) -> acc' is exactly what the step computes
    assert all(od.evaluate(insert, env) == want for env, want in derived)
    # and re-running the whole fold reproduces the outer I/O (anchor)
    fold = ("fold_s", insert, ("range", ("int", 0)), ("var", "xs"))
    assert all(od.evaluate(fold, env) == want for env, want in outer)


# --- LEVER C: OE enumeration crosses a deep COMPOSITION the evolutionary search could not ---------
def test_oe_enumeration_solves_num_objects():
    task = next(t for t in ec.TASKS if t.name == "grid_num_objects")
    tr = ec.sample_io(task, 16, random.Random(1)); ho = ec.sample_io(task, 12, random.Random(2))
    r = ss.synthesize_direct(tr, [("var", "xs"), ("var", "n"), ("int", 0), ("int", 1)],
                             unary=("len", "closure"), binary=("edges", "reach"), use_filter=True,
                             pred_vars=("_x", "_i"), max_nodes=10, time_budget=30)
    assert r["solved"] and od.fitness(r["tree"], ho) >= 1.0
    assert "closure" in r["program"] and "edges" in r["program"]


def test_fold_synthesis_self_invents_sort():
    """The headline: sort (d7, X4.3's fitness-0.50 failure) self-invents from I/O via fold_s + deduction."""
    task = next(t for t in ec.TASKS if t.name == "seq_sort")
    outer = ss.prefix_closed_io(task.ref, "xs", n_lists=9, max_len=5, rng=random.Random(1))
    verify = ec.sample_io(task, 12, random.Random(7)); ho = ec.sample_io(task, 16, random.Random(999))
    r = ss.synthesize_fold(outer, "xs", verify, step_binary=("cat",), step_pred_vars=("_x", "_e"),
                           step_pred_consts=(), max_nodes=18, time_budget=90)
    assert r["solved"] and r["verified"]
    assert od.fitness(r["tree"], ho) >= 1.0                       # generalises to unseen full-length lists
    assert r["tree"][0] == "fold_s"


def test_compounding_promoted_sort_opens_dependents():
    """Promote the discovered sort -> median + second_max open as shallow compositions (the causal channel);
    the base grammar without the primitive cannot."""
    task = next(t for t in ec.TASKS if t.name == "seq_sort")
    outer = ss.prefix_closed_io(task.ref, "xs", n_lists=9, max_len=5, rng=random.Random(1))
    verify = ec.sample_io(task, 12, random.Random(7))
    r = ss.synthesize_fold(outer, "xs", verify, step_binary=("cat",), step_pred_vars=("_x", "_e"),
                           step_pred_consts=(), max_nodes=18, time_budget=90)
    assert r["solved"]
    state = od.new_state()
    assert ss.promote_scheme(state, "seq", r["tree"]) is True
    prims = ss.promoted_primitives(state, "seq")
    med = next(t for t in ec.TASKS if t.name == "seq_median")
    tr = ec.sample_io(med, 14, random.Random(3)); ho = ec.sample_io(med, 10, random.Random(4))
    rm = ss.synthesize_direct(tr, [("var", "xs"), ("int", 0), ("int", 2)], unary=("len",),
                              binary=("get", "idiv"), prims=prims, max_nodes=9, time_budget=20)
    assert rm["solved"] and od.fitness(rm["tree"], ho) >= 1.0
    assert rm["evals"] < 2000                                     # cheap (compounding), not a fresh deep search


# --- GATE (d): additive registration -> byte-identical live loop ---------------------------------
def test_live_grammar_never_emits_scheme_ops():
    scheme_keys = set(ss.SCHEME_OPS)
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
    assert not (seen & scheme_keys), f"live grammar leaked scheme ops: {seen & scheme_keys}"


def test_base_evaluate_identical_registry_on_vs_off():
    battery = [
        (("add", ("var", "a"), ("int", 1)), {"a": 4}, 5),
        (("reduce", ("add", ("var", "_acc"), ("var", "_x")), ("int", 0), ("var", "xs")), {"xs": (1, 2, 3)}, 6),
        (("map", ("mul", ("var", "_x"), ("int", 2)), ("var", "xs")), {"xs": (1, 2)}, (2, 4)),
        (("len", ("reach", ("edges", ("var", "xs"), ("var", "n")), ("int", 0))), {"xs": (1, 1, 0, 1), "n": 2}, 3),
    ]
    on = [od.evaluate(t, e) for t, e, _ in battery]
    ss.unregister()
    try:
        off = [od.evaluate(t, e) for t, e, _ in battery]
    finally:
        ss.register(force=True)
    assert on == off == [w for _, _, w in battery]


# ================================================================================================
# X4.5 FUSION — RANKER-DRIVEN SCHEME SELECTION (A1). Fast invariants; the heavy blind/ranked eval-ratio
# measurement lives in scratchpad/a1/gate_harness.py. These lock: (a) the ranker ranks the correct
# scheme+projection top, (b) second_max self-invents STANDALONE via the pair-accumulator projection, (d)
# the verification anchor rejects a wrong auxiliary (propose-verify integrity) and the wiring is additive.
# ================================================================================================

# --- GATE (a): the FHRR ranker ranks the correct scheme family TOP -------------------------------
def test_ranker_selects_correct_scheme_family_top():
    """sort -> identity-fold, num_objects -> direct, second_max -> pair-accum (the A1 discrimination)."""
    expect = {"seq_sort": "identity-fold", "grid_num_objects": "direct", "seq_second_max": "pair-accum"}
    for name, want_family in expect.items():
        task = next(t for t in ec.TASKS if t.name == name)
        spec = ec.sample_io(task, 14, random.Random(11))
        ranked = ss.rank_schemes(spec)
        top_name, top_score, top_recipe = ranked[0]
        assert top_recipe["family"] == want_family, f"{name}: top={top_name} fam={top_recipe['family']}"
        assert top_score > ranked[1][1], f"{name}: no margin over runner-up"   # decisive, not a tie


def test_ranker_second_max_beats_max_and_sorted():
    """The discriminating case: second_max must out-resonate BOTH max (same top element) and sorted."""
    task = next(t for t in ec.TASKS if t.name == "seq_second_max")
    spec = ec.sample_io(task, 14, random.Random(7))
    scores = {n: s for n, s, _ in ss.rank_schemes(spec)}
    assert scores["second_max"] == max(scores.values())
    assert scores["second_max"] > scores["max"] and scores["second_max"] > scores["sorted_asc"]


# --- GATE (b): THE test — second_max self-invents STANDALONE (no promoted sort) -------------------
def test_second_max_self_invents_standalone_via_projection_fold():
    """X4.4's standalone FAIL: seq_second_max is a scalar PROJECTION of a pair-accumulator, so blind
    fold-deduction conflicts. The pair-accumulator projection family crosses it STANDALONE."""
    task = next(t for t in ec.TASKS if t.name == "seq_second_max")
    outer = ss.prefix_closed_io(task.ref, "xs", n_lists=9, max_len=5, rng=random.Random(1))
    verify = ec.sample_io(task, 12, random.Random(7))
    ho = ec.sample_io(task, 20, random.Random(999))
    r = ss.synthesize_projection_fold(outer, "xs", verify)
    assert r["solved"] and r["verified"]
    assert r["auxiliary"] == "running_max"                       # the auxiliary was DISCOVERED, not baked
    assert r["out_index"] == 1                                   # output = 2nd component of the (max,2nd) pair
    assert od.fitness(r["tree"], ho) >= 1.0                      # generalises to unseen full-length lists
    assert r["tree"][0] == "get" and r["tree"][1][0] == "fold_s"  # a PROJECTED fold, no promoted sort


def test_x44_scalar_fold_deduction_conflicts_on_second_max():
    """The wall X4.4 NAMED: the scalar-state deduction has a FUNCTIONAL CONFLICT for second_max (same
    (acc,elem) -> two different next accs), the honest state-insufficiency signal the pair-accum resolves."""
    task = next(t for t in ec.TASKS if t.name == "seq_second_max")
    outer = ss.prefix_closed_io(task.ref, "xs", n_lists=9, max_len=5, rng=random.Random(1))
    derived = ss.derive_fold_step_examples(outer, "xs", 0)
    seen, conflicts = {}, 0
    for env, want in derived:
        key = (repr(env[ss._A]), repr(env[ss._E]))
        if key in seen and seen[key] != want:
            conflicts += 1
        seen[key] = want
    assert conflicts > 0                                         # scalar accumulator is insufficient


def test_select_and_synthesize_routes_second_max_to_pair_accum():
    """End-to-end: the ranker routes second_max to the pair-accum family and it verifies, WITHOUT the
    identity-fold blind search (the selected scheme is pair-accum, not identity-fold)."""
    task = next(t for t in ec.TASKS if t.name == "seq_second_max")
    outer = ss.prefix_closed_io(task.ref, "xs", n_lists=9, max_len=5, rng=random.Random(2))
    spec = ec.sample_io(task, 14, random.Random(52))
    verify = ec.sample_io(task, 12, random.Random(102))
    ho = ec.sample_io(task, 20, random.Random(902))
    r = ss.select_and_synthesize(spec, outer, "xs", verify)
    assert r["solved"] and r["selected"] == "second_max"
    assert od.fitness(r["tree"], ho) >= 1.0
    assert r["attempts"][0]["family"] == "pair-accum"           # ranked first -> no doomed identity search


# --- GATE (d): propose-verify integrity + additive wiring ----------------------------------------
def test_verification_anchor_rejects_wrong_auxiliary():
    """A WRONG auxiliary (running_sum) is conflict-free on the derived examples yet does NOT reproduce the
    outer I/O; the re-execution anchor must reject it -> the projection fold returns unsolved when only the
    wrong auxiliary is offered (no fabrication)."""
    task = next(t for t in ec.TASKS if t.name == "seq_second_max")
    outer = ss.prefix_closed_io(task.ref, "xs", n_lists=9, max_len=5, rng=random.Random(1))
    verify = ec.sample_io(task, 12, random.Random(7))
    only_sum = {"running_sum": ss.aux_fold_menu()["running_sum"]}
    r = ss.synthesize_projection_fold(outer, "xs", verify, aux_menu=only_sum)
    assert not r["solved"]                                       # anchor rejects the spurious sum-pairing


def test_scheme_select_flag_ab_is_consistent():
    """ATANOR_SCHEME_SELECT toggles the RANKER (ordering) only; the exact anchor gates both, so a solution
    found either way is correct. Composable with ATANOR_SCHEME_SYNTH (schemes still registered)."""
    import os
    task = next(t for t in ec.TASKS if t.name == "seq_second_max")
    outer = ss.prefix_closed_io(task.ref, "xs", n_lists=9, max_len=5, rng=random.Random(1))
    spec = ec.sample_io(task, 14, random.Random(51))
    verify = ec.sample_io(task, 12, random.Random(101))
    prev = os.environ.get("ATANOR_SCHEME_SELECT")
    try:
        os.environ["ATANOR_SCHEME_SELECT"] = "1"
        assert ss._scheme_select_on() is True
        r_on = ss.select_and_synthesize(spec, outer, "xs", verify)
    finally:
        if prev is None:
            os.environ.pop("ATANOR_SCHEME_SELECT", None)
        else:
            os.environ["ATANOR_SCHEME_SELECT"] = prev
    assert r_on["solved"] and od.fitness(r_on["tree"], verify) >= 1.0
    assert "fold_s" in r_on["program"]                          # scheme ops available (SCHEME_SYNTH composed)


def test_projection_fold_no_exec_or_eval():
    import packages.evolution.scheme_synthesis as _m
    src = open(_m.__file__, encoding="utf-8").read()
    assert "exec(" not in src and "eval(" not in src
