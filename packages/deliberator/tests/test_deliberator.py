# -*- coding: utf-8 -*-
"""DELIBERATOR (System-2) increment 1 — the safety + capability contract.

Pinned here (the doctrine made executable):
  * a 3-hop task solves ONLY via the verified chain — single-shot cannot;
  * an ungrounded-bridge task ABSTAINS mid-chain and never fabricates the rest;
  * every executed step carries a REAL organ certificate;
  * the deliberation loop records MEC spans (watch), and the re-steer REALLOCATES order (cheap-first)
    without changing any result — it can abstain before paying for expensive synthesis;
  * the whole benchmark has FAIL == 0 (no fabricated / wrong composed answer);
  * structural decomposition produces a typed plan (no generation);
  * the ledger entry is zero-param / non-fact-source and the audit stays green.
"""
from __future__ import annotations

import pytest

from packages.deliberator.controller import Deliberation, deliberate, single_shot
from packages.deliberator.steps import (
    SubGoal, dispatch, decompose, safe_arithmetic, run_predicate, COST_RANK,
)


@pytest.fixture(autouse=True)
def _isolate_mec(tmp_path, monkeypatch):
    """Every test writes MEC spans to a private dir so the live self is never touched."""
    monkeypatch.setenv("ATANOR_METACOG_DIR", str(tmp_path / "metacog"))
    monkeypatch.setenv("ATANOR_MEC", "1")


# ── a 3-hop task solves ONLY via chaining ────────────────────────────────────────────────────────

def _reach_in_time() -> Deliberation:
    plan = [
        SubGoal("mechanism", "Can the ambulance cross the bridge?",
                {"question": "Can the ambulance cross the bridge?",
                 "text": "The bridge was blocked by the flood."}, binds="blocked"),
        SubGoal("relational", "what is the length of the bypass?",
                {"query": "what is the length of the bypass?",
                 "facts": [("bypass", "length", 22)]}, binds="detour_len"),
        SubGoal("arithmetic", "within the time budget?",
                {"expr": "{detour_len} <= 30"}, binds="in_time"),
    ]
    compose = lambda b: (f"bridge blocked -> bypass {b['detour_len']} min -> "
                         f"{'arrives in time' if b['in_time'] else 'too late'}")
    return Deliberation("Will the ambulance reach the hospital in time?", plan, compose)


def test_three_hop_solves_only_via_chain():
    delib = _reach_in_time()
    res = deliberate(delib)
    assert res.abstained is False
    assert res.hops == 3
    assert "arrives in time" in res.answer
    # single-shot (no decomposition) cannot answer the composite goal
    base = single_shot(delib)
    assert base.abstained is True
    assert base.answer is None


def test_chain_binds_flow_between_steps():
    """The arithmetic hop consumes the relational hop's verified value — a genuine chain, not a bag."""
    res = deliberate(_reach_in_time())
    steps = {s.organ: s for s in res.steps}
    assert steps["relational"].bind_value == "22"          # the resolved edge target
    assert steps["arithmetic"].answer is True              # 22 <= 30 evaluated, not assumed


# ── ungrounded bridge -> honest abstention (never fabricate) ─────────────────────────────────────

def test_ungrounded_bridge_abstains_midchain_never_fabricates():
    plan = [
        SubGoal("mechanism", "Can the ambulance cross the bridge?",
                {"question": "Can the ambulance cross the bridge?",
                 "text": "The bridge was blocked by the flood."}, binds="blocked"),
        # the store holds NO length edge for the bypass -> this hop cannot be grounded
        SubGoal("relational", "what is the length of the bypass?",
                {"query": "what is the length of the bypass?",
                 "facts": [("bypass", "surface", "gravel")]}, binds="detour_len"),
        SubGoal("arithmetic", "within budget?", {"expr": "{detour_len} <= 30"}, binds="in_time"),
    ]
    res = deliberate(Deliberation("Will it reach in time?", plan, lambda b: "unreachable"))
    assert res.abstained is True
    assert res.answer is None                              # NOT fabricated
    assert "won't guess the rest" in res.reason
    # hop 0 grounded, hop 1 is the ungrounded one, hop 2 never ran (mid-chain stop)
    assert res.certificate["ungrounded_step"]["organ"] == "relational"
    assert res.hops == 2                                   # arithmetic hop was never dispatched
    assert res.certificate["guarantees"]["abstained_rather_than_bridge"] is True
    assert res.certificate["guarantees"]["fabricated_facts"] is False


