# -*- coding: utf-8 -*-
"""D2: a slot the schema could not derive becomes a request, and the request gets served.

The property that matters is not "a function came back". It is that the gate the function had to
pass was written by the LOOP and not by a person: if the asserts came from the author of this file,
the measure would be fitted to one idea of progress and the exercise would be theatre.
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.loop_schema.authoring import (
    author_slot, authoring_task, missing_progress)


@dataclass(frozen=True)
class Blind:
    """Counters and a moved-flag. Nothing here accumulates."""
    round_index: int
    total: int
    unresolved: int
    moved: bool


def _run(unresolved: list[int], total: int = 100) -> list[Blind]:
    out, prev = [], None
    for i, u in enumerate(unresolved, start=1):
        out.append(Blind(i, total, u, moved=(prev is None and u < total) or
                                          (prev is not None and u < prev)))
        prev = u
    return out


BLIND = [_run([70, 45, 45]), _run([80, 60, 30, 30])]


def test_a_loop_that_cannot_say_whether_it_is_getting_anywhere_asks_for_a_measure():
    req = missing_progress("blind", BLIND)
    assert req is not None and req.slot == "progress"
    assert req.label_field == "moved"
    assert "unresolved" in req.params and "total" in req.params


def test_a_loop_that_already_has_the_slot_is_left_alone():
    """Do not invent a rival for a measure the loop already reports."""
    @dataclass(frozen=True)
    class Fine:
        got: float
        moved: bool
        dry: bool

    ok = [[Fine(0.3, True, False), Fine(0.7, True, False), Fine(0.7, False, True)]]
    assert missing_progress("fine", ok) is None


def test_without_a_varying_moved_signal_there_are_no_labels_and_no_request():
    """An authored measure could not be checked against anything, so nothing is asked for."""
    always = [[Blind(1, 100, 90, True), Blind(2, 100, 80, True)]]
    assert missing_progress("nolabels", always) is None


def test_the_generated_test_comes_from_the_trace_not_from_this_file():
    req = missing_progress("blind", BLIND)
    task = authoring_task(req, BLIND)
    assert task.signature.startswith("def progress_blind(")
    # the labels in the asserts are the loop's own booleans, verbatim
    assert "[True, True, False]" in task.test
    assert "[True, True, True, False]" in task.test
    assert "fell on run" in task.test and "wrong rounds" in task.test


def test_the_slot_is_filled_and_the_body_passes_the_loops_own_gate():
    req = missing_progress("blind", BLIND)
    got = author_slot(req, BLIND)
    assert got.verified and got.body and not got.abstained
    assert any("counters" in n for n in got.notes)

    # and it really is a progress measure on the observed rounds
    ns: dict = {}
    exec(f"def _p({', '.join(req.params)}):\n    {got.body}", ns)
    for run in BLIND:
        vals = [ns["_p"](**{p: getattr(r, p) for p in req.params}) for r in run]
        assert all(b >= a for a, b in zip(vals, vals[1:]))
        rose = [vals[0] > 0] + [b > a for a, b in zip(vals, vals[1:])]
        assert rose == [r.moved for r in run]


def test_abstention_reports_the_coordinate_rather_than_a_bare_no():
    """Measured on `code_author` directly: two parameters of this shape are authored in 4 tries,
    three enumerate 1134 candidates and abstain, five report tried=0 -- the families do not open at
    all. So a refusal has to say how wide and how deep it searched, or the next lever is a guess."""
    impossible = [[Blind(1, 100, 90, True), Blind(2, 100, 95, False)]]   # unresolved goes UP
    req = missing_progress("impossible", impossible)
    if req is None:
        return                                     # no labels -> nothing to ask, already honest
    got = author_slot(req, impossible, max_params=2)
    if not got.verified:
        assert got.abstained and any("subsets" in n for n in got.notes)
