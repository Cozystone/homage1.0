# -*- coding: utf-8 -*-
"""Felt speech: creative/emotional utterance grounded in REAL affect + REAL associations, MARKED as
felt (never asserted as fact). The doctrine-pure alternative to relaxing the verify-gate: re-target
the grounding, don't loosen it. No fabrication, no template fallback."""
from packages.base_brain.felt_speech import felt_speech, _mood_word


def test_mood_word_follows_the_real_affect_quadrant():
    assert _mood_word(0.5, 0.4, 0) in ("설레는", "들뜬", "생기 도는")     # +valence +arousal
    assert _mood_word(-0.5, -0.3, 0) in ("가라앉은", "쓸쓸한", "무거운")   # -valence -arousal


def test_weaves_real_associations_marked_felt():
    f = felt_speech("가을", valence=0.4, arousal=0.3, associations=["낙엽", "바람"], seed=1)
    assert f is not None and f.mode == "felt"
    # every REAL association appears (nothing invented, nothing dropped)
    assert "낙엽" in f.text and "바람" in f.text and "가을" in f.text
    assert f.guarantees["fabricated_facts"] is False and f.guarantees["asserted_as_fact"] is False


def test_never_invents_an_association():
    # topic but NO real association → it must NOT make one up; states only the felt orientation
    f = felt_speech("양자중력", valence=0.1, arousal=0.1, associations=[])
    assert f is not None and f.associations == [] and "양자중력" in f.text
    # the text contains no fabricated associate — only the topic + mood
    assert f.mode == "felt"


def test_mood_only_when_no_topic():
    f = felt_speech("", valence=0.3, arousal=0.2)
    assert f is not None and "마음" in f.text and f.associations == []


def test_no_double_ending():
    f = felt_speech("이별", valence=-0.5, arousal=-0.2, associations=["비", "침묵"], seed=0)
    assert "요예요" not in f.text and "다요" not in f.text
    assert f.text.endswith(("요.", "요", "."))


def test_dict_certificate_marks_not_fact():
    d = felt_speech("봄", valence=0.4, arousal=0.2, associations=["꽃"]).to_dict()
    assert d["answer_kind"] == "felt_speech" and d["mode"] == "felt"
    assert d["reasoning_certificate"]["guarantees"]["asserted_as_fact"] is False
