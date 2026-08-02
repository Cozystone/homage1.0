# -*- coding: utf-8 -*-
"""Tests for the rung ladder — each rung runs a REAL engine and abstain is the floor."""
from __future__ import annotations

from types import SimpleNamespace

from packages.deliberator.controller import Deliberation
from packages.deliberator.steps import SubGoal
from packages.co_allocator.ladder import run_r0, run_r1, run_r2, spread_work_counter, ABSTAIN


def _q(**kw):
    base = dict(anchor="x", intent=(), text="", facts_local={}, facts_web={}, delib=None, delib_deep=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_r0_reads_intent_edge_grounded():
    q = _q(anchor="france", intent=("capital",), text="capital of france?",
           facts_local={"france": [("france", "capital", "paris")]})
    r = run_r0(q)
    assert r.rung == "R0" and r.answer == "paris" and r.grounded is True
    assert r.cost > 0                                  # real spread work was done


def test_r0_abstains_or_guesses_without_intent_edge():
    q = _q(anchor="france", intent=("capital",), text="capital of france?",
           facts_local={"france": [("france", "is_a", "country")]})
    r = run_r0(q)
    assert r.grounded is False                          # no capital edge -> not grounded (a guess at most)


def test_r1_runs_real_deliberator_and_grounds_multi_hop():
    plan = [
        SubGoal("relational", "pop of A?", {"query": "what is the population of a?",
                                            "facts": [("a", "population", 5000)]}, binds="a"),
        SubGoal("arithmetic", ">= min?", {"expr": "{a} >= 1000"}, binds="ok"),
    ]
    q = _q(anchor="a", intent=(), text="is a big enough?",
           delib=Deliberation("is a big enough?", plan, compose=lambda b: f"a={b['a']} ok={b['ok']}"))
    r = run_r1(q)
    assert r.rung == "R1" and r.grounded is True
    assert "5000" in str(r.answer)
    assert r.verifier_score == 1.0                     # both steps grounded


def test_r1_deliberator_abstains_never_fabricates():
    # a chain whose second hop cannot ground -> the deliberator abstains (honest floor)
    plan = [
        SubGoal("relational", "len?", {"query": "what is the length of the bypass?",
                                       "facts": [("bypass", "surface", "gravel")]}, binds="len"),
        SubGoal("arithmetic", "<= 30?", {"expr": "{len} <= 30"}, binds="ok"),
    ]
    q = _q(anchor="bypass", intent=(), text="reach in time?",
           delib=Deliberation("reach in time?", plan, compose=lambda b: "x"))
    r = run_r1(q)
    assert r.abstained is True and r.answer is None     # abstained rather than bridge


def test_r2_deep_spread_can_drift_to_a_web_distractor():
    # the honest overthinking channel: a converging web hub makes the deep argmax flip off the answer
    N = 12
    local = {"c": [("c", "capital", "right")] + [("c", "has_part", f"a{i}") for i in range(N)]}
    web = {}
    for i in range(N):
        web[f"a{i}"] = [(f"a{i}", "part_of", f"b{i}")]
        web[f"b{i}"] = [(f"b{i}", "located_in", "wrong")]
    q = _q(anchor="c", intent=("capital",), text="capital of c?", facts_local=local, facts_web=web)
    r0 = run_r0(q)
    r2 = run_r2(q)
    assert r0.answer == "right"                         # the cheap read is correct
    assert r2.answer == "wrong"                         # deep integration drifted (measured, not stipulated)


def test_spread_work_counter_counts_expansions():
    calls = []
    fn, box = spread_work_counter(lambda t: calls.append(t) or [])
    fn("a"); fn("b")
    assert box["n"] == 2


def test_abstain_floor_is_never_grounded():
    assert ABSTAIN.abstained is True and ABSTAIN.answer is None and ABSTAIN.grounded is False
