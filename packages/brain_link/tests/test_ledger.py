# -*- coding: utf-8 -*-
"""The hash-chained ledger: append-only, signed, and TAMPER-EVIDENT — any rewrite of past history
is detected. Audit trail immutable; knowledge stays retractable (a retract is a new chained entry)."""
from packages.brain_link.ledger import Ledger
from packages.brain_link.protocol import generate_identity


def test_chain_verifies_and_signatures_check():
    pub, sec = generate_identity()
    L = Ledger()
    L.append("a", "hello", {"tier": "pc"}, sec, ts=1.0)
    L.append("a", "turn", {"utterance": "Where is the football?"}, sec, ts=2.0)
    L.append("a", "fact_offer", {"bones": [["coffee", "is_a", "beverage"]]}, sec, ts=3.0)
    v = L.verify(pubkeys={"a": pub})
    assert v["ok"] and v["length"] == 3


def test_tampering_a_past_entry_is_detected():
    pub, sec = generate_identity()
    L = Ledger()
    L.append("a", "turn", {"utterance": "original"}, sec, ts=1.0)
    L.append("a", "turn", {"utterance": "second"}, sec, ts=2.0)
    # a malicious rewrite of entry 0's recorded content (payload_hash) breaks its hash + the chain
    L.entries[0].payload_hash = "deadbeef" * 8
    v = L.verify()
    assert not v["ok"] and v["broken_at"] == 0 and "tamper" in v["reason"]


def test_forged_signature_is_detected():
    pub, sec = generate_identity()
    _, other = generate_identity()
    L = Ledger()
    e = L.append("a", "turn", {"utterance": "hi"}, sec, ts=1.0)
    from packages.brain_link.protocol import sign
    e.sig = sign(other, {"h": e.this_hash})               # signed by the WRONG key
    v = L.verify(pubkeys={"a": pub})
    assert not v["ok"] and "signature" in v["reason"]


def test_retraction_is_append_only_history_immutable_truth_revisable():
    pub, sec = generate_identity()
    L = Ledger()
    L.append("a", "fact_offer", {"bones": [["moon", "made_of", "cheese"]]}, sec, ts=1.0)
    L.append("a", "retract", {"retracts_seq": 0, "reason": "false"}, sec, ts=2.0)
    v = L.verify(pubkeys={"a": pub})
    assert v["ok"] and v["length"] == 2                    # retraction is a NEW entry; history intact
