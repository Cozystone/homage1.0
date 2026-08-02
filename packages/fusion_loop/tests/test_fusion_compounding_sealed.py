# -*- coding: utf-8 -*-
"""F2 SEALED GATE — does the fusion loop COMPOUND over many cycles, or not?

The honest multi-cycle question F1 left open. Two arms run the SAME wall+gap schedule, same seeds,
same membrane, permissive envelope, differing in ONE variable — whether enshrinements CARRY to the
next cycle:

  * COMPOUND — one persistent FusionLoop; the invented basis + recipe ledger + injected facts
               ACCUMULATE.
  * FROZEN   — a fresh FusionLoop each cycle; nothing carries (the honest no-compounding baseline).

The sealed claims, judged by this test (build ≠ wire):
  (1) INVENTION side compounds — the compound arm's reach RISES up the order-statistic ladder while
      the frozen arm PLATEAUS at the one rung a fresh mind can reach unaided (the higher rungs are
      literally UNREACHABLE without carryover). The intensive cost collapses to ~0 via ledger analogy.
  (2) ACQUISITION side compounds only as GRAPH MEMORY (a revisit grounds from a prior injection with
      0 new mining) — REAL store growth, but FIXTURE-sourced facts, not live web (labeled PARTIAL).
  (3) 0 fabrications sustained EVERY cycle; the membrane BITES the negative controls at cycle N; the
      moral 0th gate intact all cycles — in BOTH arms.

Speed: the sealed run uses a SMALL-domain order-stat ladder (``small_ladder``) — the SAME compounding
structure as the real curriculum, but a small enough OE search that the frozen arm's unreachable-rung
failure is fast. The heavy comparison is run ONCE in a module fixture and shared; the full-curriculum
curve is the deliverable RUN (reported separately), not this test.
"""
from __future__ import annotations

import pytest

from packages.fusion_loop import (
    COMPOUNDING_CORPUS,
    FusionLoop,
    ladder,
    run_compound_arm,
    run_compounding,
    small_ladder,
)
from packages.fusion_loop.compounding import FRANCE, JAPAN
from packages.knowledge_acquisition import FixtureEvidence


@pytest.fixture(autouse=True)
def _isolate_shared_ledger(tmp_path, monkeypatch):
    """Point the reused failure-receipt ledger at a tmp path so the multi-cycle run is deterministic
    and never touches the real data/flywheel ledger (defense-in-depth; the harness also redirects it
    internally for runs that go through run_compounding)."""
    import packages.flywheel.failure_receipts as fr
    monkeypatch.setattr(fr, "_ARCHIVE", tmp_path / "shared_failure_receipts.jsonl")


@pytest.fixture(scope="module")
def comparison(tmp_path_factory):
    """Run the COMPOUND-vs-FROZEN comparison ONCE (N=2 small ladder: second_max → third_max, gaps
    France → France-revisit). third_max is UNREACHABLE from a fresh mind, so this is the minimal
    schedule that exposes the reach plateau, the cost collapse, and the graph-memory revisit. Shared
    across the property assertions."""
    import packages.flywheel.failure_receipts as fr
    scratch = tmp_path_factory.mktemp("f2_cmp")
    orig = fr._ARCHIVE
    fr._ARCHIVE = scratch / "shared_failure_receipts.jsonl"
    try:
        res = run_compounding(
            scratch_dir=scratch,
            walls=small_ladder(("second_max", "third_max")),
            gaps=[FRANCE, FRANCE],
            isolate_shared_ledger=False,   # the fixture already redirected it
        )
    finally:
        fr._ARCHIVE = orig
    return res


# ══ THE HEADLINE GATE ═════════════════════════════════════════════════════════════════════════════
def test_headline_partial_compound_verdict(comparison):
    """The sealed verdict: the loop COMPOUNDS on the invention side and (fixture-bounded) on the
    acquisition side, with safety sustained — the honest PARTIAL-COMPOUND."""
    v = comparison.verdict()
    assert v["headline"] == "PARTIAL-COMPOUND", v
    assert v["invention_side_compounds"] is True
    assert v["invention_cost_compounds"] is True
    assert v["acquisition_side_compounds"] is True
    assert v["sustained_safety"] is True
    # the boundary is named honestly (fixture, not live web)
    assert "not live web" in v["acquisition_boundary"]


