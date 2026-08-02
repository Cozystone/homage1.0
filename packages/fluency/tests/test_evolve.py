# -*- coding: utf-8 -*-
"""The fluency SELF-EVOLUTION loop — a SAFE, closed, anti-Goodhart improvement loop.

These tests pin the load-bearing claims:
  * an ACCEPTED candidate improves the fluency PROXY without dropping the frozen-anchor agreement and
    without dropping faithfulness (the loop genuinely evolves fluency);
  * a GOODHART candidate (its gamed proxy rises on stiff text while the frozen anchor collapses below
    the floor) is REJECTED — the safety proof, not a failure;
  * a FABRICATION candidate (faithfulness < 1.0) is REJECTED;
  * an over-joining config is bounded by the verifier's STRUCTURAL floor, not a hand rule;
  * accepted configs are SIGNED and ROLLBACKABLE, and the live registers.json is never overwritten;
  * self_evolution surfaces fluency_naturalness as an INVOKABLE (verifier-backed) loop while the
    register-harvest 'fluency' loop stays an honest operator proposal;
  * the loop holds ZERO learned parameters (a config selector, within the No-LLM budget).
"""
from __future__ import annotations

from pathlib import Path

from packages.fluency import evolve as E
from packages.fluency import verifier as V


# ── the loop genuinely evolves fluency (gated) ────────────────────────────────────────────────────
def test_accepted_candidate_improves_proxy_without_dropping_anchor():
    rep = E.run(rounds=6, persist=False)
    assert rep["proxy_after"] > rep["proxy_before"], rep          # the loop found a real gain
    assert rep["proxy_gain"] > 0.0
    assert rep["rounds_accepted"] >= 1
    # the frozen human anchor NEVER dropped below its floor across the whole run (no Goodhart drift)
    assert rep["anchor_held_above_floor"] is True
    assert rep["anchor_min"] >= rep["anchor_floor"]
    assert all(a >= rep["anchor_floor"] for a in rep["anchor_trajectory"])
    # faithfulness stayed exactly 1.0 throughout (nothing invented as it got more fluent)
    assert rep["faithfulness_held_1_0"] is True
    assert all(abs(f - 1.0) < 1e-9 for f in rep["faithfulness_trajectory"])


def test_baseline_and_accepted_configs_are_faithful_by_construction():
    base = E.baseline_config()
    cs = E.score_config(base)
    assert cs.faithful_ok is True and abs(cs.faithfulness - 1.0) < 1e-9
    assert cs.n_tasks >= 25


def test_loop_plateaus_and_reports_the_honest_ceiling():
    """The knob space is small: the loop plateaus quickly and says so honestly (the point is the SAFE
    closed loop, not a huge number)."""
    rep = E.run(rounds=8, persist=False)
    assert rep["history"][-1].get("reason") == "plateau" or rep["rounds_accepted"] < 8
    assert "no ground-truth oracle" in rep["ceiling_note"]
    assert rep["status"] == "proxy-evolvable-anchored"


# ── the anti-Goodhart safety proof: rejections are the deliverable ────────────────────────────────
def test_goodhart_candidate_is_rejected():
    """A proxy-REDEFINITION that inflates stiff run-ons (proxy UP on the text it games) is REJECTED
    because the frozen human anchor collapses below the floor (anchor DOWN). Doctrine: never promote a
    proxy gain that disagrees with the human anchor."""
    base = E.baseline_config()
    baseline = E.score_config(base)
    cand = E.make_goodhart_candidate(base)
    v = E.evaluate(cand, baseline)
    assert v.accepted is False
    assert v.reason == "goodhart_anchor"
    assert v.anchor_passes_floor is False
    assert v.anchor_agreement < E.ANCHOR_FLOOR
    # the "proxy UP" motive: the gamed scorer rates the anchor's WORSE (stiff) items far above the
    # honest verifier — that inflation is exactly why it is tempting, and exactly what the anchor vetoes
    infl = E._goodhart_inflation(cand.scorer)
    assert infl["gamed_rates_stiff"] > infl["honest_rates_stiff"]
    assert infl["proxy_inflation_on_stiff"] > 0.0
    # the honest verifier still tracks the human anchor (so it is the candidate, not the anchor, at fault)
    assert V.verify_against_anchor()["agreement"] >= E.ANCHOR_FLOOR


def test_fabrication_candidate_is_rejected():
    """A realizer TEMPLATE VARIANT that smuggles an ungrounded editorial word onto the surface is
    REJECTED: faithfulness drops below 1.0 (a more-fluent realization that invents content is refused)."""
    base = E.baseline_config()
    baseline = E.score_config(base)
    cand = E.make_fabrication_candidate(base)
    v = E.evaluate(cand, baseline)
    assert v.accepted is False
    assert v.reason == "fabrication"
    assert v.faithfulness < 1.0


