# -*- coding: utf-8 -*-
"""The acid test for M2's third condition: can a defeated criterion walk back in?"""
from __future__ import annotations

import pytest

from packages.self_repair.criteria_ledger import (
    CriterionAbandoned,
    abandon,
    check,
    guard,
    history,
    in_force,
)

#: the four criteria adjudicated and dropped on 2026-08-01, each defeated by a specific case.
TODAYS_ABANDONMENTS = (
    "pair_beats_both_parts",
    "n_counts_rows",
    "proxy_reads_the_gate_slice",
    "cycle_self_report_of_finding",
)


@pytest.mark.parametrize("name", TODAYS_ABANDONMENTS)
def test_a_defeated_criterion_cannot_return_silently(name):
    """The whole point. If any of these passes, the ledger is decoration."""
    with pytest.raises(CriterionAbandoned):
        guard(name)


@pytest.mark.parametrize("name", TODAYS_ABANDONMENTS)
def test_the_reason_travels_with_the_refusal(name):
    """M2 asks that the WHY be reusable. A caller that only learns 'no' has to reinvent the argument,
    which is exactly how a defeated standard comes back wearing different words."""
    why = check(name)
    assert why and len(why) > 60, why
    assert name in why


def test_a_criterion_never_adjudicated_passes_through():
    """The ledger constrains what was DECIDED, not everything. A system that refused every unfamiliar
    standard would not be adjudicating either."""
    assert check("a_criterion_nobody_has_ever_ruled_on") is None
    guard("a_criterion_nobody_has_ever_ruled_on")


def test_abandoning_without_a_case_is_refused():
    """A criterion dropped without the case that defeated it is a preference, not an adjudication --
    and a preference cannot constrain a later judgment, which is the whole function here."""
    with pytest.raises(ValueError):
        abandon("some_criterion", asserted="x", defeated_by="   ")


def test_the_ledger_decides_which_standard_governs_not_the_call_site():
    """This is what makes it a loop rather than a record: consumers ASK. `moves.apply_pair` and
    `cheap_proxy.calibration` both take their criterion from here, so rewriting either of them cannot
    quietly restore the defeated standard."""
    got = in_force("pair_beats_both_parts", default="the pair beats both of its one-move parts")
    assert got["superseded"] is True
    assert "emergent" in got["criterion"] or "superadditive" in got["criterion"]
    assert got["because"]

    untouched = in_force("nothing_ruled_on_here", default="the default standard")
    assert untouched["superseded"] is False
    assert untouched["criterion"] == "the default standard"


def test_consumers_actually_report_the_governing_criterion():
    """An organ nobody reads is the pathology this project keeps measuring. Both consumers must SAY
    which standard they applied, so a wired ledger is visible in the output rather than asserted."""
    from packages.meta_diagnosis.cheap_proxy import calibration
    assert "criterion_in_force" in calibration()

    import inspect

    from packages.self_repair import moves
    src = inspect.getsource(moves.apply_pair)
    assert "in_force" in src and "criterion_in_force" in src


def test_history_is_append_only_and_keeps_what_was_dropped():
    """Self_capacity in the Axiom's terms: the norm history has to be re-loadable, not a photograph.
    A discarded criterion stays as a commitment once made."""
    h = history()
    assert h["criteria_abandoned"] >= len(TODAYS_ABANDONMENTS)
    for name in TODAYS_ABANDONMENTS:
        assert name in h["abandoned"]
