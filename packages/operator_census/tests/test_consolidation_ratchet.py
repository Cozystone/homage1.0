# -*- coding: utf-8 -*-
"""M0a — duplication may only go down. The ratchet that makes consolidation irreversible.

    pytest packages/operator_census/tests/test_consolidation_ratchet.py

WHY A RATCHET AND NOT A REPORT. `operator_census` has been able to measure this all along -- 52 recurring
computations in 261 copies across 81 of 143 organs, one shape re-implemented twelve times -- and the number
kept growing anyway, because nothing was watching. On 2026-07-30 alone two more copies of the same
discriminator were found (`SpriteTracker.motion_split`'s 1-D k-means and the text layer's widest-jump), and
a third keyword-based census was written by hand while this organ sat unwired. A measurement nobody is
accountable to is not a control.

So the count is pinned to a recorded baseline and this test fails when it rises. Consolidation becomes the
only direction the codebase can move in, which is what the roadmap's M0 needs before M1 builds a SHARED
gate -- into a codebase with 261 duplicate copies, a shared gate becomes copy 262.

WHEN YOU IMPROVE IT, LOWER THE BASELINE BY HAND. The test deliberately does not rewrite
packages/operator_census/consolidation_baseline.json for you: a self-updating ratchet ratchets nothing, and the
whole failure mode here is a number drifting while everyone assumes someone is watching it.

WHAT THIS CANNOT CATCH, stated so it is not mistaken for more than it is: removing one duplicated shape
while introducing another keeps the count flat and passes. The per-organ table is asserted too, so a
reviewer at least sees WHERE the mass moved, but the count alone is not proof that consolidation happened.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.operator_census import duplication_report, organ_duplication

BASELINE = Path(__file__).resolve().parents[1] / "consolidation_baseline.json"
ROOT = Path(".")


def _n(v):
    return v if isinstance(v, int) else len(v)


@pytest.fixture(scope="module")
def measured():
    return duplication_report(ROOT, min_spread=3)


@pytest.fixture(scope="module")
def baseline():
    if not BASELINE.exists():
        pytest.skip(f"no baseline recorded at {BASELINE}")
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def test_duplicate_copies_never_rise(measured, baseline):
    now, was = _n(measured["duplicate_copies"]), baseline["duplicate_copies"]
    assert now <= was, (
        f"duplicated copies rose {was} -> {now}. Some computation was hand-written again instead of "
        f"being imported. Find it with `python -c \"from pathlib import Path; "
        f"from packages.operator_census import organ_duplication; print(organ_duplication(Path('.')))\"`"
    )


def test_recurring_shapes_never_rise(measured, baseline):
    now, was = _n(measured["recurring_shapes"]), baseline["recurring_shapes"]
    assert now <= was, (
        f"distinct re-implemented computations rose {was} -> {now}. A NEW operation is now duplicated "
        f"across three or more organs, which is the pathology this ratchet exists to stop."
    )


def test_spread_never_widens(measured, baseline):
    now, was = _n(measured["widest"]), baseline["widest"]
    assert now <= was, (
        f"the most-duplicated single computation went from {was} copies to {now}."
    )


def test_no_organ_accumulates_more_duplicates_than_before(baseline):
    """Per organ, so that a flat total cannot hide mass moving into a heavily-imported package."""
    was = baseline.get("organ_duplication", {})
    if not was:
        pytest.skip("baseline carries no per-organ breakdown")
    now = dict(organ_duplication(ROOT, min_spread=3))
    worse = {k: (was.get(k, 0), v) for k, v in now.items() if v > was.get(k, 0)}
    assert not worse, (
        f"these organs now hold more re-implemented shapes than the baseline: {worse}. "
        f"graph_scale matters most here -- 141 modules import it, so a duplicate placed there "
        f"travels further than one placed anywhere else."
    )


def test_the_baseline_is_not_silently_stale(measured, baseline):
    """A ratchet left far above the real number stops being a ratchet. Loud, but not a failure."""
    now, was = _n(measured["duplicate_copies"]), baseline["duplicate_copies"]
    if now < was:
        print(f"\nconsolidation progressed: {was} -> {now} duplicate copies. "
              f"Lower the baseline in {BASELINE} so the gain cannot be given back.")
