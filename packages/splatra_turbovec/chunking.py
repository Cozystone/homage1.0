from __future__ import annotations

import math
from collections import defaultdict

from .models import Particle, SplatChunk


def _chunk_key(particle: Particle, chunk_size: float) -> tuple[int, int, int]:
    return (
        math.floor(particle.x / chunk_size),
        math.floor(particle.y / chunk_size),
        math.floor(particle.z / chunk_size),
    )


def chunk_particles(particles: list[Particle], chunk_size: float) -> list[SplatChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    grouped: dict[tuple[int, int, int], list[Particle]] = defaultdict(list)
    for particle in particles:
        grouped[_chunk_key(particle, chunk_size)].append(particle)

    chunks: list[SplatChunk] = []
    for key in sorted(grouped):
        ix, iy, iz = key
        chunks.append(
            SplatChunk(
                chunk_id=f"chunk_{ix}_{iy}_{iz}_lod0",
                origin=(ix * chunk_size, iy * chunk_size, iz * chunk_size),
                size=chunk_size,
                lod_level=0,
                particles=grouped[key],
                metadata={"grid_key": key},
            )
        )
    return chunks
