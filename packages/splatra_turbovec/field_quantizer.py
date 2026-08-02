"""Data-calibrated per-field quantizer for ATANOR node physical state.

This is the TurboQuant *principle*, decomposed and re-applied to ATANOR's native
representation — NOT a port of turbovec, and NOT for learned embeddings (ATANOR has
none). A node's numeric state is 6 floats: position(x, y, z) + amplitude + phase +
frequency (see ``packages/holographic_fold/folding.py``). At trillion scale, storing
those as float32 costs 24 B/node = 24 TB at 1e12 nodes.

What we take from TurboQuant (and only this):
  1. **Calibrate to the empirical distribution.** A Lloyd-Max codebook per field puts
     the available bits where the data actually is (TurboQuant's data-oblivious idea,
     realised here as 1-D Lloyd's algorithm / k-means).
  2. **Quantize + bit-pack** each field to a few bits → a few bytes/node.
  3. **Dequantize via centroids** for round-trip / compute-on-codes.

Deterministic, numpy, CPU. A pure storage codec: it never invents node state, and it
carries an explicit per-field distortion so nothing is passed off as exact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np


# The six physical fields an ATANOR node carries (folding.py). Phase is cyclic.
NODE_FIELDS: tuple[str, ...] = ("x", "y", "z", "amplitude", "phase", "frequency")
CYCLIC_FIELDS: frozenset[str] = frozenset({"phase"})
# Log-domain quantization is available (set per-field) and minimises *relative* error —
# useful when ratios matter. The default node codec measures/optimises LINEAR distortion,
# where data-calibrated Lloyd-Max already handles skew, so the default uses linear domain.
LOG_FIELDS: frozenset[str] = frozenset()
TWO_PI = 2.0 * math.pi
_LOG_EPS = 1e-9

# A balanced default bit budget (52 bits = 7 bytes/node vs 24 → ~3.4x). Position
# needs the most precision; phase is cyclic and 8 bits ≈ 0.025 rad.
DEFAULT_BITS: dict[str, int] = {
    "x": 10, "y": 10, "z": 10, "amplitude": 8, "phase": 8, "frequency": 8,
}


@dataclass(frozen=True)
class FieldCodebook:
    """Calibrated scalar codebook for one field."""

    bits: int
    centroids: np.ndarray        # (levels,) bucket representative values (in working domain)
    boundaries: np.ndarray       # (levels-1,) internal cut points (working domain)
    cyclic: bool = False
    period: float = TWO_PI
    log_domain: bool = False     # centroids/boundaries live in log space; (de)quant uses exp

    @property
    def levels(self) -> int:
        return 1 << self.bits


def fit_field(
    values: Sequence[float] | np.ndarray,
    bits: int,
    *,
    cyclic: bool = False,
    log_domain: bool = False,
    iters: int = 12,
) -> FieldCodebook:
    """Fit a Lloyd-Max codebook to the empirical distribution of one field."""
    if bits < 1 or bits > 16:
        raise ValueError("bits must be in 1..16")
    levels = 1 << bits
    v = np.asarray(values, dtype=np.float64).ravel()

    if cyclic:
        # Uniform on the circle is MSE-optimal for ~uniform phase; centroids at bin centres.
        edges = np.linspace(0.0, TWO_PI, levels + 1)
        centroids = (edges[:-1] + edges[1:]) * 0.5
        return FieldCodebook(bits, centroids, edges[1:-1].copy(), True, TWO_PI)

    if log_domain:
        v = np.log(np.maximum(v, _LOG_EPS))

    if v.size == 0:
        centroids = np.zeros(levels, dtype=np.float64)
        return FieldCodebook(bits, centroids, np.zeros(levels - 1), False, TWO_PI, log_domain)

    lo, hi = float(v.min()), float(v.max())
    # Lloyd's algorithm only finds a LOCAL optimum and can get stuck on heavy tails.
    # Run it from two inits and keep the better one:
    #   - uniform-in-value: Lloyd monotonically decreases MSE, so this can NEVER end
    #     worse than the plain uniform quantizer (our floor guarantee).
    #   - quantile-span: denser centroids where the data is dense (often better).
    cand_uniform = _lloyd(v, levels, np.linspace(lo, hi, levels), iters)
    cand_quantile = _lloyd(v, levels, np.quantile(v, np.linspace(0.0, 1.0, levels)), iters)
    centroids = cand_uniform if _mse(v, cand_uniform) <= _mse(v, cand_quantile) else cand_quantile
    boundaries = (centroids[:-1] + centroids[1:]) * 0.5
    return FieldCodebook(bits, centroids, boundaries, False, TWO_PI, log_domain)


def _lloyd(v: np.ndarray, levels: int, init: np.ndarray, iters: int) -> np.ndarray:
    """Lloyd's algorithm (1-D k-means) from an explicit centroid init."""
    centroids = _ensure_increasing(np.asarray(init, dtype=np.float64), levels)
    for _ in range(iters):
        boundaries = (centroids[:-1] + centroids[1:]) * 0.5
        idx = np.searchsorted(boundaries, v, side="right")
        sums = np.bincount(idx, weights=v, minlength=levels)[:levels]
        counts = np.bincount(idx, minlength=levels)[:levels]
        new = centroids.copy()
        nonempty = counts > 0
        new[nonempty] = sums[nonempty] / counts[nonempty]
        new = _ensure_increasing(new, levels)
        if np.allclose(new, centroids, rtol=0, atol=1e-12):
            return new
        centroids = new
    return centroids


