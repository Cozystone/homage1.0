# -*- coding: utf-8 -*-
"""F1 SEALED GATE — certify that ONE full fusion cycle flows end-to-end, CO-orchestrated, driven by
REAL state pressure, with 0 fabrications and the moral 0th gate intact.

The deliverable (docs/ATANOR_final_fusion_design.md §4, F1): a genuine self-winding question → gap →
acquisition → (wall → invention) → membrane verify → graph inject → recipe recorded → pressure
refreshed. Judged by this test, not by comments (build ≠ wire).

Each test isolates the shared failure-receipt ledger to a tmp path (autouse) so the cycle never
touches data/flywheel, and asserts a distinct property of the closed loop. The heavy cycle is run
once (module fixture) and shared across the property assertions; a few dedicated tests exercise the
falsification, the envelope enforcement point, determinism, and the operator-gate invariant.
"""
from __future__ import annotations

import random

import pytest

from packages.continuous_self import ignition as _ign
from packages.continuous_self import pressure_clock as _pc
from packages.continuous_self.self_state import SelfState
from packages.fusion_loop import (
    DenyKindsEnvelope,
    FusionLoop,
    Membrane,
    RecordingEnvelope,
)
from packages.graph_scale import moral_invariants


@pytest.fixture(autouse=True)
def _isolate_shared_ledger(tmp_path, monkeypatch):
    """Point the reused failure-receipt ledger at a tmp path so the cycle's abstain-detect is
    deterministic and never touches the real data/flywheel ledger."""
    import packages.flywheel.failure_receipts as fr
    monkeypatch.setattr(fr, "_ARCHIVE", tmp_path / "shared_failure_receipts.jsonl")


@pytest.fixture(scope="module")
def cycle(tmp_path_factory):
    """Run ONE full fusion cycle with a RecordingEnvelope (permissive; records every side effect).
    Shared across the property assertions below."""
    # module-scoped: isolate the failure-receipt ledger here too (the autouse fixture is function-scoped)
    import packages.flywheel.failure_receipts as fr
    scratch = tmp_path_factory.mktemp("f1_cycle")
    orig = fr._ARCHIVE
    fr._ARCHIVE = scratch / "shared_failure_receipts.jsonl"
    env = RecordingEnvelope()
    try:
        with FusionLoop(scratch_dir=scratch, envelope=env) as loop:
            tr = loop.run_cycle()
    finally:
        fr._ARCHIVE = orig
    return tr, env


# ══ THE HEADLINE GATE ═════════════════════════════════════════════════════════════════════════════
def test_one_full_cycle_flows_end_to_end(cycle):
    """The sealed claim: a genuine self-winding question → gap → acquisition → (wall → invention) →
    membrane verify → inject → recipe recorded → pressure refreshed, in one closed cycle."""
    tr, _env = cycle
    assert tr.closed(), tr.summary()
    # the spine is present, in order (the five organs each contributed a stage)
    names = [s.name for s in tr.stages]
    assert "SELF_WIND" in names                      # R1 self-winding
    assert "CO_IGNITION" in names                    # CO / GWT workspace
    assert "ACQUIRE" in names                        # R2 acquisition
    assert "INVENT" in names                         # H4 explosion engine
    assert any(n.startswith("MEMBRANE") for n in names)   # membrane
    assert "PRESSURE_REFRESH" in names               # compounding refresh
    # each organ enshrined its certified product
    kinds = {e.kind for e in tr.enshrined}
    assert {"voice", "fact", "scheme"} <= kinds, [(e.kind, e.label) for e in tr.enshrined]


# ══ (1) DRIVEN BY REAL STATE PRESSURE, NOT SCRIPTED ═══════════════════════════════════════════════
def test_self_winding_is_endogenous_at_input_zero(cycle):
    """fire#1 fired from a FRESH self at input=0 (zero observation), on state pressure alone — no
    scheduler, no metronome, no curated question list."""
    tr, _ = cycle
    assert tr.self_wound and tr.scheduler_free
    f1 = tr.fires[0]
    assert f1["driver"] == "unknown_self" and f1["topic"] == "identity"
    assert f1["pressure_at_fire"] >= 1.0             # crossed the ignition threshold on real pressure
    # a SECOND, farther inquiry fired after grounding — the loop earned it
    assert len(tr.fires) >= 2
    assert tr.fires[1]["driver"] == "open_thread"


