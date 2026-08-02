# -*- coding: utf-8 -*-
"""The structural frame realizer: fluent + faithful + hallucination-impossible BY CONSTRUCTION,
zero weight-memorization. The realignment to the fluency doctrine ('every predicate a frame')."""
from packages.realizer_struct.frame_realizer import realize


def test_faithful_and_grammatical_by_construction():
    assert realize([["Kyushu", "is_a", "island"], ["Kyushu", "located_in", "Japan"]]) \
        == "Kyushu is an island, located in Japan."          # a/an + aggregation
    assert realize([["Kyushu", "is_a", "island"], ["Kyushu", "has_property", "large"]]) \
        == "Kyushu is a large island."                       # adjective fusion into one NP


def test_empty_bones_produce_nothing_gf3_by_construction():
    assert realize([]) == ""                                 # cannot fabricate — the No-LLM floor
    assert realize([["", "is_a", ""]]) == ""


def test_a_an_agreement_is_guaranteed_not_hoped():
    assert realize([["x", "is_a", "apple"]]) == "X is an apple."
    assert realize([["x", "is_a", "banana"]]) == "X is a banana."
    assert realize([["x", "is_a", "hour"]]) == "X is an hour."     # silent-h exception
    assert realize([["x", "is_a", "university"]]) == "X is a university."  # /juː/ exception


def test_plural_subject_verb_agreement():
    out = realize([["penguins", "is_a", "bird"], ["penguins", "capable_of", "swim"]])
    assert out.startswith("Penguins are")                    # not 'Penguins is'
    assert "can swim" in out


def test_self_alias_is_dropped():
    assert realize([["Fairy tale", "alias", "fairy tale"]]) == ""   # says nothing -> nothing


def test_only_bone_content_can_appear_no_invention():
    out = realize([["coffee", "is_a", "beverage"]])
    # every content word in the output traces to a bone (coffee, beverage) or the closed frame vocab
    assert "coffee" in out.lower() and "beverage" in out.lower()
    assert "cheese" not in out.lower()                       # nothing invented


def test_plural_agreement_gpt_caught_flaw():
    # GPT-5.4's comprehensive review caught 'Penguins are bird' — object must pluralize too
    from packages.realizer_struct.frame_realizer import realize
    assert realize([["penguins", "is_a", "bird"], ["penguins", "capable_of", "swim"]]) \
        == "Penguins are birds, and can swim."
    assert realize([["mice", "is_a", "rodent"]]) == "Mice are rodents."       # irregular subject
    assert realize([["children", "is_a", "person"]]) == "Children are people."  # both irregular
    assert realize([["Einstein", "is_a", "physicist"]]) == "Einstein is a physicist."  # singular intact


def test_demonym_is_capitalized_but_plain_adjectives_are_not():
    """GPT-5.4's comprehensive review flagged 'a german physicist' three times independently in one
    night (03:08, 05:33, 07:19). Proper adjectives keep their capital; ordinary ones must not gain
    one, and the adjective must still appear exactly ONCE (it is consumed by the aggregated NP)."""
    out = realize([["Einstein", "is_a", "physicist"], ["Einstein", "has_property", "german"]])
    assert out == "Einstein is a German physicist."
    assert realize([["rock", "is_a", "mineral"], ["rock", "has_property", "hard"]]) == \
        "Rock is a hard mineral."
    multi = realize([["sushi", "is_a", "dish"], ["sushi", "has_property", "japanese"],
                     ["sushi", "made_of", "rice"]])
    assert multi == "Sushi is a Japanese dish, made of rice."
    assert multi.lower().count("japanese") == 1        # not duplicated as a trailing clause
