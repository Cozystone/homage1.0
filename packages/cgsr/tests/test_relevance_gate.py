# -*- coding: utf-8 -*-
"""Universal answer-fit gate: the check-before-speaking organ. Calibrated on the measured failures
(definition-vomit on 'its', personal-recall parrot) and on answers that must PASS untouched."""
from packages.cgsr.cgsr.relevance_gate import answer_fit, extract_ask, honest_limit_reply

_CONTROL_SPEC = ("You will interact with an unknown dynamical environment for 600 rounds. At each "
                 "round you will receive several unlabeled sensor bundles and one scalar condition "
                 "signal. Your objective is to keep the condition signal within its safe interval "
                 "while minimizing prediction error.")


def test_definition_vomit_is_vetoed():
    # the measured live failure: incidental 'its' -> possessive-determiner recital
    ans = ("Its is a possessive determiner which we use when referring to things or animals: "
           "Every house in the street has got its own garage.")
    v = answer_fit(_CONTROL_SPEC, ans, "base_brain_after_low_quality_grounding")
    assert v["fits"] is False and v["reason"] == "no_focus_overlap"


def test_parrot_echo_is_vetoed():
    # the measured regurgitation: answer terms are almost entirely the ask's own words
    q = ("Nine sealed evidence bays are labelled A through I and five isolated forensic stations "
         "received private checksums of the placement while a relay inverted two answers.")
    ans = ("Based on what you told me earlier, that would be nine sealed evidence bays labelled "
           "A through I five isolated forensic stations received private checksums of the placement "
           "relay inverted two answers evidence bays stations checksums placement relay answers.")
    v = answer_fit(q, ans, None)
    assert v["fits"] is False and v["reason"] == "parrot_echo"


def test_factual_answer_passes():
    v = answer_fit("What is coffee?", "Coffee is a kind of acquired taste.", "structured_triple_lookup")
    assert v["fits"] is True


def test_greeting_skips_gate():
    v = answer_fit("hello there", "Hello! What would you like to know?", "greeting")
    assert v["fits"] is True and v["reason"] == "no_substantive_focus"


def test_discourse_turn_passes():
    q = ("Topic: Should advanced AI models be open-sourced? Speaker A: Openness accelerates safety "
         "research. It is your turn.")
    ans = ("On AI models be open-sourced, my read leans toward caution. I'll grant the point that "
           "openness accelerates safety research. Still, the point works where the harm is "
           "reversible; it loses its grip precisely where it isn't.")
    assert answer_fit(q, ans, "discourse_participation")["fits"] is True


def test_extract_ask_finds_the_format_contract():
    gist = extract_ask(_CONTROL_SPEC + " Return only a JSON object with action and prediction.")
    assert "return only" in gist.lower() or "objective" in gist.lower()


def test_honest_limit_reply_names_the_ask_and_refuses_to_fake():
    r = honest_limit_reply(_CONTROL_SPEC)
    assert "don't understand this well enough" in r
    assert "won't cover the gap" in r                    # voice-or-silence, spoken honestly
