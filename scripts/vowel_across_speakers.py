# -*- coding: utf-8 -*-
"""Does the WORD survive the SPEAKER? The same vowel from different throats and pitches.

OWNER'S QUESTION, and it is the central one for hearing language rather than hearing sound: the same
word said by a man, a woman and a child is three different signals. Is anything common extractable?

TWO SEPARATE PROBLEMS HIDE IN "different voices", and they need different answers.

    PITCH        the source. f0 90 or 220 is the same tract buzzing at a different rate. The
                 source-filter split already handles this, and the truncated cepstrum in `mouth._heard`
                 was written for exactly it -- keep the slow envelope, drop the fast comb.

    TRACT LENGTH the filter itself. A shorter tract puts EVERY resonance higher by roughly the same
                 factor -- about 15-20% for a woman against a man, 25% for a child. That is not noise
                 on the envelope, it IS the envelope, moved. No amount of source removal touches it.

AND THE SECOND ONE IS CHEAP IN THIS SUBSTRATE, which is the point worth testing. A uniform scaling of
frequency is a SHIFT on a logarithmic frequency axis, and the cochleagram is already logarithmic
because the cochlea is. So speaker normalisation is: slide one spectrum along the band axis and take
the best alignment. No learning, no labels, a dozen lines.

REGISTERED BEFORE RUNNING:
    1  plain comparison clusters by SPEAKER -- vowels from one throat look more alike than the same
       vowel from two throats. If it does not, there is no problem here to solve.
    2  shift-aligned comparison clusters by VOWEL instead.
    3  and the shift it finds tracks the actual tract scale, or it is fitting noise.

The oracle is free: every voice here is synthesised, so the vowel and the throat are both known.

Run:  python scripts/vowel_across_speakers.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.perception.ear import cochleagram                 # noqa: E402
from packages.perception.mouth import Gesture, say              # noqa: E402

OUT = "data/perception/vowel_across_speakers.json"

VOWELS = {"a": (700, 1220, 2600), "i": (300, 2300, 3000),
          "u": (350, 800, 2600), "e": (500, 1750, 2500)}
#: three throats and three pitches, crossed. The scale is the tract-length factor.
SPEAKERS = {"man": (1.00, 110.0), "woman": (1.17, 190.0), "child": (1.30, 260.0)}


def envelope(x) -> np.ndarray:
    """The spectral shape on the ear's log-frequency axis, level removed."""
    c = cochleagram(x).mean(0)
    return c - c.mean()


def plain(a, b) -> float:
    return float(np.linalg.norm(a - b))


def shift_aligned(a, b, max_shift: int = 8) -> tuple:
    """Best distance over a slide along the band axis — and the slide it took.

    On a log axis a uniform stretch of the frequency scale is exactly this translation, so a shift
    that fits IS the tract-length difference, in band units."""
    best, at = float("inf"), 0
    for s in range(-max_shift, max_shift + 1):
        bb = np.roll(b, s)
        if s > 0:
            seg_a, seg_b = a[s:], bb[s:]
        elif s < 0:
            seg_a, seg_b = a[:s], bb[:s]
        else:
            seg_a, seg_b = a, bb
        if len(seg_a) < 12:
            continue
        d = float(np.linalg.norm(seg_a - seg_b) / np.sqrt(len(seg_a)) * np.sqrt(len(a)))
        if d < best:
            best, at = d, s
    return best, at


def main() -> None:
    reps, meta = {}, {}
    for v, F in VOWELS.items():
        for s, (scale, f0) in SPEAKERS.items():
            g = Gesture(f0=f0, formants=tuple(f * scale for f in F), seconds=0.3)
            reps[(v, s)] = envelope(say(g, seed=1))
            meta[(v, s)] = (scale, f0)
    keys = list(reps)

    def nearest(metric) -> tuple:
        by_vowel = by_speaker = 0
        for k in keys:
            others = [(metric(reps[k], reps[o]), o) for o in keys if o != k]
            _, o = min(others)
            by_vowel += int(o[0] == k[0])
            by_speaker += int(o[1] == k[1])
        return by_vowel / len(keys), by_speaker / len(keys)

    pv, ps = nearest(plain)
    sv, ss = nearest(lambda a, b: shift_aligned(a, b)[0])
    print("%-24s %14s %14s" % ("nearest neighbour is...", "same VOWEL", "same SPEAKER"))
    print("%-24s %13.0f%% %13.0f%%" % ("plain comparison", 100 * pv, 100 * ps))
    print("%-24s %13.0f%% %13.0f%%" % ("shift-aligned", 100 * sv, 100 * ss))

    print()
    print("does the shift track the throat?  (bands, mel axis)")
    rows = []
    for v in VOWELS:
        line = []
        for s in ("woman", "child"):
            _, at = shift_aligned(reps[(v, "man")], reps[(v, s)])
            line.append("%s %+d" % (s, at))
            rows.append({"vowel": v, "speaker": s, "scale": SPEAKERS[s][0], "shift": at})
        print("   %-3s  %s" % (v, "   ".join(line)))
    consistent = len({r["shift"] for r in rows if r["speaker"] == "woman"}) == 1 and \
        len({r["shift"] for r in rows if r["speaker"] == "child"}) == 1
    print("   one shift per speaker, whatever the vowel: %s" % consistent)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"plain": {"same_vowel": pv, "same_speaker": ps},
                   "shift_aligned": {"same_vowel": sv, "same_speaker": ss},
                   "shifts": rows, "one_shift_per_speaker": consistent,
                   "note": "synthesised voices, so vowel and throat are both known"}, f, indent=1)
    print("\nwrote %s" % OUT)


if __name__ == "__main__":
    main()
