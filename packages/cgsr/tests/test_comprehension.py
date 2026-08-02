# -*- coding: utf-8 -*-
"""Unified perception front: ONE comprehension pass whose Understanding the pipeline consults."""
from packages.cgsr.cgsr.comprehension import perceive

_SPEC = ("You will interact with an unknown dynamical environment for 600 rounds. Return only: "
         '{ "action": [four numbers between -1 and 1] }. Your objective is to keep the condition '
         "signal within its safe interval while minimizing prediction error.")


def test_perceive_reads_focus_ask_and_format_contract():
    u = perceive(_SPEC)
    assert u.substantive and "environment" in u.focus and "prediction" in u.focus
    assert u.format_contract == "return_only"            # the output contract was READ, not missed
    assert "return only" in u.ask_gist.lower() or "objective" in u.ask_gist.lower()


def test_perceive_greeting_is_not_substantive():
    u = perceive("hello!")
    assert not u.substantive and u.engages(set())         # nothing to engage -> anyone may speak


def test_understanding_engages_rejects_stray_function_word_answer():
    u = perceive(_SPEC)
    # a possessive-determiner recital shares no content term with the spec's focus
    assert not u.engages({"possessive", "determiner", "house", "garage"})
    assert u.engages({"prediction", "signal"})            # a real engagement passes


def test_perceive_carries_discussion_state():
    ctx = [{"role": "system", "content": "Topic: Should AI be open-sourced?"},
           {"role": "user", "content": "Speaker A: Openness accelerates research."}]
    u = perceive("You are Speaker C. Your turn.", ctx)
    assert u.discussion is not None and "open-sourced" in u.discussion["subject"]