def _mse(v: np.ndarray, centroids: np.ndarray) -> float:
    boundaries = (centroids[:-1] + centroids[1:]) * 0.5
    idx = np.searchsorted(boundaries, v, side="right")
    recon = centroids[np.clip(idx, 0, len(centroids) - 1)]
    return float(np.mean((v - recon) ** 2))


def _ensure_increasing(centroids: np.ndarray, levels: int) -> np.ndarray:
    """Keep a strictly-increasing, correct-length centroid vector (empty buckets / ties)."""
    c = np.sort(np.asarray(centroids, dtype=np.float64))
    # nudge exact duplicates apart so searchsorted stays well-defined
    for i in range(1, len(c)):
        if c[i] <= c[i - 1]:
            c[i] = np.nextafter(c[i - 1], np.inf)
    if len(c) < levels:
        pad = np.full(levels - len(c), c[-1] if len(c) else 0.0)
        c = np.concatenate([c, pad])
    return c[:levels]


def quantize_field(cb: FieldCodebook, values: Sequence[float] | np.ndarray) -> np.ndarray:
    v = np.asarray(values, dtype=np.float64).ravel()
    if cb.cyclic:
        vv = np.mod(v, cb.period)
        codes = np.floor(vv / cb.period * cb.levels).astype(np.int64)
        return np.clip(codes, 0, cb.levels - 1)
    if cb.log_domain:
        v = np.log(np.maximum(v, _LOG_EPS))
    return np.clip(np.searchsorted(cb.boundaries, v, side="right"), 0, cb.levels - 1).astype(np.int64)


def dequantize_field(cb: FieldCodebook, codes: Sequence[int] | np.ndarray) -> np.ndarray:
    idx = np.clip(np.asarray(codes, dtype=np.int64), 0, cb.levels - 1)
    out = cb.centroids[idx]
    return np.exp(out) if cb.log_domain else out


@dataclass
class NodeFieldCodec:
    """Per-field codec for the 6-float node state, with an explicit byte budget."""

    bits: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_BITS))
    codebooks: dict[str, FieldCodebook] = field(default_factory=dict)

    @property
    def bits_per_node(self) -> int:
        return sum(self.bits[f] for f in NODE_FIELDS)

    @property
    def bytes_per_node(self) -> float:
        return self.bits_per_node / 8.0

    @property
    def compression_ratio(self) -> float:
        # vs float32 (4 bytes) per field
        return (4 * len(NODE_FIELDS)) / self.bytes_per_node

    def fit(self, columns: dict[str, np.ndarray]) -> "NodeFieldCodec":
        for f in NODE_FIELDS:
            self.codebooks[f] = fit_field(
                columns[f], self.bits[f],
                cyclic=(f in CYCLIC_FIELDS),
                log_domain=(f in LOG_FIELDS),
            )
        return self

    def encode(self, columns: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        return {f: quantize_field(self.codebooks[f], columns[f]) for f in NODE_FIELDS}

    def decode(self, codes: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        return {f: dequantize_field(self.codebooks[f], codes[f]) for f in NODE_FIELDS}

    def round_trip(self, columns: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        return self.decode(self.encode(columns))

    def distortion(self, columns: dict[str, np.ndarray]) -> dict[str, float]:
        """Per-field RMSE normalised by field spread (cyclic-aware for phase)."""
        recon = self.round_trip(columns)
        out: dict[str, float] = {}
        for f in NODE_FIELDS:
            orig = np.asarray(columns[f], dtype=np.float64).ravel()
            rec = np.asarray(recon[f], dtype=np.float64).ravel()
            if f in CYCLIC_FIELDS:
                err = np.angle(np.exp(1j * (orig - rec)))  # wraparound-correct residual
                scale = TWO_PI
            else:
                err = orig - rec
                scale = max(float(orig.std()), 1e-12)
            out[f] = float(np.sqrt(np.mean(err * err)) / scale)
        return out
