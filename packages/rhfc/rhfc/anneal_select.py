"""Standalone simulated annealing selector for RHFC candidate subsets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class AnnealSelection:
    """Selected subset and final QUBO energy."""

    selected: list[int]
    energy: float
    iterations: int


def qubo_energy(x: NDArray[np.integer], q: NDArray[np.floating], bias: NDArray[np.floating] | None = None) -> float:
    """Return binary QUBO energy x^T Q x + bias^T x."""

    vec = x.astype(np.float64)
    value = float(vec @ q @ vec)
    if bias is not None:
        value += float(np.asarray(bias, dtype=np.float64) @ vec)
    return value


def anneal_select(
    candidates: Sequence[object],
    compatibility: NDArray[np.floating],
    *,
    bias: NDArray[np.floating] | None = None,
    iterations: int = 2_000,
    initial_temp: float = 2.0,
    final_temp: float = 0.02,
    seed: int = 0,
) -> AnnealSelection:
    """Select a low-energy subset from candidates using simulated annealing.

    The compatibility matrix is interpreted as a QUBO matrix; lower energy is
    better. Negative diagonal/bias terms encourage selection, positive pairwise
    terms discourage incompatible combinations.
    """

    n = len(candidates)
    q = np.asarray(compatibility, dtype=np.float64)
    if q.shape != (n, n):
        raise ValueError("compatibility matrix must be square with len(candidates)")
    rng = np.random.default_rng(seed)
    x = rng.integers(0, 2, size=n, dtype=np.int8)
    if not np.any(x) and n:
        x[rng.integers(0, n)] = 1
    current = qubo_energy(x, q, bias)
    best_x = x.copy()
    best_energy = current
    for step in range(1, int(iterations) + 1):
        t = initial_temp * ((final_temp / initial_temp) ** (step / max(1, iterations)))
        idx = int(rng.integers(0, n))
        trial = x.copy()
        trial[idx] = 1 - trial[idx]
        trial_energy = qubo_energy(trial, q, bias)
        delta = trial_energy - current
        if delta <= 0.0 or rng.random() < np.exp(-delta / max(t, 1e-12)):
            x = trial
            current = trial_energy
            if current < best_energy:
                best_x = x.copy()
                best_energy = current
    return AnnealSelection([i for i, value in enumerate(best_x.tolist()) if value], float(best_energy), int(iterations))
