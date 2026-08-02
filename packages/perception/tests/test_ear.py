# -*- coding: utf-8 -*-
"""The cochlear front end, checked on sounds built here — so the right answer is known.

These fix the SURFACE, not hearing. A later change that still produces a plausible-looking array but
has broken the frequency map, the log scaling or the onset sign fails here instead of passing quietly
and poisoning everything learned on top of it.
"""
from __future__ import annotations

import numpy as np
import pytest

from packages.perception.ear import N_BANDS, SR, cochleagram, filterbank, onsets


def tone(f, d=0.5, sr=SR):
    t = np.arange(int(d * sr)) / sr
    return (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)).astype("float32")


def test_shape_is_frames_by_bands():
    cg = cochleagram(tone(440))
    assert cg.ndim == 2 and cg.shape[1] == N_BANDS
    assert len(cg) > 10


def test_the_frequency_map_is_monotone():
    """The whole point of a mel filterbank: higher pitch, higher band. A flipped or scrambled map
    produces numbers that look fine and mean nothing."""
    peaks = [int(cochleagram(tone(f)).mean(0).argmax()) for f in (100, 200, 400, 800, 1600, 3200)]
    assert peaks == sorted(peaks)
    assert peaks[-1] > peaks[0]


def test_loudness_is_logarithmic():
    """A thousandfold difference in pressure must stay a manageable difference here, or the same
    representation cannot serve a quiet room and a loud one without a gain schedule."""
    quiet = cochleagram(tone(440) * 0.001).mean()
    loud = cochleagram(tone(440) * 1.0).mean()
    assert 3.0 < (loud - quiet) < 12.0


