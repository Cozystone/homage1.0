# -*- coding: utf-8 -*-
"""D1: the slots are read off behaviour, so nothing here may depend on what a field is called.

Every fixture below deliberately spells its fields differently from the loops the schema was
derived on. If a test passes only because a field happens to be named `stalled`, the module is a
hand list wearing a schema's clothes.
"""
from __future__ import annotations

from dataclasses import dataclass

from packages.loop_schema import conforms, read_schema


@dataclass(frozen=True)
class Round:
    """A loop that spells its slots in its own vocabulary."""
    tick: int
    coverage: float
    junk: int
    moved: bool
    dry: bool


def _run(covs: list[float]) -> list[Round]:
    out, prev = [], 0.0
    for i, c in enumerate(covs, start=1):
        out.append(Round(tick=i, coverage=c, junk=7, moved=c > prev, dry=not (c > prev)))
        prev = c
    return out


def test_the_slots_are_found_without_being_named():
    got = read_schema("elsewhere", [_run([0.4, 0.7, 0.7])])
    assert got is not None
    assert got.progress == "coverage" and got.stalled == "dry" and got.improved == "moved"
    assert got.complete


def test_a_round_counter_is_a_clock_not_progress():
    """`tick` is monotone in every run and would be a perfect-looking, completely empty measure.
    What separates progress from a clock is that progress CAN FAIL TO RISE."""
    got = read_schema("clockwork", [_run([0.4, 0.7, 0.7]), _run([0.2, 0.5, 0.9, 0.9])])
    assert got.progress == "coverage"
    assert "tick" in got.candidates            # it was a candidate, and it was rejected


def test_a_measure_that_can_fall_is_not_progress():
    """Something that goes up and down is measuring a state, not accumulated progress, and putting
    a termination rule on it would stop the loop at a dip."""
    wobble = [Round(1, 0.4, 7, True, False), Round(2, 0.2, 7, False, True),
              Round(3, 0.6, 7, True, False)]
    got = read_schema("wobbly", [wobble])
    assert got is None or got.progress != "coverage"


def test_a_sequence_with_nothing_accumulating_is_not_a_loop():
    flat = [Round(1, 0.0, 7, False, True), Round(2, 0.0, 7, False, True)]
    assert read_schema("flat", [flat]) is None


def test_a_measure_must_hold_across_every_trace_not_just_one():
    """A measure that only works on one subject is a coincidence. `junk` is constant here and
    `coverage` rises in both, so only one of them can be the measure.

    Both runs end on a stalled round, as a real loop trace does -- a trace that rose on every round
    never exercised the stall slot, and the module refuses to name one on that evidence."""
    got = read_schema("two", [_run([0.3, 0.6, 0.6]), _run([0.1, 0.4, 0.8, 0.8])])
    assert got.progress == "coverage" and got.traces == 2 and got.rounds == 7


def test_a_bounded_rate_is_preferred_to_a_raw_count():
    """Both are monotone; only the rate is comparable between subjects, which is what makes it
    usable as a termination rule rather than just a number that went up."""
    @dataclass(frozen=True)
    class Both:
        placed: int
        ratio: float
        moved: bool
        dry: bool

    run = [Both(3, 0.3, True, False), Both(7, 0.7, True, False), Both(7, 0.7, False, True)]
    got = read_schema("both", [run])
    assert got.progress == "ratio" and "placed" in got.candidates


def test_conformance_requires_the_run_to_end_where_the_stall_was_detected():
    """That is what separates a loop from a fixed-count pass: a run that stalls in the middle and
    keeps going is spending rounds it already knows are worthless."""
    schema = read_schema("s", [_run([0.4, 0.7, 0.7])])
    assert conforms(_run([0.2, 0.5, 0.5]), schema).ok

    kept_going = _run([0.4, 0.4, 0.9, 0.9])            # stalls at round 2 and carries on
    assert not conforms(kept_going, schema).terminated_on_stall


def test_a_schema_derived_elsewhere_can_be_checked_on_a_held_out_run():
    schema = read_schema("held", [_run([0.4, 0.7, 0.7]), _run([0.1, 0.2, 0.9, 0.9])])
    got = conforms(_run([0.5, 0.8, 0.8]), schema)
    assert got.monotone and got.stall_agrees and got.terminated_on_stall and got.ok
