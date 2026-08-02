# -*- coding: utf-8 -*-
"""G0: the family, the sign convention, and the control that decides whether a site counts."""
from __future__ import annotations

from packages.contrast_family.contrasts import (
    CONTROLS, NON_MEMBERS, REAL, admit, constant, cross_swap, inverted, probe, rank_gap,
    ratio_to_mean)


def test_every_contrast_agrees_on_which_way_is_up():
    """Higher = singles the target out more. Without one convention the comparison is meaningless,
    and `_bridging` is written the other way round so it is re-expressed, not re-designed."""
    standout, background = 9.0, [1.0, 1.0, 1.0]
    ordinary = 1.0
    for fn in REAL.values():
        assert fn(standout, background) > fn(ordinary, background), fn.__name__


def test_the_family_members_are_genuinely_different_computations():
    """If they agreed everywhere there would be one contrast, not three, and nothing to swap."""
    # one wild background member: the ratio is dragged down, the rank is not
    target, skewed = 5.0, [1.0, 1.0, 100.0]
    assert ratio_to_mean(target, skewed) < 1.0
    assert rank_gap(target, skewed) > 0.5


def test_a_site_that_cannot_fail_is_refused_admission():
    """A contrast may substitute because the contrasts are equivalent, or because the site's metric
    cannot tell them apart. Those look identical in a results table."""
    blind = admit("blind", lambda fn: 0.5)
    assert not blind.admitted and "cannot discriminate" in blind.reason

    sighted = admit("sighted", lambda fn: 1.0 if fn in REAL.values() else 0.0)
    assert sighted.admitted


def test_the_controls_are_deterministic():
    """A shuffle would need a seed; these need none, so the control is reproducible."""
    assert constant(3.0, [1.0, 2.0]) == constant(99.0, [7.0])
    assert inverted(3.0, [1.0, 2.0]) == inverted(3.0, [1.0, 2.0]) < 0


def test_instances_that_do_not_fit_the_interface_are_recorded_not_forced_in():
    """TWO of the four turned out not to implement it. `read_schema` takes two aligned sequences;
    `_bridging` normalises by the population size, which this interface does not supply. Widening
    the interface to admit them would be inventing a shape to make a member fit -- refused for the
    first, so refused for the second, even though the cost is that the family shrinks to two."""
    assert "loop_schema.read_schema" in NON_MEMBERS
    assert "edge_attribution._bridging" in NON_MEMBERS
    assert all(k.split(".")[-1] not in REAL for k in NON_MEMBERS)
    assert len(REAL) == 2


def test_an_unadmitted_site_contributes_no_swap_result(monkeypatch):
    got = probe({"blind": (lambda fn: 0.5, "ratio_to_mean")})
    assert got["sites_admitted"] == 0 and got["swaps"] == {}
    assert got["incumbent_beaten_somewhere"] is False


def test_a_genuine_cross_site_win_is_reported_when_there_is_one():
    """The gate must be able to read positive, or the negative means nothing."""
    def run(fn):
        return 1.0 if fn is rank_gap else 0.2
    got = probe({"rigged": (run, "ratio_to_mean")})
    assert got["incumbent_beaten_somewhere"] is True
    assert got["beats"][0]["beaten_by"] == "rank_gap"


def test_the_incumbent_is_marked_so_a_win_can_be_attributed():
    rows = cross_swap("s", lambda fn: 1.0, "rank_gap")
    assert [r.incumbent for r in rows if r.contrast == "rank_gap"] == [True]
