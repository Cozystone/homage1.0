# -*- coding: utf-8 -*-
"""Hypothesis elimination (G4): deduce the answer by ruling candidates out — with proof — and
honestly report under-determined / inconsistent rather than guessing."""
from packages.situation_model.hypothesis import (
    Constraint, eliminate, from_text, must_have_property, must_not_have_property, not_candidate)


def test_single_survivor_is_named_with_its_proof():
    v = eliminate(["Ada", "Ben", "Cara"],
                  [not_candidate("Ada"), not_candidate("Ben")])
    assert v.determined and v.survivors == ["Cara"]
    assert "must be Cara" in v.reply and "Ada" in v.reply and "Ben" in v.reply


def test_property_constraints_rule_in_and_out():
    # only those with access, and not those with an alibi, survive
    v = eliminate(["Ada", "Ben", "Cara"], [
        must_have_property("access", {"Ada", "Cara"}),      # Ben has no access -> out
        must_not_have_property("alibi", {"Ada"}),           # Ada has an alibi -> out
    ])
    assert v.survivors == ["Cara"] and v.determined


def test_under_determined_is_reported_not_guessed():
    v = eliminate(["Ada", "Ben", "Cara"], [not_candidate("Ada")])
    assert not v.determined and set(v.survivors) == {"Ben", "Cara"}
    assert "Under-determined" in v.reply and "won't guess" in v.reply


def test_inconsistent_constraints_yield_no_culprit():
    v = eliminate(["Ada", "Ben"], [not_candidate("Ada"), not_candidate("Ben")])
    assert v.survivors == [] and "won't name one" in v.reply


def test_every_elimination_carries_its_reason():
    v = eliminate(["Ada", "Ben", "Cara"], [not_candidate("Ada"), not_candidate("Ben")])
    reasons = {e.candidate: e.by for e in v.eliminated}
    assert reasons["Ada"] and reasons["Ben"]                 # proof of exclusion, not a bare verdict


def test_extracts_and_solves_a_black_relay_shaped_passage():
    text = ("Three suspects are Mara, Idris, and Petra. Mara was cleared by the night log. "
            "Idris has an alibi. Petra remained on site the whole evening.")
    v = from_text(text)
    assert v is not None and v.determined and v.survivors == ["Petra"]


def test_from_text_returns_none_off_genre():
    assert from_text("The catalyst lowered the barrier and heat was released.") is None
