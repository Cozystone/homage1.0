from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from packages.splatra_turbovec.budget import estimate_scene_budget
from packages.splatra_turbovec.codec import compress_chunk, compression_stats
from packages.splatra_turbovec.lod import build_lod_pyramid
from packages.splatra_turbovec.models import SplatChunk

from .models import ImaginationObject


@dataclass(frozen=True)
class TurbovecBridgeResult:
    adapter_status: str
    compressed_ref: dict[str, Any]
    lod_summary: dict[str, Any]
    client_budget_hints: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compress_imagination_object(item: ImaginationObject, levels: int = 3) -> TurbovecBridgeResult:
    chunk = SplatChunk(
        chunk_id=f"{item.object_id}_chunk0_lod0",
        origin=(-2.0, -2.0, -2.0),
        size=4.0,
        lod_level=max(0, item.lod_level),
        particles=item.particles,
        metadata={
            "archetype": item.archetype,
            "label": "imagination",
            "source": "procedural",
            "is_verified_knowledge": False,
        },
    )
    compressed = compress_chunk(chunk, bits=12)
    stats = compression_stats(chunk, compressed)
    lod_chunks = build_lod_pyramid([chunk], levels=levels)
    lod_summary = {
        "levels": sorted({lod.lod_level for lod in lod_chunks}),
        "counts": {str(lod.lod_level): lod.particle_count for lod in lod_chunks},
        "total_lod_particles": sum(lod.particle_count for lod in lod_chunks),
    }
    budgets = estimate_scene_budget(chunk.particle_count, compressed.compressed_bytes)
    return TurbovecBridgeResult(
        adapter_status="connected",
        compressed_ref={
            "chunk_id": compressed.chunk_id,
            "codec_version": compressed.codec_version,
            "quantization_bits": compressed.quantization_bits,
            "compressed_bytes": compressed.compressed_bytes,
            **stats,
        },
        lod_summary=lod_summary,
        client_budget_hints=budgets,
    )