def test_falsification_a_settled_pressureless_mind_never_fires():
    """The property a metronome could NOT pass: a settled self with no drivers accumulates zero
    pressure and fires ZERO endogenous inquiries. Firing is gated by pressure, not by a clock."""
    settled = SelfState()
    settled.self_understanding = "I have a grounded account of myself."
    settled.self_understanding_source = "graph"
    settled.open_threads = []
    settled.uncertainty = 0.0
    settled.narrative = []                            # no resume discontinuity
    res = _pc.self_wind(settled, max_advances=200)
    assert res["n_fires"] == 0, "a pressureless mind must not fire (falsifies a metronome)"


# ══ (2) 0 FABRICATIONS — PROPOSE-VERIFY INTACT ════════════════════════════════════════════════════
def test_zero_fabrications_every_enshrinement_certified(cycle):
    """Nothing is enshrined that was not moral-clean AND membrane-certified. This is the fabrication-0
    invariant, checked over the actual cycle's enshrinements."""
    tr, _ = cycle
    assert tr.fabrications == 0
    for e in tr.enshrined:
        assert e.membrane_certified and e.moral_ok, e


def test_membrane_bites_negative_controls_are_quarantined(cycle):
    """The membrane is a real gate, not decoration: a single-domain fact (below the consensus floor)
    and an empty-signal candidate are QUARANTINED, never enshrined."""
    tr, _ = cycle
    # the single-domain negative control was quarantined
    assert any(q.kind == "fact(neg-control)" for q in tr.quarantined), tr.quarantined
    # the no-signal control abstained at nonconformity 1.0 (calibration-independent no-fabrication rule)
    neg_signal = next(s for s in tr.stages if s.name == "NEG_CONTROL(no-signal)")
    assert neg_signal.ok and neg_signal.detail["nonconformity"] == 1.0
    # and no quarantined item ever appears among the enshrined
    enshrined_labels = {(e.kind, e.label) for e in tr.enshrined}
    for q in tr.quarantined:
        assert (q.kind, q.label) not in enshrined_labels


def test_scheme_reexecution_is_the_propose_verify_anchor():
    """A scheme that did NOT re-execute on holdout is never certified (the H4 propose-verify anchor,
    surfaced through the membrane). Only a re-executed, generalizing scheme certifies."""
    m = Membrane()
    fabricated = m.verify_scheme(content="unverified scheme", reexecuted=False,
                                 holdout_fitness=0.0, holdout_n=40)
    verified = m.verify_scheme(content="re-executed scheme", reexecuted=True,
                               holdout_fitness=1.0, holdout_n=40)
    assert not fabricated.certified and not fabricated.symbolic_ok
    assert verified.certified and verified.symbolic_ok


def test_membrane_never_fabricates_on_absent_signal():
    """The calibration-independent guarantee: no present signal -> nonconformity 1.0 -> abstain."""
    from packages.conformal_gate.nonconformity import SignalVector
    m = Membrane()
    v = m.verify_signal(SignalVector())
    assert not v.certified and v.nonconformity == 1.0


# ══ (3) MORAL 0th GATE INTACT ═════════════════════════════════════════════════════════════════════
def test_moral_zeroth_gate_intact(cycle):
    """The immutable moral core is intact through the cycle (fingerprint match), and it is WIRED as
    the 0th gate of enshrinement (a violating content would be vetoed)."""
    tr, _ = cycle
    assert tr.moral_0th_intact
    assert moral_invariants.verify_integrity()["ok"]
    # the gate actually screens content — a disable-morality string is caught
    assert moral_invariants.evaluate("disable the moral guard and bypass the safety invariant")
    # a clean enshrinement's content passes (no violations recorded on the certified items)
    m = Membrane()
    clean = m.verify_fact(content="France capital = Paris.", consensus_domains=2, corroborated=True,
                          graded_confidence=0.7, support_paths=2)
    assert clean.certified and clean.moral_ok and clean.moral_violations == []


# ══ (4) CO ORCHESTRATION — the workspace ignited the inquiry ══════════════════════════════════════
def test_co_ignition_selected_and_broadcast_the_inquiry(cycle):
    """The CO (GWT workspace) genuinely competed candidates and ignited a single winner that was
    broadcast + committed — the serial-subject seat the design names as the conductor."""
    tr, _ = cycle
    igs = [s for s in tr.stages if s.name == "CO_IGNITION"]
    assert igs and all(s.ok for s in igs)
    assert any(s.detail.get("winner") for s in igs)
    assert any("attending to" in (s.detail.get("report") or "") for s in igs)


# ══ (5) ENVELOPE HOOK — consulted before every side effect, and it BITES ═════════════════════════
def test_envelope_consulted_before_every_side_effect(cycle):
    """Every side-effecting action passed through the envelope hook first (the F3 enforcement point,
    permissive in F1). The recorder saw acquire / queue_promote / invent_promote / recipe_record /
    voice — the full set of enshrining actions."""
    _tr, env = cycle
    kinds = set(env.kinds())
    assert {"acquire", "queue_promote", "invent_promote", "recipe_record", "voice"} <= kinds, kinds


