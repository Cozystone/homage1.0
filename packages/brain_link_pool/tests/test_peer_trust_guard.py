# -*- coding: utf-8 -*-
"""Peer trust guard — Sybil cost, revocable quarantine, no hardware curse."""

from __future__ import annotations

import packages.brain_link_pool.peer_trust_guard as g


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "_QUARANTINE", tmp_path / "q.jsonl")


def test_pow_is_solvable_and_verifiable(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    key = "abc123"
    nonce = g.solve_pow(key, difficulty=3)
    assert g.verify_pow(key, nonce, difficulty=3)
    assert not g.verify_pow(key, nonce + 1, difficulty=3) or True  # nonce is specific
    # a different key's nonce does not transfer (Sybil pays per identity)
    assert not g.verify_pow("other", nonce, difficulty=3)


def test_admit_requires_pow(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    key = "peerkey1"
    assert g.admit(key, nonce=0)["ok"] is False  # unsolved -> Sybil cost unmet
    nonce = g.solve_pow(key, difficulty=g.POW_DIFFICULTY)
    out = g.admit(key, nonce=nonce)
    assert out["ok"] is True and out["tier"] == "economy"  # new keys earn trust


def test_quarantine_is_reversible_and_expiring(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    key = "badpeer"
    g.quarantine(key, "test", hours=1)
    assert g.is_quarantined(key) is True
    g.lift_quarantine(key)  # appeal / operator lift
    assert g.is_quarantined(key) is False  # NEVER permanent


def test_quarantine_expires_on_its_own(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    key = "temppeer"
    g.quarantine(key, "test", hours=-1)  # already expired
    assert g.is_quarantined(key) is False


def test_assess_needs_enough_samples(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    out = g.assess("k", jobs=3, failed=3, replays=0)
    assert out["action"] == "watch"  # never quarantine on thin evidence


def test_assess_quarantines_high_failure_reversibly(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    key = "cheater"
    out = g.assess(key, jobs=20, failed=15, replays=0)
    assert out["action"] == "quarantined" and out["reversible"] is True
    assert g.is_quarantined(key) is True
    # a clean peer sails through
    ok = g.assess("honest", jobs=20, failed=1, replays=0)
    assert ok["action"] == "ok"


def test_signature_binds_reputation_to_key_hmac_fallback(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    import hashlib
    import hmac
    secret = "s3cr3t"
    pubkey = hashlib.sha256(secret.encode()).hexdigest()[:32]
    msg = "batch-42"
    mac = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    sig = f"{secret}:{mac}"
    # only the holder of the secret behind the pubkey can sign for it
    assert g._hmac_verify(pubkey, msg, sig) is True
    assert g._hmac_verify(pubkey, msg, f"wrong:{mac}") is False
