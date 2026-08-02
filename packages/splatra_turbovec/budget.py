from __future__ import annotations

from typing import Any


CLIENT_BUDGETS: dict[str, dict[str, int]] = {
    "low": {"max_particles": 20_000, "max_chunk_bytes": 2 * 1024 * 1024},
    "medium": {"max_particles": 100_000, "max_chunk_bytes": 12 * 1024 * 1024},
    "high": {"max_particles": 500_000, "max_chunk_bytes": 64 * 1024 * 1024},
    "ultra": {"max_particles": 2_000_000, "max_chunk_bytes": 256 * 1024 * 1024},
}


def estimate_scene_budget(total_particles: int, compressed_bytes: int) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, budget in CLIENT_BUDGETS.items():
        particle_fraction = min(1.0, budget["max_particles"] / max(1, total_particles))
        byte_fraction = min(1.0, budget["max_chunk_bytes"] / max(1, compressed_bytes))
        allowed_fraction = min(particle_fraction, byte_fraction)
        result[name] = {
            **budget,
            "fits_full_scene": total_particles <= budget["max_particles"] and compressed_bytes <= budget["max_chunk_bytes"],
            "recommended_particle_budget": int(total_particles * allowed_fraction),
            "recommended_fraction": round(allowed_fraction, 4),
        }
    return result
