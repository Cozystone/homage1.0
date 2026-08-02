# -*- coding: utf-8 -*-
"""Three ways to understand a voice you have never heard — the ones people actually use.

WHY THREE AND NOT ONE. The first attempt here searched for the best band-shift PER PAIR of sounds,
which took same-vowel nearest-neighbour from 0% to 75%. Then the owner asked how PEOPLE do it, and
the literature says: not like that.

    Joos 1948                a vowel is heard against the OTHER vowels that talker produces, not
                             against an absolute scale.
    Ladefoged & Broadbent    a carrier phrase before the target shifts what the target is heard as.
    1957                     The listener calibrates from the voice FIRST, then decides the word.
    intrinsic accounts       formant RATIOS, or F3 and F0 -- which track vocal tract length -- used
                             to interpret F1 and F2 without any context at all.

Per-pair search is none of these. It refits the speaker for every comparison, so it can bend a
confusable pair into agreement, which is the most likely source of the 25% it still gets wrong.

SO THE ARMS ARE THE MECHANISMS, count-matched on the same sounds:

    per-pair      the current method: best shift for this comparison
    extrinsic     one shift per SPEAKER, estimated from that speaker's OTHER utterances and then
                  applied fixed -- Ladefoged & Broadbent, and Joos's point about the talker's set
    intrinsic     no context at all: each sound normalised by its own spectral scale, so a stranger's
                  first word is already interpretable

REGISTERED BEFORE RUNNING:
    1  extrinsic beats per-pair. Calibrating once per voice should be more robust than refitting per
       comparison, and if it is not, the per-pair number was measuring something other than speaker
       scale.
    2  intrinsic beats plain, since it is doing real work, but loses to extrinsic -- a single sound
       carries less information about a throat than a stretch of speech does.
    3  and the extrinsic shift stays constant across what the speaker says.

Free oracle throughout: the voices are synthesised, so vowel and throat are both known.

Run:  python scripts/three_ways_to_hear_a_stranger.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.perception.ear import envelope                    # noqa: E402
from packages.perception.mouth import Gesture, say              # noqa: E402

OUT = "data/perception/three_ways_to_hear_a_stranger.json"

VOWELS = {"a": (700, 1220, 2600), "i": (300, 2300, 3000), "u": (350, 800, 2600),
          "e": (500, 1750, 2500), "o": (450, 900, 2400), "ae": (660, 1720, 2410)}
SPEAKERS = {"man": (1.00, 110.0), "woman": (1.17, 190.0),
            "child": (1.30, 260.0), "tall_man": (0.91, 95.0)}
MAX_SHIFT = 8


def _shifted(v, s):
    r = np.roll(v, s)
    if s > 0:
        r[:s] = v[0]
    elif s < 0:
        r[s:] = v[-1]
    return r


def _d(a, b) -> float:
    return float(np.linalg.norm(a - b))


def per_pair(a, b) -> float:
    return min(_d(a, _shifted(b, s)) for s in range(-MAX_SHIFT, MAX_SHIFT + 1))


def speaker_shift(their: list, reference: list) -> int:
    """One calibration for a voice, from a stretch of it — Ladefoged and Broadbent's carrier phrase.

    Their MEAN spectrum against the reference speaker's mean. A single number for the throat, found
    without knowing which word any of it was, and then not touched again."""
    t, r = np.mean(their, axis=0), np.mean(reference, axis=0)
    return int(min(range(-MAX_SHIFT, MAX_SHIFT + 1), key=lambda s: _d(r, _shifted(t, s))))


def intrinsic(v) -> np.ndarray:
    """No context: put this sound on a canonical scale using only itself.

    Its own spectral centroid on the log-frequency axis stands in for the throat -- a shorter tract
    puts everything higher, so its centre of mass moves up. That is the cheapest version of the
    intrinsic accounts, which use F3 or formant ratios for the same purpose."""
    w = np.maximum(v - v.min(), 1e-9)
    c = float((w * np.arange(len(v))).sum() / w.sum())
    return _shifted(v, int(round(len(v) / 2 - c)))


def main() -> None:
    reps = {}
    for vw, F in VOWELS.items():
        for sp, (scale, f0) in SPEAKERS.items():
            reps[(vw, sp)] = envelope(say(Gesture(f0=f0, formants=tuple(f * scale for f in F),
                                                  seconds=0.3), seed=1))
    keys = list(reps)

    # extrinsic: calibrate each speaker against the reference, from their utterances only
    ref = [reps[(v, "man")] for v in VOWELS]
    shifts = {sp: (0 if sp == "man" else
                   speaker_shift([reps[(v, sp)] for v in VOWELS], ref)) for sp in SPEAKERS}
    calibrated = {k: _shifted(reps[k], shifts[k[1]]) for k in keys}
    intr = {k: intrinsic(reps[k]) for k in keys}

    def score(get, metric) -> tuple:
        vw = sp = 0
        for k in keys:
            _, o = min((metric(get(k), get(o)), o) for o in keys if o != k)
            vw += int(o[0] == k[0])
            sp += int(o[1] == k[1])
        return vw / len(keys), sp / len(keys)

    rows = {
        "plain (no normalisation)": score(lambda k: reps[k], _d),
        "per-pair shift": score(lambda k: reps[k], per_pair),
        "extrinsic (one shift per voice)": score(lambda k: calibrated[k], _d),
        "intrinsic (no context)": score(lambda k: intr[k], _d),
    }
    print("%-34s %12s %12s" % ("nearest neighbour is...", "same VOWEL", "same SPEAKER"))
    for name, (v, s) in rows.items():
        print("%-34s %11.0f%% %11.0f%%" % (name, 100 * v, 100 * s))

    print()
    print("calibration found per voice (bands): %s"
          % ", ".join("%s %+d" % (k, v) for k, v in shifts.items()))
    print("true tract scales:                   %s"
          % ", ".join("%s x%.2f" % (k, v[0]) for k, v in SPEAKERS.items()))

    # does the calibration hold across what they say, or is it a per-word accident?
    spread = {}
    for sp in SPEAKERS:
        if sp == "man":
            continue
        per_word = [speaker_shift([reps[(v, sp)]], ref) for v in VOWELS]
        spread[sp] = (min(per_word), max(per_word))
    print("per-word shift range per voice:      %s"
          % ", ".join("%s %d..%d" % (k, a, b) for k, (a, b) in spread.items()))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"rows": {k: {"same_vowel": v, "same_speaker": s} for k, (v, s) in rows.items()},
                   "calibration": shifts, "per_word_range": {k: list(v) for k, v in spread.items()},
                   "vowels": len(VOWELS), "speakers": len(SPEAKERS),
                   "note": "synthesised voices with uniform tract scaling; both labels known"},
                  f, indent=1)
    print("\nwrote %s" % OUT)


if __name__ == "__main__":
    main()
