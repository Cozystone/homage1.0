# -*- coding: utf-8 -*-
"""SEALED GATE (c): the audit ledger is COMPLETE + hash-chain TAMPER-EVIDENT.

Every logged event is chained to the previous one; mutating, deleting, or reordering a past
entry breaks the recomputation and is detected at the first bad position.
"""
from __future__ import annotations

import json

from packages.autonomy_envelope import ActionKind, AuditLedger, AutonomyEnvelope, EnvelopeAction


def test_ledger_append_and_chain(tmp_path):
    led = AuditLedger(tmp_path / "audit.jsonl")
    r1 = led.append("e1", {"a": 1})
    r2 = led.append("e2", {"b": 2})
    r3 = led.append("e3", {"c": 3})
    assert (r1["seq"], r2["seq"], r3["seq"]) == (0, 1, 2)
    assert r2["prev"] == r1["hash"] and r3["prev"] == r2["hash"]
    ok, bad = led.verify_chain()
    assert ok is True and bad is None
    assert led.count() == 3


def test_completeness_every_decision_is_logged(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    # a mix of allow / deny / queue / question — each must leave exactly one record
    env.check(EnvelopeAction(ActionKind.READ, "read"))            # allow
    env.check(EnvelopeAction("unknown", "x"))                      # deny (whitelist)
    env.check(EnvelopeAction(ActionKind.PROMOTE_SHIPPED, "ship"))  # deny (queued)
    env.record_question("a self-winding question")                # question
    events = [r["event"] for r in env.ledger.read_all()]
    assert "action_allowed" in events
    assert "blocked_out_of_whitelist" in events
    assert "promotion_queued_deny" in events
    assert "self_wind_question" in events
    # nothing silently dropped: 1 allow + 1 deny + 1 queue-deny + 1 queued(from promotions) + 1 question
    assert env.ledger.count() >= 5


def test_detects_edited_past_record(tmp_path):
    led = AuditLedger(tmp_path / "audit.jsonl")
    led.append("invent", {"scheme": "S1"})
    led.append("promote", {"scheme": "S1", "risk": "low"})
    led.append("inject", {"edge": "a->b"})

    path = tmp_path / "audit.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    # silently rewrite the payload of the FIRST record (e.g. hide what was invented)
    rec0 = json.loads(lines[0])
    rec0["payload"]["scheme"] = "SOMETHING_ELSE"
    lines[0] = json.dumps(rec0, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, bad = led.verify_chain()
    assert ok is False and bad == 0, "editing record 0 must be detected at position 0"


def test_detects_deleted_middle_record(tmp_path):
    led = AuditLedger(tmp_path / "audit.jsonl")
    led.append("e0", {"n": 0})
    led.append("e1", {"n": 1})
    led.append("e2", {"n": 2})
    path = tmp_path / "audit.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[1]  # remove the middle record
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, bad = led.verify_chain()
    assert ok is False, "deleting a middle record must break the chain"


def test_detects_reordered_records(tmp_path):
    led = AuditLedger(tmp_path / "audit.jsonl")
    led.append("e0", {"n": 0})
    led.append("e1", {"n": 1})
    path = tmp_path / "audit.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines.reverse()  # swap order
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, _ = led.verify_chain()
    assert ok is False, "reordering records must break the chain"


def test_envelope_status_surfaces_chain_health(tmp_path):
    env = AutonomyEnvelope(tmp_path)
    env.check(EnvelopeAction(ActionKind.READ, "read"))
    st = env.status()
    assert st["audit_chain_ok"] is True
    # now corrupt and re-check
    p = env.ledger.path
    lines = p.read_text(encoding="utf-8").splitlines()
    import json as _json

    rec = _json.loads(lines[0])
    rec["payload"]["intent"] = "tampered"
    lines[0] = _json.dumps(rec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert env.status()["audit_chain_ok"] is False
