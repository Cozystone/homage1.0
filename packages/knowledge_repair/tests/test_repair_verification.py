# -*- coding: utf-8 -*-
"""The muscle-patch test: a cosmetic repair fails because the world asks again.

Owner's formulation: a person training does not wear a muscle patch, structurally because "there
is essentially no progress" -- the patch fails the next time a box must be lifted. The verifier is
the ordinary work recurring, not an inspection.
"""
from __future__ import annotations

import json

import packages.knowledge_repair.conflict_ledger as CL
from packages.knowledge_repair.repair_verification import MIN_EXPOSURE, verify, verify_all


def _ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(CL, "LEDGER", tmp_path / "conflicts.jsonl")
    return tmp_path / "conflicts.jsonl"


def _hit(subject, ts, predicate="country"):
    """One ledger row at an exact timestamp (the module compares ts lexicographically)."""
    import json
    return json.dumps({"ts": ts, "subject": subject, "predicate": predicate,
                       "values": ["a", "b"], "source": "test"}, ensure_ascii=False)


def _write(path, rows):
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_a_repair_that_holds_is_confirmed_by_the_symptom_not_returning(tmp_path, monkeypatch):
    p = _ledger(tmp_path, monkeypatch)
    _write(p, [_hit("Athens", "2026-07-28T10:00:00"),
               _hit("Athens", "2026-07-28T11:00:00"),
               # after the claim, other subjects keep firing -> the lane is being exercised
               _hit("Cambridge", "2026-07-28T13:00:00"),
               _hit("Cambridge", "2026-07-28T14:00:00"),
               _hit("Cambridge", "2026-07-28T15:00:00")])
    v = verify("Athens", "country", "2026-07-28T12:00:00")
    assert v.hits_before == 2 and v.hits_after == 0
    assert v.verdict == "held" and v.held


def test_a_cosmetic_repair_is_caught_because_the_world_asks_again(tmp_path, monkeypatch):
    """The muscle patch. Nothing inspects the repair -- the box simply has to be lifted again."""
    p = _ledger(tmp_path, monkeypatch)
    _write(p, [_hit("Athens", "2026-07-28T10:00:00"),
               _hit("Athens", "2026-07-28T13:00:00"),
               _hit("Athens", "2026-07-28T14:00:00")])
    v = verify("Athens", "country", "2026-07-28T12:00:00")
    assert v.hits_after == 2
    assert v.verdict == "recurred" and not v.held


def test_silence_without_exposure_is_unproven_never_success(tmp_path, monkeypatch):
    """A verifier that counted "nobody tested me" as passing would be the cheat it exists to
    catch."""
    p = _ledger(tmp_path, monkeypatch)
    _write(p, [_hit("Athens", "2026-07-28T10:00:00")])
    v = verify("Athens", "country", "2026-07-28T12:00:00")
    assert v.exposure_after == 0
    assert v.verdict == "unproven" and not v.held


def test_exposure_must_reach_the_floor_before_silence_counts(tmp_path, monkeypatch):
    p = _ledger(tmp_path, monkeypatch)
    rows = [_hit("Athens", "2026-07-28T10:00:00")]
    rows += [_hit("Other", f"2026-07-28T1{3+i}:00:00") for i in range(MIN_EXPOSURE - 1)]
    _write(p, rows)
    assert verify("Athens", "country", "2026-07-28T12:00:00").verdict == "unproven"


def test_recurrence_outranks_unproven_in_the_report(tmp_path, monkeypatch):
    """A repair that silently came undone is more urgent than one still awaiting exposure."""
    p = _ledger(tmp_path, monkeypatch)
    _write(p, [_hit("Athens", "2026-07-28T13:00:00"),
               _hit("Berlin", "2026-07-28T09:00:00")])
    got = verify_all({("Berlin", "country"): "2026-07-28T12:00:00",
                      ("Athens", "country"): "2026-07-28T12:00:00"})
    assert [v.subject for v in got] == ["Athens", "Berlin"]
    assert got[0].verdict == "recurred" and got[1].verdict == "unproven"


def test_a_different_predicate_on_the_same_subject_is_not_this_repair(tmp_path, monkeypatch):
    p = _ledger(tmp_path, monkeypatch)
    _write(p, [_hit("Athens", "2026-07-28T13:00:00", predicate="capital"),
               _hit("X", "2026-07-28T13:30:00"), _hit("Y", "2026-07-28T14:00:00"),
               _hit("Z", "2026-07-28T14:30:00")])
    v = verify("Athens", "country", "2026-07-28T12:00:00")
    assert v.hits_after == 0 and v.verdict == "held"


def test_a_claim_in_utc_does_not_mark_earlier_local_conflicts_as_recurrence(tmp_path):
    """The defect that made verification useless: two writers, two clock conventions.

    The conflict ledger wrote naive local time and the driver wrote UTC, so a conflict at 19:38
    local (10:38 UTC) sorted AFTER a claim at 13:03 UTC under string comparison, and every repair
    came back `recurred` no matter what it did."""
    from packages.knowledge_repair.repair_verification import verify

    led = tmp_path / "conflicts.jsonl"
    led.write_text(
        json.dumps({"ts": "2026-07-28T19:38:29", "subject": "Athens", "predicate": "country"})
        + "\n" + json.dumps({"ts": "2026-07-28T19:40:00", "subject": "Cambridge",
                             "predicate": "country"}) + "\n"
        + json.dumps({"ts": "2026-07-28T22:10:00", "subject": "Berlin",
                      "predicate": "country"}) + "\n"
        + json.dumps({"ts": "2026-07-28T22:11:00", "subject": "Lima",
                      "predicate": "country"}) + "\n", encoding="utf-8")

    # 13:03 UTC is 22:03 in the +09:00 zone the naive rows were written in.
    got = verify("Athens", "country", "2026-07-28T13:03:06+00:00", path=led)
    assert got.hits_before == 1 and got.hits_after == 0
    assert got.exposure_after == 2                    # Berlin and Lima came after
    assert got.verdict == "unproven"                  # below MIN_EXPOSURE, and honestly so


def test_an_unreadable_timestamp_cannot_convict_a_repair(tmp_path):
    """It is not evidence a repair came undone, so it counts as before."""
    from packages.knowledge_repair.repair_verification import verify

    led = tmp_path / "c.jsonl"
    led.write_text(json.dumps({"ts": "not-a-date", "subject": "Athens",
                               "predicate": "country"}) + "\n", encoding="utf-8")
    got = verify("Athens", "country", "2026-07-28T13:03:06+00:00", path=led)
    assert got.hits_after == 0 and got.verdict != "recurred"
