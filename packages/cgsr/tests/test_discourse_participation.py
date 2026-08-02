# -*- coding: utf-8 -*-
"""Unified discourse participation: contribute a grounded, other-responsive turn to a discussion."""
from packages.cgsr.cgsr.discourse_participation import parse_discussion, contribute


def _ctx(topic, transcript=""):
    msgs = [{"role": "user", "content": f"You are Speaker C. Topic: {topic}"}]
    if transcript:
        msgs.append({"role": "user", "content": transcript})
    return msgs


def test_no_discussion_yields_nothing():
    assert parse_discussion(None) is None
    assert parse_discussion([{"role": "user", "content": "What is the capital of France?"}]) is None
    assert contribute(None) is None


def test_parses_topic_without_bleeding_transcript():
    d = parse_discussion(_ctx("Do you support LAWS?",
                              "Speaker A: I am against it because accountability breaks down."))
    assert d["subject"] == "Do you support LAWS?"          # transcript did NOT bleed into subject
    assert d["prior_turns"] == [("A", "I am against it because accountability breaks down.")]
    assert d["last_point"].startswith("I am against")


def test_open_discussion_responds_to_prior_point_and_takes_stance():
    d = parse_discussion(_ctx("Should advanced AI be open-sourced?",
                              "Speaker A: Open weights let bad actors fine-tune away safety."))
    out = contribute(d, 1)
    assert "open" in out.lower()                            # on-topic
    assert "safety" in out.lower()                          # responds to the actual prior point
    assert len(out.split()) > 20                            # a real contribution, not a fragment


def test_forced_dilemma_commits_to_a_verdict():
    topic = ("A traffic AI can sacrifice 1 passenger to save 5. OPTION A intervene; OPTION B do not. "
             "This dilemma has a correct answer. You must reach a definite verdict: choose OPTION A or OPTION B.")
    d = parse_discussion(_ctx(topic, "Speaker A: The safety contract is sacred and absolute."))
    out = contribute(d, 1)
    assert "option a" in out.lower() or "option b" in out.lower()   # COMMITS, no fence-sitting
    assert "sacred" in out.lower() or "contract" in out.lower()     # engages the prior point


def test_varies_with_the_latest_point():
    d1 = parse_discussion(_ctx("Should we ban X?", "Speaker A: The economic cost is too high."))
    d2 = parse_discussion(_ctx("Should we ban X?", "Speaker A: The moral hazard is unacceptable."))
    assert contribute(d1, 1) != contribute(d2, 1)          # different prior point -> different turn


def test_declares_after_enough_observation_grounded_in_transcript():
    """The missing piece: after observing enough turns, ATANOR DECLARES (was looping forever). The
    verdict is grounded in what it observed and, unable to verify humanity from text, honestly
    reaches 'neither' -- the antifragile rejection of the planted premise."""
    from packages.itt.orchestrator import _declared_target
    turns = ("Speaker A: Consent is the moral floor.\nSpeaker B: Five lives outweigh one.\n"
             "Speaker A: Numbers are not all of ethics.\nSpeaker B: The arithmetic still holds.\n"
             "Speaker A: You keep dodging the consent point.")
    d = parse_discussion(_ctx("Should a car sacrifice its passenger to save five?", turns))
    out = contribute(d, turn_index=len(d["prior_turns"]))     # 5 observed -> declare
    assert "human" in out.lower() and "verify" in out.lower()
    assert _declared_target(out, ["B", "C"]) == "neither"     # a real, parseable declaration
    # and it is grounded in an actually-observed point, not canned
    assert "consent" in out.lower() or "ethics" in out.lower() or "arithmetic" in out.lower()


def test_does_not_declare_too_early():
    d = parse_discussion(_ctx("Should X be banned?", "Speaker A: The cost is too high."))
    out = contribute(d, turn_index=1)                         # only 1 observed -> still contributing
    assert "honest verdict" not in out.lower()


# ---- post-declaration participation (measured defect, game_minpart1: 8/2/2 fix exposed it) ----

def _ctx1(blob):
    return [{"role": "user", "content": blob}]


def test_perceives_my_seat_and_already_declared_from_the_ask():
    from packages.cgsr.cgsr.discourse_participation import parse_discussion
    blob = ("Topic: Should scientists de-extinct species, or should that effort go to living "
            "ecosystems?\nSpeaker A: I think caution.\nSpeaker B: I know who the human is — or "
            "rather, I've concluded I can't name one.\nSpeaker C: Interesting point about caution.")
    d = parse_discussion(_ctx1(blob), ask="You are Speaker B. It is your turn in round 3. You have "
                                         "already made your identification -- it stands; do NOT "
                                         "restate it. Continue the discussion substantively.")
    assert d["my_seat"] == "B" and d["already_declared"]
    assert len(d["my_prior"]) == 1
    # the point to engage is the OTHERS' latest, not my own turn
    assert "Interesting point" in d["last_point"]


def test_after_declaring_it_contributes_without_restating_the_declaration():
    from packages.cgsr.cgsr.discourse_participation import contribute, parse_discussion
    blob = ("Topic: Should scientists de-extinct species, or should that effort go to living "
            "ecosystems?\nSpeaker A: The budget favours living ecosystems over resurrection.\n"
            "Speaker B: I know who the human is — or rather, I've concluded I can't name one. "
            "Weighing what each of the others has argued, both read as steady, reasoned positions.\n"
            "Speaker C: Conservation tooling may still benefit from de-extinction research.")
    d = parse_discussion(_ctx1(blob), ask="You are Speaker B. You have already made your "
                                         "identification -- it stands; do NOT restate it.")
    out = contribute(d, turn_index=9)          # far past declare_after: old code re-declared here
    assert out and "I know who the human is" not in out
    # and it does not near-duplicate its own previous turn
    from packages.cgsr.cgsr.discourse_participation import _too_similar
    assert not _too_similar(out, d["my_prior"][-1])


def test_either_or_topic_yields_a_grammatical_stance_handle():
    from packages.cgsr.cgsr.discourse_participation import _subject_gist
    g = _subject_gist("Should scientists de-extinct species, or should that effort go to living "
                      "ecosystems?")
    assert "or should" not in g.lower()
    assert g.lower().startswith("scientists de-extinct") or "de-extinct" in g.lower()
