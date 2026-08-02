# -*- coding: utf-8 -*-
"""The orchestrator: two-layer split, signed rollbackable generations, and node adoption.

Pins the constitution end-to-end: a data-carrying/PII contribution never reaches a generation; the
sealed judge gates promotion; the universal layer ships as a signed, hash-chained generation that
rolls back; and the PERSONAL layer is NEVER written by federation (share the ability, keep the
personhood).
"""
from __future__ import annotations

import json

import pytest

from packages.federation.contribution import Contribution
from packages.federation.orchestrator import (
    FederationStore,
    Orchestrator,
    PersonalLayerWriteError,
    adopt,
)

SCHEMA_CORRECT = {
    "rules": [
        {"on": "enter", "args": ["e", "p"], "effect": [["set", "at", "e", "p"]]},
        {"on": "move", "args": ["e", "src", "dst"],
         "effect": [["clear", "at", "e"], ["set", "at", "e", "dst"]]},
    ],
    "queries": {"where": {"predicate": "at", "by": "e"}},
}
SCHEMA_BROKEN = {
    "rules": [
        {"on": "enter", "args": ["e", "p"], "effect": [["set", "at", "e", "p"]]},
        {"on": "move", "args": ["e", "src", "dst"], "effect": [["set", "at", "e", "src"]]},
    ],
    "queries": {"where": {"predicate": "at", "by": "e"}},
}


def _orch(tmp_path):
    return Orchestrator(FederationStore(tmp_path / "fed"))


def _good(node="node-a"):
    return Contribution(node_id=node, capability_kind="schema", capability_id="location_tracking",
                        payload=SCHEMA_CORRECT, self_reported_score=0.6, target_suite="location_tracking")


def _bad(node="node-b"):
    return Contribution(node_id=node, capability_kind="schema", capability_id="location_tracking",
                        payload=SCHEMA_BROKEN, self_reported_score=0.95, target_suite="location_tracking")


def _pii(node="node-c"):
    return Contribution(node_id=node, capability_kind="schema", capability_id="contact_schema",
                        payload={**SCHEMA_CORRECT, "note": "from chat with Sarah Kim, sarah@example.com"},
                        self_reported_score=0.8, target_suite="location_tracking")


# ── promotion / rejection end-to-end ────────────────────────────────────────────────────────────────
def test_verified_contribution_is_promoted_into_a_signed_generation(tmp_path):
    orch = _orch(tmp_path)
    res = orch.integrate([_good()])
    assert res["promoted"] == ["location_tracking"]
    assert res["generation"]["generation_id"] == "gen-0001"
    assert len(res["generation"]["signature"]) == 64
    assert orch.verify_chain() is True


def test_non_reproducing_contribution_is_rejected_and_not_shipped(tmp_path):
    orch = _orch(tmp_path)
    res = orch.integrate([_bad()])
    assert res["promoted"] == []
    assert res["generation"] is None                       # nothing promoted -> no generation
    assert res["rejected"][0]["stage"] == "judge"


def test_data_carrying_contribution_is_rejected_before_judging(tmp_path):
    """Structure-only enforced: a payload shaped like a corpus never reaches the judge."""
    orch = _orch(tmp_path)
    corpus = Contribution(node_id="n", capability_kind="schema", capability_id="c",
                          payload={"corpus": ["row1", "row2"], "rules": []},
                          target_suite="location_tracking")
    res = orch.integrate([corpus])
    assert res["promoted"] == []
    assert res["rejected"][0]["stage"] == "sanitize"
    assert "data_carrying_key" in res["reviews"][0]["sanitize_reasons"]


def test_pii_contribution_is_rejected_at_sanitize(tmp_path):
    orch = _orch(tmp_path)
    res = orch.integrate([_pii()])
    assert res["promoted"] == []
    assert res["rejected"][0]["stage"] == "sanitize"
    reasons = res["reviews"][0]["sanitize_reasons"]
    assert "pii" in reasons and "entity_leak" in reasons


def test_mixed_batch_promotes_only_the_verified_one(tmp_path):
    orch = _orch(tmp_path)
    res = orch.integrate([_good("node-a"), _bad("node-b"), _pii("node-c")])
    assert res["promoted"] == ["location_tracking"]
    assert {r["capability_id"] for r in res["rejected"]} == {"location_tracking", "contact_schema"}


# ── two-layer split: federation NEVER writes the personal layer ─────────────────────────────────────
def test_federation_refuses_to_write_a_personal_path(tmp_path):
    store = FederationStore(tmp_path / "fed")
    with pytest.raises(PersonalLayerWriteError):
        store._write_text(store.personal_path("node-a"), "{}")
    with pytest.raises(PersonalLayerWriteError):
        store._append_line(store.personal_path("node-a"), {"x": 1})


