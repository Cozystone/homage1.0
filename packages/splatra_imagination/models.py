from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from packages.splatra_turbovec.models import Particle


Archetype = Literal[
    "orb",
    "tower",
    "tree",
    "creature",
    "circuit",
    "city_block",
    "constellation",
    "machine_core",
    "abstract_memory_cloud",
]

ImaginationState = Literal["imagining", "resting", "speaking", "thinking", "previewing", "blocked"]

ARCHETYPES: tuple[Archetype, ...] = (
    "orb",
    "tower",
    "tree",
    "creature",
    "circuit",
    "city_block",
    "constellation",
    "machine_core",
    "abstract_memory_cloud",
)


@dataclass(frozen=True)
class ImaginationSeed:
    seed_id: str
    archetype: Archetype
    randomness: float = 0.5
    valence: float = 0.0
    arousal: float = 0.45
    curiosity: float = 0.5
    speaking_energy: float = 0.0
    state: ImaginationState = "imagining"
    particle_budget: int = 2500
    lod_target: int = 0
    created_at: str = "1970-01-01T00:00:00Z"

    def __post_init__(self) -> None:
        if self.archetype not in ARCHETYPES:
            raise ValueError(f"unsupported archetype: {self.archetype}")
        for name in ("randomness", "arousal", "curiosity", "speaking_energy"):
            value = float(getattr(self, name))
            if value < 0.0 or value > 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.valence < -1.0 or self.valence > 1.0:
            raise ValueError("valence must be between -1 and 1")
        if self.particle_budget <= 0:
            raise ValueError("particle_budget must be positive")
        if self.lod_target < 0:
            raise ValueError("lod_target must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ImaginationObject:
    object_id: str
    archetype: Archetype
    particles: list[Particle]
    metadata: dict[str, Any] = field(default_factory=dict)
    compressed_ref: dict[str, Any] | None = None
    lod_level: int = 0
    safety_flags: dict[str, Any] = field(default_factory=dict)
    is_verified_knowledge: bool = False

    @property
    def particle_count(self) -> int:
        return len(self.particles)

    def to_dict(self, include_particles: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        payload["particle_count"] = self.particle_count
        if include_particles:
            payload["particles"] = [particle.to_dict() for particle in self.particles]
        else:
            payload.pop("particles", None)
        return payload


@dataclass(frozen=True)
class ImaginationFrame:
    frame_id: str
    objects: list[ImaginationObject]
    controls: dict[str, Any] = field(default_factory=dict)
    label: str = "imagination"
    source: str = "procedural"
    proof_only: bool = True

    def to_dict(self, include_particles: bool = True) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "objects": [item.to_dict(include_particles=include_particles) for item in self.objects],
            "controls": self.controls,
            "label": self.label,
            "source": self.source,
            "proof_only": self.proof_only,
            "is_verified_knowledge": False,
            "safety_flags": default_safety_flags(),
        }


def default_safety_flags() -> dict[str, bool]:
    return {
        "external_llm": False,
        "external_sllm": False,
        "image_model_used": False,
        "local_brain_write": False,
        "production_store_mutated": False,
        "candidate_promotion": False,
        "unrestricted_shell": False,
        "arbitrary_js_eval": False,
        "auto_commit": False,
        "auto_push": False,
        "generated_scene_committed": False,
        "proof_only": True,
    }
