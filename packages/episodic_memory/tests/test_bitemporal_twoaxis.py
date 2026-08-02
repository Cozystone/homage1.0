# -*- coding: utf-8 -*-
"""True bitemporal (valid-time x recorded-time) tests. The legacy single-axis behaviour must stay
byte-for-byte identical (regression guard), and the new `as_known` two-axis query must let a
late-recorded correction NOT rewrite an earlier belief."""
from packages.episodic_memory.bitemporal import BitemporalMemory, Event


def _mk(events):
    m = BitemporalMemory()
    for e in events:
        m.ingest(e)
    return m


def test_late_correction_does_not_rewrite_earlier_belief():
    # rt=1 we recorded blue (valid from t=10); rt=2 we learned it was actually red since t=10.
    m = _mk([
        Event("f1", "assert", "x", "color", "blue", t=10, rt=1),
        Event("f2", "correct", "x", "color", "red", t=10, rt=2, retracts="f1"),
    ])
    assert m.as_known("x", "color", 15, rec_t=1) == ("blue", "f1")   # as we believed it at rt=1
    assert m.as_known("x", "color", 15, rec_t=2) == ("red", "f2")    # after the correction landed
    assert m.current("x", "color") == ("red", "f2")                  # now = latest knowledge


def test_recorded_cutoff_hides_not_yet_learned_facts():
    m = _mk([
        Event("f1", "assert", "x", "status", "open", t=5, rt=1),
        Event("f2", "assert", "x", "status", "closed", t=20, rt=3),  # learned later
    ])
    # at rec_t=1 we only knew the open fact; the closed(valid=20) fact was not yet recorded
    assert m.as_known("x", "status", None, rec_t=1) == ("open", "f1")
    assert m.as_known("x", "status", None, rec_t=3) == ("closed", "f2")


def test_late_correction_to_earlier_valid_time_over_later_assert():
    # blue@valid10(rt1), green@valid20(rt2), then a late correction red@valid10(rt3).
    m = _mk([
        Event("f1", "assert", "x", "c", "blue", t=10, rt=1),
        Event("f2", "assert", "x", "c", "green", t=20, rt=2),
        Event("f3", "correct", "x", "c", "red", t=10, rt=3, retracts="f1"),
    ])
    assert m.as_known("x", "c", 25, rec_t=3) == ("green", "f2")   # green is the latest valid-time
    assert m.as_known("x", "c", 15, rec_t=3) == ("red", "f3")     # corrected value at valid 15
    assert m.as_known("x", "c", 15, rec_t=1) == ("blue", "f1")    # before we knew the correction


def test_recorded_retraction_gap_is_time_travel_aware():
    m = _mk([
        Event("f1", "assert", "x", "p", "v", t=10, rt=1),
        Event("f2", "retract", "x", "p", "", t=30, rt=2),
    ])
    # we did not yet know about the retraction at rec_t=1
    assert m.as_known("x", "p", 40, rec_t=1) == ("v", "f1")
    assert m.as_known("x", "p", 40, rec_t=2) is None               # retraction gap, once learned


def test_legacy_single_axis_unchanged_by_rt_default():
    # events with no explicit rt: legacy as_of/current must behave exactly as the interval model,
    # ignoring recorded-time entirely (regression guard for the 452/452 validation).
    m = _mk([
        Event("f1", "assert", "s", "p", "a", t=1),
        Event("f2", "correct", "s", "p", "b", t=5, retracts="f1"),
        Event("f3", "retract", "s", "p", "", t=9),
    ])
    assert m.as_of("s", "p", 2) == ("a", "f1")
    assert m.as_of("s", "p", 6) == ("b", "f2")
    assert m.as_of("s", "p", 10) is None      # after the retraction gap
    assert m.current("s", "p") is None
