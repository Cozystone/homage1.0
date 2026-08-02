from __future__ import annotations

from dataclasses import dataclass
from math import dist
from typing import Any

from .models import SplatChunk


@dataclass(frozen=True)
class Camera:
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)


def downsample_particles_for_lod(chunk: SplatChunk, target_ratio: float) -> SplatChunk:
    if target_ratio <= 0 or target_ratio > 1:
        raise ValueError("target_ratio must be in (0, 1]")
    if target_ratio >= 1 or chunk.particle_count <= 1:
        return chunk
    target_count = max(1, int(round(chunk.particle_count * target_ratio)))
    step = max(1, chunk.particle_count // target_count)
    selected = chunk.particles[::step][:target_count]
    return SplatChunk(
        chunk_id=f"{chunk.chunk_id.rsplit('_lod', 1)[0]}_lod{chunk.lod_level + 1}",
        origin=chunk.origin,
        size=chunk.size,
        lod_level=chunk.lod_level + 1,
        particles=selected,
        metadata={**chunk.metadata, "source_chunk_id": chunk.chunk_id, "target_ratio": target_ratio},
    )


def build_lod_pyramid(chunks: list[SplatChunk], levels: int = 3) -> list[SplatChunk]:
    if levels < 1:
        raise ValueError("levels must be >= 1")
    pyramid = list(chunks)
    current = list(chunks)
    ratios = [0.5, 0.25, 0.125, 0.0625]
    for level in range(1, levels):
        ratio = ratios[min(level - 1, len(ratios) - 1)]
        current = [downsample_particles_for_lod(chunk, ratio) for chunk in current]
        pyramid.extend(current)
    return pyramid


def _chunk_center(chunk: SplatChunk) -> tuple[float, float, float]:
    ox, oy, oz = chunk.origin
    half = chunk.size / 2
    return (ox + half, oy + half, oz + half)


def select_chunks_for_camera(manifest: Any, camera: Camera | dict[str, Any], budget: dict[str, int]) -> list[Any]:
    position = tuple(camera.get("position", (0.0, 0.0, 0.0))) if isinstance(camera, dict) else camera.position
    max_particles = int(budget.get("max_particles", 100_000))
    selected = []
    total = 0
    chunks = getattr(manifest, "chunks", manifest.get("chunks", []))
    ordered = sorted(chunks, key=lambda chunk: dist(position, _chunk_center(chunk) if isinstance(chunk, SplatChunk) else tuple(chunk.origin)))
    for chunk in ordered:
        count = chunk.particle_count
        if total + count > max_particles:
            continue
        selected.append(chunk)
        total += count
    return selected
