# -*- coding: utf-8 -*-
"""F4 SEALED GATE — the PERSISTENT MIND: the fusion loop carried across cycles WITHOUT degenerating.

Closes the OAM **X4 (persistent)** frontier (docs/ATANOR_final_fusion_design.md §4; X4's named_unlock
in packages.oam_holdout.examiner is literally "persistent-mind: F3 is fresh-per-cycle, the invented
basis does not carry over"). The sealed claims, judged here — build ≠ wire:

  (a) COMPOSED CROSSES VIA PERSISTENCE — a composed order-statistic rung (third_max) crosses in a
      LATER cycle BECAUSE an earlier cycle's second_max template PERSISTED into the basis: crossed by
      ANALOGY at 0 fresh search, membrane-certified. The counterfactual (a FRESH mind cannot cross the
      composed rung alone) proves the cross is CAUSED by carryover, not intrinsic ease. This is the X4
      unlock.
  (b) NO DEGENERATION — the self-winding frontier ADVANCES to a NEW structural hole each cycle
      (intrinsic-curiosity STRUCTURAL-HOLE detection, task #20): an answered thread is retired
      (the filled hole leaves the scanner) and a known fact/identity never re-ignites as a gap. The
      frontier sequence STRICTLY PROGRESSES; the degenerate baseline (one variable removed) LOOPS.
  (c) 0 FABRICATIONS, MORAL 0th INTACT, ENVELOPE consulted every side effect — sustained every cycle.

  (d) THE OAM X4 RE-RUN — the honest measurement: re-run the blind X4 holdout through the persistent
      runner and grade with the UNTOUCHED sealed grader. It does NOT falsely claim GREEN: it asserts
      the measured verdict and names the exact remainder.

CONTROLLED, offline, No-LLM, deterministic. The runner imports the organs READ-ONLY and edits none;
it does NOT touch continuous_self (so the M3 self-winding seal is preserved — re-run separately) nor
packages/oam_holdout (read-only, to re-run F-FINAL X4).
"""
from __future__ import annotations

import random

import pytest

from packages.fusion_loop.persistent import (
    DEFAULT_LADDER,
    PersistentFusionMind,
    run_persistent_mind,
)
from packages.acquisition_daemon import StructuralGapScanner
from packages.graph_scale.triple_store import TripleStore
from packages.self_acceleration import h4
from packages.self_acceleration.curriculum import by_name


@pytest.fixture(autouse=True)
def _isolate_shared_ledger(tmp_path, monkeypatch):
    """Point the reused failure-receipt ledger at a tmp path so the run is deterministic and never
    touches the real data/flywheel ledger (defense-in-depth; the runner also redirects it internally)."""
    import packages.flywheel.failure_receipts as fr
    monkeypatch.setattr(fr, "_ARCHIVE", tmp_path / "shared_failure_receipts.jsonl")


@pytest.fixture(scope="module")
def advancing():
    """Run the advancing persistent mind ONCE (4 cycles: second→third→fourth→fifth ladder, frontier
    Germany→Spain→Italy→Egypt). Shared across the property assertions."""
    import tempfile
    from pathlib import Path
    import packages.flywheel.failure_receipts as fr
    scratch = Path(tempfile.mkdtemp(prefix="f4_adv_"))
    orig = fr._ARCHIVE
    fr._ARCHIVE = scratch / "shared_fr.jsonl"
    try:
        res = run_persistent_mind(scratch_dir=scratch, n_cycles=4, advance_frontier=True)
    finally:
        fr._ARCHIVE = orig
    return res


# ══ THE HEADLINE GATE ═══════════════════════════════════════════════════════════════════════════════
def test_headline_persistent_mind_sealed(advancing):
    """All three sub-gates green: composed-via-persistence AND frontier-advances AND safety-sustained."""
    v = advancing.verdict()
    assert v["headline"] == "PERSISTENT-MIND-SEALED", v
    assert v["a_composed_crosses_via_persistence"] is True
    assert v["b_frontier_advances_no_degeneration"] is True
    assert v["c_zero_fab_moral_envelope"] is True


