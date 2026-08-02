# -*- coding: utf-8 -*-
"""B2: a default-deny gate was recording only what it ALLOWED.

`_write_manifest` persists every approved promotion. Refusals went nowhere, which is the wrong half
to keep for a gate whose job is refusing: a gate that starts refusing everything merely looks quiet,
and a gate that starts allowing what it used to refuse has no before-picture to be compared to.
"""
from __future__ import annotations

from packages.candidate_promotion_gate.gate import CandidatePromotionGate
from packages.candidate_promotion_gate.refusal_ledger import read_verdicts, refusal_profile

APPROVED = {"item_id": "a1", "item_type": "cloud_candidate", "title": "ok", "risk_level": "low",
            "status": "approved", "confidence": 0.95, "source_refs": ["u1", "u2"]}
UNSOURCED = {"item_id": "a2", "item_type": "cloud_candidate", "title": "no source", "risk_level": "low",
             "status": "approved", "confidence": 0.95, "source_refs": []}
UNAPPROVED = {"item_id": "a3", "item_type": "cloud_candidate", "title": "pending", "risk_level": "low",
              "status": "pending", "confidence": 0.95, "source_refs": ["u1"]}


def test_refusals_are_recorded_with_the_reason(tmp_path, monkeypatch):
    led = tmp_path / "v.jsonl"
    monkeypatch.setattr("packages.candidate_promotion_gate.refusal_ledger.LEDGER", led)

    CandidatePromotionGate(staging_dir=tmp_path).evaluate([APPROVED, UNSOURCED, UNAPPROVED])
    rows = {r["item_id"]: r for r in read_verdicts(path=led)}
    assert rows["a2"]["eligible"] is False
    assert "missing_source_refs" in rows["a2"]["rejection_reasons"]
    assert any(r.startswith("not_human_approved") for r in rows["a3"]["rejection_reasons"])


def test_accepts_are_recorded_too_or_the_rate_cannot_move(tmp_path, monkeypatch):
    """A ledger holding refusals alone cannot answer "did the accept rate move?", which is the
    question that catches a gate quietly loosening."""
    led = tmp_path / "v.jsonl"
    monkeypatch.setattr("packages.candidate_promotion_gate.refusal_ledger.LEDGER", led)

    CandidatePromotionGate(staging_dir=tmp_path).evaluate([APPROVED, UNSOURCED])
    profile = refusal_profile(path=led)
    assert profile["verdicts"] == 2 and profile["eligible"] == 1
    assert profile["accept_rate"] == 0.5
    assert profile["top_refusal_reasons"][0][0] == "missing_source_refs"


def test_the_unattended_path_that_refused_everything_is_no_longer_silent(tmp_path, monkeypatch):
    """`plan_candidate_intents` returns None when nothing is eligible, and used to leave no trace
    at all. That is the run with nobody watching."""
    led = tmp_path / "v.jsonl"
    monkeypatch.setattr("packages.candidate_promotion_gate.refusal_ledger.LEDGER", led)

    gate = CandidatePromotionGate(staging_dir=tmp_path)
    assert gate.plan_candidate_intents([UNSOURCED]) is None
    rows = read_verdicts(path=led)
    assert len(rows) == 1 and rows[0]["mode"] == "auto" and rows[0]["eligible"] is False


def test_a_dead_ledger_cannot_change_a_verdict(tmp_path, monkeypatch):
    """Canonical 2.3: the gate's answer is never altered by whether its receipt landed."""
    monkeypatch.setattr("packages.candidate_promotion_gate.refusal_ledger.LEDGER",
                        tmp_path / "nope" / "v.jsonl")

    def _boom(*a, **k):
        raise OSError("read-only filesystem")
    monkeypatch.setattr("pathlib.Path.open", _boom)

    got = CandidatePromotionGate(staging_dir=tmp_path).evaluate([APPROVED, UNSOURCED])
    assert [e.eligible for e in got] == [True, False]


def test_no_candidate_payload_is_copied_into_the_ledger(tmp_path, monkeypatch):
    """Otherwise the audit becomes a second copy of the review queue."""
    led = tmp_path / "v.jsonl"
    monkeypatch.setattr("packages.candidate_promotion_gate.refusal_ledger.LEDGER", led)

    fat = dict(APPROVED, item_id="big", body="S" * 5000, title="T" * 400)
    CandidatePromotionGate(staging_dir=tmp_path).evaluate([fat])
    row = read_verdicts(path=led)[0]
    assert "body" not in row and len(row["title"]) <= 100
