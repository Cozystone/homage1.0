# -*- coding: utf-8 -*-
"""Device profile + OOM-resilient execution — stable on modest local GPUs.

Owner requirement (2026-07-09): GPU acceleration is great, but LOCAL operation
must be stable on average / low-end hardware — an RTX 4060 (8 GB), an AMD
Radeon (no CUDA on Windows torch), an older NVIDIA Quadro (little VRAM). None
of the accelerated paths may assume the 17 GB dev card.

Three guarantees this module provides:
  * PROBE, don't assume — read free VRAM and pick work-block sizes proportional
    to it, so an 8 GB card gets small blocks and a 24 GB card gets big ones;
  * DEGRADE, never crash — a CUDA out-of-memory is caught and the block is
    HALVED and retried (down to a floor), so a too-dense chunk shrinks instead
    of killing the run;
  * ALWAYS have a CPU path — no CUDA (Radeon/Quadro-without-CUDA/no GPU) simply
    runs the identical CPU code; the answer is the same, only slower.
"""
from __future__ import annotations

from typing import Any, Callable

try:
    import torch
    _HAVE_TORCH = True
except Exception:  # pragma: no cover
    torch = None
    _HAVE_TORCH = False


def profile() -> dict[str, Any]:
    """What are we running on, and how much room is there? Never raises."""
    if not (_HAVE_TORCH and torch.cuda.is_available()):
        return {"backend": "cpu", "name": "cpu", "total_vram_gb": 0.0,
                "free_vram_gb": 0.0, "tier": "cpu"}
    try:
        free_b, total_b = torch.cuda.mem_get_info()
        free_gb, total_gb = free_b / 1e9, total_b / 1e9
        name = torch.cuda.get_device_name(0)
    except Exception:
        free_gb = total_gb = 0.0
        name = "cuda"
    tier = ("high" if total_gb >= 12 else "mid" if total_gb >= 6 else "low")
    return {"backend": "cuda", "name": name, "total_vram_gb": round(total_gb, 1),
            "free_vram_gb": round(free_gb, 1), "tier": tier}


def safe_block(free_vram_gb: float, *, high: int = 8000, mid: int = 3000,
               low: int = 1000, cpu: int = 0) -> int:
    """Rows-per-block for a chunked GPU op, scaled to FREE VRAM. Conservative
    on purpose — a stable small block beats an OOM. 0 means 'no GPU' (CPU)."""
    if free_vram_gb <= 0:
        return cpu
    if free_vram_gb >= 8:
        return high
    if free_vram_gb >= 4:
        return mid
    if free_vram_gb >= 2:
        return low
    return max(400, low // 2)


def is_cuda_oom(exc: Exception) -> bool:
    msg = str(exc).lower()
    return ("out of memory" in msg or "insufficient resources" in msg
            or "cuda error" in msg or "cublas" in msg or "cusparse" in msg)


def with_oom_backoff(fn: Callable[[int], Any], start_block: int, *,
                     min_block: int = 400) -> Any:
    """Run fn(block); on a CUDA OOM, empty the cache, HALVE the block, retry —
    down to min_block. Raises only if even min_block can't fit. This is the
    'degrade, never crash' guarantee for a single-shot op."""
    block = max(min_block, start_block)
    last: Exception | None = None
    while block >= min_block:
        try:
            return fn(block)
        except RuntimeError as e:            # torch OOM is a RuntimeError
            if not is_cuda_oom(e):
                raise
            last = e
            if _HAVE_TORCH:
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
            block //= 2
    if last:
        raise last
    return None