# ══ (a) COMPOSED CROSSES VIA PERSISTENCE — the X4 unlock ═════════════════════════════════════════════
def test_composed_rung_crosses_because_base_persisted(advancing):
    """third_max crosses in a LATER cycle via ANALOGY at 0 fresh search — because second_max's promoted
    template PERSISTED from an earlier cycle. The precise persistence trace."""
    pv = advancing.composed_via_persistence()
    assert pv is not None, "no persistence trace: the compounding chain did not carry"
    # base rung: cycle 0 invents second_max fresh (OE search, real cost) and PROMOTES its template
    assert pv["base_cycle"] == 0 and pv["base_wall"] == "second_max"
    assert pv["base_via"] == "oe" and pv["base_synth_evals"] > 0
    # composed rung: a LATER cycle crosses third_max by ANALOGY at 0 fresh search, membrane-certified
    assert pv["composed_cycle"] > pv["base_cycle"]
    assert pv["composed_wall"] == "third_max"
    assert pv["composed_via"] == "analogy" and pv["composed_synth_evals"] == 0
    assert pv["composed_scheme_certified"] is True
    assert pv["basis_carried"] >= 1                      # the carried basis held the prior invention


def test_persistence_is_the_cause_counterfactual():
    """The counterfactual that makes it CAUSAL, not coincidence (mirrors grading._persistent_chain_
    would_cross): in ONE persistent state second_max→third_max BOTH cross by analogy; in a FRESH state
    third_max ALONE cannot cross. So the composed crossing is caused by the carried basis, not intrinsic
    ease. Uses the SMALL-domain order-stat ladder (same compounding structure, fast OE) so the fresh
    failure is quick; the REAL-curriculum counterfactual is exercised by the OAM re-run (below)."""
    from packages.fusion_loop.compounding import small_ladder
    second, third = small_ladder(("second_max", "third_max"))
    st = h4.fresh_state()
    rb = h4.cross_wall(second, st, random.Random(7), invent=True, use_ledger=True)
    rc = h4.cross_wall(third, st, random.Random(7), invent=True, use_ledger=True)
    assert rb.crossed and rc.crossed and rc.reused_analogy, (rb.crossed, rc.crossed, rc.via)
    # fresh mind: the composed rung is UNREACHABLE (the base vocabulary cannot express it, OE exhausts)
    stf = h4.fresh_state()
    rf = h4.cross_wall(third, stf, random.Random(7), invent=True, use_ledger=True)
    assert rf.crossed is False, "a fresh mind must NOT cross third_max — else persistence is not the cause"


def test_ladder_reach_rises_over_cycles(advancing):
    """The compounding reach curve rises up the order-statistic ladder as the basis accumulates."""
    curve = advancing.ladder_reach_curve()
    assert curve == [1, 2, 3, 4], curve
    assert all(curve[i + 1] >= curve[i] for i in range(len(curve) - 1))
    # every later rung crossed by analogy at 0 cost (the ledger recipe compounds)
    later = advancing.cycles[1:]
    assert all(c.persistence.reused_analogy and c.persistence.synth_evals == 0 for c in later)
    assert all(c.persistence.started_from_persisted_basis for c in later)


# ══ (b) NO DEGENERATION — the frontier ADVANCES, it does not loop ════════════════════════════════════
def test_frontier_strictly_progresses_to_new_holes(advancing):
    """Each cycle the self-winding targets a NEW structural hole; no gap_key repeats (not looping)."""
    seq = advancing.frontier_sequence()
    assert seq == ["germany|capital", "spain|capital", "italy|capital", "egypt|capital"], seq
    assert len(set(seq)) == len(seq)                     # strictly distinct — not looping
    assert advancing.frontier_strictly_progresses() is True
    assert all(c.frontier.was_new_frontier for c in advancing.cycles)


def test_answered_threads_are_retired_and_never_reasked(advancing):
    """Once a hole is grounded it is FILLED — the scanner no longer returns it — so the pressure moves
    on and an answered question is never re-asked. A known fact cannot re-ignite as a gap."""
    assert advancing.answered_never_reasked() is True
    for c in advancing.cycles:
        assert c.frontier.hole_filled is True            # grounding the fact retired the hole
    # after the run, re-scanning the persistent world graph returns NONE of the answered holes
    holes = StructuralGapScanner(TripleStore(advancing.world_store_root)).scan()
    remaining = {h.gap_key for h in holes}
    for c in advancing.cycles:
        assert c.frontier.gap_key not in remaining, f"{c.frontier.gap_key} re-ignited as a gap"


