from __future__ import annotations

from typing import Any

from .generator import ImaginationGenerator
from .models import ARCHETYPES, ImaginationSeed, default_safety_flags


def run_imagination_proof(particle_budget: int = 900) -> dict[str, Any]:
    generator = ImaginationGenerator(max_particle_budget=10_000)
    results = []
    for index, archetype in enumerate(ARCHETYPES):
        seed = ImaginationSeed(
            seed_id=f"proof_{archetype}",
            archetype=archetype,
            randomness=0.31 + index * 0.03,
            valence=0.1,
            arousal=0.55,
            curiosity=0.62,
            particle_budget=particle_budget,
            created_at="2026-01-01T00:00:00Z",
        )
        frame = generator.generate_frame(seed)
        item = frame.objects[0]
        turbovec = item.metadata.get("turbovec", {})
        results.append(
            {
                "archetype": archetype,
                "particle_count": item.particle_count,
                "compression_ratio": item.compressed_ref.get("compression_ratio") if item.compressed_ref else None,
                "lod_levels": turbovec.get("lod_summary", {}).get("levels", []),
                "is_verified_knowledge": item.is_verified_knowledge,
            }
        )
    return {
        "passed": all(item["particle_count"] > 0 and item["is_verified_knowledge"] is False for item in results),
        "archetypes": results,
        "safety_flags": default_safety_flags(),
        "proof_only": True,
    }