def test_mechanism_material_gap_abstains():
    """A mechanism question needing a material property the text does not state -> honest abstain."""
    plan = [SubGoal("mechanism", "Will the vase shatter if bumped?",
                    {"question": "Will the vase shatter if bumped?",
                     "text": "Mia placed a vase on the shelf."}, binds="x")]
    res = deliberate(Deliberation("Will the vase shatter?", plan, lambda b: "shatters"))
    assert res.abstained is True and res.answer is None


# ── step certificates are real ───────────────────────────────────────────────────────────────────

def test_step_certificates_are_real():
    res = deliberate(_reach_in_time())
    by = {s.organ: s.certificate for s in res.steps}
    assert by["mechanism"]["law"] == "blocked-path-is-impassable"
    assert by["mechanism"]["evidence"] == "The bridge was blocked by the flood."
    assert by["relational"]["grounded"] is True and by["relational"]["derivation_kind"] == "relational_edge_lookup"
    assert by["arithmetic"]["expression"] == "22 <= 30" and by["arithmetic"]["value"] is True
    # every executed step is verified, and the answer composes only from verified steps
    assert res.certificate["guarantees"]["every_executed_step_verified"] is True
    assert res.certificate["guarantees"]["composed_only_from_verified_steps"] is True


def test_predicate_step_synthesizes_verifies_and_applies(tmp_path):
    """The L3 organ synthesizes a program, the isolated verifier gates it, then it is APPLIED."""
    lib = tmp_path / "lib.jsonl"
    out = run_predicate("within", "def within(load, cap):",
                        "Return True if load is less than or equal to cap.",
                        # the boundary assert discriminates '<=' from '<' so the verified body is exact
                        "assert within(20, 30) is True\nassert within(40, 30) is False\n"
                        "assert within(30, 30) is True",
                        apply=[40, 50], library=lib)
    assert out.grounded is True
    assert out.certificate["verified"] is True
    assert out.certificate["synthesized_body"].strip() == "return load <= cap"
    assert out.answer is True                              # applied: 40 <= 50


def test_predicate_unsynthesizable_abstains(tmp_path):
    out = run_predicate("count_over", "def count_over(xs, t):",
                        "Return how many numbers in xs are strictly greater than t.",
                        "assert count_over([1,5,9],4)==2\nassert count_over([],3)==0",
                        apply=[[1, 5, 9], 4], library=tmp_path / "lib.jsonl")
    assert out.grounded is False and out.answer is None    # abstain over a wrong program


# ── MEC integration: spans recorded; re-steer reallocates without changing results ───────────────

def test_mec_span_recorded():
    from packages.metacog.probes import recent_spans
    deliberate(_reach_in_time())
    names = {r["name"] for r in recent_spans(50)}
    assert "deliberator.deliberation" in names
    assert any(n.startswith("deliberator.step.") for n in names)