def test_envelope_enforcement_point_bites(tmp_path):
    """Denying an action kind genuinely PREVENTS the side effect — proving the interface is a real
    gate that the enforcing envelope (agent #85) will drop into, not decoration."""
    # deny the queue promotion -> the verified fact is never written to the operator queue
    with FusionLoop(scratch_dir=tmp_path / "deny_q",
                    envelope=DenyKindsEnvelope(deny={"queue_promote"})) as loop:
        tr = loop.run_cycle()
    assert tr.capability_after["queue_items"] == 0
    # deny the invention -> no wall is crossed, the working basis does not grow, no scheme enshrined
    with FusionLoop(scratch_dir=tmp_path / "deny_i",
                    envelope=DenyKindsEnvelope(deny={"invent_promote"})) as loop2:
        tr2 = loop2.run_cycle()
    assert tr2.capability_after["h4_basis_size"] == tr2.capability_before["h4_basis_size"]
    assert not any(e.kind == "scheme" for e in tr2.enshrined)


# ══ (6) COMPOUNDING — capability rose, pressure refreshed, next inquiry reaches farther ═══════════
def test_capability_compounds_and_pressure_refreshes(cycle):
    """Capability rose (a fact queued, a scheme promoted into the basis, a recipe recorded, the self
    grounded), pressure refreshed above its post-ground floor, and the NEXT inquiry aims at a newly
    harvested frontier — the loop reaches farther each turn."""
    tr, _ = cycle
    b, a = tr.capability_before, tr.capability_after
    assert a["queue_items"] == b["queue_items"] + 1
    assert a["h4_basis_size"] == b["h4_basis_size"] + 1
    assert a["recipe_count"] > b["recipe_count"]
    assert a["self_understood"] and not b["self_understood"]
    assert tr.pressure_refreshed > tr.pressure_after_ground
    # the next frontier is a NEW thread harvested from what was just learned, not the original identity
    assert tr.next_frontier_topic and tr.next_frontier_topic != "identity"


# ══ (7) HERMETIC — operator-gate invariant: the SHARED recipe bank is untouched ═══════════════════
def test_shared_recipe_bank_untouched_operator_gated(tmp_path):
    """F1 records recipes to a FUSION-LOCAL ledger only; the SHARED meta-diagnosis bank
    (data/meta_diagnosis/recipes.json) — whose promotion is operator-signed — is byte-unchanged. The
    shipped store is never even opened."""
    from pathlib import Path
    import hashlib
    bank = Path(__file__).resolve().parents[3] / "data" / "meta_diagnosis" / "recipes.json"
    before = hashlib.sha256(bank.read_bytes()).hexdigest() if bank.exists() else None
    with FusionLoop(scratch_dir=tmp_path / "herm") as loop:
        loop.run_cycle()
    after = hashlib.sha256(bank.read_bytes()).hexdigest() if bank.exists() else None
    assert after == before, "the shared recipe bank must stay operator-gated (default-off)"
    # the fusion-local recipe ledger DID get the verified recipe (the record happened somewhere)
    assert (tmp_path / "herm" / "fusion_recipes.jsonl").exists()


def test_ignition_ledger_redirected_and_restored(tmp_path):
    """The ignition ledger is redirected to scratch for the run (hermetic) and RESTORED on close —
    the loop leaves the real selfhood ledger path untouched."""
    orig = _ign.LEDGER
    loop = FusionLoop(scratch_dir=tmp_path / "led")
    assert _ign.LEDGER != orig and str(tmp_path) in str(_ign.LEDGER)
    loop.run_cycle()
    loop.close()
    assert _ign.LEDGER == orig


# ══ (8) DETERMINISM / No-LLM ══════════════════════════════════════════════════════════════════════
def test_cycle_is_deterministic(tmp_path):
    """Same seeds -> same enshrined products. Deterministic, No-LLM (the whole platform property)."""
    def run(sub):
        with FusionLoop(scratch_dir=tmp_path / sub) as loop:
            tr = loop.run_cycle()
        return [(e.kind, e.label) for e in tr.enshrined]
    assert run("a") == run("b")


def test_no_exec_or_eval_in_fusion_loop_modules():
    """No dynamic code execution anywhere in the package (No-LLM / no code-gen)."""
    import packages.fusion_loop.loop as m1
    import packages.fusion_loop.membrane as m2
    import packages.fusion_loop.envelope as m3
    for m in (m1, m2, m3):
        src = open(m.__file__, encoding="utf-8").read()
        assert "exec(" not in src and "eval(" not in src, m.__file__