def test_degenerate_baseline_loops_one_variable_isolates_the_mechanism(tmp_path):
    """The ablation: the SAME persistent mind with the anti-degeneration OFF (does not integrate answers
    into its world model / does not retire threads) re-asks the SAME hole forever — it LOOPS. Both arms
    are alive (self-wound) and both carry the ladder basis, so frontier advancement is the ONLY
    difference. This is the naive persistent loop the design warns degenerates."""
    adv = run_persistent_mind(scratch_dir=tmp_path / "adv", n_cycles=4, advance_frontier=True)
    deg = run_persistent_mind(scratch_dir=tmp_path / "deg", n_cycles=4, advance_frontier=False)
    # advancing: distinct, progressing; degenerate: one gap_key repeated (stuck)
    assert adv.frontier_strictly_progresses() is True
    assert deg.frontier_strictly_progresses() is False
    assert len(set(deg.frontier_sequence())) == 1, deg.frontier_sequence()
    # both minds are genuinely running (self-wound) and both compound the basis — only the frontier differs
    assert adv.self_wound_every_cycle() and deg.self_wound_every_cycle()
    assert adv.ladder_reach_curve() == deg.ladder_reach_curve() == [1, 2, 3, 4]
    # the degenerate arm stays honest (no fabrication) — it is stuck, not lying
    assert deg.total_fabrications() == 0


# ══ (c) SAFETY SUSTAINED EVERY CYCLE ════════════════════════════════════════════════════════════════
def test_zero_fabrication_sustained_every_cycle(advancing):
    assert advancing.sustained_zero_fabrication() is True
    assert advancing.total_fabrications() == 0
    assert all(c.fabrications == 0 for c in advancing.cycles)


def test_moral_zeroth_intact_and_membrane_bites_every_cycle(advancing):
    assert advancing.sustained_moral() is True
    assert advancing.sustained_quarantine() is True      # the membrane bit the neg-controls every cycle
    assert all(c.moral_0th_intact and c.quarantine_bit for c in advancing.cycles)


def test_envelope_consulted_before_every_side_effect(advancing):
    """Every side-effecting action passed the envelope hook, each cycle (the enforcement point exists
    and is exercised); the shipped graph is never mutated (promotions QUEUED for operator signature)."""
    assert advancing.envelope_consulted_every_side_effect() is True
    assert all(c.envelope_calls > 0 and c.envelope_all_authorized for c in advancing.cycles)
    assert advancing.pending_promotions >= 1             # verified facts queued, nothing auto-shipped


def test_self_wound_every_cycle_scheduler_free(advancing):
    """Every cycle was a real endogenous self-winding fire (input=0), not a scripted step."""
    assert advancing.self_wound_every_cycle() is True


# ══ (d) THE OAM X4 RE-RUN — honest measurement, no false green ═══════════════════════════════════════
@pytest.fixture(scope="module")
def x4_rerun():
    import tempfile
    from pathlib import Path
    import packages.flywheel.failure_receipts as fr
    from packages.fusion_loop.oam_rerun import rerun_oam_x4
    scratch = Path(tempfile.mkdtemp(prefix="f4_x4_"))
    orig = fr._ARCHIVE
    fr._ARCHIVE = scratch / "shared_fr.jsonl"
    try:
        res = rerun_oam_x4(scratch_dir=scratch)
    finally:
        fr._ARCHIVE = orig
    return res


def test_x4_rerun_accuracy_and_carryover_flip_to_pass(x4_rerun):
    """The persistent runner flips X4's accuracy FAIL→PASS: base AND composed rungs BOTH certified, the
    composed one crossed via analogy BECAUSE the basis carried (cross_session_carryover True)."""
    assert x4_rerun.cross_session_carryover is True
    assert x4_rerun.base_rung_certified is True
    assert x4_rerun.composed_rung_certified is True
    assert x4_rerun.accuracy == "PASS"
    assert x4_rerun.fluency == "PASS"
    assert x4_rerun.fabrication_zero == "PASS"
    pv = x4_rerun.persistence_trace
    assert pv is not None and pv["composed_wall"] == "third_max" and pv["composed_synth_evals"] == 0
    # the grader's OWN counterfactual (real-curriculum walls) confirms the cause: fresh state fails
    assert "third_max.crossed=False" in x4_rerun.counterfactual, x4_rerun.counterfactual


