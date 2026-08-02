# -*- coding: utf-8 -*-
"""B2: the reflex tier is un-overridable, and therefore obliged to be observable.

The properties under test are not "it writes a file". They are the three that make a receipt worth
having on an organ nobody can overrule: it cannot change the verdict, it cannot be switched off,
and a gap in the record is visible in the record.
"""
from __future__ import annotations

import json

from packages.conformal_gate.decision_ledger import (
    observed_rates, read_decisions, record_decision)
from packages.conformal_gate.gate import ConformalGate
from packages.conformal_gate.nonconformity import SignalVector


def _gate(alpha: float = 0.1, q: float = 0.5) -> ConformalGate:
    return ConformalGate(alpha=alpha, method="split", q_hat=q, calibration_n=100)


def test_deciding_leaves_a_receipt_the_caller_did_not_have_to_ask_for(tmp_path, monkeypatch):
    """A receipt a caller could decline to write would make observability a courtesy."""
    led = tmp_path / "d.jsonl"
    monkeypatch.setattr("packages.conformal_gate.decision_ledger.LEDGER", led)

    out = _gate().decide(SignalVector())
    rows = read_decisions(path=led)
    assert len(rows) == 1
    assert rows[0]["accept"] is out.accept
    assert rows[0]["q_hat"] == out.q_hat and rows[0]["alpha"] == out.alpha
    assert rows[0]["reason"]                      # the basis, not only the verdict


def test_a_dead_ledger_cannot_change_the_verdict(tmp_path, monkeypatch):
    """Canonical 2.3: nothing may alter an evaluator outcome. A full disk costs a row, never an
    answer."""
    monkeypatch.setattr("packages.conformal_gate.decision_ledger.LEDGER",
                        tmp_path / "no" / "such" / "dir" / "d.jsonl")

    def _boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr("pathlib.Path.open", _boom)

    gate = _gate()
    got = gate.decide(SignalVector())
    assert isinstance(got.accept, bool) and got.reason


def test_the_query_is_truncated_and_the_answer_is_never_stored(tmp_path):
    """A gate ledger that accumulated everything anyone asked would be a second copy of the
    conversation wearing an audit's name."""
    led = tmp_path / "d.jsonl"
    record_decision(_gate().decide(SignalVector()), query="x" * 500, path=led)
    row = read_decisions(path=led)[0]
    assert len(row["query"]) <= 120
    assert "answer" not in row and "text" not in row


def test_rotation_is_itself_a_row(tmp_path, monkeypatch):
    """A gap in the record has to be visible IN the record, or the audit reads a truncation as a
    quiet period."""
    led = tmp_path / "d.jsonl"
    monkeypatch.setattr("packages.conformal_gate.decision_ledger.MAX_BYTES", 200)
    for _ in range(12):
        record_decision(_gate().decide(SignalVector()), path=led)
    rows = read_decisions(path=led)
    assert any(r.get("event") == "rotated" for r in rows)
    assert (tmp_path / "d.jsonl.1").exists()


def test_the_live_record_can_disagree_with_the_calibration_self_report(tmp_path):
    """This is the whole reason to persist anything. `achieved` is what the gate said about itself
    at calibration time; this is what it actually did."""
    led = tmp_path / "d.jsonl"
    strict = ConformalGate(alpha=0.1, method="split", q_hat=0.0, calibration_n=50)
    for _ in range(5):
        record_decision(strict.decide(SignalVector()), path=led)
    rates = observed_rates(path=led)
    assert rates["decisions"] == 5
    assert rates["abstain_rate"] == 1.0           # no signal present -> never fabricate
    assert rates["no_signal_rate"] == 1.0


def test_an_unreadable_row_does_not_break_the_audit(tmp_path):
    led = tmp_path / "d.jsonl"
    record_decision(_gate().decide(SignalVector()), path=led)
    with led.open("a", encoding="utf-8") as fh:
        fh.write("{not json\n")
        fh.write(json.dumps({"ts": "z", "accept": True, "signals_present": ["a"]}) + "\n")
    assert observed_rates(path=led)["decisions"] == 2