def test_integration_never_touches_an_existing_personal_record(tmp_path):
    store = FederationStore(tmp_path / "fed")
    store.personal_dir.mkdir(parents=True, exist_ok=True)
    p = store.personal_path("node-a")
    p.write_text('{"felt_state": {"pride": 0.4}, "lived_record": ["Busan with Mr. Han"]}',
                 encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    Orchestrator(store).integrate([_good("node-a")])
    assert p.read_text(encoding="utf-8") == before          # untouched
    # and nothing personal is in the universal ledger on disk
    ledger = store.universal_ledger.read_text(encoding="utf-8")
    assert "Busan" not in ledger and "felt_state" not in ledger and "pride" not in ledger


# ── redistribute + adopt: ability transfers, personhood does not ────────────────────────────────────
def test_redistribute_manifest_is_signed_and_structure_only(tmp_path):
    orch = _orch(tmp_path)
    orch.integrate([_good()])
    m = orch.redistribute()
    assert m["chain_valid"] is True and len(m["signature"]) == 64
    assert [c["capability_id"] for c in m["capabilities"]] == ["location_tracking"]
    # a manifest carries only shapes — no personal keys anywhere in it
    blob = json.dumps(m)
    assert "felt_state" not in blob and "lived_record" not in blob


def test_node_adopts_ability_not_personhood(tmp_path):
    from packages.federation import judge as judge_mod
    orch = _orch(tmp_path)
    orch.integrate([_good("node-a")])
    manifest = orch.redistribute()
    # node-b has its own personhood; it adopts node-a's ABILITY into its universal layer only
    node_b_personal = {"felt_state": {"curiosity": 0.5}, "personhood": "node-b"}
    node_b_universal = adopt(manifest, {})
    assert "location_tracking" in node_b_universal
    # node-b can now solve the task with the adopted shape...
    score = judge_mod.score_on_suite("schema", node_b_universal["location_tracking"]["payload"],
                                     "location_tracking")
    assert score == 1.0
    # ...while node-b's personhood is untouched and node-a's never entered the manifest
    assert node_b_personal["personhood"] == "node-b"
    assert "node-a" not in json.dumps(manifest["capabilities"][0]["payload"])


# ── signed, rollbackable generations (constitution 5) ───────────────────────────────────────────────
def test_generations_chain_and_head_advances(tmp_path):
    orch = _orch(tmp_path)
    orch.integrate([_good()])
    g2 = Contribution(node_id="node-d", capability_kind="organ-param", capability_id="linear_sep",
                      payload={"weights": [1.0, 1.0, -1.0], "bias": 0.0}, target_suite="linear_sep")
    orch.integrate([g2])
    assert orch.store.head() == "gen-0002"
    layer = orch.store.universal_layer()
    assert set(layer.keys()) == {"location_tracking", "linear_sep"}


def test_rollback_reverts_the_floor_and_verifies_signature(tmp_path):
    orch = _orch(tmp_path)
    orch.integrate([_good()])                               # gen-0001
    g2 = Contribution(node_id="node-d", capability_kind="organ-param", capability_id="linear_sep",
                      payload={"weights": [1.0, 1.0, -1.0], "bias": 0.0}, target_suite="linear_sep")
    orch.integrate([g2])                                    # gen-0002
    rb = orch.rollback("gen-0001")
    assert rb["ok"] is True
    assert orch.store.head() == "gen-0001"
    # the second capability is no longer in the active floor (append-only: it still exists on disk)
    assert set(orch.store.universal_layer().keys()) == {"location_tracking"}
    # roll forward again by re-pointing HEAD
    assert orch.rollback("gen-0002")["ok"] is True
    assert set(orch.store.universal_layer().keys()) == {"location_tracking", "linear_sep"}


def test_tampered_generation_fails_verification(tmp_path):
    orch = _orch(tmp_path)
    orch.integrate([_good()])
    # tamper with the on-disk generation payload without re-signing
    gens = orch.store.generations_log.read_text(encoding="utf-8").splitlines()
    rec = json.loads(gens[0])
    rec["capabilities"][0]["payload"]["rules"] = []         # gut the ability, keep the signature
    orch.store.generations_log.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    assert orch.verify_generation("gen-0001") is False
    assert orch.verify_chain() is False
    # a tampered chain cannot be rolled into
    assert orch.rollback("gen-0001")["ok"] is False
