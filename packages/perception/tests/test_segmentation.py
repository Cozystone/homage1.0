# -*- coding: utf-8 -*-
"""Finding words with nothing but counts — Saffran's mechanism, on streams built here.

Every stream is generated in the test, so the boundaries are known and no result rests on a distance
I invented. The shuffled control is not optional: on a language of three-syllable words, cutting
every third position scores well while having learned nothing.
"""
from __future__ import annotations

import numpy as np

from packages.perception.segmentation import (boundaries, score,
                                              transitional_probabilities)

WORDS = [("tu", "pi", "ro"), ("go", "la", "bu"), ("da", "pa", "ti"), ("do", "ku", "bi")]


def stream(n, seed=0, shuffle=False):
    rng = np.random.default_rng(seed)
    seq, bounds, prev = [], [], None
    for _ in range(n):
        pool = [w for w in WORDS if w != prev]
        w = pool[int(rng.integers(len(pool)))]
        prev = w
        seq.extend(w)
        bounds.append(len(seq))
    if shuffle:
        seq = [seq[i] for i in rng.permutation(len(seq))]
    return seq, sorted(set(bounds[:-1]))


def test_the_statistic_is_what_saffran_says_it_is():
    """High inside a word, low across a boundary. If this is not true the rest is meaningless."""
    seq, _ = stream(120)
    tp = transitional_probabilities(seq)
    inside = np.mean([tp[a][b] for w in WORDS for a, b in zip(w, w[1:])])
    across = np.mean([tp[w[-1]].get(x[0], 0.0) for w in WORDS for x in WORDS if x != w])
    assert inside > 0.9 and across < 0.5


def test_boundaries_are_found_from_counts_alone():
    seq, truth = stream(120)
    s = score(boundaries(seq), truth, len(seq))
    assert s["f1"] > 0.9
    assert s["precision"] > s["chance_precision"] * 2


def test_shuffling_destroys_it():
    """The control that separates finding words from finding a rhythm."""
    seq, truth = stream(120)
    sh, _ = stream(120, shuffle=True)
    good = score(boundaries(seq), truth, len(seq))
    bad = score(boundaries(sh), truth, len(sh))
    assert bad["f1"] < good["f1"] * 0.5
    assert bad["precision"] <= bad["chance_precision"] + 0.05


def test_a_dip_is_used_rather_than_a_threshold():
    """A boundary is defined by its neighbours, so a language whose probabilities are all high is
    still segmentable and no cut-off has to be chosen by hand."""
    seq = ["a", "b", "c"] * 40
    tp = transitional_probabilities(seq)
    assert all(v == 1.0 for d in tp.values() for v in d.values()), "wholly predictable"
    assert boundaries(seq) == [], "nothing dips, so nothing is claimed"


def test_score_reports_chance_so_a_dense_guess_cannot_look_good():
    seq, truth = stream(60)
    everywhere = list(range(1, len(seq)))
    s = score(everywhere, truth, len(seq))
    assert s["recall"] > 0.99
    assert s["precision"] <= s["chance_precision"] + 1e-9, "guessing everywhere buys nothing"


def test_discovery_from_sound_finds_units_without_being_told_them():
    from packages.perception.ear import cochleagram
    from packages.perception.mouth import Gesture, glide, say
    from packages.perception.segmentation import discover
    syl = {"tu": (350, 800, 2600, 1900), "pi": (300, 2300, 3000, 700),
           "la": (700, 1220, 2600, 1300), "go": (450, 950, 2350, 2400)}
    seq = ["tu", "pi", "la", "go"] * 12
    out = []
    for s in seq:
        f1, f2, f3, locus = syl[s]
        on = Gesture(f0=120, formants=(300, locus, 2500), seconds=0.015, burst=0.5)
        body = Gesture(f0=120, formants=(f1, f2, f3), seconds=0.125)
        out.extend([on] + glide(on, body, 0.06) + [body])
    d = discover(cochleagram(say(out, seed=1)), expect_units=4, syllable_frames=20)
    assert d["distinct_found"] == 4, "four sounds went in; four kinds should come out"
    assert len(d["spans"]) > len(seq) * 0.8