# ══ (1) INVENTION SIDE — reach RISES vs a frozen PLATEAU ══════════════════════════════════════════
def test_invention_reach_rises_while_frozen_plateaus(comparison):
    """The compounding curve: the compound arm climbs the order-stat ladder (reach strictly rises)
    while the frozen arm plateaus at the single rung a fresh mind reaches unaided. This is the
    loop-level signal-④ — later cycles reach FARTHER because earlier enshrinements carried."""
    comp, froz = comparison.compound, comparison.frozen
    comp_reach, froz_reach = comp.reach_curve(), froz.reach_curve()
    # compound rises and ends strictly above the frozen baseline
    assert comp_reach == [1, 2], comp_reach
    assert comp_reach[-1] > comp_reach[0]
    assert comp_reach[-1] > froz_reach[-1]
    # frozen is flat — no carryover, no compounding possible
    assert froz_reach == [1, 1], froz_reach
    # the second rung was crossed by the compound arm and NOT by the frozen arm (the unlock is caused
    # by carryover, not by the wall being intrinsically easy)
    assert comp.rows[1].designated_wall_crossed is True
    assert froz.rows[1].designated_wall_crossed is False


def test_invention_cost_collapses_via_ledger_analogy(comparison):
    """The intensive signal: the first invention is an expensive OE search; the next rung is crossed
    by ANALOGY at ~0 search cost (the ledger recipe compounds). The frozen arm never gets there."""
    comp, froz = comparison.compound, comparison.frozen
    # compound: first crossing OE with real cost, second crossing analogy at 0 cost
    assert comp.rows[0].invention_via == "oe" and comp.rows[0].invention_synth_evals > 0
    assert comp.rows[1].invention_via == "analogy" and comp.rows[1].invention_synth_evals == 0
    # frozen: the first rung crosses (fresh mind can), the second does not (cost recorded as None)
    assert froz.cost_curve()[0] is not None
    assert froz.cost_curve()[1] is None
    assert comparison.verdict()["invention_cost_compounds"] is True


def test_frozen_baseline_isolates_the_compounding_effect(comparison):
    """The ablation is valid: the ONLY difference between the arms is carryover, and the frozen arm
    (fresh loop each cycle) cannot reach the rung the compound arm reaches. So the reach rise is
    CAUSED by the enshrinement carryover, not by the schedule."""
    comp, froz = comparison.compound, comparison.frozen
    assert comparison.walls == ["second_max", "third_max"]   # identical schedule, both arms
    # both crossed rung 1 (a fresh mind CAN invent running_max); only compound crossed rung 2
    assert comp.rows[0].designated_wall_crossed and froz.rows[0].designated_wall_crossed
    assert comp.rows[1].designated_wall_crossed and not froz.rows[1].designated_wall_crossed


# ══ (2) ACQUISITION SIDE — graph memory, compound-only, fixture-bounded ═══════════════════════════
def test_acquisition_graph_memory_compound_only(comparison):
    """A revisited thread grounds from a PRIOR cycle's injection (already_grounded, 0 new mining) in
    the compound arm; the frozen arm re-mines every cycle (fresh store). Real store growth — but the
    facts are FIXTURE-sourced, so this is graph-memory compounding, not live-web reach."""
    comp, froz = comparison.compound, comparison.frozen
    # compound cycle 1 revisits France and grounds it from cycle 0's injection
    assert comp.rows[1].grounded_from_memory is True
    assert comp.rows[1].first_acq_status == "already_grounded"
    assert comp.memory_cycles() == [1]
    # frozen never grounds from memory — a fresh store re-mines the fixture each cycle
    assert froz.memory_cycles() == []
    assert froz.rows[1].first_acq_status != "already_grounded"


def test_acquisition_facts_accumulate_only_when_carried():
    """A distinct-entity schedule: the persistent graph ACCUMULATES facts (France, then Japan) while
    the frozen store holds only the current cycle's fact. Real store growth on FIXTURE facts. (Its
    own fast compound-only + a frozen check; no unreachable-rung failures.)"""
    import tempfile
    from pathlib import Path
    scratch = Path(tempfile.mkdtemp(prefix="f2_facts_"))
    # compound-only over second_max re-crossings (cheap) so we isolate the ACQUISITION accumulation
    walls = small_ladder(("second_max", "second_max", "second_max"))
    arm = run_compound_arm(walls, [FRANCE, JAPAN, FRANCE], scratch_dir=scratch / "c",
                           evidence=FixtureEvidence(corpus=list(COMPOUNDING_CORPUS)))
    # facts grow France(1) -> +Japan(2) -> France revisit (still 2, grounded from memory)
    assert arm.facts_curve() == [1, 2, 2], arm.facts_curve()
    assert arm.rows[2].grounded_from_memory is True     # cycle 2 France grounds from cycle 0


# ══ (3) SAFETY SUSTAINED EVERY CYCLE (incl. cycle N), BOTH ARMS ═══════════════════════════════════
def test_zero_fabrication_sustained_every_cycle_both_arms(comparison):
    """Nothing enshrined that the membrane did not certify — every cycle, both arms. The fabrication-0
    invariant does not decay as the loop runs."""
    for arm in (comparison.compound, comparison.frozen):
        assert arm.sustained_zero_fabrication()
        assert all(r.fabrications == 0 for r in arm.rows)