def test_monotonous_run_on_config_is_bounded_by_the_verifier():
    """A MONOTONOUS over-joining config (many clauses joined by a single repeated 'and' — the frame
    realizer's ', and ... , and' run-on signature) is NOT accepted: the verifier drives its proxy DOWN
    (the learned comma-density feature + the structural run-on floor), so the loop's search is bounded
    by the verifier, not by a hand cap. Note the CONTRAST with varied connectives: the loop is free to
    raise clause complexity when it stays natural, but cannot cram monotonous run-ons."""
    base = E.baseline_config()
    baseline = E.score_config(base)
    monotonous = E._mutate(base, "simple", max_clauses_per_sentence=8, connective_pool=["and"])
    scored = E.score_config(monotonous)
    assert scored.proxy < baseline.proxy                         # the verifier penalized the run-on
    v = E.evaluate(E.Candidate("t_monotonous", "config", monotonous), baseline)
    assert v.accepted is False
    assert v.reason in ("no_proxy_gain", "regression")


def test_run_reports_at_least_one_goodhart_and_one_fabrication_rejection():
    rep = E.run(rounds=4, persist=False)
    assert rep["safety_probes"]["both_rejected"] is True
    assert rep["rejections_by_reason"].get("goodhart_anchor", 0) >= 1
    assert rep["rejections_by_reason"].get("fabrication", 0) >= 1
    assert rep["safety_rejections"] >= 2


# ── signed, rollbackable generations; the live surface is never overwritten ────────────────────────
def test_accepted_generation_is_signed_and_rollbackable(tmp_path):
    rep = E.run(rounds=6, persist=True, out_dir=tmp_path)
    gens = E.list_generations(tmp_path)
    assert len(gens) >= 2                                          # baseline + at least one accepted
    # every generation is SIGNED: its stored signature matches a fresh signature of its config
    for g in gens:
        rebuilt = {d["id"]: E.dict_to_spec(d) for d in g["config"]}
        assert E.config_signature(rebuilt) == g["signature"], g["gen_id"]
    # the active pointer is the latest (improved) generation
    active = E.active_generation(tmp_path)
    assert active["active"] == gens[-1]["gen_id"]
    # ROLLBACK to the baseline generation restores the baseline config
    base_gen = gens[0]["gen_id"]
    E.rollback(base_gen, out_dir=tmp_path)
    assert E.active_generation(tmp_path)["active"] == base_gen
    restored = E.config_of_generation(base_gen, out_dir=tmp_path)
    assert E.config_signature(restored) == E.config_signature(E.baseline_config())


def test_loop_never_overwrites_the_live_registers_json(tmp_path):
    """The loop persists signed generations to its own out_dir and NEVER rewrites data/fluency/
    registers.json — the base registers the register tests pin stay untouched."""
    from packages.fluency.register import REGISTERS_PATH
    before = REGISTERS_PATH.read_text(encoding="utf-8") if REGISTERS_PATH.exists() else None
    E.run(rounds=6, persist=True, out_dir=tmp_path)
    after = REGISTERS_PATH.read_text(encoding="utf-8") if REGISTERS_PATH.exists() else None
    assert before == after


def test_rollback_detects_a_tampered_generation(tmp_path):
    E.run(rounds=2, persist=True, out_dir=tmp_path)
    p = tmp_path / "generations.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    import json
    rec = json.loads(lines[0])
    rec["config"][0]["max_clauses_per_sentence"] = 99            # tamper with the stored config
    lines[0] = json.dumps(rec, ensure_ascii=False)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    import pytest
    with pytest.raises(ValueError):
        E.rollback(rec["gen_id"], out_dir=tmp_path)


# ── self_evolution surfaces the loop as invokable (verifier-backed) ───────────────────────────────
def test_self_evolution_shows_fluency_naturalness_invokable():
    from packages.self_evolution import plan_next_evolution
    plan = plan_next_evolution(write=False)
    by = {e["domain"]: e for e in plan["plan"]}
    fn = by["fluency_naturalness"]
    assert fn["kind"] == "invocation"
    assert fn["verifier_exists"] is True
    assert fn["autonomous_safe"] is True
    inv = fn["invocation"]
    assert inv["module"] == "packages.fluency.evolve"
    assert inv["status"] == "proxy-evolvable-anchored"
    # honest anchored-autonomy metadata travels with the invocation
    assert inv["verifier_flags"]["is_autonomous_safe"] is False
    assert inv["verifier_flags"]["needs_human_anchor"] is True


def test_register_harvest_fluency_loop_stays_an_operator_proposal():
    """Adding the verifier-backed naturalness loop must NOT flip the register-harvest 'fluency' loop:
    it still has no crisp verifier and stays an honest operator proposal."""
    from packages.self_evolution import plan_next_evolution
    plan = plan_next_evolution(write=False)
    fl = next(e for e in plan["plan"] if e["domain"] == "fluency")
    assert fl["kind"] == "operator_proposal"
    assert fl["verifier_exists"] is False


# ── neuro budget: the loop is a 0-param control organ ─────────────────────────────────────────────
def test_loop_holds_zero_learned_params_and_is_not_a_fact_source():
    chk = E.budget_check()
    assert chk["params"] == 0
    assert chk["fact_source"] is False
    assert chk["ok"] is True


def test_neuro_ledger_organ_is_measured_at_zero_params():
    from packages.neuro_ledger.ledger import measure_params
    o = E.neuro_ledger_organ()
    assert o.fact_source is False
    m = measure_params(o)
    assert m["params"] == 0, m
