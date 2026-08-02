from __future__ import annotations

import numpy as np

from rhfc.cleanup_memory import ModernHopfieldMemory
from rhfc.hypervector import HyperVector, cosine_similarity, random_bipolar


def test_hopfield_recalls_noisy_pattern() -> None:
    patterns = [random_bipolar(1024, seed=i) for i in range(24)]
    memory = ModernHopfieldMemory.store(patterns)
    target = patterns[5]
    noisy = target.values.copy()
    noisy[:80] *= -1.0
    recalled = memory.recall(HyperVector(noisy, "bipolar"), beta=24.0)
    assert memory.nearest_index(recalled) == 5
    assert cosine_similarity(target, recalled) > 0.75


def test_hopfield_store_rejects_empty_patterns() -> None:
    try:
        ModernHopfieldMemory.store([])
    except ValueError as exc:
        assert "at least one" in str(exc)
    else:
        raise AssertionError("expected ValueError")
