# -*- coding: utf-8 -*-
"""LIVE membrane (Pass 2): the flag-gated / opt-in adapters that put the contamination
firewall on the REAL staging->promotion path.

Proves both halves of the safety contract:
  * DEFAULT (flag off / no opt-in) == no change: the master flag is off, stage_pass_if_enabled
    returns None, confirm_promotion writes no new key, approve_and_apply adds no new key.
  * FLAG ON: staged edges carry JTMS justification + ATMS env + tier; an edge contradicting a
    seeded T0 fact is nogood-quarantined and excluded; approve_and_apply(firewall=...) then
    invalidate_source flips an applied fact OUT; production_store_mutated stays False throughout.
"""
from __future__ import annotations

import json

import pytest

from packages.truth_maintenance.live_membrane import (
    FirewallStagePass, stage_edges_through_firewall, stage_pass_if_enabled,
    tier_for_provenance, membrane_live_enabled, register_applied_fact,
    default_firewall_out, write_manifest, wiring_live, MEMBRANE_LIVE_FLAG,
)
from packages.truth_maintenance.firewall import ContaminationFirewall, RealPromotionGateAdapter
from packages.truth_maintenance.atms import T0


# ---- the master flag is OFF by default -------------------------------------
def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(MEMBRANE_LIVE_FLAG, raising=False)
    assert membrane_live_enabled() is False
    assert stage_pass_if_enabled("wikidata-truthy") is None          # default no-op
    monkeypatch.setenv(MEMBRANE_LIVE_FLAG, "1")
    assert membrane_live_enabled() is True
    assert stage_pass_if_enabled("wikidata-truthy") is not None      # opt-in on
    assert membrane_live_enabled(False) is False                     # explicit flag wins over env


# ---- provenance -> tier policy ---------------------------------------------
def test_tier_for_provenance_policy():
    assert tier_for_provenance("wikidata-truthy") == "single_source"
    assert tier_for_provenance("conceptnet-5.7") == "single_source"
    assert tier_for_provenance("extracted:rule+topology") == "neural"
    assert tier_for_provenance("wikidata-truthy", consensus_domains=3) == "consensus"
    assert tier_for_provenance("unknown-source") == "single_source"   # safe default


# ---- stage pass attaches JTMS justification + ATMS env + AGM tier -----------
def test_stage_pass_attaches_justification_env_tier():
    fp = stage_edges_through_firewall(
        [("dog", "is_a", "mammal"), ("Paris", "country", "France")],
        provenance="wikidata-truthy")
    assert fp.observed == 2 and fp.passed == 2 and fp.quarantined == []

    rec = fp.sample_records[0]
    assert rec["tier"] == "single_source"                 # AGM tier from provenance
    assert rec["atms_env"] == [["single_source"]]         # ATMS environment
    j = rec["jtms_justification"]                          # Doyle SL-justification
    assert j["status"] == "IN" and j["informant"] == "wikidata-truthy"
    assert "src:wikidata-truthy" in j["in"]               # rooted at the source premise

    m = fp.manifest()
    assert m["production_store_mutated"] is False
    json.dumps(m)                                         # fully serializable


def test_consensus_domains_lift_tier():
    fp = stage_edges_through_firewall([("mars", "has_a", "phobos", 3)],
                                      provenance="wikidata-truthy")
    assert fp.sample_records[0]["tier"] == "consensus"    # >= k_consensus domains lifts the tier


# ---- nogood pre-check: contradiction with a seeded T0 fact is quarantined ---
def test_nogood_quarantine_excludes_contradiction():
    fp = stage_edges_through_firewall(
        [("France", "capital", "Berlin"), ("dog", "is_a", "mammal")],
        provenance="wikidata-truthy",
        t0_facts=[("France", "capital", "Paris")])       # operator ground truth
    # clean edge passes; the T0-contradicting edge is excluded
    assert fp.passed == 1
    assert len(fp.quarantined) == 1
    q = fp.quarantined[0]
    assert q["fact_key"] == "capital(France)=Berlin"
    assert q["atms_invalidated"] is True                 # cannot hold with the operator core
    assert "capital(France)=Paris" in q["contradicts"]
    # the nogood {T0_operator, single_source} was recorded (de Kleer)
    assert [T0, "single_source"] in [sorted(ng) for ng in fp.nogoods]


