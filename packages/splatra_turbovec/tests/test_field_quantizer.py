"""Distortion + byte-budget golden tests for the node field quantizer.

Locks the trillion-scale promise: a node's 6-float physical state round-trips within a
bounded per-field distortion at a few bytes/node, and the codebook is calibrated to the
data (Lloyd-Max) rather than a fixed uniform range.
"""

from __future__ import annotations

import numpy as np

from packages.splatra_turbovec.field_quantizer import (
    DEFAULT_BITS,
    NODE_FIELDS,
    NodeFieldCodec,
    fit_field,
    quantize_field,
    dequantize_field,
)


def _synthetic_field(n: int, seed: int = 7) -> dict[str, np.ndarray]:
    """A realistic ATANOR node field: folded-geometry positions, skewed amplitude,
    uniform cyclic phase, log-spread frequency."""
    rng = np.random.default_rng(seed)
    return {
        "x": rng.normal(0.0, 1.5, n),
        "y": rng.normal(0.0, 1.5, n),
        "z": rng.normal(0.0, 1.2, n),
        "amplitude": rng.exponential(0.4, n),          # skewed, mostly small
        "phase": rng.uniform(0.0, 2 * np.pi, n),       # cyclic
        "frequency": np.exp(rng.normal(0.0, 0.5, n)),  # log-normal spread
    }


def test_round_trip_distortion_is_bounded() -> None:
    cols = _synthetic_field(200_000)
    codec = NodeFieldCodec().fit(cols)
    dist = codec.distortion(cols)
    # Measured ~0.27% on a 1M field; bound at 0.5% with margin (default 10/10/10/8/8/8).
    assert dist["x"] < 0.005 and dist["y"] < 0.005 and dist["z"] < 0.005, dist
    assert dist["amplitude"] < 0.02, dist     # exponential, 8-bit linear ≈ 1.6%
    assert dist["phase"] < 0.005, dist        # 8-bit cyclic ≈ 0.11% of 2π
    assert dist["frequency"] < 0.03, dist      # log-normal, 8-bit ≈ 2.4%
    assert max(dist.values()) < 0.03, dist


def test_byte_budget_and_compression() -> None:
    codec = NodeFieldCodec()
    assert codec.bits_per_node == sum(DEFAULT_BITS.values()) == 54
    assert codec.bytes_per_node == 6.75
    # vs 24 bytes (6 x float32)
    assert 3.5 < codec.compression_ratio < 3.6


def test_lloyd_beats_uniform_on_skewed_field() -> None:
    # Calibrated Lloyd-Max must beat a fixed-range uniform quantizer on skewed data.
    rng = np.random.default_rng(1)
    v = rng.exponential(0.4, 100_000)
    bits = 6
    cb = fit_field(v, bits)
    recon = dequantize_field(cb, quantize_field(cb, v))
    lloyd_rmse = float(np.sqrt(np.mean((v - recon) ** 2)))
    # uniform over [min,max]
    lo, hi = float(v.min()), float(v.max())
    levels = 1 << bits
    codes_u = np.clip(np.round((v - lo) / (hi - lo) * (levels - 1)), 0, levels - 1)
    recon_u = lo + codes_u / (levels - 1) * (hi - lo)
    uniform_rmse = float(np.sqrt(np.mean((v - recon_u) ** 2)))
    assert lloyd_rmse < uniform_rmse, (lloyd_rmse, uniform_rmse)


def test_codec_never_invents_state_shape() -> None:
    cols = _synthetic_field(1_000)
    codec = NodeFieldCodec().fit(cols)
    recon = codec.round_trip(cols)
    for f in NODE_FIELDS:
        assert recon[f].shape == cols[f].shape


def test_aggressive_budget_more_compression() -> None:
    aggressive = {"x": 8, "y": 8, "z": 8, "amplitude": 6, "phase": 8, "frequency": 4}
    codec = NodeFieldCodec(bits=aggressive)
    assert codec.bits_per_node == 42  # 5.25 bytes/node
    assert codec.compression_ratio > 4.5
