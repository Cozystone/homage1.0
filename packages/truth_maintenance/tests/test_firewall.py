# -*- coding: utf-8 -*-
"""Firewall pipeline + adapter onto the REAL operator-signed promotion gate.

Demonstrates the six-stage default-deny pipeline end to end on scratch stores,
shows the adapter handing a firewall batch to the shipped
`candidate_promotion_gate.CandidatePromotionGate`, and proves the firewall never
writes the shipped store.
"""
from __future__ import annotations

import pytest

from packages.truth_maintenance.firewall import (
    ContaminationFirewall, RealPromotionGateAdapter, AbstainingBattery,
    ConformalBattery, wiring_pending,
)
from packages.truth_maintenance.atms import T0, NEURAL


# ---- default-deny staging + promotion --------------------------------------
def test_stage_is_quarantined_and_default_deny():
    fw = ContaminationFirewall()
    rec = fw.stage_candidate("mars", "has_a", "moon", provenance="web:x", source_id="src:x")
    # staged only under {neural}; not promoted knowledge yet
    assert rec.status == "staged"
    assert fw.safe_context() == []                    # nothing in safe mode
    assert "has_a(mars)=moon" in fw.creative_context()  # visible only in creative

    # default-deny: no operator sign, no consensus -> stays quarantined
    out = fw.promote(rec)
    assert out["promoted"] is False
    assert out["reason"] == "default_deny_no_operator_no_consensus"


def test_operator_sign_promotes_and_records_justification():
    fw = ContaminationFirewall()
    rec = fw.stage_candidate("france", "capital_of", "paris",
                             provenance="operator", source_id="src:op")
    out = fw.promote(rec, operator_signed=True)
    assert out["promoted"] is True and out["tier"] == "operator"
    assert out["production_store_mutated"] is False
    # JTMS justification + ATMS env recorded
    assert out["jtms_justification"]["status"] == "IN"
    assert [T0] in out["atms_env"]
    # promoted into the AGM belief base, now visible in safe mode
    assert fw.safe_context() == ["capital_of(france)=paris"]


def test_consensus_promotes_at_consensus_tier():
    fw = ContaminationFirewall(k_consensus=2)
    rec = fw.stage_candidate("mars", "has_a", "phobos", provenance="web", source_id="src:m")
    out = fw.promote(rec, consensus_domains=3)
    assert out["promoted"] is True and out["tier"] == "consensus"


def test_agm_conflict_with_operator_is_rejected_at_firewall():
    fw = ContaminationFirewall()
    op = fw.stage_candidate("france", "capital_of", "paris",
                            provenance="operator", source_id="src:op")
    fw.promote(op, operator_signed=True)
    # a consensus fact contradicting the operator core is rejected by AGM
    bad = fw.stage_candidate("france", "capital_of", "berlin",
                             provenance="web", source_id="src:bad")
    out = fw.promote(bad, consensus_domains=5)
    assert out["promoted"] is False
    assert "operator" in out["reason"]


# ---- stage 5: dependency-directed retraction on source invalidation --------
def test_invalidate_source_flips_dependents_out():
    fw = ContaminationFirewall()
    rec = fw.stage_candidate("x", "has_a", "y", provenance="web:src", source_id="src:1")
    fw.promote(rec, consensus_domains=3)
    assert fw.jtms.is_in("has_a(x)=y")
    res = fw.invalidate_source("src:1")
    assert "has_a(x)=y" in res["flipped_out"]
    assert fw.jtms.is_in("has_a(x)=y") is False       # structurally impermanent


# ---- M3 blind-spot path -----------------------------------------------------
def test_inheritance_exception_withdraws_without_negation():
    fw = ContaminationFirewall()
    fw.register_inheritance_default("penguin", "bird", "can_fly")
    res = fw.register_exception("penguin", "can_fly", marker="cannot_fly(penguin)")
    assert res["status"] == "WITHDRAWN"
    assert res["asserted_negations"] == []            # undercut, negation not asserted


# ---- verification battery (stage 2) ----------------------------------------
def test_abstaining_battery_is_default_deny():
    fw = ContaminationFirewall()
    rec = fw.stage_candidate("a", "has_a", "b", provenance="p", source_id="s")
    outcome = fw.verify(rec)
    assert outcome.verified is False and outcome.method == "abstain_no_battery"
    # with require_verification the abstain blocks promotion even with a sign
    out = fw.promote(rec, operator_signed=True, require_verification=True)
    assert out["promoted"] is False


