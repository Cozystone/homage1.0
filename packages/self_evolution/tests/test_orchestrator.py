# -*- coding: utf-8 -*-
"""Orchestrator: ranks by impact x evolvability, emits specs vs proposals, persists + journals."""
from __future__ import annotations

import json
from pathlib import Path

from packages.self_evolution import (
    build_weakness_map,
    evolvability,
    headroom,
    impact,
    journal,
    plan_next_evolution,
    rank_score,
)
from packages.self_evolution.deficiency_sensus import DomainWeakness


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _mk(domain, score, base_impact, *, gate=True, gen=True, ver=True, auto=True, kind="data"):
    return DomainWeakness(
        domain=domain, loop_id=domain, score=score, gate_exists=gate, generator_exists=gen,
        verifier_exists=ver, evolvable=gate and gen and ver, autonomous_safe=auto,
        generator_kind=kind, base_impact=base_impact,
    )


def test_rank_is_impact_times_evolvability():
    w = _mk("d", 0.2, 0.5)
    assert rank_score(w) == round(impact(w) * evolvability(w), 6)
    assert impact(w) == round(0.5 * headroom(0.2), 6)


def test_headroom_and_evolvability_scalars():
    assert headroom(1.0) == 0.0
    assert headroom(0.0) == 1.0
    assert headroom(None) == 0.5                      # unmeasured -> conservative mid, never hidden
    # autonomous beats needs-verifier beats architecture-gated at equal headroom
    auto = _mk("a", 0.0, 1.0)
    needs_ver = _mk("b", 0.0, 1.0, ver=False, auto=False)
    arch = _mk("c", 0.0, 1.0, auto=False, kind="architecture")
    assert evolvability(auto) == 1.0
    assert evolvability(needs_ver) == 0.35
    assert evolvability(arch) == 0.15
    assert rank_score(auto) > rank_score(needs_ver) > rank_score(arch)


def test_plan_entries_are_sorted_descending_by_rank():
    plan = plan_next_evolution(write=False)
    ranks = [e["rank"] for e in plan["plan"]]
    assert ranks == sorted(ranks, reverse=True)
    # the top overall entry is the highest impact x evolvability domain
    assert plan["plan"][0]["rank"] == max(ranks)


def test_ranking_orders_a_synthetic_pair_by_impact_times_evolvability():
    """A higher impact x evolvability domain must rank above a lower one — the core ordering law."""
    hi = _mk("hi", 0.0, 0.9)                            # impact 0.9, evolvability 1.0 -> 0.90
    lo = _mk("lo", 0.9, 0.5)                            # impact 0.05, evolvability 1.0 -> 0.05
    assert rank_score(hi) > rank_score(lo)
    mid = _mk("mid", 0.0, 0.9, ver=False, auto=False)  # 0.9 x 0.35 -> 0.315
    assert rank_score(hi) > rank_score(mid) > rank_score(lo)


def test_plan_persists_to_plan_json_with_required_keys():
    plan = plan_next_evolution(write=True)
    p = _root() / "data" / "self_evolution" / "plan.json"
    assert p.exists()
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    for key in ("weakness_map", "plan", "ceiling", "top_overall", "top_autonomous", "doctrine",
                "summary"):
        assert key in on_disk, key
    assert on_disk["summary"]["n_domains"] == len(build_weakness_map())


def test_plan_is_journalled():
    before = len(journal.read_all())
    plan_next_evolution(write=True)
    after = journal.read_all()
    assert len(after) == before + 1
    last = after[-1]
    assert last["event"] == "plan_next_evolution"
    assert "top_overall" in last["payload"]
    assert "ceiling_needs_verifier" in last["payload"]


def test_every_plan_entry_is_spec_or_proposal():
    plan = plan_next_evolution(write=False)
    for e in plan["plan"]:
        assert e["kind"] in ("invocation", "operator_proposal", "rejected_wireheading")
        if e["kind"] == "operator_proposal":
            assert e.get("missing_piece")
            assert e.get("operator_action")
        if e["kind"] == "invocation":
            assert e.get("invocation") is not None
            assert e.get("verifier")