def test_onsets_fire_on_a_beginning_and_not_on_silence():
    sig = np.concatenate([np.zeros(SR // 2, "float32"), tone(880, 0.3), np.zeros(SR // 2, "float32")])
    o = onsets(cochleagram(sig))
    start = int(0.5 * SR / 160)
    assert abs(int(o.argmax()) - start) < 12, "the loudest rise is where the sound starts"
    assert o[:start - 15].max() < o.max() * 0.5, "silence before it is not an event"


def test_an_ending_is_not_an_onset():
    """Rectified on purpose. A sound stopping and a sound starting are different events, and taking
    the absolute value of the flux would report both as the same thing."""
    sig = np.concatenate([tone(880, 0.4), np.zeros(SR // 2, "float32")])
    o = onsets(cochleagram(sig))
    stop = int(0.4 * SR / 160)
    assert o[stop + 2:].max() < o.max() * 0.35


def test_the_same_source_lands_nearer_than_a_different_one():
    rng = np.random.default_rng(0)

    def emb(x):
        c = cochleagram(x).mean(0)
        return c / np.linalg.norm(c)
    a1 = emb(tone(440) + 0.02 * rng.standard_normal(SR // 2).astype("float32"))
    a2 = emb(tone(440) + 0.02 * rng.standard_normal(SR // 2).astype("float32"))
    b = emb(tone(1500) + 0.02 * rng.standard_normal(SR // 2).astype("float32"))
    assert float(a1 @ a2) > float(a1 @ b) + 0.5


def test_filterbank_covers_the_range_without_gaps():
    fb = filterbank()
    assert fb.shape[0] == N_BANDS
    assert fb.sum() > 0
    assert (fb.sum(0) > 0).mean() > 0.5, "most spectrum bins belong to some band"


def test_short_input_does_not_explode():
    assert cochleagram(np.zeros(7, dtype="float32")).shape[1] == N_BANDS


def test_silence_is_finite():
    cg = cochleagram(np.zeros(SR // 2, dtype="float32"))
    assert np.isfinite(cg).all(), "the epsilon in the log exists for exactly this"
    assert onsets(cg).max() == pytest.approx(0.0, abs=1e-4)


def test_the_word_is_buried_under_the_speaker_without_alignment():
    """The problem, pinned. Comparing spectra directly compares voices."""
    from packages.perception.ear import envelope, same_word_different_throat
    from packages.perception.mouth import Gesture, say
    man_a = envelope(say(Gesture(f0=110, formants=(700, 1220, 2600), seconds=0.3), seed=1))
    man_i = envelope(say(Gesture(f0=110, formants=(300, 2300, 3000), seconds=0.3), seed=1))
    woman_a = envelope(say(Gesture(f0=190, formants=(819, 1427, 3042), seconds=0.3), seed=1))
    plain = lambda p, q: float(np.linalg.norm(p - q))          # noqa: E731
    assert plain(man_a, man_i) < plain(man_a, woman_a), "same throat wins on a plain comparison"
    aligned_same, _ = same_word_different_throat(man_a, woman_a)
    aligned_diff, _ = same_word_different_throat(man_a, man_i)
    assert aligned_same < aligned_diff, "aligning lets the word through"


def test_the_shift_measures_the_throat_and_not_the_vowel():
    """One speaker, one shift, whatever they say — otherwise it is fitting noise."""
    from packages.perception.ear import envelope, same_word_different_throat
    from packages.perception.mouth import Gesture, say
    shifts = set()
    for F in ((700, 1220, 2600), (350, 800, 2600), (500, 1750, 2500)):
        man = envelope(say(Gesture(f0=110, formants=F, seconds=0.3), seed=1))
        woman = envelope(say(Gesture(f0=190, formants=tuple(f * 1.17 for f in F),
                                     seconds=0.3), seed=1))
        shifts.add(same_word_different_throat(man, woman)[1])
    assert len(shifts) == 1, f"one throat should give one shift, got {shifts}"
    assert next(iter(shifts)) < 0, "a shorter tract sits higher in frequency"


def _voice(F, scale, f0):
    from packages.perception.ear import envelope
    from packages.perception.mouth import Gesture, say
    return envelope(say(Gesture(f0=f0, formants=tuple(f * scale for f in F), seconds=0.3), seed=1))


VOWEL_SET = ((700, 1220, 2600), (300, 2300, 3000), (350, 800, 2600), (500, 1750, 2500))


def test_a_voice_is_calibrated_once_and_the_calibration_tracks_the_throat():
    from packages.perception.ear import Talker
    ref = [_voice(F, 1.00, 110.0) for F in VOWEL_SET]
    found = {}
    for name, (scale, f0) in {"woman": (1.17, 190.0), "child": (1.30, 260.0),
                              "tall": (0.91, 95.0)}.items():
        t = Talker()
        found[name] = t.calibrate([_voice(F, scale, f0) for F in VOWEL_SET], ref)
    assert found["tall"] > found["woman"] > found["child"], f"monotone in tract length: {found}"


def test_calibrating_from_a_stretch_beats_calibrating_from_one_word():
    """Joos's point as a test: one word is a bad estimate of a throat."""
    from packages.perception.ear import Talker
    ref = [_voice(F, 1.00, 110.0) for F in VOWEL_SET]
    hers = [_voice(F, 1.17, 190.0) for F in VOWEL_SET]
    steady = Talker().calibrate(hers, ref)
    per_word = {Talker().calibrate([h], ref) for h in hers}
    assert len(per_word) > 1, "single words disagree with each other"
    assert steady in per_word or min(per_word) <= steady <= max(per_word)


def test_calibrating_lets_the_word_through():
    from packages.perception.ear import Talker
    ref = [_voice(F, 1.00, 110.0) for F in VOWEL_SET]
    hers = [_voice(F, 1.17, 190.0) for F in VOWEL_SET]
    t = Talker()
    t.calibrate(hers, ref)
    d = lambda p, q: float(np.linalg.norm(p - q))              # noqa: E731
    same = d(ref[1], t.hear(hers[1]))                          # her /i/ against his /i/
    other = min(d(ref[1], t.hear(hers[j])) for j in (0, 2, 3))
    assert same < other, "after calibration the matching vowel is nearest"


def test_a_stranger_is_still_partly_understandable_with_no_calibration():
    """The fallback that stops the ear refusing to listen until it has heard enough."""
    from packages.perception.ear import without_knowing_the_voice as bare
    d = lambda p, q: float(np.linalg.norm(p - q))              # noqa: E731
    his_i, her_i = _voice(VOWEL_SET[1], 1.00, 110.0), _voice(VOWEL_SET[1], 1.17, 190.0)
    his_a = _voice(VOWEL_SET[0], 1.00, 110.0)
    assert d(bare(his_i), bare(her_i)) < d(bare(his_i), bare(his_a))