def test_conformal_battery_adapter_duck_types_decide():
    class _FakeDecision:
        accept = True
        nonconformity = 0.1
        q_hat = 0.3
        certificate = {"alpha": 0.1}

    class _FakeGate:
        def decide(self, signals):
            return _FakeDecision()

    fw = ContaminationFirewall(battery=ConformalBattery(_FakeGate()))
    rec = fw.stage_candidate("a", "has_a", "b", provenance="p", source_id="s")
    outcome = fw.verify(rec, signals=object())
    assert outcome.verified is True and outcome.method == "conformal_gate"


# ---- adapter onto the REAL shipped gate ------------------------------------
def test_adapter_hands_batch_to_real_gate(tmp_path):
    from packages.candidate_promotion_gate import REQUIRED_CONFIRMATION_PHRASE

    fw = ContaminationFirewall()
    rec = fw.stage_candidate("france", "capital_of", "paris",
                             provenance="operator", source_id="src:op")
    fw.promote(rec, operator_signed=True)

    adapter = RealPromotionGateAdapter(fw, staging_dir=tmp_path / "staging")

    # wrong phrase -> the real gate's default-deny refuses
    denied = adapter.confirm_batch(
        [rec], operator_confirmed=True, confirmation_phrase="nope",
        source_refs=["https://example.org/evidence"],
    )
    assert denied["allowed"] is False

    # exact phrase + confirmed flag -> real gate signs a staged manifest
    signed = adapter.confirm_batch(
        [rec], operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        source_refs=["https://example.org/evidence"],
    )
    assert signed["allowed"] is True
    assert signed["promotion_approved_staged"] is True
    assert signed["production_store_mutated"] is False     # never mutates production
    # firewall belief-management provenance attached per item
    tm = signed["truth_maintenance"]["capital_of(france)=paris"]
    assert tm["tier"] == "operator"
    assert tm["jtms_justification"]["status"] == "IN"
    assert [T0] in tm["atms_env"]
    # the real signed manifest was written to the SCRATCH dir, not production
    assert (tmp_path / "staging").exists()


def test_shipped_store_guard_refuses():
    with pytest.raises(PermissionError):
        ContaminationFirewall.assert_not_shipped("data/graph_scale/kg_triples")
    # a scratch dir is fine
    ContaminationFirewall.assert_not_shipped("some/scratch/staging")


def test_wiring_pending_is_explicit():
    items = wiring_pending()
    assert len(items) >= 3
    assert any("conformal_gate" in s for s in items)
    assert any("invalidate_source" in s for s in items)


# ---- optional end-to-end: stage -> sign -> apply into a SCRATCH store -------
def test_end_to_end_apply_into_scratch_store_never_shipped(tmp_path):
    """Full path through the REAL acquisition queue apply step, writing only a
    scratch TripleStore (never the shipped kg_triples). Skips if the store stack
    (numpy) is unavailable."""
    pytest.importorskip("numpy")
    try:
        from packages.acquisition_daemon.promotion_queue import AcquisitionQueue
        from packages.candidate_promotion_gate import REQUIRED_CONFIRMATION_PHRASE
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"promotion stack unavailable: {exc}")

    # a firewall-verified, consensus-promoted fact
    fw = ContaminationFirewall()
    rec = fw.stage_candidate("mars", "has_a", "phobos", provenance="web", source_id="src:m")
    fw.promote(rec, consensus_domains=3)

    # build the queue item the REAL apply step consumes (consensus-verified shape)
    item = RealPromotionGateAdapter.record_to_gate_item(
        rec, confidence=0.8, source_refs=["https://a.example/1", "https://b.example/2"])
    item.update({"status": "pending", "domains": ["a.example", "b.example"],
                 "urls": ["https://a.example/1"], "consensus_domains": 2})

    queue = AcquisitionQueue(tmp_path / "queue.json")
    queue._save({item["item_id"]: item})   # seed the scoped queue directly

    scratch_store = tmp_path / "scratch_store"
    result = queue.approve_and_apply(
        scratch_store, operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        staging_dir=tmp_path / "manifests",
        forbid_root="data/graph_scale/kg_triples",
    )
    assert result["allowed"] is True
    assert result["applied"] == 1
    assert result["production_store_mutated"] is False
    # wrote only the scratch store
    assert scratch_store.exists()
