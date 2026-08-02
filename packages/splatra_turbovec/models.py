from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _bounded(name: str, value: float, low: float = 0.0, high: float = 1.0) -> None:
    if value < low or value > high:
        raise ValueError(f"{name} must be between {low} and {high}")


@dataclass(frozen=True)
class Particle:
    x: float
    y: float
    z: float
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    r: float = 1.0
    g: float = 1.0
    b: float = 1.0
    a: float = 1.0
    radius: float = 0.01
    material_id: str = "default"
    emotion_weight: float = 0.0
    audio_reactive_weight: float = 0.0

    def __post_init__(self) -> None:
        for name in ("r", "g", "b", "a", "emotion_weight", "audio_reactive_weight"):
            _bounded(name, float(getattr(self, name)))
        if self.radius <= 0:
            raise ValueError("radius must be positive")
        if not self.material_id:
            raise ValueError("material_id is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SplatChunk:
    chunk_id: str
    origin: tuple[float, float, float]
    size: float
    lod_level: int
    particles: list[Particle]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.chunk_id:
            raise ValueError("chunk_id is required")
        if self.size <= 0:
            raise ValueError("size must be positive")
        if self.lod_level < 0:
            raise ValueError("lod_level must be non-negative")

    @property
    def particle_count(self) -> int:
        return len(self.particles)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["particle_count"] = self.particle_count
        return payload


@dataclass(frozen=True)
class CompressedSplatChunk:
    chunk_id: str
    origin: tuple[float, float, float]
    size: float
    lod_level: int
    particle_count: int
    codec_version: str
    quantization_bits: int
    compressed_payload: bytes
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def compressed_bytes(self) -> int:
        return len(self.compressed_payload)

    def to_dict(self, include_payload: bool = False) -> dict[str, Any]:
        payload = asdict(self)
        payload["compressed_bytes"] = self.compressed_bytes
        if include_payload:
            payload["compressed_payload_hex"] = self.compressed_payload.hex()
        payload.pop("compressed_payload", None)
        return payload


@dataclass(frozen=True)
class SceneManifest:
    scene_id: str
    chunks: list[CompressedSplatChunk]
    lod_levels: list[int]
    total_particles: int
    compressed_bytes: int
    estimated_uncompressed_bytes: int
    compression_ratio: float
    client_budget_hints: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["chunks"] = [chunk.to_dict() for chunk in self.chunks]
        return payload


@dataclass(frozen=True)
class CitySceneManifest(SceneManifest):
    district_id: str = "district_0"
    tile_id: str = "tile_0"
    world_bounds: tuple[tuple[float, float, float], tuple[float, float, float]] = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    lod_tiles: dict[str, list[str]] = field(default_factory=dict)
    streaming_priority: dict[str, float] = field(default_factory=dict)
    near_field_chunks: list[str] = field(default_factory=list)
    far_field_chunks: list[str] = field(default_factory=list)
    impostor_chunks: list[str] = field(default_factory=list)
    splat_materials: dict[str, dict[str, Any]] = field(default_factory=dict)
    estimated_gpu_memory: dict[str, int] = field(default_factory=dict)
