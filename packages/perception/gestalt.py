# -*- coding: utf-8 -*-
"""One grouping operation, frozen, for every sense that has to decide where one thing ends.

THIS FILE EXISTS BECAUSE THE SAME OPERATION WAS HAND-WRITTEN TWICE. `SpriteTracker.motion_split` runs its
own 1-D k-means over speeds; the text layer ran its own widest-jump over pixel gaps. Both answer the same
question -- given numbers from one scene, where does this set separate into two regimes? -- and neither
knew about the other. A codebase that keeps re-deriving its discriminators domain by domain is not
building a general perceiver, it is building one parser per domain and calling the pile "perception".

So the operation is written ONCE here and imported everywhere. Nothing in this file knows what a pixel is,
what a second is, or what a sprite is. It takes numbers and returns a boundary, or returns nothing.

WHY IT CAN BE ONE OPERATION. Grouping by proximity is the oldest result in the study of human perception
-- Wertheimer 1923 -- and it is not about pixels. Things that are close belong together, in space, in
time, in any dimension carrying a metric. What makes it computable rather than vague is that real scenes
are MULTIMODAL: gaps within a word are one regime, gaps between words another, and the boundary between
regimes is a fact about the scene rather than a number someone chose.

TWO PROPERTIES ARE LOAD-BEARING.

  the cut is DERIVED, never chosen -- the split maximising between-class variance, one-dimensional Otsu.

  the organ ABSTAINS when there is nothing to find, because an organ that always returns a cut invents
    boundaries, which is the same failure as seeing objects in noise.

THE ABSTENTION TEST IS REFERENCED TO A MEASURED NULL, and it did not used to be. The first version divided
the widest jump by the median gap and called it multimodality. That statistic is unstable exactly where it
matters: the median gap collapses toward zero whenever values are dense, so the ratio explodes on
featureless input. Sixty evenly spaced points with noise on them scored 25.4 and shattered into 58 groups.
It was measuring noise structure and reporting regime structure.

What replaces it is the separation a split actually buys -- between-class over total variance -- compared
against the SAME statistic computed on unstructured draws over the same range. A uniform sample splits at
eta^2 = 0.75 by construction, so unimodal data cannot clear its own null, while two real clusters approach
1.0 and clear it easily. Nothing is compared against a number chosen by hand.

AND THE ORGAN IS RECURSIVE, which is where the hierarchy comes from. Glyphs group into lines, lines into
paragraphs -- one operation applied at successive scales, each level re-deriving its cut from its own
gaps. The earlier version cut once globally, which is why 2,065 commits came back as three sessions: one
enormous break dominated the whole set and nothing looked inside the pieces. Recursion also removed the
need for a linear-versus-log scale heuristic, which was a guess in the shape of a rule; a heavy tail is
now peeled one level at a time, which is what a heavy tail actually is.
"""
from __future__ import annotations

import numpy as np

ALPHA = 0.01          # a boundary must beat unstructured data this decisively
NULL_DRAWS = 200      # resamples backing every abstention decision
MIN_N = 8             # below this a split cannot be told from noise by any test
MAX_DEPTH = 16        # guard on recursion, not a threshold on the data


def _best_split(v):
    """(eta^2, cut) for the split of SORTED v maximising between-class variance. Vectorised over all k."""
    n = len(v)
    tot = float(((v - v.mean()) ** 2).sum())
    if n < 2 or tot <= 0:
        return 0.0, None
    k = np.arange(1, n)
    c = np.cumsum(v)
    m1 = c[:-1] / k
    m2 = (c[-1] - c[:-1]) / (n - k)
    ssb = k * (m1 - v.mean()) ** 2 + (n - k) * (m2 - v.mean()) ** 2
    i = int(np.argmax(ssb))
    return float(ssb[i] / tot), float((v[i] + v[i + 1]) / 2.0)


def separation(values) -> dict:
    """How much of the variance the best split explains, and where it falls. Scale-free by construction."""
    v = np.sort(np.asarray(values, dtype=float))
    v = v[np.isfinite(v)]
    eta, cut = _best_split(v)
    return {"n": int(len(v)), "eta2": eta, "cut": cut}


