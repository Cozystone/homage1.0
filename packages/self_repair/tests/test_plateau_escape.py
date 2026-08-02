# -*- coding: utf-8 -*-
"""Plateau escape — naming WHICH dimension is saturated, from the judge's own refusal reasons.

Automates a move made by hand three times in one day: read why the proposals were refused, and notice
which dimension every refusal points at. The classification is not invented here; `judge()` refuses on
four named conditions and stamps which one fired into its verdict, so this reads the gate's structure
rather than describing an idea of it.
"""
from __future__ import annotations

from packages.self_repair.plateau_escape import _HEALTHY, _NEXT_KIND, classify, diagnose


def test_each_refusal_reason_maps_to_a_dimension():
    """Verbatim strings the gate emits, not paraphrases."""
    assert classify("... — REFUSED: the instances disagree about which relation they are") \
        == "relation_vocabulary"
    assert classify("... — REFUSED: margin under 15%; the objects fit several relations") \
        == "discriminator"
    assert classify("... — REFUSED: below 35% familiarity") == "profile_coverage"
    assert classify("... — REFUSED: these objects fit 'made_of' better than 'used_for'") \
        == "proposal_targeting"


def test_a_working_cross_product_is_not_a_blockage():
    """Most refusals are the cue being offered to every relation and redirected to the right one.
    Counting those as saturation would report a plateau every run and mean nothing."""
    assert "proposal_targeting" in _HEALTHY


def test_no_diagnosis_while_progress_continues():
    """A prescription offered while things are still being found is advice nobody asked for, and it
    trains its reader to ignore the one that matters."""
    d = diagnose()
    if not d.get("plateaued"):
        assert d["saturated"] is None


def test_every_dimension_prescribes_a_requirement_not_a_design():
    """The escape says what a new kind of proposal must DO. Writing the design is the part that still
    needs a person, and pretending otherwise is the overclaim this module has to avoid."""
    for name, text in _NEXT_KIND.items():
        assert text and len(text) > 40, name


def test_it_distinguishes_a_missing_organ_from_an_ignored_one():
    """The first run of this diagnosis prescribed 'build relation discovery' -- which had been built
    an hour earlier and had already found HasA. The blocker was not a missing organ but an organ whose
    output nobody acted on, and a diagnosis that cannot tell those apart sends you to rebuild what you
    have."""
    d = diagnose()
    if d.get("plateaued") and d.get("saturated") == "relation_vocabulary":
        assert "capability_exists" in d
        if d["capability_exists"]:
            assert "do not rebuild" in d["next_kind"]


def test_the_limit_is_stated_in_the_result_itself():
    """It names the direction; it does not build the organ. A reader should not have to open the
    source to learn that."""
    d = diagnose()
    if d.get("plateaued"):
        assert "does not build" in d["limit"]
