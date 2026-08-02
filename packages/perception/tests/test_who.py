# -*- coding: utf-8 -*-
"""One identity, several cues — and any cue brings the rest.

Every voice here is synthesised, so who is speaking is known. The ledger is redirected to a temporary
file per test: an identity store that leaks between runs would make yesterday's people appear in
today's result, which is the kind of contamination that looks like memory.
"""
from __future__ import annotations

import numpy as np
import pytest

from packages.perception import who as W
from packages.perception.ear import envelope
from packages.perception.mouth import Gesture, say

VOWELS = {"a": (700, 1220, 2600), "i": (300, 2300, 3000), "u": (350, 800, 2600),
          "e": (500, 1750, 2500), "o": (450, 900, 2400), "ae": (660, 1720, 2410)}
PEOPLE = {"ana": (1.17, 190.0), "bo": (1.00, 110.0), "cy": (1.30, 260.0), "di": (0.91, 95.0)}


@pytest.fixture(autouse=True)
def _clean_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "LEDGER", tmp_path / "identities.jsonl")


def utter(person, vowel):
    scale, f0 = PEOPLE[person]
    F = tuple(f * scale for f in VOWELS[vowel])
    return envelope(say(Gesture(f0=f0, formants=F, seconds=0.3), seed=1))


def meet_everyone(heard=("a", "i", "u")):
    looks = {}
    rng = np.random.default_rng(0)
    for p in PEOPLE:
        looks[p] = rng.standard_normal(24)
        W.bind("voice", W.voice_print([utter(p, v) for v in heard]), identity=p, seen_as=p + "'s coat")
        W.bind("appearance", looks[p], identity=p, seen_as=p + "'s coat")
    return looks


def test_a_name_given_is_not_overridden_by_similarity():
    """The bug that collapsed four people onto one node: an explicit identity fell through to
    similarity matching when its node did not exist yet, so everyone joined the first person."""
    meet_everyone()
    s = W.summary()
    assert s["identities"] == len(PEOPLE)
    assert s["known_in_more_than_one_way"] == len(PEOPLE)


def test_a_voice_brings_back_what_was_seen():
    looks = meet_everyone()
    r = W.recall_from("voice", [utter("cy", v) for v in ("e", "o", "ae")])
    assert r is not None and r["identity"] == "cy"
    assert "appearance" in r["also"], "hearing reaches the modality it is not"
    got = W.cue_of("cy", "appearance")
    sims = {p: float(got @ looks[p] / (np.linalg.norm(got) * np.linalg.norm(looks[p])))
            for p in PEOPLE}
    assert max(sims, key=sims.get) == "cy"


def test_it_declines_rather_than_guessing_on_a_stranger():
    """A wrong identity activates the wrong memories, which is worse than none."""
    meet_everyone()
    stranger = [envelope(say(Gesture(f0=140, formants=tuple(f * 1.05 for f in VOWELS[v]),
                                     seconds=0.3), seed=3)) for v in ("e", "o", "ae")]
    assert W.recall_from("voice", stranger) is None


def test_when_it_speaks_it_is_right():
    """The property that matters more than coverage. Across every held-out word, no misidentification."""
    meet_everyone()
    said = wrong = 0
    for p in PEOPLE:
        for v in ("e", "o", "ae"):
            r = W.recall("voice", utter(p, v))
            if r is not None:
                said += 1
                wrong += int(r["identity"] != p)
    assert said > 0
    assert wrong == 0


def test_averaging_utterances_is_what_makes_it_about_the_speaker():
    """A single envelope is mostly a record of the VOWEL: same-person pairs sit at median cosine
    0.880 and different-person at 0.779, which overlap badly. Averaging cancels the word."""
    a = W.voice_print([utter("ana", v) for v in VOWELS])
    a2 = W.voice_print([utter("ana", v) for v in ("e", "o", "ae")])
    b = W.voice_print([utter("bo", v) for v in ("e", "o", "ae")])
    cos = lambda p, q: float(p @ q / (np.linalg.norm(p) * np.linalg.norm(q)))   # noqa: E731
    assert cos(a, a2) > cos(a, b)


def test_an_unknown_cue_type_is_simply_another_cue():
    """Nothing here knows what a face or a voice is, which is what stops it becoming a schema."""
    meet_everyone()
    W.bind("gait", np.arange(16, dtype=float), identity="ana")
    r = W.recall("gait", np.arange(16, dtype=float))
    assert r is not None and r["identity"] == "ana"
    assert set(r["also"]) >= {"voice", "appearance"}
