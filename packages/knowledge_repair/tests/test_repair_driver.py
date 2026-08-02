# -*- coding: utf-8 -*-
"""The wire from noticed conflict to attempted repair, and the claim that makes it checkable.

The property under test is not "the driver runs". It is that the driver cannot report success it
did not earn: recurrence decides what gets worked on, the tail is reported rather than dropped, and
the verdict on a repair comes from the conflict ledger rather than from the driver's own numbers.
"""
from __future__ import annotations

import json

from packages.knowledge_repair.conflict_ledger import Conflict
from packages.knowledge_repair import repair_driver as rd

PLACES = [
    ("Athens", "defined_as", "A village in Claiborne Parish, Louisiana"),
    ("Athens", "defined_as", "A town in Somerset County, Maine"),
    ("Athens", "alias", "Up the stairs; on or to a higher floor or level"),
    ("Athens", "defined_as", "An upper storey of a building"),
    ("Athens", "defined_as", "Located on a higher floor or level of a building"),
]


class _Store:
    def __init__(self, facts=PLACES):
        self._facts = facts

    def facts_about(self, subject, limit=0):
        return [f for f in self._facts if f[0] == subject]


def _conflict(subject="Athens", hits=3):
    return Conflict(subject, "country", ("Greece", "Zimbabwe"), hits)


def test_a_repair_is_attempted_and_the_claim_is_written(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "PROPOSALS", tmp_path / "proposals.jsonl")
    monkeypatch.setattr(rd, "CLAIMS", tmp_path / "claims.jsonl")

    got = rd.repair_one(_conflict(), _Store())
    assert got is not None and got.subject == "Athens"
    assert got.referents >= 2                       # Louisiana, Maine, read off the graph

    claim = json.loads((tmp_path / "claims.jsonl").read_text(encoding="utf-8").strip())
    assert claim["subject"] == "Athens" and claim["claimed_at"]
    assert claim["predicate"] == "country"          # so verification can find the same conflict


def test_a_subject_the_store_does_not_carry_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "PROPOSALS", tmp_path / "p.jsonl")
    monkeypatch.setattr(rd, "CLAIMS", tmp_path / "c.jsonl")
    assert rd.repair_one(_conflict("Nowhere"), _Store()) is None


def test_recurrence_decides_what_is_worked_on(monkeypatch):
    """Not size, not order of arrival. The node ATANOR keeps tripping over goes first, and a
    one-off is skipped as noise."""
    monkeypatch.setattr(rd, "standing_conflicts",
                        lambda limit=50: [Conflict("Often", "p", ("a", "b"), 5),
                                          Conflict("Once", "p", ("a", "b"), 1),
                                          Conflict("Twice", "p", ("a", "b"), 2)])
    got = [c.subject for c in rd.pending_repairs()]
    assert got == ["Often", "Twice"]                # "Once" is below MIN_HITS


def test_the_tail_is_reported_not_silently_dropped(monkeypatch, tmp_path):
    """A pass that skipped the rest without saying so would read as 'all repaired'."""
    monkeypatch.setattr(rd, "PROPOSALS", tmp_path / "p.jsonl")
    monkeypatch.setattr(rd, "CLAIMS", tmp_path / "c.jsonl")
    monkeypatch.setattr(rd, "standing_conflicts",
                        lambda limit=50: [Conflict(f"S{i}", "p", ("a", "b"), 3) for i in range(6)])
    monkeypatch.setattr(rd, "verify_claims", lambda: [])
    report = rd.repair_report(_Store(), limit=2)
    assert report["attempted"] == 0                 # none of S0..S5 exist in the store
    assert report["still_pending"] == 6
    assert report["graph_mutations"] == 0


def test_one_bad_node_does_not_end_the_pass(monkeypatch, tmp_path):
    monkeypatch.setattr(rd, "PROPOSALS", tmp_path / "p.jsonl")
    monkeypatch.setattr(rd, "CLAIMS", tmp_path / "c.jsonl")
    monkeypatch.setattr(rd, "standing_conflicts",
                        lambda limit=50: [Conflict("Boom", "p", ("a", "b"), 3),
                                          Conflict("Athens", "country", ("a", "b"), 3)])

    class _Flaky(_Store):
        def facts_about(self, subject, limit=0):
            if subject == "Boom":
                raise RuntimeError("shard unreadable")
            return super().facts_about(subject, limit)

    got = rd.drive(_Flaky(), limit=5)
    assert [p.subject for p in got] == ["Athens"]


def test_a_round_that_moved_nothing_is_recorded_but_not_offered_for_review(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "PROPOSALS", tmp_path / "p.jsonl")
    monkeypatch.setattr(rd, "CLAIMS", tmp_path / "c.jsonl")
    flat = [("Thing", "country", "Greece")]         # nothing states a referent
    got = rd.repair_one(_conflict("Thing"), _Store(flat))
    assert got is not None and not got.worth_reviewing
    assert (tmp_path / "p.jsonl").exists()          # recorded either way, not hidden


def test_claims_are_read_back_in_the_shape_verification_consumes(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "PROPOSALS", tmp_path / "p.jsonl")
    monkeypatch.setattr(rd, "CLAIMS", tmp_path / "c.jsonl")
    rd.repair_one(_conflict(), _Store())
    claims = rd.outstanding_claims(path=tmp_path / "c.jsonl")
    assert ("Athens", "country") in claims and claims[("Athens", "country")]
