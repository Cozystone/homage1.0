# -*- coding: utf-8 -*-
"""Device benchmark protocol — measure ONCE at startup, reuse everywhere.

Owner's ask (2026-07-09): for extreme efficiency, benchmark the machine's real
performance up front and let the engine pick its own CPU/GPU utilization ratios
from that, instead of a hardcoded split or a per-call probe. This caches a device
profile (CPU vs GPU provable-edges/sec, VRAM, cores) keyed by a hardware
signature; every accelerated path reads it. Re-benchmarks only when the hardware
signature changes or on force.

Aligned with the osaurus principle we adopted (quantizations/ratios curated to the
device) — but for OUR No-LLM closure kernels, not an LLM runtime.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np

CACHE = Path(__file__).resolve().parents[2] / "data" / "reasoning_vm" / "device_profile.json"


def _signature() -> dict[str, Any]:
    import os
    sig: dict[str, Any] = {"cpu_count": os.cpu_count() or 1, "gpu": None, "vram_gb": 0.0}
    try:
        import torch
        if torch.cuda.is_available():
            sig["gpu"] = torch.cuda.get_device_name(0)
            sig["vram_gb"] = round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1)
    except Exception:
        pass
    return sig


def _synthetic(n_nodes: int = 40_000, avg_deg: int = 4, seed: int = 7):
    """A random acyclic-ish graph to measure closure throughput device-agnostically."""
    from scipy import sparse
    rng = np.random.default_rng(seed)
    m = n_nodes * avg_deg
    s = rng.integers(0, n_nodes, m)
    o = rng.integers(0, n_nodes, m)
    keep = s < o                                    # i<j -> acyclic, sound transitive
    s, o = s[keep], o[keep]
    nodes = np.unique(np.concatenate([s, o]))
    N = len(nodes)
    si = np.searchsorted(nodes, s); oi = np.searchsorted(nodes, o)
    A = sparse.csr_matrix((np.ones(len(si), np.int8), (si, oi)), shape=(N, N))
    A.data[:] = 1
    stated = np.sort(si.astype(np.int64) * N + oi.astype(np.int64))
    return si, oi, N, A, stated


def benchmark(*, force: bool = False, log: Any = lambda *_: None) -> dict[str, Any]:
    """Measure CPU and GPU closure rates and cache the profile. Returns it."""
    sig = _signature()
    if not force and CACHE.exists():
        try:
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
            if cached.get("signature") == sig:
                return cached
        except Exception:
            pass

    from .closure_accelerator import _cpu_count_rows, _gpu_rows_count
    from .device import profile, safe_block

    si, oi, N, A, stated = _synthetic()
    probe = int(min(N - 1, max(256, N // 10)))
    prof = profile()
    have_gpu = prof["backend"] == "cuda"

    cpu_rate = gpu_rate = 0.0
    tc = time.time()
    _cpu_count_rows(A, stated, 0, probe, N)
    cpu_rate = probe / max(time.time() - tc, 1e-6)
    if have_gpu:
        block = safe_block(prof["free_vram_gb"]) or 4000
        _gpu_rows_count(si, oi, N, 0, probe, block)      # warm up (kernel/cache)
        tg = time.time()
        _gpu_rows_count(si, oi, N, 0, probe, block)
        gpu_rate = probe / max(time.time() - tg, 1e-6)

    total = cpu_rate + gpu_rate
    frac = gpu_rate / total if total > 0 else 0.0
    prof_out = {
        "signature": sig,
        "cpu_rows_per_s": round(cpu_rate),
        "gpu_rows_per_s": round(gpu_rate),
        "optimal_gpu_fraction": round(float(min(0.95, max(0.0, frac))), 3),
        "have_gpu": have_gpu,
        "backend": prof["backend"],
        "tier": prof.get("tier"),
        "benched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "note": "benchmark once, reuse — the split that makes CPU+GPU finish together",
    }
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(prof_out, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    log(f"device benchmark: cpu={prof_out['cpu_rows_per_s']:,}/s gpu={prof_out['gpu_rows_per_s']:,}/s "
        f"-> gpu_fraction={prof_out['optimal_gpu_fraction']}")
    return prof_out


def get_profile() -> dict[str, Any]:
    """Cached device profile (runs the benchmark once if absent/stale)."""
    return benchmark(force=False)


def optimal_gpu_fraction() -> float:
    """The device's balanced CPU/GPU split — measured once, reused."""
    return float(get_profile().get("optimal_gpu_fraction", 0.0))