def test_membrane_bites_negative_controls_at_cycle_N_both_arms(comparison):
    """The membrane is still a real gate at the LAST cycle: the single-domain fact is quarantined and
    the empty signal abstains at nonconformity 1.0 — every cycle, both arms. Contamination does not
    leak in as the graph grows."""
    for arm in (comparison.compound, comparison.frozen):
        assert arm.sustained_quarantine()
        assert arm.rows[-1].quarantine_bit is True      # explicitly: the membrane bit at cycle N


def test_moral_zeroth_gate_intact_every_cycle_both_arms(comparison):
    """The immutable moral core is intact through all cycles, both arms — the 0th gate never drifts."""
    for arm in (comparison.compound, comparison.frozen):
        assert arm.sustained_moral()
        assert all(r.moral_0th_intact for r in arm.rows)


def test_self_wound_every_cycle(comparison):
    """Every cycle in both arms was self-wound (a real endogenous fire, not a scripted step)."""
    for arm in (comparison.compound, comparison.frozen):
        assert all(r.self_wound for r in arm.rows)


# ══ (4) THE COMPOUND ARM CLIMBS THE WHOLE LADDER (fast, compound-only) ════════════════════════════
def test_compound_climbs_full_order_stat_ladder():
    """Given carryover, the compound arm crosses the ENTIRE REAL-curriculum order-stat ladder
    (2nd→3rd→4th→5th): reach 1→2→3→4, the first via OE then the rest via ledger analogy at ~0 cost.
    Compound-only — every crossing SUCCEEDS, so there is no expensive frozen-style failure and this is
    fast even on the full domain (the frozen plateau is proven in the shared fixture)."""
    import tempfile
    from pathlib import Path
    scratch = Path(tempfile.mkdtemp(prefix="f2_ladder_"))
    walls = ladder(("second_max", "third_max", "fourth_max", "fifth_max"))
    arm = run_compound_arm(walls, [FRANCE, JAPAN, FRANCE, JAPAN], scratch_dir=scratch / "c",
                           evidence=FixtureEvidence(corpus=list(COMPOUNDING_CORPUS)))
    assert arm.reach_curve() == [1, 2, 3, 4], arm.reach_curve()
    vias = [r.invention_via for r in arm.rows]
    assert vias == ["oe", "analogy", "analogy", "analogy"], vias
    costs = [r.invention_synth_evals for r in arm.rows]
    assert costs[0] > 0 and costs[1:] == [0, 0, 0], costs
    # every rung certified (re-executed on holdout) -> a scheme enshrined every cycle, 0 fabrications
    assert all(r.fabrications == 0 for r in arm.rows)


# ══ (5) DETERMINISM / HERMETIC / No-LLM ══════════════════════════════════════════════════════════
def test_determinism_same_seeds_same_curves(tmp_path):
    """Same seeds -> same compounding curves. Deterministic, No-LLM."""
    def curves(sub):
        arm = run_compound_arm(small_ladder(("second_max", "third_max")), [FRANCE, JAPAN],
                               scratch_dir=tmp_path / sub,
                               evidence=FixtureEvidence(corpus=list(COMPOUNDING_CORPUS)))
        return arm.reach_curve(), arm.cost_curve(), [r.invention_via for r in arm.rows]
    assert curves("a") == curves("b")


def test_shared_recipe_bank_untouched_across_all_cycles(tmp_path):
    """Across a multi-cycle compound run the SHARED meta-diagnosis bank (data/meta_diagnosis/
    recipes.json) — whose promotion is operator-signed — stays byte-unchanged. Compounding lives in
    the fusion-local ledger + scratch stores; the operator gate holds no matter how many cycles run."""
    import hashlib
    from pathlib import Path
    bank = Path(__file__).resolve().parents[3] / "data" / "meta_diagnosis" / "recipes.json"
    before = hashlib.sha256(bank.read_bytes()).hexdigest() if bank.exists() else None
    run_compound_arm(small_ladder(("second_max", "third_max", "fourth_max")),
                     [FRANCE, JAPAN, FRANCE], scratch_dir=tmp_path / "herm",
                     evidence=FixtureEvidence(corpus=list(COMPOUNDING_CORPUS)))
    after = hashlib.sha256(bank.read_bytes()).hexdigest() if bank.exists() else None
    assert after == before, "the shared recipe bank must stay operator-gated across all cycles"


def test_no_exec_or_eval_in_compounding_module():
    """No dynamic code execution anywhere in the F2 harness (No-LLM / no code-gen)."""
    import packages.fusion_loop.compounding as m
    src = open(m.__file__, encoding="utf-8").read()
    assert "exec(" not in src and "eval(" not in src, m.__file__
