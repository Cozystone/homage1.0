# -*- coding: utf-8 -*-
"""Render-model economy: BME invariants, proof-of-inference catches cheaters,
reputation gates tiers, escrow settles only on verification."""
from __future__ import annotations

from packages.brain_link_pool.render_economy import (
    CreditLedger, JobEscrow, PeerRegistry, proof_of_inference, synapse_bench,
)


def _engine(x):  # the deterministic reference engine (stands in for cgsr)
    return {"concept": str(x).upper(), "len": len(str(x))}


def _setup(tmp_path):
    ledger = CreditLedger(tmp_path / "ledger.jsonl")
    registry = PeerRegistry(tmp_path / "peers.json")
    return ledger, registry


def test_bme_no_mint_without_verified_work(tmp_path):
    ledger, _ = _setup(tmp_path)
    ledger.grant("alice", 100, "genesis")
    assert not ledger.mint("bob", 10, "job1", {"verified": False})
    assert ledger.balance("bob") == 0.0
    assert ledger.mint("bob", 10, "job1", {"verified": True, "checked": 3, "matched": 3})
    assert ledger.balance("bob") == 10.0


def test_burn_requires_balance(tmp_path):
    ledger, _ = _setup(tmp_path)
    assert not ledger.burn("poor", 5, "job1")
    ledger.grant("poor", 5, "genesis")
    assert ledger.burn("poor", 5, "job1")
    assert ledger.balance("poor") == 0.0


def test_proof_of_inference_catches_cheater():
    items = ["서울", "커피", "김치", "나무", "사랑"]
    honest = [_engine(x) for x in items]
    assert proof_of_inference(items, honest, _engine, sample=3)["verified"]
    lazy = list(honest)
    lazy[0] = {"concept": "WRONG", "len": 0}
    lazy[2] = {"concept": "ALSO WRONG", "len": 0}
    # 2/5 corrupted, sample 3 — deterministic content-seeded sampling; run the
    # check as the escrow would: any mismatch in the sample fails verification
    proof = proof_of_inference(items, lazy, _engine, sample=5)
    assert not proof["verified"]


def test_reputation_failures_cost_more_than_successes(tmp_path):
    _, reg = _setup(tmp_path)
    reg.register("peer1")
    r0 = reg.register("peer1")["reputation"]
    reg.record_outcome("peer1", True)
    gain = reg.register("peer1")["reputation"] - r0
    reg2 = PeerRegistry(tmp_path / "peers2.json")
    reg2.register("peer2")
    reg2.record_outcome("peer2", False)
    loss = 0.5 - reg2.register("peer2")["reputation"]
    assert loss > gain * 2  # lying must not pay


def test_tiers_and_matcher_prefer_trusted_then_reputation(tmp_path):
    _, reg = _setup(tmp_path)
    reg.register("newbie")
    reg.register("veteran")
    reg.set_bench("veteran", 120.0)
    for _ in range(12):
        reg.record_outcome("veteran", True)
    reg.register("partner", trusted=True)
    assert reg.tier("newbie") == "economy"
    assert reg.tier("veteran") == "priority"
    assert reg.tier("partner") == "trusted"
    assert reg.rank_for_job()[0] == "partner"
    assert reg.rank_for_job()[1] == "veteran"


def test_escrow_full_cycle_and_equilibrium(tmp_path):
    ledger, reg = _setup(tmp_path)
    ledger.grant("requester", 50, "genesis")
    reg.register("worker")
    escrow = JobEscrow(ledger, reg)
    items = ["개념", "그래프", "위상"]
    sub = escrow.submit("requester", "job-1", items, price=7.5)
    assert sub["accepted"] and sub["provider"] == "worker"
    out = escrow.deliver("job-1", [_engine(x) for x in items], _engine)
    assert out["settled"] and out["result_hash"]
    assert ledger.balance("worker") == 7.5
    eq = ledger.equilibrium()
    assert eq["burned"] == 7.5 and eq["minted"] == 7.5  # BME holds
    assert reg.register("worker")["reputation"] > 0.5


def test_escrow_rejects_bad_delivery(tmp_path):
    ledger, reg = _setup(tmp_path)
    ledger.grant("requester", 50, "genesis")
    reg.register("cheater")
    escrow = JobEscrow(ledger, reg)
    items = ["개념", "그래프"]
    escrow.submit("requester", "job-2", items, price=5)
    out = escrow.deliver("job-2", [{"junk": 1}, {"junk": 2}], _engine)
    assert not out["settled"]
    assert ledger.balance("cheater") == 0.0          # no mint
    assert reg.register("cheater")["reputation"] < 0.5  # reputation bleeds


def test_synapse_bench_measures_throughput():
    rate = synapse_bench(_engine, ["a"] * 200)
    assert rate > 0
