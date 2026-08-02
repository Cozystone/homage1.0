# -*- coding: utf-8 -*-
"""Finding words in a stream that has no gaps — the thing infants do before they know any meanings.

    from packages.perception.segmentation import transitional_probabilities, boundaries, discover

SAFFRAN'S RESULT, which is the whole reason this is worth attempting at our scale. Eight-month-olds
hear two minutes of a continuous synthetic language with NO pauses, no stress, no pitch marking --
nothing but syllables running together -- and afterwards distinguish its words from part-words. The
only available cue is statistical: the transitional probability from one syllable to the next is high
inside a word and low across a boundary, because within a word the next syllable is nearly certain
and at a boundary any word may follow. Aslin, Saffran and Newport (1998) showed it is the CONDITIONAL
probability rather than raw frequency, and the same mechanism works on non-linguistic tone sequences,
so it is not a language organ.

WHICH MATTERS HERE FOR A SPECIFIC REASON. The owner's constraint on the ear is that every kind of
sound must be heard the way a person hears it, and that a label cannot be attached to each one. A
mechanism that finds units from co-occurrence alone is what that constraint requires, and it is free:
nothing has to be annotated for a count of what follows what.

THE HONEST VERSION IS THE HARD HALF. Handing this module a sequence of syllable IDENTIFIERS and
asking for the dips would be doing the difficult part for it -- an infant is not given the syllables,
it is given sound. So `discover` starts from audio: cut at energy troughs, describe each piece with
the ear, cluster the pieces into recurring types with no idea what any of them is, and only then
count what follows what. The unit inventory is DISCOVERED, and the segmentation is scored against
boundaries we know because we generated the stream.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np


def transitional_probabilities(seq) -> dict:
    """P(next | current) for every pair seen. The entire statistic, and it is a count."""
    after = defaultdict(Counter)
    for a, b in zip(seq, seq[1:]):
        after[a][b] += 1
    return {a: {b: c / sum(cnt.values()) for b, c in cnt.items()} for a, cnt in after.items()}


def boundaries(seq, tp: dict | None = None) -> list:
    """Where the stream is least predictable — a boundary is a DIP, not a low value.

    A LOCAL MINIMUM RATHER THAN A THRESHOLD, and the difference matters more than it looks. A cut-off
    on transitional probability is a number somebody chooses, and a number chosen by me has been the
    wrong move repeatedly in this project. A dip is defined by its neighbours: the transition here is
    less predictable than the one before it AND the one after it. Nothing to tune, and it survives a
    language whose probabilities are all high or all low."""
    tp = tp or transitional_probabilities(seq)
    p = [tp.get(a, {}).get(b, 0.0) for a, b in zip(seq, seq[1:])]
    return [i + 1 for i in range(1, len(p) - 1) if p[i] < p[i - 1] and p[i] < p[i + 1]]


def score(found, true_bounds, n: int) -> dict:
    """Precision and recall against boundaries we know, plus what chance would give.

    The chance line is not decoration. Proposing a boundary every third position scores well on a
    language whose words are three syllables long while having learned nothing, so a result that does
    not beat its own density-matched chance is not a result."""
    f, t = set(found), set(true_bounds)
    hit = len(f & t)
    prec = hit / max(1, len(f))
    rec = hit / max(1, len(t))
    # A SEQUENCE OF n UNITS HAS n-1 PLACES A BOUNDARY COULD GO, not n. Dividing by n made chance
    # very slightly too low, and the test that proposes a boundary EVERYWHERE -- which by definition
    # cannot beat chance -- came out 0.330 against a chance of 0.328 and appeared to. A denominator
    # off by one is enough to turn "learned nothing" into "beat the baseline".
    slots = max(1, n - 1)
    return {"precision": prec, "recall": rec,
            "f1": 2 * prec * rec / max(1e-9, prec + rec),
            "chance_precision": len(t) / slots,
            "proposed": len(f), "true": len(t), "density": len(f) / slots}


# ---------------------------------------------------------------- from sound, not from symbols

def _troughs(energy: np.ndarray, min_gap: int) -> list:
    """Cut where the stream is quietest. Syllables are energy peaks; the seams are between them."""
    cuts, last = [], -min_gap
    for i in range(1, len(energy) - 1):
        if energy[i] <= energy[i - 1] and energy[i] <= energy[i + 1] and i - last >= min_gap:
            cuts.append(i)
            last = i
    return cuts


def _kmeans(X, k, iters=30, seed=0):
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), size=min(k, len(X)), replace=False)].copy()
    a = np.zeros(len(X), dtype=int)
    for _ in range(iters):
        a = ((X[:, None, :] - C[None, :, :]) ** 2).sum(2).argmin(1)
        for j in range(len(C)):
            m = X[a == j]
            if len(m):
                C[j] = m.mean(0)
    return a, C


def discover(cochleagram: np.ndarray, *, expect_units: int = 12, syllable_frames: int = 18) -> dict:
    """Units, then statistics, then boundaries — from sound alone.

    `expect_units` is how many distinct sounds to look for, not what they are. That is a real
    assumption and it is stated rather than hidden: an infant is not told the inventory size either,
    but it is a far weaker thing to supply than the inventory itself.

    Returns the discovered unit sequence and the frame positions where the statistics dip."""
    cg = np.asarray(cochleagram, dtype=np.float64)
    energy = cg.mean(1)
    cuts = _troughs(energy, max(4, int(syllable_frames * 0.6)))
    edges = [0] + cuts + [len(cg)]
    pieces, spans = [], []
    for a, b in zip(edges, edges[1:]):
        if b - a < 3:
            continue
        seg = cg[a:b]
        v = seg.mean(0)
        pieces.append(v - v.mean())
        spans.append((a, b))
    if len(pieces) < expect_units:
        return {"units": [], "spans": spans, "boundary_frames": [], "why": "too few pieces"}
    X = np.stack(pieces)
    X = X / np.maximum(1e-9, np.linalg.norm(X, axis=1, keepdims=True))
    labels, _ = _kmeans(X, expect_units)
    seq = [int(v) for v in labels]
    b = boundaries(seq)
    return {"units": seq, "spans": spans, "boundary_frames": [spans[i][0] for i in b if i < len(spans)],
            "distinct_found": len(set(seq))}
