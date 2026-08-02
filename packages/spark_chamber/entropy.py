from __future__ import annotations

import os
import random
import time


def make_deterministic_entropy(seed: int | None) -> random.Random:
    """Return reproducible pseudo-random entropy for proof tests."""

    return random.Random(0 if seed is None else seed)


def collect_environmental_entropy(disabled_by_default: bool = True) -> dict[str, object]:
    """Collect optional bounded jitter metadata; disabled by default."""

    if disabled_by_default:
        return {"enabled": False, "value": 0.0, "notes": ["environmental entropy disabled by default"]}
    start = time.perf_counter_ns()
    _ = os.urandom(1)
    elapsed = time.perf_counter_ns() - start
    return {"enabled": True, "value": normalize_entropy(elapsed), "notes": ["bounded local jitter sample"]}


def normalize_entropy(value: int | float) -> float:
    """Normalize a numeric jitter value into [0, 1]."""

    return abs(float(value) % 10000.0) / 10000.0
