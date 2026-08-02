# -*- coding: utf-8 -*-
"""Plausibility re-verification — an implausible-for-a-room or low-confidence detection is held
tentative until re-verified across frames (owner: )."""
from __future__ import annotations

from packages.perception.plausibility import (
    annotate,
    is_confident,
    is_plausible_indoors,
    needs_reverify,
)


def test_room_objects_are_plausible_and_accepted_at_once():
    assert is_plausible_indoors("사람") and is_plausible_indoors("책") and is_plausible_indoors("선풍기")
    assert is_confident("사람", 0.8, frames_seen=1)          # plausible + confident → real now


def test_impossible_room_objects_are_held_until_reverified():
    assert not is_plausible_indoors("고래") and not is_plausible_indoors("비행기")
    assert needs_reverify("고래", 0.9)                        # even at high score, a whale indoors is suspect
    assert not is_confident("고래", 0.9, frames_seen=1)       # one glimpse → not accepted
    assert not is_confident("고래", 0.9, frames_seen=2)
    assert is_confident("고래", 0.9, frames_seen=3)           # persisted across frames → re-verified


def test_low_confidence_is_reverified_even_when_plausible():
    assert needs_reverify("컵", 0.2)                          # a plausible object but too faint
    assert not is_confident("컵", 0.2, frames_seen=1)
    assert is_confident("컵", 0.2, frames_seen=3)


def test_annotate_flags_tentative_with_a_reason():
    frames = {"사람": 5, "고래": 1, "컵": 1}
    dets = [{"label_ko": "사람", "score": 0.8}, {"label_ko": "고래", "score": 0.9},
            {"label_ko": "컵", "score": 0.2}]
    out = annotate(dets, lambda ko: frames.get(ko, 1))
    by = {d["label_ko"]: d for d in out}
    assert by["사람"]["tentative"] is False
    assert by["고래"]["tentative"] is True and "방 안에 있기 어려운" in by["고래"]["reverify_reason"]
    assert by["컵"]["tentative"] is True and "흐릿" in by["컵"]["reverify_reason"]
