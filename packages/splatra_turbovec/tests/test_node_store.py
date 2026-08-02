"""Guards the RAM-boundedness + fidelity of the disk-backed quantized node store —
the measured " " property: peak scan memory is bounded by the window,
INDEPENDENT of node count N, so a fixed-RAM PC serves an arbitrarily large graph."""

from __future__ import annotations

import tracemalloc

import numpy as np

from packages.splatra_turbovec.field_quantizer import NODE_FIELDS
from packages.splatra_turbovec.node_store import QuantizedNodeStore


def _columns(n: int, seed: int = 0) -> dict[str, np.ndarray]:
    """Field-appropriate synthetic node state: position is linear, amplitude in [0,1],
    phase cyclic in [0,2pi), frequency positive (log domain) — matching the codec's
    per-field treatment so round-trip error reflects the quantizer, not bad inputs."""
    rng = np.random.default_rng(seed)
    two_pi = 2.0 * np.pi
    return {
        "x": rng.standard_normal(n).astype(np.float64),
        "y": rng.standard_normal(n).astype(np.float64),
        "z": rng.standard_normal(n).astype(np.float64),
        "amplitude": rng.uniform(0.0, 1.0, n).astype(np.float64),
        "phase": rng.uniform(0.0, two_pi, n).astype(np.float64),
        "frequency": rng.uniform(0.1, 10.0, n).astype(np.float64),
    }


def _scan_peak_bytes(store: QuantizedNodeStore, window: int) -> int:
    tracemalloc.start()
    for _s, _e, _c in store.scan_windows(window):
        pass
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def test_scan_peak_memory_is_flat_across_N(tmp_path):
    """Peak scan memory at N=500k must be within a small factor of N=50k — bounded by
    the window, not N. (Baseline full-load would be ~10x from 50k->500k.)"""
    window = 4096
    small = QuantizedNodeStore.build(tmp_path / "s_small", _columns(50_000))
    large = QuantizedNodeStore.build(tmp_path / "s_large", _columns(500_000))
    peak_small = _scan_peak_bytes(small, window)
    peak_large = _scan_peak_bytes(large, window)
    # 10x more nodes must NOT grow peak scan memory beyond a tiny bookkeeping margin.
    assert peak_large <= peak_small * 1.5, (peak_small, peak_large)
    # And the absolute peak is window-sized, not N-sized (well under 5 MB for 4096 nodes).
    assert peak_large < 5_000_000


def test_disk_grows_linearly_and_bytes_per_node_constant(tmp_path):
    a = QuantizedNodeStore.build(tmp_path / "a", _columns(20_000))
    b = QuantizedNodeStore.build(tmp_path / "b", _columns(200_000))
    bpn_a = a.disk_bytes() / a.n
    bpn_b = b.disk_bytes() / b.n
    assert abs(bpn_a - bpn_b) < 1e-6          # constant bytes/node
    assert b.disk_bytes() > a.disk_bytes() * 9  # ~10x nodes -> ~10x disk
    assert bpn_b < 12                            # far under float32's 24 B/node


def test_roundtrip_fidelity_within_quantizer_error(tmp_path):
    cols = _columns(40_000, seed=3)
    store = QuantizedNodeStore.build(tmp_path / "rt", cols)
    # Reassemble decoded columns from the bounded windows and compare to source.
    decoded = {f: np.empty(store.n, dtype=np.float64) for f in NODE_FIELDS}
    for start, end, win in store.scan_windows(4096):
        for f in NODE_FIELDS:
            decoded[f][start:end] = win[f]
    for f in NODE_FIELDS:
        rng = float(cols[f].max() - cols[f].min()) or 1.0
        rmse = float(np.sqrt(np.mean((decoded[f] - cols[f]) ** 2)))
        assert rmse / rng < 0.05, (f, rmse / rng)  # <5% normalized RMSE