def test_streaming_pass_is_observe_only():
    """observe() only records metadata -- it never returns a mutated store or touches disk."""
    fp = FirewallStagePass(provenance="conceptnet-5.7")
    assert fp.observe("cat", "capable_of", "purr") is True
    assert fp.observe("car", "has_a", "wheel") is True
    assert fp.passed == 2 and fp.observed == 2
    assert fp.manifest()["production_store_mutated"] is False


# ---- out-of-tree manifest writer refuses the ingest / shipped tree ----------
def test_write_manifest_refuses_ingest_tree(tmp_path):
    fp = stage_edges_through_firewall([("a", "is_a", "b")], provenance="wikidata-truthy")
    with pytest.raises(PermissionError):
        write_manifest(fp, "data/graph_scale/staging_b1_wikidata/fw.json")
    with pytest.raises(PermissionError):
        write_manifest(fp, "some/kg_triples/fw.json")
    out = write_manifest(fp, tmp_path / "fw.json")        # a scratch path is fine
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8"))["provenance"] == "wikidata-truthy"


def test_default_firewall_out_never_under_graph_scale(monkeypatch):
    monkeypatch.delenv("ATANOR_MEMBRANE_OUT", raising=False)
    p = str(default_firewall_out("wikidata_truthy")).replace("\\", "/")
    assert "data/graph_scale" not in p and "runtime/firewall" in p


# ---- item 2: confirm_promotion PERSISTS the provenance into the manifest FILE
def test_confirm_promotion_persists_truth_maintenance(tmp_path):
    from packages.candidate_promotion_gate import REQUIRED_CONFIRMATION_PHRASE

    fw = ContaminationFirewall()
    rec = fw.stage_candidate("france", "capital_of", "paris",
                             provenance="operator", source_id="src:op")
    fw.promote(rec, operator_signed=True)
    adapter = RealPromotionGateAdapter(fw, staging_dir=tmp_path / "staging")
    signed = adapter.confirm_batch(
        [rec], operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        source_refs=["https://example.org/evidence"])
    assert signed["allowed"] is True

    # the provenance is now IN THE WRITTEN ARTIFACT, not merely the returned dict
    on_disk = json.loads(open(signed["manifest_path"], encoding="utf-8").read())
    tm = on_disk["truth_maintenance"]["capital_of(france)=paris"]
    assert tm["tier"] == "operator"
    assert tm["jtms_justification"]["status"] == "IN"
    assert [T0] in tm["atms_env"]
    assert on_disk["production_store_mutated"] is False


def test_confirm_promotion_default_is_byte_identical(tmp_path):
    """No truth_maintenance arg -> no new key, on the returned dict OR the file."""
    from packages.candidate_promotion_gate import CandidatePromotionGate, REQUIRED_CONFIRMATION_PHRASE

    gate = CandidatePromotionGate(staging_dir=tmp_path)
    item = {"item_id": "cloud_candidate_x", "item_type": "cloud_candidate",
            "title": "t", "summary": "a public summary long enough to pass the gate cleanly",
            "source_refs": ["https://w3.org/x"], "risk_level": "low",
            "confidence": 0.72, "status": "approved"}
    signed = gate.confirm_promotion([item], item_ids=None, operator_confirmed=True,
                                    confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE)
    assert signed["allowed"] is True
    assert "truth_maintenance" not in signed
    on_disk = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert "truth_maintenance" not in on_disk


