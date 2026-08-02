# -*- coding: utf-8 -*-
"""Tests for the allocator control loop — meta-greedy depth-1, Schmitt, refractory, diminishing stop,
verifier-gated stop, and the abstain floor."""
from __future__ import annotations

from types import SimpleNamespace

from packages.co_allocator.allocator import (
    Allocator, AllocatorConfig, Features, escalate_score, DEFAULT_W, amortize_w)


def _q(**kw):
    base = dict(anchor="x", intent=(), text="", facts_local={}, facts_web={}, delib=None, delib_deep=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_escalate_score_is_one_dot_product_and_monotone():
    lo = Features(inv_for=0.0, x1_voc=0.0, conflict=0.0, abstain_margin=0.0,
                  difficulty_prior=0.0, remaining_budget=1.0)
    hi = Features(inv_for=1.0, x1_voc=1.0, conflict=1.0, abstain_margin=1.0,
                  difficulty_prior=1.0, remaining_budget=1.0)
    assert escalate_score(lo) < escalate_score(hi)
    # every non-budget feature argues FOR escalation -> raising any of them cannot lower the score
    base = escalate_score(lo)
    bumped = escalate_score(Features(0.5, 0.0, 0.0, 0.0, 0.0, 1.0))
    assert bumped >= base


def test_easy_query_stops_at_r0():
    # a directly-present, dominant answer -> the allocator must NOT waste deeper compute
    q = _q(anchor="japan", intent=("capital",), text="what is the capital of japan?",
           facts_local={"japan": [("japan", "capital", "tokyo")]})
    tr = Allocator().allocate(q)
    assert tr.answer == "tokyo" and tr.rung_reached == "R0"
    assert tr.total_cost == tr.rungs[0].cost           # only R0 was paid


def test_hard_query_climbs_and_grounds():
    # answer only in the web -> R0 cannot ground, the allocator must climb to R2 and recover it
    q = _q(anchor="acmedrug", intent=("treats",), text="what does acmedrug treat?",
           facts_local={}, facts_web={"acmedrug": [("acmedrug", "treats", "migraine")]})
    tr = Allocator().allocate(q)
    assert tr.answer == "migraine" and tr.rung_reached in ("R1", "R2")
    assert tr.total_cost > tr.rungs[0].cost            # it paid for a climb


def test_overthinking_query_stops_before_drift():
    # R0 right, deep spread would drift to a web hub -> the allocator stops at the confident R0
    N = 12
    local = {"c": [("c", "capital", "right")] + [("c", "has_part", f"a{i}") for i in range(N)]}
    web = {}
    for i in range(N):
        web[f"a{i}"] = [(f"a{i}", "part_of", f"b{i}")]
        web[f"b{i}"] = [(f"b{i}", "located_in", "wrong")]
    q = _q(anchor="c", intent=("capital",), text="capital of c?", facts_local=local, facts_web=web)
    tr = Allocator().allocate(q)
    assert tr.answer == "right" and tr.rung_reached == "R0"


def test_diminishing_stop_guarantees_termination_under_tiny_budget():
    # a hard query but a budget that only covers R0 -> the loop must terminate at R0 (not spin)
    q = _q(anchor="z", intent=("q",), text="a hard AND compositional multi entity question?",
           facts_local={}, facts_web={})
    tr = Allocator(AllocatorConfig(budget=1.0)).allocate(q)
    assert tr.rung_reached == "R0"                     # budget floor forces a stop


def test_abstain_when_nothing_grounds():
    # no local, no web, no plan -> every rung abstains -> the allocator abstains (never fabricates)
    q = _q(anchor="nothing", intent=("unknown_rel",), text="unknown?", facts_local={}, facts_web={})
    tr = Allocator().allocate(q)
    assert tr.abstained is True and tr.answer is None and tr.final_rung == "ABSTAIN"


def test_schmitt_hysteresis_band_is_ordered():
    cfg = AllocatorConfig()
    assert cfg.theta_lo < cfg.theta_hi                 # a real hysteresis band exists (anti-thrash)


def test_amortize_w_returns_normalized_nonnegative_weights():
    # a tiny synthetic log: high-feature rows were worth escalating, low-feature rows were not
    log = [([1.0, 1.0, 1.0, 1.0, 1.0, 0.5], 1), ([0.0, 0.0, 0.0, 0.0, 0.0, 1.0], 0)] * 20
    w = amortize_w(log, iters=200)
    assert len(w) == len(DEFAULT_W)
    assert all(wi >= 0 for wi in w) and abs(sum(w) - 1.0) < 1e-6
