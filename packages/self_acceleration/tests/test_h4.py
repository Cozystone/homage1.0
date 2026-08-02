# -*- coding: utf-8 -*-
"""H4 (generative self-acceleration) — fast unit tests locking the invariants.

The heavy signal-4 measurement (H4 vs two frozen baselines across the full curriculum) lives in
scratchpad/h4/run_signal4.py; these fast tests lock: (a) the arbitrary-k scheme substrate is CORRECT,
(b) the relativise/instantiate promotion is inverse, (c) PROPOSE-VERIFY integrity (a wrong scheme is
rejected — zero fabrication), (d) the loop crosses second_max by genuine OE invention and PROMOTES the
step, (e) COMPOUNDING — third_max then crosses by ANALOGY at ZERO synth-evals, (f) the reachability
ablation (no-invention cannot cross the deep walls), and (g) No-LLM / no-exec + autonomy."""
from __future__ import annotations

import random

from packages.evolution import open_domain as od
from packages.self_acceleration import scheme_space as sp
from packages.self_acceleration import trace_signature as tsig
from packages.self_acceleration import proposer as _proposer
from packages.self_acceleration import h4
from packages.self_acceleration.ledger import SchemeLedger
from packages.self_acceleration.curriculum import by_name, CURRICULUM


# --- (b) promotion representation: relativise / instantiate are inverse ---------------------------
def test_relativize_instantiate_inverse():
    step = ("max2", ("get", ("var", sp._A), ("int", 1)),
            ("min2", ("var", sp._E), ("get", ("var", sp._A), ("int", 0))))
    tmpl = sp.relativize(step, 1)
    assert tmpl == ("max2", (sp._REL, 0), ("min2", ("var", sp._E), (sp._REL, -1)))
    assert sp.instantiate_rel(tmpl, 1) == step                       # round-trip at the origin index
    at2 = sp.instantiate_rel(tmpl, 2)                                # re-index (the compounding shift)
    assert at2 == ("max2", ("get", ("var", sp._A), ("int", 2)),
                   ("min2", ("var", sp._E), ("get", ("var", sp._A), ("int", 1))))


# --- (a) the arbitrary-k projection chain COMPUTES the k-th order statistic ------------------------
def _order_stat_template():
    return sp.relativize(("max2", ("get", ("var", sp._A), ("int", 1)),
                          ("min2", ("var", sp._E), ("get", ("var", sp._A), ("int", 0)))), 1)


def test_assembled_projection_computes_kth_max():
    T = _order_stat_template()
    rmax = sp.lift("max2")
    T_aux = sp.Aux("order", T, -sp.CLAMP, "invented@t")
    for k in (2, 3, 4):
        chain = [rmax] + [T_aux] * (k - 2)
        out_step = sp.instantiate_rel(T, k - 1)                      # analogy: the same template on top
        prog = sp.assemble_projection(chain, out_step, 0, "xs")
        for xs in [(3, 1, 2, 5, 4), (9, 8, 7), (2, 2, 2), (5,), ()]:
            want = sp.kth_desc(xs, k - 1)
            assert od.evaluate(prog, {"xs": xs}) == want, f"k={k} xs={xs}"


# --- (a) synthesise second_max STANDALONE by OE (genuine invention, no analogy) --------------------
def test_synthesize_second_max_via_oe():
    w = by_name("second_max")
    rng = random.Random(3)
    outer = w.outer(10, rng)
    verify = w.samples(14, rng)
    ho = w.samples(30, rng)
    chain = [sp.lift("max2")]                                        # k=2: running_max aux, output at 1
    r = sp.synthesize_projection_chain(outer, "xs", verify, chain, analogy_template=None)
    assert r["solved"] and r["via"] == "oe" and r["synth_evals"] > 0  # a real search happened
    assert od.fitness(r["tree"], ho) >= 1.0                          # generalises
    assert r["out_step_template"] is not None                       # a promotable template fell out


# --- (e) COMPOUNDING: with the promoted template, third_max crosses by ANALOGY at ZERO synth-evals -
def test_third_max_analogy_zero_search():
    w = by_name("third_max")
    rng = random.Random(4)
    outer = w.outer(10, rng)
    verify = w.samples(14, rng)
    ho = w.samples(30, rng)
    T = _order_stat_template()
    T_aux = sp.Aux("order", T, -sp.CLAMP, "invented@second_max")
    chain = [sp.lift("max2"), T_aux]                                 # k=3 chain built from the invention
    r = sp.synthesize_projection_chain(outer, "xs", verify, chain, analogy_template=T)
    assert r["solved"] and r["via"] == "analogy"
    assert r["synth_evals"] == 0                                     # NO search — reused by index shift
    assert od.fitness(r["tree"], ho) >= 1.0                          # and it is CORRECT (verified)


