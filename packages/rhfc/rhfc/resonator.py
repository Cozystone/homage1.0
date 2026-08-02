"""Resonator-style factor recovery for bound role/filler pairs."""

from __future__ import annotations

from dataclasses import dataclass

from .cleanup_memory import ModernHopfieldMemory
from .fft_binding import bind, unbind
from .hypervector import HyperVector, bundle, cosine_similarity


@dataclass(frozen=True)
class ResonatorRecovery:
    """Recovered role/filler pair and convergence diagnostics."""

    role: str
    filler: str
    score: float
    iterations: int


def compose_role_filler_pairs(pairs: list[tuple[HyperVector, HyperVector]]) -> HyperVector:
    """Bind role/filler pairs and superpose them into one composite vector."""

    if not pairs:
        raise ValueError("at least one pair is required")
    return bundle([bind(role, filler) for role, filler in pairs])


def factorize_role_filler_pairs(
    composite: HyperVector,
    roles: dict[str, HyperVector],
    fillers: dict[str, HyperVector],
    *,
    max_iter: int = 6,
    threshold: float = 0.18,
) -> list[ResonatorRecovery]:
    """Recover likely role/filler pairs from a superposed HRR composite.

    Stage 1 uses a bounded coordinate-descent approximation: each known role is
    unbound from the composite, cleaned up against filler memory, then accepted
    if reconstructed binding still resonates with the composite.
    """

    if not roles or not fillers:
        return []
    memory = ModernHopfieldMemory.store(list(fillers.values()))
    filler_names = list(fillers.keys())
    recovered: list[ResonatorRecovery] = []
    for role_name, role_hv in roles.items():
        estimate = unbind(composite, role_hv)
        best_name = ""
        best_score = -1.0
        for iteration in range(1, max_iter + 1):
            cleaned = memory.recall(estimate, beta=18.0 + iteration)
            index = memory.nearest_index(cleaned)
            candidate_name = filler_names[index]
            candidate = fillers[candidate_name]
            score = cosine_similarity(bind(role_hv, candidate), composite)
            if score > best_score:
                best_name = candidate_name
                best_score = score
            estimate = candidate
        if best_score >= threshold:
            recovered.append(ResonatorRecovery(role_name, best_name, float(best_score), max_iter))
    return recovered