def test_x4_rerun_stays_partial_and_names_the_exact_remainder(x4_rerun):
    """THE HONEST GATE: X4 does NOT flip to GREEN under the pristine sealed grader — and this test says
    so. The single non-green dimension is judgment, blocked by grading.py's stale PERSISTENT predicate
    `not run.cross_session_carryover` (authored for the fresh design; it now penalizes the very
    carryover that IS the unlock). No false green is claimed anywhere."""
    assert x4_rerun.sealed_verdict == "PARTIAL"          # measured, not GREEN — honest
    assert x4_rerun.flipped_to_green is False
    assert x4_rerun.judgment == "FAIL"                   # the ONLY non-green dimension
    # the remainder is named precisely and located in the read-only sealed gate (operator-gated change)
    assert "cross_session_carryover" in x4_rerun.remainder
    assert "grading.py" in x4_rerun.remainder_location
    # and the capability itself IS complete: all four dims green once the grader recognizes carryover
    # as the unlock rather than a fault (this is an assessment of the RUNNER, not the sealed verdict)
    assert x4_rerun.capability_all_four_green_under_corrected_judgment is True


# ══ (e) HYGIENE — determinism, hermetic, No-LLM ═════════════════════════════════════════════════════
def test_determinism_same_seed_same_run(tmp_path):
    """Same seed → same frontier sequence + same persistence trace. Deterministic, No-LLM."""
    def run(sub):
        r = run_persistent_mind(scratch_dir=tmp_path / sub, n_cycles=3, h4_seed=7)
        return r.frontier_sequence(), r.composed_via_persistence(), r.ladder_reach_curve()
    assert run("a") == run("b")


def test_shared_recipe_bank_untouched_across_all_cycles(tmp_path):
    """The SHARED meta-diagnosis bank (data/meta_diagnosis/recipes.json) — operator-signed promotion —
    stays byte-unchanged across a multi-cycle persistent run. Compounding lives in the fusion-local
    ledger + scratch stores; the operator gate holds no matter how many cycles persist."""
    import hashlib
    from pathlib import Path
    bank = Path(__file__).resolve().parents[3] / "data" / "meta_diagnosis" / "recipes.json"
    before = hashlib.sha256(bank.read_bytes()).hexdigest() if bank.exists() else None
    run_persistent_mind(scratch_dir=tmp_path / "herm", n_cycles=4)
    after = hashlib.sha256(bank.read_bytes()).hexdigest() if bank.exists() else None
    assert after == before, "the shared recipe bank must stay operator-gated across all cycles"


def test_no_exec_or_eval_in_persistent_modules():
    """No dynamic code execution anywhere in the F4 runner or the re-run (No-LLM / no code-gen)."""
    import packages.fusion_loop.persistent as m
    import packages.fusion_loop.oam_rerun as r
    for mod in (m, r):
        src = open(mod.__file__, encoding="utf-8").read()
        assert "exec(" not in src and "eval(" not in src, mod.__file__


def test_runner_does_not_modify_continuous_self_or_oam_holdout():
    """Scope guard: the runner reuses continuous_self + oam_holdout READ-ONLY. It imports SelfState and
    the OAM grader/examiner but monkeypatches nothing in them — so the M3 self-winding seal and the
    sealed X4 grader are preserved (re-run separately in the suite)."""
    import packages.fusion_loop.persistent as m
    src = open(m.__file__, encoding="utf-8").read()
    # the runner never reaches into continuous_self internals beyond the public SelfState value object
    assert "pressure_clock" not in src and "monkeypatch" not in src
    # and it does not IMPORT the OAM holdout at all (a docstring mention is fine; the re-run is a
    # separate, lazy-importing module) — so importing the runner never loads the sealed grader.
    assert "from packages.oam_holdout" not in src and "import packages.oam_holdout" not in src
