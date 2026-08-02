# -*- coding: utf-8 -*-
"""The ONE UTC timeline: events on a single world-standard-time axis; a transcript becomes
first-class utterance nodes (Gemini's fix)."""
import re
from packages.temporal_reasoning.unified_timeline import Timeline, utc_now, Event


def test_utc_now_is_world_standard_time():
    s = utc_now()
    assert s.endswith("Z") and re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", s)


def test_records_across_kinds_on_one_axis_with_monotonic_seq():
    tl = Timeline()
    tl.record("perception", "a person opened the fridge", who="camera")
    tl.record("thought", "they may be about to drink", who="atanor")
    tl.record("action", "answered the question", who="atanor")
    seqs = [e.seq for e in tl.all()]
    assert seqs == [0, 1, 2]                       # total order even at same wall-clock ms
    assert {e.kind for e in tl.all()} == {"perception", "thought", "action"}


def test_transcript_becomes_utterance_events():
    tl = Timeline()
    evs = tl.ingest_transcript(
        "Speaker A: I am against LAWS because accountability breaks down.\n"
        "Speaker B: I also lean against; efficiency does not justify the risk.")
    assert len(evs) == 2 and all(e.kind == "utterance" for e in evs)
    assert evs[0].who == "speaker_A" and "accountability" in evs[0].content
    assert evs[1].who == "speaker_B"
    assert [e.who for e in tl.utterances()] == ["speaker_A", "speaker_B"]   # order preserved


def test_reject_unknown_kind():
    tl = Timeline()
    try:
        tl.record("banana", "x")
        assert False, "should reject unknown kind"
    except ValueError:
        pass


def test_since_and_latest_walk_one_axis():
    tl = Timeline()
    a = tl.record("fact", "one")
    tl.record("fact", "two")
    assert tl.latest("fact").content == "two"
    assert len(tl.since(a.t_utc)) >= 1


def test_revise_corrects_the_past_in_place_but_keeps_the_original():
    # owner: the timeline is "adjustable back and forth" -- re-examination yields the corrected past,
    # yet the original stays auditable (never a silent overwrite).
    tl = Timeline()
    a = tl.record("fact", "the meeting is on Tuesday")
    tl.record("fact", "unrelated")
    tl.revise(a.seq, "the meeting is on Wednesday", reason="organiser moved it")
    view = tl.current_view()
    contents = [e.content for e in view]
    assert "the meeting is on Wednesday" in contents      # corrected version shows in place
    assert "the meeting is on Tuesday" not in contents     # superseded original is gone from the view
    assert any(e.content == "the meeting is on Tuesday" for e in tl.all())   # but still on the record
    assert len(view) == 2                                  # revision-marker does not add a phantom row


def test_retract_withdraws_a_claim():
    tl = Timeline()
    a = tl.record("fact", "X is true")
    tl.retract(a.seq, reason="found counter-evidence")
    assert all(e.content != "X is true" for e in tl.current_view())   # withdrawn from what stands
    assert any(e.content == "X is true" for e in tl.all())            # original still auditable


def test_as_of_recovers_belief_as_it_stood():
    tl = Timeline()
    a = tl.record("fact", "one")
    cut = a.t_utc
    tl.record("fact", "two")
    early = tl.as_of(cut)
    assert all(e.t_utc <= cut for e in early)             # re-check the past: only what was known then
