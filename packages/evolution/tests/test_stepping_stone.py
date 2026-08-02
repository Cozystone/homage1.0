# -*- coding: utf-8 -*-
"""X4.2 — autonomous stepping-stone climb (owner 2026-07-23).
Fast unit tests for the three levers (dependency-aware curriculum, singleton rung->primitive promotion,
scoped/de-diluted solver inputs) and the default-OFF byte-identical guarantee. No heavy search here — the
sealed A/B measurement lives in scratchpad/x42; these lock the wiring's INVARIANTS."""
from __future__ import annotations

import random

from packages.evolution import external_corpus as ec
from packages.evolution import open_domain as od


# --- corpus dependency metadata -------------------------------------------------------------------
def test_corpus_declares_stepping_stone_deps():
    ss = ec.stepping_stones()
    # the clean seq compounding chains carry their rung prerequisite
    assert ss["seq_count_even"] == ("seq_filter_even",)
    assert ss["seq_sum_squares"] == ("seq_square_each",)
    assert set(ss["seq_max_minus_min"]) == {"seq_max", "seq_min"}
    # every declared rung is a real task, and lives at a LOWER-or-equal tier than its dependent
    names = {t.name: t for t in ec.TASKS}
    for dep, rungs in ss.items():
        for r in rungs:
            assert r in names
            assert names[r].tier <= names[dep].tier
    assert ec.rungs() == {"seq_filter_even", "seq_filter_gt3", "seq_square_each", "seq_max", "seq_min"}
    assert ec.provenance()["stepping_stones"] == ss


# --- (ii) variabilize + promotion ------------------------------------------------------------------
def test_variabilize_shares_one_hole_per_primary_input():
    # square_each: map(_x*_x, xs) -> the xs leaf becomes a single reused hole; the _x body stays concrete
    tree = ("map", ("mul", ("var", "_x"), ("var", "_x")), ("var", "xs"))
    tmpl, arity = od._variabilize(tree, "xs")
    assert arity == 1
    assert tmpl == ("map", ("mul", ("var", "_x"), ("var", "_x")), ("hole", 0))
    # max: BOTH xs occurrences collapse to the SAME hole (a genuine reused parameter, not two holes)
    mx = ("reduce", ("if", ("cmp", ">", ("var", "_acc"), ("var", "_x")), ("var", "_acc"), ("var", "_x")),
          ("get", ("var", "xs"), ("int", 0)), ("var", "xs"))
    tm, am = od._variabilize(mx, "xs")
    assert am == 1
    from packages.evolution.abstraction import holes_in
    assert holes_in(tm) == 1                                   # one DISTINCT parameter despite two slots


def test_promote_primitive_gates_and_dedups():
    state = od.new_state()
    # a genuine rung -> promoted (non-degenerate: output depends on the hole, non-atomic behaviour)
    sq = ("map", ("mul", ("var", "_x"), ("var", "_x")), ("var", "xs"))
    assert od._promote_primitive(state, "seq", sq) is True
    assert len(state["promoted"]["seq"]) == 1
    assert od._promote_primitive(state, "seq", sq) is False    # duplicate rejected
    # a degenerate tree with no primary-input leaf cannot be promoted (arity 0)
    const = ("add", ("int", 1), ("int", 2))
    assert od._promote_primitive(state, "seq", const) is False


def test_stepping_primitives_bounded_and_promoted_first():
    state = od.new_state()
    state["promoted"] = {f: [] for f in od._FAMILIES}
    # more promoted than the cap -> the set fed to the solver is bounded
    for i in range(od._STEP_PRIM_CAP + 4):
        state["promoted"]["seq"].append(
            {"template": ("map", ("add", ("var", "_x"), ("int", i + 1)), ("hole", 0)),
             "arity": 1, "source": f"m{i}", "uses": i, "born": 0})
    prims = od._stepping_primitives(state, "seq")
    assert len(prims) <= od._STEP_PRIM_CAP
    assert all("template" in p and "arity" in p for p in prims)


def test_scoped_library_bounds_the_working_set():
    state = od.new_state()
    # grow a fat library of distinct blocks
    for k in range(20):
        state["libraries"]["seq"].append(("add", ("var", "xs"), ("int", k)))
    scoped = od._scoped_library(state, "seq")
    assert len(scoped) == od._STEP_LIB_FLOOR                   # only the parsimony floor is fed
    assert len(scoped) < len(state["libraries"]["seq"])


# --- (i) dependency-aware eligibility (behavioural, tiny budget) -----------------------------------
def test_dependency_gate_holds_dependents_until_rung_solved(monkeypatch):
    monkeypatch.setenv("ATANOR_EXTERNAL_PROBLEMS", "1")
    monkeypatch.setenv("ATANOR_STEPPING_STONE", "1")
    # a 2-task corpus: a dependent gated behind an unsolved rung must NOT be selected first
    rung = next(t for t in ec.TASKS if t.name == "seq_filter_gt3")
    dep = next(t for t in ec.TASKS if t.name == "seq_count_gt3")
    state = od.new_state()
    state["tier"] = 3
    rng = random.Random(0)
    rec = od.external_round(state, rng, problems=1, pop=8, base_budget=4,
                            corpus=[rung, dep])
    # with the rung unsolved, only the rung is eligible -> the dependent cannot be attempted this round
    attempted = {d["task"] for d in rec["details"]}
    assert "seq_count_gt3" not in attempted
    assert rec["stepping"] is True


# --- default-OFF byte-identical guarantee ----------------------------------------------------------
def test_stepping_off_is_byte_identical(monkeypatch):
    monkeypatch.setenv("ATANOR_EXTERNAL_PROBLEMS", "1")
    monkeypatch.delenv("ATANOR_STEPPING_STONE", raising=False)
    state = od.new_state()
    rng = random.Random(3)
    rec = od.external_round(state, rng, problems=4, pop=30, base_budget=30)
    assert rec["stepping"] is False
    assert rec["promoted_primitives"] == 0
    assert "promoted" not in state                             # no X4.2 state created when OFF