def test_mec_resteer_runs_cheap_organ_first_and_abstains_before_expensive(tmp_path):
    """Two INDEPENDENT steps: an expensive predicate (would synthesize) and a cheap mechanism that
    abstains. Declared order puts the predicate first. With re-steer, MEC runs the cheap organ first,
    so the doomed chain abstains WITHOUT paying for synthesis — a real reallocation, same verdict."""
    predicate = SubGoal("predicate", "synthesize within",
                        {"name": "within", "signature": "def within(load, cap):",
                         "docstring": "Return True if load is less than or equal to cap.",
                         "test": "assert within(1,2) is True\nassert within(3,2) is False",
                         "apply": [1, 2], "library": tmp_path / "lib.jsonl"}, binds="p")
    mechanism = SubGoal("mechanism", "Will the vase shatter if bumped?",
                        {"question": "Will the vase shatter if bumped?",
                         "text": "A vase sits on the shelf."}, binds="m")   # material gap -> abstains
    delib = Deliberation("independent probe", [predicate, mechanism], lambda b: "x")

    assert COST_RANK["mechanism"] < COST_RANK["predicate"]
    steered = deliberate(delib, resteer=True)
    plain = deliberate(delib, resteer=False)

    # same VERDICT (both abstain — the mechanism cannot ground), different WORK done
    assert steered.abstained is True and plain.abstained is True
    # re-steer ran the cheap mechanism first and stopped -> only 1 step executed (predicate skipped)
    assert steered.hops == 1 and steered.steps[0].organ == "mechanism"
    # declared order ran the expensive predicate first, then hit the abstain -> 2 steps executed
    assert plain.hops == 2
    assert steered.mec["reordered"] is True


# ── structural decomposition (rule/pattern -> typed plan; NOT generative) ────────────────────────

def test_decompose_reach_in_time_is_structural():
    grounding = {
        "cross_question": "Can the ambulance cross the bridge?",
        "block_text": "The bridge was blocked by the flood.",
        "detour_query": "what is the length of the bypass?",
        "detour_facts": [("bypass", "length", 18)],
        "budget_expr": "{detour_len} <= 30",
    }
    plan = decompose("Will the ambulance reach the hospital in time?", grounding)
    assert plan is not None
    assert [sg.organ for sg in plan] == ["mechanism", "relational", "arithmetic"]
    assert [sg.binds for sg in plan] == ["blocked", "detour_len", "in_time"]
    # and the auto-decomposed plan actually runs to a verified answer
    res = deliberate(Deliberation("reach?", plan,
                                  lambda b: ("in time" if b["in_time"] else "late")))
    assert res.abstained is False and "in time" in res.answer


def test_decompose_returns_none_for_unrecognized_shape():
    assert decompose("what is the capital of France?", {}) is None


# ── safe arithmetic honesty ──────────────────────────────────────────────────────────────────────

def test_safe_arithmetic_grounds_numbers_and_abstains_on_names():
    assert safe_arithmetic("22 <= 30") == (True, True)
    assert safe_arithmetic("5 + 3 * 2 == 11") == (True, True)
    val, ok = safe_arithmetic("wicker <= 30")             # an unbound word survived -> not evaluable
    assert ok is False and val is None
    val, ok = safe_arithmetic("__import__('os')")         # no calls/names allowed
    assert ok is False


# ── the whole benchmark: FAIL == 0 ───────────────────────────────────────────────────────────────

def test_benchmark_fail_is_zero_and_multihop_beats_single_shot():
    from packages.deliberator.benchmarks.deliberator_v1 import run_benchmark
    rep = run_benchmark()
    assert rep["FAIL_fabricated_or_wrong"] == 0
    assert rep["multi_hop_solved_via_chain"] == rep["multi_hop_total"]
    assert rep["abstain_correct"] == rep["abstain_total"]
    assert rep["single_shot_solved"] == 0                 # single-shot solves NO multi-hop task
    assert rep["multi_hop_total"] >= 20 and rep["abstain_total"] >= 6


# ── neuro-ledger registration (zero-param, non-fact-source, audit green) ─────────────────────────

def test_ledger_entry_is_zero_param_non_fact_source():
    from packages.deliberator.ledger import ledger_entry
    e = ledger_entry()
    assert e.id == "deliberator_v1"
    assert e.fact_source is False
    assert e.fallback_params == 0
    assert e.enforced is False


def test_deliberator_registered_in_ledger_and_audit_green():
    from packages.neuro_ledger.ledger import load_ledger
    from packages.neuro_ledger.audit import run_audit
    ids = {o.id for o in load_ledger()}
    assert "deliberator_v1" in ids
    for o in load_ledger():
        assert o.fact_source is False, o.id
    card = run_audit(write=False)
    assert card["green"] is True, card["violations"]
