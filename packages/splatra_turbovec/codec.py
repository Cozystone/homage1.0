from __future__ import annotations

import json
import struct
import zlib
from statistics import mean
from typing import Any

from .models import CompressedSplatChunk, Particle, SplatChunk
from .quantization import (
    dequantize_log_radius,
    dequantize_snorm,
    dequantize_unorm,
    quantize_log_radius,
    quantize_snorm,
    quantize_unorm,
)


CODEC_VERSION = "splatra-turbovec-v0"
TURBOVEC_BACKEND = "local_quantized_zlib_proof"
PARTICLE_STRUCT = struct.Struct("<HHHhhhBBBBHHBB")
ESTIMATED_UNCOMPRESSED_BYTES_PER_PARTICLE = 96


def _material_dictionary(chunk: SplatChunk) -> list[str]:
    return sorted({particle.material_id for particle in chunk.particles}) or ["default"]


def _radius_range(chunk: SplatChunk) -> tuple[float, float]:
    radii = [particle.radius for particle in chunk.particles] or [0.001]
    low = max(1e-6, min(radii))
    high = max(low * 1.0001, max(radii))
    return low, high


def _velocity_max_abs(chunk: SplatChunk) -> float:
    values = []
    for particle in chunk.particles:
        values.extend((abs(particle.vx), abs(particle.vy), abs(particle.vz)))
    return max(values, default=0.0) or max(chunk.size * 0.02, 1e-6)


def compress_chunk(chunk: SplatChunk, bits: int = 12) -> CompressedSplatChunk:
    if bits not in (10, 12, 16):
        raise ValueError("bits must be one of 10, 12, 16")
    material_dict = _material_dictionary(chunk)
    material_index = {material: index for index, material in enumerate(material_dict)}
    min_radius, max_radius = _radius_range(chunk)
    velocity_abs = _velocity_max_abs(chunk)
    ox, oy, oz = chunk.origin
    records = bytearray()

    for particle in chunk.particles:
        records.extend(
            PARTICLE_STRUCT.pack(
                quantize_unorm(particle.x - ox, bits, 0.0, chunk.size),
                quantize_unorm(particle.y - oy, bits, 0.0, chunk.size),
                quantize_unorm(particle.z - oz, bits, 0.0, chunk.size),
                quantize_snorm(particle.vx, 16, velocity_abs),
                quantize_snorm(particle.vy, 16, velocity_abs),
                quantize_snorm(particle.vz, 16, velocity_abs),
                quantize_unorm(particle.r, 8),
                quantize_unorm(particle.g, 8),
                quantize_unorm(particle.b, 8),
                quantize_unorm(particle.a, 8),
                quantize_log_radius(particle.radius, 16, min_radius, max_radius),
                material_index[particle.material_id],
                quantize_unorm(particle.emotion_weight, 8),
                quantize_unorm(particle.audio_reactive_weight, 8),
            )
        )

    stats: dict[str, Any] = {
        "turbovec_backend": TURBOVEC_BACKEND,
        "material_dict": material_dict,
        "min_radius": min_radius,
        "max_radius": max_radius,
        "velocity_max_abs": velocity_abs,
        "raw_record_bytes": len(records),
        "estimated_uncompressed_bytes": chunk.particle_count * ESTIMATED_UNCOMPRESSED_BYTES_PER_PARTICLE,
        "particle_record_bytes": PARTICLE_STRUCT.size,
        "metadata": chunk.metadata,
    }
    header = json.dumps(stats, ensure_ascii=False, sort_keys=True).encode("utf-8")
    payload = struct.pack("<I", len(header)) + header + records
    compressed = zlib.compress(payload, level=9)
    return CompressedSplatChunk(
        chunk_id=chunk.chunk_id,
        origin=chunk.origin,
        size=chunk.size,
        lod_level=chunk.lod_level,
        particle_count=chunk.particle_count,
        codec_version=CODEC_VERSION,
        quantization_bits=bits,
        compressed_payload=compressed,
        stats=stats,
    )


def decompress_chunk(compressed: CompressedSplatChunk) -> SplatChunk:
    payload = zlib.decompress(compressed.compressed_payload)
    header_len = struct.unpack_from("<I", payload, 0)[0]
    stats = json.loads(payload[4 : 4 + header_len].decode("utf-8"))
    records = payload[4 + header_len :]
    particles: list[Particle] = []
    ox, oy, oz = compressed.origin
    bits = compressed.quantization_bits
    materials = stats["material_dict"]
    min_radius = float(stats["min_radius"])
    max_radius = float(stats["max_radius"])
    velocity_abs = float(stats["velocity_max_abs"])

    for offset in range(0, len(records), PARTICLE_STRUCT.size):
        values = PARTICLE_STRUCT.unpack_from(records, offset)
        qx, qy, qz, qvx, qvy, qvz, qr, qg, qb, qa, qradius, qmaterial, qemotion, qaudio = values
        particles.append(
            Particle(
                x=ox + dequantize_unorm(qx, bits, 0.0, compressed.size),
                y=oy + dequantize_unorm(qy, bits, 0.0, compressed.size),
                z=oz + dequantize_unorm(qz, bits, 0.0, compressed.size),
                vx=dequantize_snorm(qvx, 16, velocity_abs),
                vy=dequantize_snorm(qvy, 16, velocity_abs),
                vz=dequantize_snorm(qvz, 16, velocity_abs),
                r=dequantize_unorm(qr, 8),
                g=dequantize_unorm(qg, 8),
                b=dequantize_unorm(qb, 8),
                a=dequantize_unorm(qa, 8),
                radius=dequantize_log_radius(qradius, 16, min_radius, max_radius),
                material_id=materials[min(int(qmaterial), len(materials) - 1)],
                emotion_weight=dequantize_unorm(qemotion, 8),
                audio_reactive_weight=dequantize_unorm(qaudio, 8),
            )
        )

    return SplatChunk(
        chunk_id=compressed.chunk_id,
        origin=compressed.origin,
        size=compressed.size,
        lod_level=compressed.lod_level,
        particles=particles,
        metadata=dict(stats.get("metadata") or {}),
    )


def estimate_error(original: SplatChunk, restored: SplatChunk) -> dict[str, float]:
    if original.particle_count != restored.particle_count:
        raise ValueError("particle counts differ")
    if original.particle_count == 0:
        return {"max_position_error": 0.0, "mean_position_error": 0.0, "max_color_error": 0.0}
    position_errors = []
    color_errors = []
    for a, b in zip(original.particles, restored.particles):
        position_errors.append(((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5)
        color_errors.append(max(abs(a.r - b.r), abs(a.g - b.g), abs(a.b - b.b), abs(a.a - b.a)))
    return {
        "max_position_error": max(position_errors),
        "mean_position_error": mean(position_errors),
        "max_color_error": max(color_errors),
    }


def compression_stats(original: SplatChunk, compressed: CompressedSplatChunk) -> dict[str, float | int | str]:
    estimated_uncompressed = original.particle_count * ESTIMATED_UNCOMPRESSED_BYTES_PER_PARTICLE
    ratio = estimated_uncompressed / compressed.compressed_bytes if compressed.compressed_bytes else 0.0
    return {
        "particle_count": original.particle_count,
        "estimated_uncompressed_bytes": estimated_uncompressed,
        "compressed_bytes": compressed.compressed_bytes,
        "compression_ratio": ratio,
        "codec_version": compressed.codec_version,
        "turbovec_backend": str(compressed.stats.get("turbovec_backend", TURBOVEC_BACKEND)),
    }