# --- (c) PROPOSE-VERIFY integrity: no fabrication survives the re-execution anchor ----------------
def test_anchor_rejects_a_fabricated_step_directly():
    """A deliberately WRONG output step (running-sum) assembled into a third_max scheme does NOT
    reproduce the I/O — the verification anchor scores it < 1.0. This is the no-fabrication gate."""
    w = by_name("third_max")
    rng = random.Random(5)
    verify = w.samples(20, rng)
    chain = [sp.lift("max2"), sp.Aux("order", _order_stat_template(), -sp.CLAMP, "invented@x")]
    wrong_out = ("add", ("get", ("var", sp._A), ("int", 2)), ("var", sp._E))   # running sum, not 3rd max
    prog = sp.assemble_projection(chain, wrong_out, 0, "xs")
    assert od.fitness(prog, verify) < 1.0                            # the anchor catches the wrong step


def test_wrong_analogy_never_survives_as_analogy():
    """Feeding a WRONG analogy template does not yield a fabricated 'analogy' solve: the anchor rejects
    it, and the engine honestly falls back to OE search (which, since the CHAIN is adequate, finds the
    TRUE step) — so any solve is via 'oe' and is genuinely correct on holdout, never via the bad analogy."""
    w = by_name("third_max")
    rng = random.Random(5)
    outer = w.outer(10, rng)
    verify = w.samples(14, rng)
    ho = w.samples(30, rng)
    wrong = sp.relativize(("add", ("get", ("var", sp._A), ("int", 1)), ("var", sp._E)), 1)
    chain = [sp.lift("max2"), sp.Aux("order", _order_stat_template(), -sp.CLAMP, "invented@x")]
    r = sp.synthesize_projection_chain(outer, "xs", verify, chain, analogy_template=wrong)
    assert r["via"] != "analogy"                                     # the bad analogy was NOT accepted
    if r["solved"]:
        assert r["via"] == "oe" and od.fitness(r["tree"], ho) >= 1.0  # honest fallback found the truth


# --- (a) computed projection (breadth move): range = max - min ------------------------------------
def test_computed_projection_range():
    w = by_name("range")
    rng = random.Random(6)
    outer = w.outer(10, rng)
    verify = w.samples(14, rng)
    ho = w.samples(30, rng)
    chain = [sp.lift("max2"), sp.lift("min2")]
    r = sp.synthesize_computed_projection(outer, "xs", verify, chain)
    assert r["solved"] and od.fitness(r["tree"], ho) >= 1.0


# --- (d)+(e) the LOOP: cross second_max (invent) then third_max (compound) on a fresh state --------
def test_loop_invents_then_compounds():
    state = h4.fresh_state()
    rng = random.Random(7)
    r2 = h4.cross_wall(by_name("second_max"), state, rng, invent=True, use_ledger=True)
    assert r2.crossed and r2.is_wall and r2.via == "oe" and r2.invented_new_template
    assert len(state["ledger"]) == 1 and state["invented_sources"]  # promoted + recorded
    r3 = h4.cross_wall(by_name("third_max"), state, rng, invent=True, use_ledger=True)
    assert r3.crossed and r3.via == "analogy" and r3.synth_evals == 0   # COMPOUNDING: zero-search cross
    assert r3.retrieval_similarity >= 0.75                            # the ledger recognised the family


# --- (f) REACHABILITY ablation: no-invention cannot cross third_max --------------------------------
def test_no_invention_cannot_cross_third_max():
    state = h4.fresh_state()
    rng = random.Random(8)
    # frozen_no_invent: even after "crossing" second_max, nothing is promoted, so the k=3 chain is
    # unbuildable and third_max is a hard wall.
    h4.cross_wall(by_name("second_max"), state, rng, invent=False, use_ledger=False)
    r3 = h4.cross_wall(by_name("third_max"), state, rng, invent=False, use_ledger=False)
    assert not r3.crossed                                            # the honest plateau


# --- (g) autonomy: the proposer works from (sig, spec, basis, ledger), no target answer -----------
def test_proposer_is_autonomous_and_ranks_correct_depth_top():
    w = by_name("third_max")
    rng = random.Random(9)
    spec = w.samples(16, rng)
    outer = w.outer(10, rng)
    sig = tsig.signature(spec, conflict=tsig.conflict_from_outer(outer, "xs"))
    # a basis that already contains the invented order-stat template + a ledger recipe for it
    basis = sp.base_aux_basis() + [sp.Aux("order", _order_stat_template(), -sp.CLAMP, "invented@second_max")]
    led = SchemeLedger()
    led.add(tsig.signature(w.samples(16, random.Random(1)),
                           conflict=True),
            {"family": "projection_chain", "depth": 2,
             "out_step_template": h4._to_json(_order_stat_template())}, "second_max")
    prop = _proposer.propose(sig, spec, basis, led, use_ledger=True)
    top = prop["candidates"][0]
    assert top["family"] == "projection_chain" and top["depth"] == 3   # ranker selects the right depth
    assert top["analogy_template"] is not None                         # seeded from the ledger


# --- (g) No-LLM / no exec-eval in every H4 module --------------------------------------------------
def test_no_exec_or_eval_in_h4_modules():
    import packages.self_acceleration.scheme_space as m1
    import packages.self_acceleration.proposer as m2
    import packages.self_acceleration.h4 as m3
    import packages.self_acceleration.trace_signature as m4
    import packages.self_acceleration.ledger as m5
    for m in (m1, m2, m3, m4, m5):
        src = open(m.__file__, encoding="utf-8").read()
        assert "exec(" not in src and "eval(" not in src, m.__file__
