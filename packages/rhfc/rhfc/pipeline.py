"""RHFC binding pipeline with cleanup memory.

This module is intentionally independent of q_cortex/cortex_g2. It gives Stage
2 a bounded way to evaluate whether multi-step HRR binding is useful after
cleanup memory removes residual unbinding noise.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cleanup_memory import ModernHopfieldMemory
from .fft_binding import bind, unbind
from .hypervector import HyperVector, cosine_similarity


@dataclass(frozen=True)
class BindingStore:
    """Composite binding plus cleanup memory for candidate values."""

    composite: HyperVector
    keys: list[HyperVector]
    memory: ModernHopfieldMemory
    candidates: list[HyperVector]


@dataclass(frozen=True)
class CleanupQueryResult:
    """Recovered noisy vector, cleaned vector, and nearest candidate index."""

    noisy: HyperVector
    cleaned: HyperVector
    nearest_index: int
    target_cosine: float | None = None


def bind_value_with_keys(value: HyperVector, keys: list[HyperVector]) -> HyperVector:
    """Bind one value through an ordered list of keys."""

    composite = value
    for key in keys:
        composite = bind(composite, key)
    return composite


def unbind_value_with_keys(composite: HyperVector, keys: list[HyperVector]) -> HyperVector:
    """Undo ordered multi-key binding by unbinding in reverse key order."""

    estimate = composite
    for key in reversed(keys):
        estimate = unbind(estimate, key)
    return estimate


def bind_and_store(value: HyperVector, keys: list[HyperVector], candidates: list[HyperVector]) -> BindingStore:
    """Create a multi-bind composite and cleanup memory over candidates."""

    if not candidates:
        raise ValueError("candidates are required for cleanup")
    if value.dim != candidates[0].dim:
        raise ValueError("value and candidates must share dimension")
    return BindingStore(
        composite=bind_value_with_keys(value, keys),
        keys=list(keys),
        memory=ModernHopfieldMemory.store(candidates),
        candidates=list(candidates),
    )


def query_and_cleanup(
    composite: HyperVector,
    keys: list[HyperVector],
    memory: ModernHopfieldMemory,
    *,
    target: HyperVector | None = None,
    beta: float = 32.0,
) -> CleanupQueryResult:
    """Recover a value from a composite, then clean it with Hopfield memory."""

    noisy = unbind_value_with_keys(composite, keys)
    cleaned = memory.recall(noisy, beta=beta)
    nearest = memory.nearest_index(cleaned)
    target_cosine = cosine_similarity(target, cleaned) if target is not None else None
    return CleanupQueryResult(noisy=noisy, cleaned=cleaned, nearest_index=nearest, target_cosine=target_cosine)
