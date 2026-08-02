# -*- coding: utf-8 -*-
"""Which moving thing is me: intention with momentum, not action-to-displacement.

Six attempts failed and the sixth read the data instead of inventing a seventh criterion. The true
body's own action-to-displacement table, taken from a track that was on the body 100% of the time:

    action 2  n=2  mean (+4.3, +0.0)      action 6  n=4  mean (-3.0, -1.7)
    action 7  n=5  mean (+3.6, -1.0)      action 0  n=7  mean (+0.1, +1.6)
    standard deviations 3-8 px, as large as the means

So even the real body has no clean map from button to displacement, and both criteria tried so far
assumed one. Two reasons, both structural rather than accidental:

    momentum      Ms. Pac-Man keeps travelling in the last direction and turns only where the corridor
                  permits. A button sets an INTENTION; the maze decides the displacement.
    dimensionality  the body's track yields ~30 samples over 9 actions -- three each -- and no
                  statistic estimates a two-dimensional mean from three points.

THE CRITERION THAT FOLLOWS FROM THAT, and it is the one the failure names rather than one I preferred:

    momentum   direction PERSISTS. Most frames carry no information about intention at all, and
               including them is what drowned the signal.
    intention  when direction CHANGES, the command chose the new one.

So look only at direction-change events, and ask whether the new heading is predicted by the command.
Heading is one of eight bins instead of a 2-D vector, which is also why three samples per action stops
being fatal.

NOTHING HERE KNOWS WHAT A BODY IS. The map from button to heading is not supplied and not assumed to
exist: it is estimated from the track's own changes and then scored against a per-track null in which
the actions are shuffled. A ghost changes direction on its own schedule, so its shuffled score matches
its real one; the body's does not.
"""
from __future__ import annotations

import numpy as np

BINS = 8


def _heading(dx: float, dy: float, floor: float = 0.7):
    """One of eight compass bins, or None when the thing is not really moving."""
    if abs(dx) < floor and abs(dy) < floor:
        return None
    return int(np.round(np.arctan2(dy, dx) / (2 * np.pi / BINS))) % BINS


def turns(evidence) -> list:
    """(action, new heading) at every frame where the heading changed. The whole signal, isolated."""
    out, prev = [], None
    for a, dx, dy in evidence:
        h = _heading(dx, dy)
        if h is None:
            continue
        if prev is not None and h != prev:
            out.append((int(a), h))
        prev = h
    return out


def _agreement(rows) -> float:
    """How often a turn goes where that button usually sends this thing. Modal map, estimated here."""
    if len(rows) < 6:
        return 0.0
    modal: dict = {}
    for a, h in rows:
        modal.setdefault(a, []).append(h)
    pick = {a: max(set(hs), key=hs.count) for a, hs in modal.items()}
    return float(np.mean([1.0 if pick.get(a) == h else 0.0 for a, h in rows]))


def intention_momentum(evidence, trials: int = 60, seed: int = 0) -> float:
    """Turn agreement above a per-track shuffled-action null, in null standard deviations.

    A modal map fitted on few points agrees with itself by construction, which is exactly the
    small-sample bias that made the raw correlation prefer an 18-sample track over a 30-sample one
    earlier today. The null is fitted the same way on the same number of points, so that advantage
    cancels and only real action-to-heading structure survives."""
    rows = turns(evidence)
    if len(rows) < 8:
        return -1e9
    real = _agreement(rows)
    acts = np.array([a for a, _h in rows])
    heads = [h for _a, h in rows]
    rng = np.random.default_rng(seed)
    null = [_agreement(list(zip(rng.permutation(acts).tolist(), heads))) for _ in range(trials)]
    m, sd = float(np.mean(null)), float(np.std(null))
    return (real - m) / sd if sd > 1e-9 else 0.0
