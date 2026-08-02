# -*- coding: utf-8 -*-
"""The mouth, and the loop that closes it: speak, listen with our own ear, move closer.

Targets are synthesised here with formants we set, so every check is against ground truth rather than
against the distance the search itself is minimising. That distinction is the whole lesson of the day
these were written: a proxy improved while the answer got worse, twice, and only having the truth
made it visible.
"""
from __future__ import annotations

import numpy as np
import pytest

from packages.perception.mouth import SR, Gesture, Voice, distance, imitate, say


def test_it_makes_sound_of_the_right_length():
    y = say(Gesture(seconds=0.25))
    assert y.dtype == np.float32
    assert abs(len(y) - int(0.25 * SR)) < 100
    assert np.isfinite(y).all()


def test_a_vowel_is_not_a_sine():
    """The source is a pulse train precisely so the tract has harmonics to shape. A sine source has
    one frequency and no filter can make a vowel out of it."""
    y = say(Gesture(formants=(700, 1220, 2600), seconds=0.3))
    spec = np.abs(np.fft.rfft(y))
    peaks = int((spec[2:-2] > 0.3 * spec.max()).sum())
    assert peaks > 3, "a vowel has a whole resonance structure, not one line"


def test_different_postures_sound_different_to_our_own_ear():
    a = say(Gesture(formants=(700, 1220, 2600), seconds=0.3))
    i = say(Gesture(formants=(300, 2300, 3000), seconds=0.3))
    assert distance(a, i) > 0.15
    assert distance(a, say(Gesture(formants=(700, 1220, 2600), seconds=0.3), seed=7)) < 0.1


def test_it_can_learn_a_posture_by_listening_to_itself():
    """The closed loop, on a front vowel at a pitch where the harmonic comb samples the envelope well.
    No label is involved anywhere: the only signal is the ear comparing two sounds."""
    target = say(Gesture(f0=95.0, formants=(300, 2300, 3000), seconds=0.3), seed=4)
    r = imitate(target, rounds=120, seed=0)
    got = r["gesture"].formants
    for a, b in zip(got, (300.0, 2300.0, 3000.0)):
        assert abs(a - b) / b < 0.25, f"recovered {tuple(int(x) for x in got)}"
    assert r["distance_after"] < r["distance_before"]


def test_imitation_actually_moves_rather_than_reporting_its_starting_point():
    target = say(Gesture(f0=110.0, formants=(500, 1750, 2500), seconds=0.25), seed=2)
    r = imitate(target, rounds=90, seed=0)
    assert r["improvement"] > 0.05
    assert r["distance_after"] <= r["best_of_starts"]


def test_a_high_pitch_makes_F1_hard_and_that_is_expected():
    """Not a bug to be silenced. With harmonics 155 Hz apart, an F1 near 300 Hz falls between them and
    is barely sampled, which is why real formant analysis prefers low-pitched voices. The same vowel
    at f0 95 is recovered almost exactly; this pins the phenomenon so a future change that appears to
    'fix' it is checked rather than believed."""
    low = imitate(say(Gesture(f0=95.0, formants=(300, 2300, 3000), seconds=0.3), seed=4),
                  rounds=120, seed=0)
    high = imitate(say(Gesture(f0=155.0, formants=(300, 2300, 3000), seconds=0.3), seed=1),
                   rounds=120, seed=0)
    err = (abs(low["gesture"].formants[0] - 300) / 300, abs(high["gesture"].formants[0] - 300) / 300)
    assert err[0] < err[1], f"low pitch should resolve F1 better, got {err}"


def test_F3_survives_everywhere():
    """The band nothing masks. If this ever breaks, the filter or the radiation is wrong rather than
    the search."""
    for f in ((700, 1220, 2600), (500, 1750, 2500)):
        r = imitate(say(Gesture(f0=155.0, formants=f, seconds=0.3), seed=1), rounds=120, seed=0)
        assert abs(r["gesture"].formants[2] - f[2]) / f[2] < 0.15


def test_a_voice_keeps_what_it_found_and_can_use_it_again():
    v = Voice()
    target = say(Gesture(f0=95.0, formants=(300, 2300, 3000), seconds=0.25), seed=4)
    v.learn("ee", target, rounds=60, seed=0)
    assert "ee" in v.postures
    out = v.utter(["ee", "ee"])
    assert len(out) > int(0.4 * SR)
    assert v.utter(["never_learned"]).size == 1, "silence for a posture it does not have"


def test_a_transition_carries_what_a_held_target_cannot():
    """Locus theory, and the owner's worry answered with a number. /ba/, /da/ and /ga/ share a vowel
    and differ only in where F2 comes FROM. Holding targets makes them nearly the same sound."""
    from packages.perception.mouth import glide
    a = Gesture(f0=120, formants=(700, 1220, 2600), seconds=0.22)

    def syll(locus, moving):
        on = Gesture(f0=120, formants=(300, locus, 2500), seconds=0.02, silence=0.05, burst=0.6)
        return say([on] + (glide(on, a, 0.07) if moving else []) + [a], seed=1)
    loci = (700.0, 1800.0, 2400.0)
    moved = [syll(v, True) for v in loci]
    held = [syll(v, False) for v in loci]

    def spread(w):
        return float(np.mean([distance(w[i], w[j]) for i in range(3) for j in range(i + 1, 3)]))
    assert spread(moved) > spread(held) * 1.5, "movement is where the distinction lives"


def test_the_same_syllable_twice_is_the_same_sound():
    """The identity control. Without it, 'these differ' means nothing."""
    from packages.perception.mouth import glide
    a = Gesture(f0=120, formants=(700, 1220, 2600), seconds=0.2)
    on = Gesture(f0=120, formants=(300, 1800, 2500), seconds=0.02, silence=0.05, burst=0.6)
    w = [say([on] + glide(on, a, 0.07) + [a], seed=1) for _ in range(2)]
    assert distance(w[0], w[1]) == pytest.approx(0.0, abs=1e-6)


def test_state_colours_the_voice():
    from packages.perception.mouth import coloured_by
    base = Gesture(f0=130, formants=(700, 1220, 2600), seconds=0.3)
    alarmed = coloured_by({"noradrenaline": 1.0, "cortisol": 0.9}, base)
    warm = coloured_by({"oxytocin": 1.0, "serotonin": 0.6}, base)
    assert alarmed.f0 > base.f0 * 1.2 and alarmed.jitter > base.jitter * 3
    assert alarmed.tilt < 0 < warm.tilt, "pressed against breathy"
    assert distance(say(alarmed, seed=1), say(warm, seed=1)) > 0.15


def test_state_changes_the_voice_and_not_the_word():
    """The control that makes the one above a result. A tone that destroys the vowel is not a tone,
    it is damage."""
    from packages.perception.mouth import coloured_by
    base = Gesture(f0=130, formants=(700, 1220, 2600), seconds=0.35)
    for h in ({"noradrenaline": 1.0, "cortisol": 0.9}, {"oxytocin": 1.0, "serotonin": 0.6}):
        got = imitate(say(coloured_by(h, base), seed=1), rounds=90, seed=0)["gesture"]
        assert abs(got.formants[1] - 1220) / 1220 < 0.20


def test_silence_and_degenerate_input_do_not_explode():
    assert np.isfinite(say(Gesture(amplitude=0.0, seconds=0.05))).all()
    assert distance(say(Gesture(seconds=0.05)), say(Gesture(seconds=0.05))) == pytest.approx(0, abs=1e-6)
