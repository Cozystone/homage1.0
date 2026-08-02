# -*- coding: utf-8 -*-
"""Entity-like gate contract for the structured profile lane.

The wrong-QID pollution (2026-07-13: → '39.8282,-98.5795', → 
'n ') is prevented at the SOURCE by _entity_like: a profile may only be stored
for an individual place/person/org/work, never for a class/concept. These cases are the
live-calibrated P31/P279 shapes of the exact entities that were polluted or must keep
working — offline, no network."""
from packages.graph_scale.structured_profile import _entity_like


def _claims(p31_ids=(), p279=False):
    c = {"P31": [{"mainsnak": {"datavalue": {"value": {"id": q}}}} for q in p31_ids]}
    if p279:
        c["P279"] = [{"mainsnak": {"datavalue": {"value": {"id": "Q0"}}}}]
    return c


def test_class_concepts_denied_by_p279():

    ok, why = _entity_like(_claims(p31_ids=["Q11862829"], p279=True))
    assert not ok and "P279" in why


def test_phenomena_and_numbers_denied_by_default():

    # P279 — the DEFAULT-DENY on unknown P31 classes is what stops them
    assert not _entity_like(_claims(p31_ids=["Q104934", "Q1293220"]))[0]
    assert not _entity_like(_claims(p31_ids=["Q10338607", "Q1081248"]))[0]


def test_no_claims_denied():
    assert not _entity_like(_claims())[0]
    assert not _entity_like({})[0]


def test_entities_pass():
    assert _entity_like(_claims(p31_ids=["Q3624078", "Q6256"]))[0]
    assert _entity_like(_claims(p31_ids=["Q515", "Q174844"]))[0]
    assert _entity_like(_claims(p31_ids=["Q5"]))[0]
    assert _entity_like(_claims(p31_ids=["Q4830453"]))[0]
    assert _entity_like(_claims(p31_ids=["Q212057"]))[0]


def test_mixed_unknown_plus_entity_passes():

    assert _entity_like(_claims(p31_ids=["Q99999999", "Q515"]))[0]
