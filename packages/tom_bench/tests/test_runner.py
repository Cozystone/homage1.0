# -*- coding: utf-8 -*-
"""The runner must score deterministically over the REAL answer path, and a reality-control
failure must flag the run as ToM-invalid (guarding against reporting noise as social cognition)."""
from packages.tom_bench.generator import Question, Story, generate
from packages.tom_bench.runner import (REALITY_VALID_THRESHOLD, Report, classify,
                                       format_report, run)


def test_classify_outcomes():
    assert classify("crate", "crate", "tin") == "correct"
    assert classify("tin", "crate", "tin") == "egocentric"    # answered the TRUE loc on an FB q
    assert classify(None, "crate", "tin") == "abstain"
    assert classify("urn", "crate", "tin") == "other"
    assert classify("the crate", "crate", "tin") == "correct"  # article-insensitive


def test_run_is_deterministic():
    a, b = run(), run()
    for cat in a.cats:
        assert a.cats[cat].correct == b.cats[cat].correct
        assert a.cats[cat].abstain == b.cats[cat].abstain


def test_reality_control_passes_so_run_is_valid():
    rep = run()
    # the state tracker must actually follow ground truth, else all ToM numbers are meaningless
    assert rep.reality_accuracy >= REALITY_VALID_THRESHOLD
    assert rep.tom_valid is True


def test_memory_control_confirms_state_tracking():
    # a genuine trajectory query (not guessing): must be well above chance
    rep = run()
    assert rep.cats["memory"].accuracy >= REALITY_VALID_THRESHOLD


def test_first_order_false_belief_is_measured():
    # honest measurement: the category is populated and scored (whatever the score turns out to be)
    rep = run()
    assert rep.cats["first_order_fb"].n == 40


def test_reality_control_failure_flags_invalid_run():
    # a synthetic story the tracker cannot follow -> reality-control fails -> run flagged INVALID
    bad = Story(sid=0, kind="false_belief", model="copula",
                text="Zzz qqq wob.",
                ents={"p1": "A", "p2": "B", "obj": "widget", "c1": "alpha", "c2": "beta",
                      "setting": "room", "mover": "B"},
                questions=[Question("Where is the widget?", "beta", "reality", "beta")])
    rep = run([bad])
    assert rep.reality_accuracy < REALITY_VALID_THRESHOLD
    assert rep.tom_valid is False


def test_format_report_runs():
    assert "reality-control" in format_report(run())
