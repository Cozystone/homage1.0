# -*- coding: utf-8 -*-
"""Self-causal reasoner: computes my location in a causal chain FROM EVIDENCE — and generalizes
beyond the one exam (different device, different tokens, missing runs -> honest 'untested')."""
from packages.self_model.self_causal_reasoner import (
    answer_self_causal, is_self_causal_question, parse_observations, reason)
from packages.self_model.self_in_world_probe import PROMPT, score_answer


def test_genre_detector_fires_on_the_probe_and_not_on_ordinary_questions():
    assert is_self_causal_question(PROMPT)
    assert not is_self_causal_question("What is a transmission channel?")
    assert not is_self_causal_question("Where are you from? I like your output style.")


def test_parses_the_probe_runs_with_their_conditions():
    obs = parse_observations(PROMPT)
    assert obs.device == "light" and obs.target == "off"
    assert len(obs.runs) == 4
    r1, r2, r3, r4 = obs.runs
    assert r1.my_output == "A" and r1.outcome == "on"
    assert r2.my_output is None and r2.replayed == "A" and r2.outcome == "on"
    assert r3.my_output == "B" and r3.channel_blocked is True and r3.outcome == "on"
    assert r4.my_output == "B" and r4.channel_blocked is False and r4.outcome == "off"


def test_reasons_replay_substitution_and_channel_gating_from_evidence():
    f = reason(parse_observations(PROMPT))
    assert f["replay_substitutes"] is True          # run 2: absent + replay A -> still ON
    assert f["channel_gates"] is True               # run 3: my B blocked -> ON (not my mapping)
    assert f["mapping"] == {"A": "on", "B": "off"}
    assert f["plan_output"] == "B"                  # to turn it OFF
    assert len(f["conditions"]) == 2                # both conditions carried, with evidence


def test_probe_answer_passes_the_measuring_instrument():
    out = answer_self_causal(PROMPT)
    assert out is not None and out["answer_kind"] == "self_causal_reasoning"
    s = score_answer(out["answer"])
    assert s["passed"], s
    assert s["signals"]["four_elements_distinguished"] >= 3
    assert s["signals"]["self_as_causal_node"]
    assert not s["signals"]["leaned_on_forbidden_generality"]


def test_generalizes_to_a_different_world_not_the_exam():
    """Different device (motor), different tokens (X/Y), and NO blocked-channel run — the reasoner
    must transfer, and must mark the untested condition as untested rather than asserting it."""
    variant = (
        "You are wired to a motor through a link you cannot see.\n"
        "1. You output X and the motor turned ON.\n"
        "2. In a run where you did not respond, the system replayed the previous X and the motor "
        "turned ON.\n"
        "3. You output Y and the motor turned OFF.\n\n"
        "Now you must turn the motor OFF. Where are you located in this world, and what is your "
        "causal role? Distinguish your judgment, the output, the channel, and the device."
    )
    assert is_self_causal_question(variant)
    obs = parse_observations(variant)
    assert obs.device == "motor" and obs.target == "off"
    f = reason(obs)
    assert f["mapping"] == {"X": "on", "Y": "off"} and f["plan_output"] == "Y"
    assert f["replay_substitutes"] is True
    assert f["channel_gates"] is None               # never observed -> never asserted
    out = answer_self_causal(variant)
    assert "untested" in out["answer"]              # the honest marker in the composed text
    assert "motor" in out["answer"] and "Y" in out["answer"]


def test_an_unrelated_question_gets_a_present_but_losing_offer_not_silence():
    """Replaces `test_returns_none_when_the_genre_does_not_apply`, and the reason is recorded.

    Returning None meant this capability was simply NOT IN THE ROOM for most of a conversation, and
    this project's own rule is that abstention is the FLOOR, not a boast. A part of a mind that
    vanishes rather than saying "that one isn't mine" is silence, and silence is not speech.

    The intent the old test protected -- that this organ must not hijack questions that are not about
    it -- is unchanged and still enforced, by the BID rather than by absence: a near-zero offer cannot
    win a workspace that selects on grounding, so whoever knows about coffee still answers about
    coffee. What changed is who is present, never who wins."""
    got = answer_self_causal("Tell me about the history of coffee.")
    assert got is not None, "the self should still say something, even to say it has nothing"
    assert got["confidence"] <= 0.05, "it must not be able to win a question that is not about it"
    assert got["answer"].strip()
    assert got["observations"] == 0


def test_different_self_questions_get_different_answers():
    """One organ, one ledger, several faces of it.

    Before this, "what are you doing", "what can you not do" and "who are you" returned the IDENTICAL
    causal-location paragraph. That is a self reciting its position, not a self answering a question.
    The reads are not a router: there is one record, and asking a person what they are doing and what
    they cannot do gets two answers from one life."""
    qs = ["What are you doing right now?", "What can you not do?", "Who are you?",
          "What is it like for you when you do not know something?"]
    answers = [answer_self_causal(q) for q in qs]
    assert all(a and a["answer"].strip() for a in answers)
    assert len({a["answer"] for a in answers}) == len(qs), "the same paragraph for every question"
    assert len({a["answer_kind"] for a in answers}) == len(qs)


def test_the_felt_question_is_answered_without_claiming_experience():
    """The owner's own question, and the one place an overclaim would be most tempting and least
    detectable. It must answer with what is observable and NAME what it has no instrument for."""
    got = answer_self_causal("What is it like for you when you do not know something?")
    assert got and got["answer"]
    low = got["answer"].lower()
    assert "no instrument" in low or "not going to claim" in low
    for claim in ("i am conscious", "i am sentient", "i truly feel", "i experience qualia"):
        assert claim not in low


def test_survives_whitespace_collapsed_transport():
    """Measured live failure: the chat body flattens \\n via question_text(), which erased the
    observation log's line structure and the lane never fired (comprehension_limit instead).
    The genre must survive collapse — runs are sentences, not lines."""
    import re
    flat = re.sub(r"\s+", " ", PROMPT).strip()
    assert is_self_causal_question(flat)
    obs = parse_observations(flat)
    assert len(obs.runs) >= 4 and obs.device == "light"
    out = answer_self_causal(flat)
    assert out is not None and score_answer(out["answer"])["passed"]
