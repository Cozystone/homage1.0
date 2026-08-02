"""Modern Hopfield cleanup memory for hypervectors."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .hypervector import HyperVector


def _softmax(x: NDArray[np.floating]) -> NDArray[np.floating]:
    shifted = x - np.max(x)
    exp = np.exp(shifted)
    denom = np.sum(exp)
    return exp / max(float(denom), 1e-12)


@dataclass
class ModernHopfieldMemory:
    """Single-step modern Hopfield associative memory.

    Recall uses z = V^T softmax(beta * V * xi), where rows of V are stored
    normalized patterns and xi is the query vector.
    """

    patterns: NDArray[np.float64]

    @classmethod
    def store(cls, patterns: list[HyperVector]) -> "ModernHopfieldMemory":
        """Create a cleanup memory from hypervectors."""

        if not patterns:
            raise ValueError("at least one pattern is required")
        dim = patterns[0].dim
        if any(pattern.dim != dim for pattern in patterns):
            raise ValueError("all patterns must share dimension")
        rows = []
        for pattern in patterns:
            real = np.real(pattern.values).astype(np.float64)
            norm = np.linalg.norm(real)
            rows.append(real / max(float(norm), 1e-12))
        return cls(np.vstack(rows))

    def recall(self, query: HyperVector, beta: float = 16.0) -> HyperVector:
        """Recall the closest stored pattern in one Hopfield update."""

        q = np.real(query.values).astype(np.float64)
        q = q / max(float(np.linalg.norm(q)), 1e-12)
        weights = _softmax(float(beta) * (self.patterns @ q))
        recalled = self.patterns.T @ weights
        return HyperVector(recalled, "bipolar").normalized()

    def nearest_index(self, query: HyperVector) -> int:
        """Return the index of the stored pattern closest to query."""

        q = np.real(query.values)
        q = q / max(float(np.linalg.norm(q)), 1e-12)
        return int(np.argmax(self.patterns @ q))
