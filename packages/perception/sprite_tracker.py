# -*- coding: utf-8 -*-
"""Keep the moving things apart. One-to-one assignment against predicted positions.

Body-finding failed five ways today and the diagnosis, run against a verified oracle, ruled out
everything except the plumbing:

    detection     the body is inside a blob in 100.0% of frames, nearest at 0.54 px      not this
    the statistic the true body's track ranked FIRST of 42 under command_prediction      not this
    fragmentation the id holding the body survived 7 frames against the 12 samples the
                  statistic needs; 66 distinct ids held it across 700 frames             THIS

Chains fixed the dying but introduced merging: nine of them all landed within 55.9-57.4% of frames on
the body, a spread of 0.74 percentage points, because each chain independently took the nearest moving
blob and nothing stopped two chains taking the SAME one. Nine labels, one hypothesis.

TWO THINGS ARE MISSING AND BOTH ARE STANDARD, WHICH IS THE POINT — the failure was never conceptual.

    one-to-one assignment   if a track claims a blob, no other track may. `match()` in the babble
                            script has done this since the morning; the chains simply never used it.
    prediction              assign against where a track is GOING, not where it was. Two sprites
                            passing close by are separable by velocity and not by proximity, and every
                            identity swap today happened at exactly such a crossing.

A track that finds no blob COASTS on its velocity instead of dying, which is what keeps evidence
accumulating past the 7-frame lifetime that starved the statistic.

Nothing here knows what a body is, what a ghost is, or what game this is. It keeps moving things apart;
which one is the self is decided elsewhere, by whether the commands predict it.
"""
from __future__ import annotations

import numpy as np


class Track:
    __slots__ = ("pos", "vel", "misses", "evidence", "id", "speeds")

    def __init__(self, pos, tid: int):
        self.pos = np.asarray(pos, float)
        self.vel = np.zeros(2)
        self.misses = 0
        self.evidence: list = []
        self.id = tid
        self.speeds: list = []

    def predict(self) -> np.ndarray:
        return self.pos + self.vel

    def speed(self) -> float:
        """Typical speed over this track's life. The median, so one teleport does not define it."""
        return float(np.median(self.speeds)) if self.speeds else 0.0


class SpriteTracker:
    """Multi-object tracking over blob centroids. Domain-blind; the only inputs are positions."""

    def __init__(self, max_jump: float = 14.0, max_misses: int = 8, smoothing: float = 0.5):
        self.tracks: list[Track] = []
        self.max_jump = max_jump
        self.max_misses = max_misses
        self.smoothing = smoothing
        self._next = 0

    def _spawn(self, pos) -> Track:
        t = Track(pos, self._next)
        self._next += 1
        self.tracks.append(t)
        return t

    def step(self, blobs, action: int | None = None, moving_only: bool = True) -> None:
        """Advance one frame. `blobs` are (x, y, size); `action` labels the evidence for later scoring."""
        P = np.array([[b[0], b[1]] for b in blobs], float) if blobs else np.zeros((0, 2))
        if not self.tracks:
            for p in P:
                self._spawn(p)
            return

        pred = np.array([t.predict() for t in self.tracks])
        # ONE-TO-ONE, greedy over the global distance order. A blob goes to one track and no other.
        pairs = []
        if len(P):
            D = np.hypot(pred[:, None, 0] - P[None, :, 0], pred[:, None, 1] - P[None, :, 1])
            order = np.dstack(np.unravel_index(np.argsort(D, axis=None), D.shape))[0]
            ti, bi = set(), set()
            for i, j in order:
                if D[i, j] > self.max_jump:
                    break
                if i in ti or j in bi:
                    continue
                ti.add(int(i))
                bi.add(int(j))
                pairs.append((int(i), int(j)))
        taken_b = {j for _i, j in pairs}
        taken_t = {i for i, _j in pairs}

        for i, j in pairs:
            t = self.tracks[i]
            d = P[j] - t.pos
            t.vel = self.smoothing * d + (1 - self.smoothing) * t.vel
            t.speeds.append(float(np.hypot(d[0], d[1])))
            t.pos = P[j]
            t.misses = 0
            if action is not None and (not moving_only or abs(d[0]) > 0.5 or abs(d[1]) > 0.5):
                t.evidence.append((action, float(d[0]), float(d[1])))
        for i, t in enumerate(self.tracks):
            if i in taken_t:
                continue
            t.pos = t.predict()          # COAST: absence is not death, it is one frame unobserved
            t.misses += 1
        self.tracks = [t for t in self.tracks if t.misses <= self.max_misses]
        for j in range(len(P)):
            if j not in taken_b:
                self._spawn(P[j])

    def motion_split(self):
        """Moving tracks and static ones, with the cut DERIVED from the observed speeds.

        Stationarity is information, not noise. Everything downstream was built on "a blob is a moving
        thing", so a mask that also returns stationary things -- which is what a learned segmenter buys --
        broke every consumer: blobs 10 -> 111, buckets 7 -> 396, body-finding 71.2% -> 0.2%. The fix is
        not a better mask, it is consumers that can tell the two apart.

        The cut is the midpoint of the two speed clusters found by one pass of 1-D k-means on the
        observed medians, so it is read off the scene rather than chosen. A pellet sits at ~0 and a
        sprite at several pixels a step, which is why a split exists at all."""
        sp = np.array([t.speed() for t in self.tracks], float)
        if len(sp) < 4 or sp.max() - sp.min() < 1e-6:
            return list(self.tracks), []
        lo, hi = float(sp.min()), float(sp.max())
        for _ in range(20):
            mid = (lo + hi) / 2.0
            a, b = sp[sp <= mid], sp[sp > mid]
            if not len(a) or not len(b):
                break
            lo, hi = float(a.mean()), float(b.mean())
        cut = (lo + hi) / 2.0
        moving = [t for t in self.tracks if t.speed() > cut]
        static = [t for t in self.tracks if t.speed() <= cut]
        return moving, static

    def scored(self, score_fn, min_evidence: int = 12, moving_only: bool = False):
        """(track, score) for every track with enough evidence, best first. The caller supplies the
        criterion, so this module never learns what it is looking for."""
        pool = self.motion_split()[0] if moving_only else self.tracks
        out = [(t, score_fn(t.evidence)) for t in pool if len(t.evidence) >= min_evidence]
        return sorted(out, key=lambda x: -x[1])

    def best(self, score_fn, min_evidence: int = 12):
        s = self.scored(score_fn, min_evidence)
        return s[0][0] if s else None
