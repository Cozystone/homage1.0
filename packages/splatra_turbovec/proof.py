from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
from typing import Any

from .budget import estimate_scene_budget
from .chunking import chunk_particles
from .city_manifest import build_synthetic_city
from .codec import compress_chunk, compression_stats, decompress_chunk, estimate_error
from .emotion_mapping import map_emotion_to_splatra_controls
from .lod import build_lod_pyramid
from .models import Particle, SceneManifest, SplatChunk


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "splatra_turbovec" / "proofs"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def generate_orb_particles(count: int = 10_000, seed: int = 1209) -> list[Particle]:
    rng = random.Random(seed)
    particles: list[Particle] = []
    palette = ((0.08, 0.92, 1.0), (0.22, 0.56, 1.0), (0.78, 0.36, 1.0), (1.0, 0.25, 0.58))
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(count):
        band = i % len(palette)
        t = (i + 0.5) / count
        theta = i * golden
        shell_mix = 0.28 if rng.random() < 0.42 else 1.0
        y = (1 - 2 * t) * shell_mix
        ring = math.sqrt(max(0.0, 1 - y * y))
        ribbon = math.sin(t * math.tau * (2.0 + band * 0.13) + band) * 0.28
        radius = 1.0 + math.sin(t * math.tau * 5 + band) * 0.18
        x = math.cos(theta + ribbon) * ring * radius
        z = math.sin(theta + ribbon) * ring * radius * (0.55 + band * 0.05)
        r, g, b = palette[band]
        particles.append(
            Particle(
                x=x,
                y=y + ribbon * 0.25,
                z=z,
                vx=-z * 0.02,
                vy=math.sin(theta) * 0.01,
                vz=x * 0.02,
                r=r,
                g=g,
                b=b,
                a=0.42 + rng.random() * 0.52,
                radius=0.006 + rng.random() * 0.02,
                material_id="glass_shell" if shell_mix < 1 else "voice_ribbon",
                emotion_weight=rng.random() * 0.4,
                audio_reactive_weight=0.3 + rng.random() * 0.5,
            )
        )
    return particles


def _manifest_from_chunks(scene_id: str, compressed_chunks: list[Any]) -> SceneManifest:
    total_particles = sum(chunk.particle_count for chunk in compressed_chunks)
    compressed_bytes = sum(chunk.compressed_bytes for chunk in compressed_chunks)
    estimated = sum(int(chunk.stats.get("estimated_uncompressed_bytes", 0)) for chunk in compressed_chunks)
    return SceneManifest(
        scene_id=scene_id,
        chunks=compressed_chunks,
        lod_levels=sorted({chunk.lod_level for chunk in compressed_chunks}),
        total_particles=total_particles,
        compressed_bytes=compressed_bytes,
        estimated_uncompressed_bytes=estimated,
        compression_ratio=estimated / compressed_bytes if compressed_bytes else 0.0,
        client_budget_hints=estimate_scene_budget(total_particles, compressed_bytes),
    )


def run_orb_proof() -> dict[str, Any]:
    particles = generate_orb_particles(10_000)
    chunk = SplatChunk(
        chunk_id="hologram_orb_lod0",
        origin=(-2.0, -2.0, -2.0),
        size=4.0,
        lod_level=0,
        particles=particles,
        metadata={"scene": "hologram_orb", "all_particles_in_single_chunk": True},
    )
    compressed = compress_chunk(chunk, bits=12)
    restored = decompress_chunk(compressed)
    error = estimate_error(chunk, restored)
    stats = compression_stats(chunk, compressed)
    return {
        "particles": len(particles),
        "chunk_count": 1,
        "compression": stats,
        "error": error,
        "passed": stats["compression_ratio"] > 1.0 and error["max_position_error"] < 0.004,
    }


def run_city_proof() -> dict[str, Any]:
    manifest = build_synthetic_city(count=200_000)
    return {
        "particles": 200_000,
        "compressed_chunks": len(manifest.chunks),
        "lod_levels": manifest.lod_levels,
        "compression_ratio": manifest.compression_ratio,
        "compressed_bytes": manifest.compressed_bytes,
        "estimated_uncompressed_bytes": manifest.estimated_uncompressed_bytes,
        "budget_hints": manifest.client_budget_hints,
        "city_manifest_fields": {
            "district_id": manifest.district_id,
            "tile_id": manifest.tile_id,
            "near_field_chunks": len(manifest.near_field_chunks),
            "far_field_chunks": len(manifest.far_field_chunks),
            "impostor_chunks": len(manifest.impostor_chunks),
            "estimated_gpu_memory": manifest.estimated_gpu_memory,
        },
        "passed": manifest.compression_ratio > 1.0 and len(manifest.lod_levels) >= 3,
    }


