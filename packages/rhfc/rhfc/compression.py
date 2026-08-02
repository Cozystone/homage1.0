"""Compression utilities for RHFC hypervector storage.

The functions here measure storage boundaries without changing the core RHFC
math.  They compress stored vectors and reconstruct them for cleanup-memory
experiments so Stage 4 can report where precision/dimension reduction starts
to matter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from .hypervector import HyperVector

Precision = Literal["fp64", "fp32", "int8", "binary"]


@dataclass(frozen=True)
class CompressionSpec:
    """Hypervector storage compression setting."""

    dim: int
    precision: Precision

    def bytes_per_vector(self) -> float:
        """Return packed storage bytes per vector for this spec."""

        if self.precision == "fp64":
            return float(self.dim * 8)
        if self.precision == "fp32":
            return float(self.dim * 4)
        if self.precision == "int8":
            return float(self.dim)
        if self.precision == "binary":
            return float((self.dim + 7) // 8)
        raise ValueError(f"unsupported precision: {self.precision}")

    def gib_for_vectors(self, count: int) -> float:
        """Return GiB required to store ``count`` vectors."""

        return (float(count) * self.bytes_per_vector()) / float(1024**3)


def downsample_vector(vector: HyperVector, dim: int) -> HyperVector:
    """Reduce dimensionality by deterministic striding.

    This is intentionally simple and measurable.  It is not a learned
    projection, and therefore does not add hidden model state.
    """

    if dim <= 0:
        raise ValueError("dim must be positive")
    if dim > vector.dim:
        raise ValueError("target dim cannot exceed source dim")
    if dim == vector.dim:
        return vector
    indices = np.linspace(0, vector.dim - 1, num=dim, dtype=np.int64)
    return HyperVector(vector.values[indices], vector.kind).normalized()


def compress_values(values: NDArray[np.floating], precision: Precision) -> NDArray[np.generic]:
    """Compress real values into the requested storage precision."""

    real = np.asarray(values, dtype=np.float64)
    if precision == "fp64":
        return real.astype(np.float64)
    if precision == "fp32":
        return real.astype(np.float32)
    if precision == "int8":
        clipped = np.clip(real, -1.0, 1.0)
        return np.rint(clipped * 127.0).astype(np.int8)
    if precision == "binary":
        bits = (real >= 0.0).astype(np.uint8)
        return np.packbits(bits)
    raise ValueError(f"unsupported precision: {precision}")


def decompress_values(payload: NDArray[np.generic], spec: CompressionSpec) -> NDArray[np.float64]:
    """Reconstruct a float64 vector from a compressed payload."""

    if spec.precision == "fp64":
        return np.asarray(payload, dtype=np.float64)
    if spec.precision == "fp32":
        return np.asarray(payload, dtype=np.float32).astype(np.float64)
    if spec.precision == "int8":
        return np.asarray(payload, dtype=np.int8).astype(np.float64) / 127.0
    if spec.precision == "binary":
        unpacked = np.unpackbits(np.asarray(payload, dtype=np.uint8))[: spec.dim]
        return np.where(unpacked > 0, 1.0, -1.0).astype(np.float64)
    raise ValueError(f"unsupported precision: {spec.precision}")


def compress_hypervector(vector: HyperVector, spec: CompressionSpec) -> NDArray[np.generic]:
    """Downsample and compress a hypervector."""

    reduced = downsample_vector(vector, spec.dim)
    return compress_values(np.real(reduced.values), spec.precision)


def decompress_hypervector(payload: NDArray[np.generic], spec: CompressionSpec) -> HyperVector:
    """Decompress a payload into a normalized bipolar hypervector."""

    return HyperVector(decompress_values(payload, spec), "bipolar").normalized()


def compressed_matrix(patterns: list[HyperVector], spec: CompressionSpec) -> NDArray[np.float64]:
    """Return decompressed matrix rows for cleanup-memory evaluation."""

    rows = [decompress_values(compress_hypervector(pattern, spec), spec) for pattern in patterns]
    matrix = np.vstack(rows).astype(np.float64)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)
