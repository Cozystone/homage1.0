from __future__ import annotations

import math
import random

from .budget import estimate_scene_budget
from .chunking import chunk_particles
from .codec import compress_chunk
from .lod import build_lod_pyramid
from .models import CitySceneManifest, CompressedSplatChunk, Particle


def generate_city_particles(count: int = 200_000, seed: int = 33033) -> list[Particle]:
    rng = random.Random(seed)
    particles: list[Particle] = []
    materials = ("tower_glass", "window_light", "street_light", "fog_spark")
    grid = max(4, int(math.sqrt(count / 900)))
    per_tower = max(20, count // (grid * grid))
    for gx in range(grid):
        for gz in range(grid):
            base_x = (gx - grid / 2) * 12.0
            base_z = (gz - grid / 2) * 12.0
            height = 8.0 + rng.random() * 34.0
            width = 2.2 + rng.random() * 3.8
            for i in range(per_tower):
                if len(particles) >= count:
                    break
                side = i % 4
                y = rng.random() * height
                edge = (rng.random() - 0.5) * width
                if side == 0:
                    x, z = base_x - width / 2, base_z + edge
                elif side == 1:
                    x, z = base_x + width / 2, base_z + edge
                elif side == 2:
                    x, z = base_x + edge, base_z - width / 2
                else:
                    x, z = base_x + edge, base_z + width / 2
                lit = 0.35 + 0.65 * (1 if rng.random() < 0.28 else rng.random() * 0.25)
                material = materials[1] if lit > 0.7 else materials[0]
                particles.append(
                    Particle(
                        x=x,
                        y=y,
                        z=z,
                        r=0.25 + lit * 0.55,
                        g=0.35 + lit * 0.45,
                        b=0.55 + lit * 0.4,
                        a=0.45 + lit * 0.45,
                        radius=0.018 + rng.random() * 0.035,
                        material_id=material,
                        emotion_weight=rng.random() * 0.2,
                        audio_reactive_weight=rng.random() * 0.15,
                    )
                )
    while len(particles) < count:
        angle = rng.random() * math.tau
        radius = rng.random() * grid * 7
        material = materials[2] if rng.random() < 0.35 else materials[3]
        particles.append(
            Particle(
                x=math.cos(angle) * radius,
                y=rng.random() * 2.5,
                z=math.sin(angle) * radius,
                r=0.8,
                g=0.75 if material == materials[2] else 0.9,
                b=0.45 if material == materials[2] else 1.0,
                a=0.4,
                radius=0.025 + rng.random() * 0.055,
                material_id=material,
                emotion_weight=0.2,
                audio_reactive_weight=0.1,
            )
        )
    return particles


def build_city_manifest(scene_id: str, compressed_chunks: list[CompressedSplatChunk]) -> CitySceneManifest:
    total_particles = sum(chunk.particle_count for chunk in compressed_chunks)
    compressed_bytes = sum(chunk.compressed_bytes for chunk in compressed_chunks)
    estimated_uncompressed = sum(int(chunk.stats.get("estimated_uncompressed_bytes", 0)) for chunk in compressed_chunks)
    lod_levels = sorted({chunk.lod_level for chunk in compressed_chunks})
    chunk_ids = [chunk.chunk_id for chunk in compressed_chunks]
    ratio = estimated_uncompressed / compressed_bytes if compressed_bytes else 0.0
    by_lod = {str(level): [chunk.chunk_id for chunk in compressed_chunks if chunk.lod_level == level] for level in lod_levels}
    return CitySceneManifest(
        scene_id=scene_id,
        chunks=compressed_chunks,
        lod_levels=lod_levels,
        total_particles=total_particles,
        compressed_bytes=compressed_bytes,
        estimated_uncompressed_bytes=estimated_uncompressed,
        compression_ratio=ratio,
        client_budget_hints=estimate_scene_budget(total_particles, compressed_bytes),
        district_id="synthetic_city_core",
        tile_id="city_tile_0_0",
        world_bounds=((-96.0, 0.0, -96.0), (96.0, 48.0, 96.0)),
        lod_tiles=by_lod,
        streaming_priority={chunk.chunk_id: 1.0 / (1 + chunk.lod_level) for chunk in compressed_chunks},
        near_field_chunks=chunk_ids[: min(12, len(chunk_ids))],
        far_field_chunks=chunk_ids[min(12, len(chunk_ids)) : min(64, len(chunk_ids))],
        impostor_chunks=[chunk.chunk_id for chunk in compressed_chunks if chunk.lod_level >= 2],
        splat_materials={
            "tower_glass": {"alpha": 0.55, "roughness": 0.2},
            "window_light": {"emissive": 0.8},
            "street_light": {"emissive": 0.9},
            "fog_spark": {"alpha": 0.35},
        },
        estimated_gpu_memory={
            "low": min(total_particles, 20_000) * 32,
            "medium": min(total_particles, 100_000) * 32,
            "high": min(total_particles, 500_000) * 32,
        },
    )


def build_synthetic_city(scene_id: str = "synthetic_city_v0", count: int = 200_000) -> CitySceneManifest:
    particles = generate_city_particles(count=count)
    chunks = chunk_particles(particles, chunk_size=16.0)
    lod_chunks = build_lod_pyramid(chunks, levels=3)
    compressed = [compress_chunk(chunk, bits=12) for chunk in lod_chunks]
    return build_city_manifest(scene_id, compressed)