def evidence(values, draws: int = NULL_DRAWS, seed: int = 0) -> dict:
    """Is there a boundary at all? The split's separation against ONE population of the same shape.

    THE NULL HAS TO BE A SINGLE CLUSTER, and getting that wrong once already cost a rung. The first null
    here was uniform over the observed range, which models NO STRUCTURE rather than ONE REGIME -- a
    different and much weaker hypothesis. Uniform data splits at eta^2 = 0.75 by construction, so the test
    demanded that two real clusters beat an arrangement that is already maximally spread, and the organ
    abstained on sprite speeds that are five at rest and five in motion. A person sees that split
    instantly; a test that cannot is testing the wrong thing.

    So the null is Gaussian with the observed mean and spread: the maximum-entropy single population given
    what was measured. The question the organ asks is "one regime or two", and this is the "one"."""
    v = np.sort(np.asarray(values, dtype=float))
    v = v[np.isfinite(v)]
    n = len(v)
    if n < MIN_N or v[-1] - v[0] <= 0:
        return {"n": int(n), "eta2": 0.0, "p": 1.0, "multimodal": False, "cut": None}
    obs, cut = _best_split(v)
    rng = np.random.default_rng(seed)
    mu, sd = float(v.mean()), float(v.std())
    hits = 0
    for _ in range(draws):
        s = np.sort(rng.normal(mu, sd, size=n))
        if _best_split(s)[0] >= obs:
            hits += 1
    p = (hits + 1) / (draws + 1)
    return {"n": int(n), "eta2": float(obs), "p": float(p),
            "multimodal": bool(p < ALPHA), "cut": cut}


def derive_cut(values, **kw):
    """The boundary between two regimes of `values`, read off the values. None when there is none."""
    e = evidence(values, **kw)
    return e["cut"] if e["multimodal"] else None


def split(values, **kw):
    """(low, high) index arrays either side of the derived boundary; (all, empty) when it abstains."""
    v = np.asarray(values, dtype=float)
    c = derive_cut(v, **kw)
    if c is None:
        return np.arange(len(v)), np.array([], int)
    return np.where(v <= c)[0], np.where(v > c)[0]


def _recurse(order, pos, depth, out, seed):
    if depth >= MAX_DEPTH or len(order) < MIN_N:
        out.append(order)
        return
    gaps = np.diff(pos)
    cut = derive_cut(gaps, seed=seed + depth)
    if cut is None:
        out.append(order)
        return
    start = 0
    for i in range(len(gaps)):
        if gaps[i] > cut:
            _recurse(order[start:i + 1], pos[start:i + 1], depth + 1, out, seed)
            start = i + 1
    if start == 0:                       # the cut separated nothing; stop rather than spin
        out.append(order)
        return
    _recurse(order[start:], pos[start:], depth + 1, out, seed)


def group_by_proximity(items, position, recursive: bool = True, seed: int = 0):
    """Items along one dimension, cut where the gap to the next exceeds the derived boundary.

    The generic form of "glyphs into lines" and of "moments into episodes". `position` maps an item to a
    coordinate; nothing else about the items is looked at. Recursion supplies the hierarchy -- each level
    re-derives its own cut from its own gaps -- and abstention terminates it, so a set with no seam comes
    back whole instead of being shattered."""
    if len(items) < 2:
        return [list(items)]
    order = sorted(items, key=position)
    pos = np.array([float(position(x)) for x in order], float)
    if not recursive:
        cut = derive_cut(np.diff(pos), seed=seed)
        if cut is None:
            return [order]
        out, cur, gaps = [], [order[0]], np.diff(pos)
        for i, x in enumerate(order[1:]):
            if gaps[i] <= cut:
                cur.append(x)
            else:
                out.append(cur)
                cur = [x]
        out.append(cur)
        return out
    out = []
    _recurse(order, pos, 0, out, seed)
    return [g for g in out if g]
