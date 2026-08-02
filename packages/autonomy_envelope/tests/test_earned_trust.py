# -*- coding: utf-8 -*-
"""Trust must be EARNED by being right about itself, and must not be grantable by itself.

The design question this answers (owner, 2026-07-28): if constraints are to be relaxed
progressively, what is the relaxation based on? Time served is not evidence. Success rate is
gameable by attempting only easy things. Self-report is gameable by lying. Calibration is not:
inflating it requires making predictions the world then confirms.
"""
from __future__ import annotations

import packages.autonomy_envelope.earned_trust as T


def _log(tmp_path, monkeypatch, rows):
    monkeypatch.setattr(T, "LEDGER", tmp_path / "earned_trust.jsonl")
    for cap, conf, correct in rows:
        T.record_outcome(cap, claimed_confident=conf, was_correct=correct, observer="test")


def test_being_right_when_confident_is_what_is_measured(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, [("graph_repair", True, True)] * 40)
    r = T.trust_records()[0]
    assert r.precision_when_confident == 1.0 and r.overconfidence == 0.0
    assert r.sufficient_evidence


def test_a_capability_that_is_usually_right_but_overclaims_is_not_ready(tmp_path, monkeypatch):
    """95% correct while always claiming confidence: the 5% arrives unannounced, and an
    unannounced failure is the one autonomy cannot absorb."""
    _log(tmp_path, monkeypatch,
         [("bold", True, True)] * 38 + [("bold", True, False)] * 2)
    scope = T.earned_scope(max_overconfidence=0.01)
    assert [c["capability"] for c in scope["argues_against"]] == ["bold"]
    assert scope["supports_relaxing"] == []


def test_abstentions_are_not_counted_as_being_right(tmp_path, monkeypatch):
    """Otherwise saying nothing would be the cheapest way to look calibrated."""
    _log(tmp_path, monkeypatch, [("quiet", False, None)] * 40)
    r = T.trust_records()[0]
    assert r.abstentions == 40 and r.confident_claims == 0
    assert not r.sufficient_evidence                     # no claims -> nothing to be trusted about
    assert T.earned_scope()["supports_relaxing"] == []


def test_a_lucky_short_run_earns_nothing(tmp_path, monkeypatch):
    """Three perfect trials is not evidence, and silence is the right output for thin data."""
    _log(tmp_path, monkeypatch, [("new", True, True)] * 3)
    scope = T.earned_scope()
    assert scope["supports_relaxing"] == []
    assert [c["capability"] for c in scope["not_enough_evidence"]] == ["new"]


def test_the_ledger_reports_and_grants_nothing(tmp_path, monkeypatch):
    """A system able to widen its own envelope by writing its own ledger measures nothing."""
    _log(tmp_path, monkeypatch, [("solid", True, True)] * 40)
    scope = T.earned_scope()
    assert scope["grants_nothing"] is True
    assert set(scope) == {"max_overconfidence", "min_observations", "supports_relaxing",
                          "argues_against", "not_enough_evidence", "grants_nothing"}
    # nothing in the returned structure is a capability token or an authorisation
    assert all(isinstance(c, dict) and "capability" in c for c in scope["supports_relaxing"])


def test_outcomes_carry_who_observed_them(tmp_path, monkeypatch):
    """The actor may not score itself; the record names the checker so that is auditable."""
    monkeypatch.setattr(T, "LEDGER", tmp_path / "earned_trust.jsonl")
    T.record_outcome("x", claimed_confident=True, was_correct=True, observer="sealed_grader")
    import json
    row = json.loads((tmp_path / "earned_trust.jsonl").read_text(encoding="utf-8").strip())
    assert row["observer"] == "sealed_grader"


def test_recording_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "LEDGER", tmp_path / "a" / "b" / "c" / "x.jsonl")
    monkeypatch.setattr(T.Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("no")))
    T.record_outcome("x", claimed_confident=True, was_correct=True, observer="t")
