# -*- coding: utf-8 -*-
"""Saffran's experiment, run on ATANOR: can it find words in speech with nothing but statistics?

THE DESIGN IS THE 1996 ONE, kept deliberately faithful because its whole value is what it REMOVES.
Four three-syllable nonsense words from a pool of twelve syllables, concatenated at random with no
word twice in a row, spoken at one constant rate, one constant pitch, one constant loudness, and NO
pauses anywhere. Every acoustic cue a listener could lean on is gone by construction. What remains is
that the syllable after the first of a word is nearly certain, and the syllable after the last of a
word could be any of four.

TWO ARMS, because only one of them is the real claim:

    symbols   the syllable sequence is handed over, and only the statistics are tested. This checks
              the mechanism and nothing else.
    sound     the stream is SYNTHESISED by our own mouth, heard by our own ear, cut at energy
              troughs, and the recurring pieces are clustered into units with no idea what any of
              them is. Only then are the statistics run. This is the honest task: an infant is given
              sound, not syllables.

CONTROLS, registered before running:
    1  a SHUFFLED stream -- the same syllables in random order -- must lose its boundary structure.
       If boundaries appear there too, the method found the cutting rhythm and not the words.
    2  results must beat DENSITY-MATCHED CHANCE. Proposing a boundary every third position scores
       well on three-syllable words while having learned nothing.
    3  the sound arm should score below the symbol arm and above chance -- finding the units is
       genuinely harder than counting them.

The oracle is free: we build the stream, so every true boundary is known.

Run:  python scripts/find_words_in_a_stream.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.perception.ear import cochleagram                             # noqa: E402
from packages.perception.mouth import Gesture, glide, say                   # noqa: E402
from packages.perception.segmentation import (boundaries, discover,         # noqa: E402
                                              score, transitional_probabilities)

OUT = "data/perception/find_words_in_a_stream.json"

#: twelve syllables, each a distinct articulatory posture. The vowel and the F2 onset differ, which
#: is what makes them different sounds rather than different labels.
SYLLABLES = {
    "tu": (350, 800, 2600, 1900), "pi": (300, 2300, 3000, 700), "ro": (450, 900, 2400, 1500),
    "go": (450, 950, 2350, 2400), "la": (700, 1220, 2600, 1300), "bu": (350, 780, 2500, 700),
    "da": (700, 1250, 2600, 1800), "pa": (720, 1200, 2550, 700), "ti": (300, 2250, 2950, 1900),
    "do": (460, 880, 2380, 1800), "ku": (340, 820, 2620, 2400), "bi": (310, 2280, 3050, 700),
}
WORDS = [("tu", "pi", "ro"), ("go", "la", "bu"), ("da", "pa", "ti"), ("do", "ku", "bi")]
SYL_SECONDS = 0.20


def stream(n_words: int, seed: int, shuffle: bool = False) -> tuple:
    """A continuous stream and the positions where its words end."""
    rng = np.random.default_rng(seed)
    seq, bounds, prev = [], [], None
    for _ in range(n_words):
        choices = [w for w in WORDS if w != prev]
        w = choices[int(rng.integers(len(choices)))]
        prev = w
        seq.extend(w)
        bounds.append(len(seq))
    if shuffle:
        order = rng.permutation(len(seq))
        seq = [seq[i] for i in order]
    return seq, sorted(set(bounds[:-1]))


def speak(seq) -> np.ndarray:
    """One voice, one pitch, one rate, no pauses. Every prosodic cue removed on purpose."""
    out = []
    for s in seq:
        f1, f2, f3, locus = SYLLABLES[s]
        onset = Gesture(f0=120, formants=(300, locus, 2500), seconds=0.015, burst=0.5)
        body = Gesture(f0=120, formants=(f1, f2, f3), seconds=SYL_SECONDS - 0.075)
        out.extend([onset] + glide(onset, body, 0.06) + [body])
    return say(out, seed=1)


def main() -> None:
    rows = {}
    seq, truth = stream(140, seed=0)
    print("stream: %d syllables, %d true word boundaries, %d distinct syllables"
          % (len(seq), len(truth), len(set(seq))))

    # --- arm 1: the mechanism, on symbols ---------------------------------------------------
    b = boundaries(seq)
    rows["symbols"] = score(b, truth, len(seq))
    sh_seq, _ = stream(140, seed=0, shuffle=True)
    rows["symbols (shuffled control)"] = score(boundaries(sh_seq), truth, len(sh_seq))

    # --- arm 2: from sound, units discovered ------------------------------------------------
    audio = speak(seq)
    cg = cochleagram(audio)
    frames_per_syllable = int(SYL_SECONDS * 16000 / 160)
    d = discover(cg, expect_units=12, syllable_frames=frames_per_syllable)
    true_frames = {int(t * frames_per_syllable) for t in truth}
    tol = max(3, frames_per_syllable // 2)
    hit = sum(1 for f in d["boundary_frames"] if any(abs(f - t) <= tol for t in true_frames))
    prec = hit / max(1, len(d["boundary_frames"]))
    rec = hit / max(1, len(true_frames))
    rows["sound (units discovered)"] = {
        "precision": prec, "recall": rec, "f1": 2 * prec * rec / max(1e-9, prec + rec),
        "proposed": len(d["boundary_frames"]), "true": len(true_frames),
        "distinct_units_found": d.get("distinct_found"), "pieces_cut": len(d["spans"]),
        "chance_precision": len(true_frames) / max(1, len(d["spans"])),
    }

    print()
    print("%-30s %10s %8s %8s %14s" % ("arm", "precision", "recall", "f1", "chance prec."))
    for k, v in rows.items():
        print("%-30s %10.3f %8.3f %8.3f %14.3f"
              % (k, v["precision"], v["recall"], v["f1"], v["chance_precision"]))

    print()
    tp = transitional_probabilities(seq)
    inside = np.mean([tp[a][b] for w in WORDS for a, b in zip(w, w[1:])])
    across = np.mean([tp[w[-1]].get(x[0], 0.0) for w in WORDS for x in WORDS if x != w])
    print("transitional probability inside a word %.2f, across a boundary %.2f" % (inside, across))
    print("pieces cut from the audio: %d for %d syllables  |  distinct units found: %s of 12"
          % (len(d["spans"]), len(seq), d.get("distinct_found")))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"rows": rows, "tp_inside": float(inside), "tp_across": float(across),
                   "syllables": len(seq), "note": "Saffran 1996 design; stream generated here so "
                                                  "every boundary is known"}, f, indent=1)
    print("\nwrote %s" % OUT)


if __name__ == "__main__":
    main()
