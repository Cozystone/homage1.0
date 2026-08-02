# -*- coding: utf-8 -*-
"""V7-2 — is a direction fitted on ONE pair of kinds able to separate a pair it has never seen?

Axis v7 §3, rung three, and the first rung that is about TRANSFER rather than about representation.
V7-0 said behaviour-derived coordinates carry signal; V7-1 said the signal survives projection into
the hyperdimensional space. Neither says anything crosses from one region of that space to another,
which is the entire point of having one space.

WHAT IS FITTED, and why it is the weakest thing that could count. A direction: the difference of the
two kinds' mean hypervectors, normalised. Nothing is trained, nothing is tuned, there is no
objective to overfit -- it is a subtraction. If even that carries across, the space has structure
shared between regions; if a subtraction does not carry, nothing heavier was going to.

THE PAIRS ARE NOT CHOSEN. Every training-kind pair is fitted, and each is scored on every held-out
kind pair. Choosing which contrast to fit and which to test on is precisely how a transfer result
gets manufactured -- pick "artifact vs place" on both sides and the answer is decided before the
run. The mean over all combinations is the reading; the best single combination is reported too, as
information rather than as the result.

DIRECTION-AGNOSTIC SEPARATION. A direction that puts the held-out kinds on the opposite sides from
the training kinds still SEPARATES them, and separation is the claim. So the score is
max(AUC, 1 - AUC): 0.5 is chance, 1.0 is perfect, and which way round is not part of the question.

THE CONTROL IS A RANDOM DIRECTION in the same space, scored the same way. In high dimensions two
tight clusters can be separated by many directions, so "some direction separates them" is nearly
free -- the control is what says whether the FITTED direction did better than luck.

PRE-REGISTERED, written before the first run: mean separation over all combinations >= 0.65 AND
strictly above the random-direction control.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Sequence

from packages.substrate.behaviour import Behaviour
from packages.substrate.holo import project

SEPARATION_GATE = 0.65


def _mean_vec(members: Sequence[Behaviour], basis: Sequence[str]):
    import numpy as np
    vs = [project(b, basis) for b in members]
    vs = [v for v in vs if v is not None]
    if not vs:
        return None
    m = np.mean(vs, axis=0)
    n = np.linalg.norm(m)
    return m / n if n > 0 else None


def fit_direction(kind_a: Sequence[Behaviour], kind_b: Sequence[Behaviour],
                  basis: Sequence[str]):
    """The difference of the two kinds' means. A subtraction, not a fit with an objective."""
    import numpy as np
    ma, mb = _mean_vec(kind_a, basis), _mean_vec(kind_b, basis)
    if ma is None or mb is None:
        return None
    d = ma - mb
    n = np.linalg.norm(d)
    return d / n if n > 0 else None


def separation(direction, kind_a: Sequence[Behaviour], kind_b: Sequence[Behaviour],
               basis: Sequence[str]) -> float:
    """max(AUC, 1-AUC) of the two kinds' projections onto the direction. 0.5 is chance."""
    import numpy as np
    if direction is None:
        return 0.5
    sa = [float(np.real(np.vdot(direction, v))) for v in
          (project(b, basis) for b in kind_a) if v is not None]
    sb = [float(np.real(np.vdot(direction, v))) for v in
          (project(b, basis) for b in kind_b) if v is not None]
    if not sa or not sb:
        return 0.5
    wins = sum(1.0 if x > y else 0.5 if x == y else 0.0 for x in sa for y in sb)
    auc = wins / (len(sa) * len(sb))
    return max(auc, 1.0 - auc)


@dataclass(frozen=True)
class TransferReading:
    fitted_pairs: int
    tested_pairs: int
    combinations: int
    mean_separation: float
    best_separation: float
    control_mean: float
    gate: float = SEPARATION_GATE
    best_where: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return self.mean_separation >= self.gate and self.mean_separation > self.control_mean

    def as_dict(self) -> dict[str, Any]:
        return {"fitted_pairs": self.fitted_pairs, "tested_pairs": self.tested_pairs,
                "combinations": self.combinations,
                "mean_separation": round(self.mean_separation, 4),
                "best_separation": round(self.best_separation, 4),
                "control_mean": round(self.control_mean, 4),
                "gate": self.gate, "passed": self.passed, "best_where": self.best_where,
                "notes": list(self.notes)}


def read_transfer(train_kinds: dict[str, list[Behaviour]],
                  held_kinds: dict[str, list[Behaviour]],
                  basis: Sequence[str], *, control_dirs: int = 24) -> TransferReading:
    """Every fitted pair against every unseen pair. No combination is selected."""
    import numpy as np

    fits = [(f"{a}|{b}", fit_direction(train_kinds[a], train_kinds[b], basis))
            for a, b in combinations(sorted(train_kinds), 2)]
    fits = [(n, d) for n, d in fits if d is not None]
    tests = list(combinations(sorted(held_kinds), 2))

    scores, best, where = [], 0.0, ""
    for fname, d in fits:
        for a, b in tests:
            s = separation(d, held_kinds[a], held_kinds[b], basis)
            scores.append(s)
            if s > best:
                best, where = s, f"{fname} -> {a}|{b}"

    # control: random unit directions in the same space, scored identically. Deterministic seed --
    # a chosen seed is one more thing that could be picked after seeing the result.
    dim = len(next((v for v in (project(b, basis)
                                for k in held_kinds.values() for b in k) if v is not None), []))
    rng = np.random.default_rng(20260729)
    ctrl = []
    for _ in range(control_dirs):
        r = rng.normal(size=dim) + 1j * rng.normal(size=dim)
        r = r / np.linalg.norm(r)
        for a, b in tests:
            ctrl.append(separation(r, held_kinds[a], held_kinds[b], basis))

    return TransferReading(
        fitted_pairs=len(fits), tested_pairs=len(tests), combinations=len(scores),
        mean_separation=float(np.mean(scores)) if scores else 0.5,
        best_separation=best,
        control_mean=float(np.mean(ctrl)) if ctrl else 0.5,
        best_where=where,
        notes=("direction is a subtraction of means, not a trained fit",
               "no combination selected: all fitted pairs x all unseen pairs",
               "score is max(AUC, 1-AUC): separation, not orientation"))