def run_lod_manifest_proof() -> dict[str, Any]:
    chunks = chunk_particles(generate_orb_particles(12_000, seed=7), chunk_size=1.25)
    lod_chunks = build_lod_pyramid(chunks, levels=3)
    compressed = [compress_chunk(chunk, bits=12) for chunk in lod_chunks]
    manifest = _manifest_from_chunks("orb_lod_manifest_v0", compressed)
    return {
        "base_chunks": len(chunks),
        "total_chunks_with_lod": len(lod_chunks),
        "lod_levels": manifest.lod_levels,
        "total_particles_with_lod": manifest.total_particles,
        "compression_ratio": manifest.compression_ratio,
        "budget_hints": manifest.client_budget_hints,
        "passed": len(manifest.lod_levels) == 3 and manifest.compression_ratio > 1.0,
    }


def run_emotion_proof() -> dict[str, Any]:
    scenarios = {
        "neutral": map_emotion_to_splatra_controls(0.0, 0.5, 0.0),
        "high_arousal": map_emotion_to_splatra_controls(0.6, 1.0, 0.0),
        "low_valence_high_arousal": map_emotion_to_splatra_controls(-0.8, 0.9, 0.0),
        "speaking_audio_energy": map_emotion_to_splatra_controls(0.3, 0.65, 0.9),
    }
    bounded = all(0.0 <= value <= 2.0 for controls in scenarios.values() for value in controls.values())
    return {"scenarios": scenarios, "passed": bounded}


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "timestamp": _timestamp(),
        "claims": {
            "can_compress_splatra_style_particle_chunks_locally": True,
            "can_build_lod_manifests_for_future_large_scenes": True,
            "can_estimate_client_budgets": True,
            "can_map_emotion_audio_to_bounded_visual_controls": True,
        },
        "non_claims": {
            "production_city_renderer_complete": False,
            "real_splatra_engine_integration_complete": False,
            "gpu_shader_decoder_complete": False,
            "fish_audio_integration_complete": False,
            "real_physics_simulation_complete": False,
        },
        "invariants": {
            "external_llm": False,
            "external_sllm": False,
            "local_brain_write": False,
            "production_store_mutated": False,
            "candidate_promotion": False,
            "large_assets_committed": False,
            "generated_scene_committed": False,
            "proof_only": True,
        },
        "orb": run_orb_proof(),
        "lod_manifest": run_lod_manifest_proof(),
        "city": run_city_proof(),
        "emotion": run_emotion_proof(),
    }
    payload["passed"] = all(
        section.get("passed") is True
        for section in (payload["orb"], payload["lod_manifest"], payload["city"], payload["emotion"])
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "splatra_turbovec_proof.json"
    md_path = output_dir / "splatra_turbovec_proof.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    payload["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# SPLATRA Turbovec Particle Compression Proof",
        "",
        f"- Passed: `{payload['passed']}`",
        f"- Orb particles: `{payload['orb']['particles']}`",
        f"- Orb compression ratio: `{payload['orb']['compression']['compression_ratio']:.3f}`",
        f"- Orb max position error: `{payload['orb']['error']['max_position_error']:.6f}`",
        f"- City particles: `{payload['city']['particles']}`",
        f"- City compressed chunks: `{payload['city']['compressed_chunks']}`",
        f"- City compression ratio: `{payload['city']['compression_ratio']:.3f}`",
        f"- LOD levels: `{payload['city']['lod_levels']}`",
        "",
        "## Claims",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in payload["claims"].items())
    lines.extend(["", "## Non-claims"])
    lines.extend(f"- {key}: `{value}`" for key, value in payload["non_claims"].items())
    lines.extend(["", "Generated proof outputs are runtime artifacts and should not be committed."])
    return "\n".join(lines) + "\n"


def main() -> None:
    result = run_proof()
    print(json.dumps({"passed": result["passed"], "outputs": result["outputs"], "city": result["city"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
