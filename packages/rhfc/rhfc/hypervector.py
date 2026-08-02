"""Hypervector primitives for RHFC Stage 1.

The implementation is deliberately small and deterministic: bipolar vectors
support VSA/HRR-style superposition and circular permutation, while complex
vectors provide a phase-friendly substrate for later resonance work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

import numpy as np
from numpy.typing import NDArray

VectorKind = Literal["bipolar", "complex"]


@dataclass(frozen=True)
class HyperVector:
    """A fixed-dimensional bipolar or complex hypervector.

    Attributes:
        values: One-dimensional NumPy array.
        kind: Vector family. Bipolar vectors use real values, complex vectors
            use complex phases/amplitudes.
    """

    values: NDArray[np.floating] | NDArray[np.complexfloating]
    kind: VectorKind = "bipolar"

    def __post_init__(self) -> None:
        arr = np.asarray(self.values)
        if arr.ndim != 1:
            raise ValueError("HyperVector values must be one-dimensional")
        if arr.size == 0:
            raise ValueError("HyperVector dimension must be positive")
        if self.kind not in {"bipolar", "complex"}:
            raise ValueError(f"Unsupported hypervector kind: {self.kind}")
        if self.kind == "complex":
            object.__setattr__(self, "values", arr.astype(np.complex128, copy=False))
        else:
            object.__setattr__(self, "values", arr.astype(np.float64, copy=False))

    @property
    def dim(self) -> int:
        """Return the dimensionality."""

        return int(self.values.size)

    def normalized(self) -> "HyperVector":
        """Return an L2-normalized copy, preserving vector kind."""

        norm = float(np.linalg.norm(self.values))
        if norm <= 1e-12:
            return self
        return HyperVector(self.values / norm, self.kind)

    def bipolarized(self) -> "HyperVector":
        """Return a bipolar sign vector useful for cleanup comparisons."""

        real = np.real(self.values)
        signs = np.where(real >= 0.0, 1.0, -1.0)
        return HyperVector(signs, "bipolar")


def _rng(seed: int | None) -> np.random.Generator:
    return np.random.default_rng(seed)


def random_bipolar(dim: int = 10_000, seed: int | None = None) -> HyperVector:
    """Create a deterministic random bipolar hypervector for a given seed."""

    if dim <= 0:
        raise ValueError("dim must be positive")
    values = _rng(seed).choice(np.array([-1.0, 1.0]), size=int(dim))
    return HyperVector(values, "bipolar")


def random_complex(dim: int = 10_000, seed: int | None = None) -> HyperVector:
    """Create a deterministic random unit-phase complex hypervector."""

    if dim <= 0:
        raise ValueError("dim must be positive")
    phases = _rng(seed).uniform(0.0, 2.0 * np.pi, size=int(dim))
    return HyperVector(np.exp(1j * phases), "complex")


def cosine_similarity(a: HyperVector, b: HyperVector) -> float:
    """Return real cosine similarity between two hypervectors."""

    if a.dim != b.dim:
        raise ValueError("dimension mismatch")
    av = np.ravel(a.values)
    bv = np.ravel(b.values)
    denom = float(np.linalg.norm(av) * np.linalg.norm(bv))
    if denom <= 1e-12:
        return 0.0
    return float(np.real(np.vdot(av, bv)) / denom)


def bundle(vectors: Iterable[HyperVector]) -> HyperVector:
    """Superpose vectors by summing and normalizing.

    Bipolar bundles are bipolarized after summation so they stay compact and
    cleanup-friendly. Complex bundles retain complex amplitudes.
    """

    items = list(vectors)
    if not items:
        raise ValueError("bundle requires at least one vector")
    dim = items[0].dim
    kind = items[0].kind
    if any(item.dim != dim for item in items):
        raise ValueError("all bundled vectors must share dimension")
    if any(item.kind != kind for item in items):
        raise ValueError("all bundled vectors must share kind")
    summed = np.sum([item.values for item in items], axis=0)
    hv = HyperVector(summed, kind)
    if kind == "bipolar":
        return hv.bipolarized()
    return hv.normalized()


def permute(v: HyperVector, shift: int) -> HyperVector:
    """Encode order by circularly shifting a hypervector."""

    return HyperVector(np.roll(v.values, int(shift)), v.kind)