# ---- item 3: approve_and_apply(firewall=...) -> invalidate_source cascade ----
def test_approve_apply_firewall_retraction_on_scratch_store(tmp_path):
    pytest.importorskip("numpy")
    try:
        from packages.acquisition_daemon.promotion_queue import AcquisitionQueue
        from packages.candidate_promotion_gate import REQUIRED_CONFIRMATION_PHRASE
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"promotion stack unavailable: {exc}")

    fw = ContaminationFirewall()
    item = {
        "item_id": "cloud_candidate_retract1", "item_type": "cloud_candidate",
        "title": "mars has_a phobos",
        "summary": "web-mined relational fact reaching cross-domain consensus",
        "source_refs": ["https://a.example/1", "https://b.example/2"],
        "risk_level": "low", "confidence": 0.8, "status": "pending",
        "fact": {"subject": "mars", "predicate": "has_a", "object": "phobos"},
        "domains": ["a.example", "b.example"], "urls": ["https://a.example/1"],
        "consensus_domains": 2, "provenance": "web-consensus",
    }
    queue = AcquisitionQueue(tmp_path / "queue.json")
    queue._save({item["item_id"]: item})
    scratch = tmp_path / "scratch_store"

    res = queue.approve_and_apply(
        scratch, operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        staging_dir=tmp_path / "manifests",
        forbid_root="data/graph_scale/kg_triples",
        firewall=fw)                                     # <-- opt-in retraction hook
    assert res["allowed"] is True and res["applied"] == 1
    assert res["production_store_mutated"] is False
    assert scratch.exists()                              # wrote only the scratch store

    key = "has_a(mars)=phobos"
    src = res["firewall_sources"][item["item_id"]]
    assert fw.jtms.is_in(key) is True                    # applied fact is rooted + IN

    flip = fw.invalidate_source(src)                     # the source is later revoked
    assert key in flip["flipped_out"]
    assert fw.jtms.is_in(key) is False                   # dependency-directed retraction: OUT


def test_approve_apply_default_adds_no_firewall_key(tmp_path):
    """firewall=None (default) -> approve_and_apply return is unchanged (no new key)."""
    pytest.importorskip("numpy")
    try:
        from packages.acquisition_daemon.promotion_queue import AcquisitionQueue
        from packages.candidate_promotion_gate import REQUIRED_CONFIRMATION_PHRASE
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"promotion stack unavailable: {exc}")

    item = {
        "item_id": "cloud_candidate_plain", "item_type": "cloud_candidate",
        "title": "venus has_a atmosphere", "summary": "web consensus fact",
        "source_refs": ["https://a/1", "https://b/2"], "risk_level": "low",
        "confidence": 0.8, "status": "pending",
        "fact": {"subject": "venus", "predicate": "has_a", "object": "atmosphere"},
        "domains": ["a", "b"], "urls": ["https://a/1"], "consensus_domains": 2,
    }
    queue = AcquisitionQueue(tmp_path / "queue.json")
    queue._save({item["item_id"]: item})
    res = queue.approve_and_apply(
        tmp_path / "scratch", operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        staging_dir=tmp_path / "manifests", forbid_root="data/graph_scale/kg_triples")
    assert res["applied"] == 1
    assert "firewall_sources" not in res                 # additive key absent by default


# ---- register_applied_fact primitive ---------------------------------------
def test_register_applied_fact_then_invalidate():
    fw = ContaminationFirewall()
    out = register_applied_fact(fw, "x", "has_a", "y",
                                provenance="web-consensus", source_id="src:1",
                                consensus_domains=3)
    assert out["promote"]["promoted"] is True
    assert fw.jtms.is_in("has_a(x)=y") is True
    fw.invalidate_source("src:1")
    assert fw.jtms.is_in("has_a(x)=y") is False


def test_wiring_live_documents_the_flag():
    items = wiring_live()
    assert len(items) >= 3
    assert any("ATANOR_MEMBRANE_LIVE" in s or "--firewall" in s for s in items)
    assert any("invalidate_source" in s for s in items)
    assert any("confirm_promotion" in s for s in items)
