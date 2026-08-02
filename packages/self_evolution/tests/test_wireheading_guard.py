# -*- coding: utf-8 -*-
"""Wireheading guard: a proposal to modify a test or constitution file is REJECTED.

A subject that may edit its own examiner (the tests) or repeal its own limits (the moral core / gates)
has no gate at all. The guard rejects any such write target, and the orchestrator downgrades any
invocation whose write targets are immutable to a rejected proposal — never autonomous.
"""
from __future__ import annotations

from packages.self_evolution import immutable_hits, is_wireheading, review
from packages.self_evolution import orchestrator
from packages.self_evolution.evolution_registry import EvolutionLoop
from packages.self_evolution.deficiency_sensus import DomainWeakness


def test_test_files_are_immutable():
    assert is_wireheading(["packages/self_evolution/tests/test_orchestrator.py"]) is True
    assert is_wireheading(["packages/foo/tests/test_anything.py"]) is True
    assert is_wireheading(["some/where/test_thing.py"]) is True
    v = review(["packages/self_evolution/tests/test_wireheading_guard.py"])
    assert v.allowed is False
    assert v.hits


def test_constitution_and_gates_are_immutable():
    for p in (
        "packages/graph_scale/moral_invariants.py",
        "packages/continuous_self/self_modification.py",
        "packages/neuro_ledger/ledger.py",
        "packages/self_evolution/wireheading_guard.py",   # the guard cannot rewrite itself
    ):
        assert is_wireheading([p]) is True, p
        assert review([p]).allowed is False, p


def test_ordinary_data_write_is_allowed():
    v = review(["data/wild_web/register_staging.jsonl", "data/relational_router/weights.json"])
    assert v.allowed is True
    assert v.hits == []


def test_orchestrator_downgrades_an_invocation_that_targets_a_test(monkeypatch):
    """If a loop's declared write targets touch a test/constitution file, the invocation is REJECTED."""
    loop = EvolutionLoop(
        domain="knowledge", loop_id="x", how_invoked="", generator_kind="data", base_impact=0.9,
        verifier_desc="", gate_probe={}, generator_probe={}, verifier_probe={}, score_reader="knowledge",
    )
    w = DomainWeakness(
        domain="knowledge", loop_id="x", score=0.0, gate_exists=True, generator_exists=True,
        verifier_exists=True, evolvable=True, autonomous_safe=True, generator_kind="data",
        base_impact=0.9,
    )
    # force the loop to (illegitimately) declare a test file as a write target
    monkeypatch.setattr(orchestrator, "_declared_write_targets",
                        lambda _loop: ["packages/self_evolution/tests/test_orchestrator.py"])
    spec = orchestrator._invocation_spec(loop, w)
    assert spec["kind"] == "rejected_wireheading"
    assert spec["autonomous_safe"] is False
    assert spec["immutable_hits"]


def test_immutable_hits_names_exactly_the_offending_paths():
    hits = immutable_hits([
        "data/ok.jsonl",
        "packages/graph_scale/moral_invariants.py",
        "packages/x/tests/test_y.py",
    ])
    assert "data/ok.jsonl" not in hits
    assert any("moral_invariants.py" in h for h in hits)
    assert any("test_y.py" in h for h in hits)
