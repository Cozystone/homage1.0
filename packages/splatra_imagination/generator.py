from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from .archetypes import generate_archetype
from .emotion_bridge import clamp, imagination_controls
from .models import ARCHETYPES, Archetype, ImaginationFrame, ImaginationObject, ImaginationSeed, default_safety_flags
from .turbovec_bridge import compress_imagination_object


def deterministic_seed(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def select_archetype(seed_id: str, curiosity: float) -> Archetype:
    rng = random.Random(deterministic_seed(f"archetype:{seed_id}:{curiosity:.4f}"))
    index = int(rng.random() * len(ARCHETYPES)) % len(ARCHETYPES)
    return ARCHETYPES[index]


def projection_metadata(archetype: Archetype, particle_count: int, controls: dict[str, object]) -> dict[str, object]:
    arousal = float(controls.get("motion_multiplier", 0.75))
    density = float(controls.get("density_multiplier", 0.75))
    state = str(controls.get("visual_state", "imagining"))
    resting = state == "resting"
    base_intensity = 0.66 + density * 0.18 + min(arousal, 1.8) * 0.07
    visual_intensity = clamp(base_intensity - (0.22 if resting else 0.0), 0.34, 0.96)
    feature_map: dict[str, list[str]] = {
        "orb": ["glass shell", "inner ribbon", "central body"],
        "tower": ["vertical spine", "window bands", "stacked floors"],
        "tree": ["trunk", "branch fan", "canopy clusters"],
        "creature": ["abstract body", "head cluster", "limb clusters"],
        "circuit": ["orthogonal traces", "junction nodes", "signal lanes"],
        "city_block": ["skyline masses", "window grid", "street depth"],
        "constellation": ["star anchors", "faint connective lines", "deep field"],
        "machine_core": ["concentric rings", "reactor core", "rotating spokes"],
        "abstract_memory_cloud": ["nebula clusters", "memory knots", "soft bridges"],
    }
    return {
        "visible_object": True,
        "product_visible": True,
        "active_archetype": archetype,
        "display_archetype": "memory_cloud" if archetype == "abstract_memory_cloud" else archetype,
        "projected_geometry": {
            "kind": "procedural_particle_archetype",
            "features": feature_map[archetype],
            "recognizable": True,
        },
        "particle_count": particle_count,
        "visual_intensity": round(visual_intensity, 4),
        "clear_radius": 0.34,
        "input_overlay_blocked": False,
        "reduced_motion_static_frame": resting,
    }


@dataclass
class ImaginationGenerator:
    max_particle_budget: int = 100_000
    default_product_budget: int = 1600
    default_lab_budget: int = 6500

    def generate_object(self, seed: ImaginationSeed, *, compress: bool = True) -> ImaginationObject:
        budget = max(1, min(int(seed.particle_budget), self.max_particle_budget))
        controls = imagination_controls(
            valence=seed.valence,
            arousal=seed.arousal,
            curiosity=seed.curiosity,
            speaking_energy=seed.speaking_energy,
            state=seed.state,
        )
        density = float(controls["density_multiplier"])
        count = max(16, min(budget, int(round(budget * density))))
        rng = random.Random(deterministic_seed(f"{seed.seed_id}:{seed.archetype}:{seed.randomness:.5f}"))
        particles = generate_archetype(seed.archetype, count, rng, controls)
        visible_metadata = projection_metadata(seed.archetype, len(particles), controls)
        object_id = f"imag_{hashlib.sha1((seed.seed_id + seed.archetype).encode('utf-8')).hexdigest()[:16]}"
        item = ImaginationObject(
            object_id=object_id,
            archetype=seed.archetype,
            particles=particles,
            metadata={
                "seed": seed.to_dict(),
                "controls": controls,
                "label": "imagination",
                "source": "procedural",
                "not_verified_memory": True,
                **visible_metadata,
            },
            lod_level=seed.lod_target,
            safety_flags=default_safety_flags(),
            is_verified_knowledge=False,
        )
        if not compress:
            return item
        bridge = compress_imagination_object(item)
        return ImaginationObject(
            object_id=item.object_id,
            archetype=item.archetype,
            particles=item.particles,
            metadata={**item.metadata, "turbovec": bridge.to_dict()},
            compressed_ref=bridge.compressed_ref,
            lod_level=item.lod_level,
            safety_flags=item.safety_flags,
            is_verified_knowledge=False,
        )

    def generate_frame(self, seed: ImaginationSeed, *, compress: bool = True, include_particles: bool = True) -> ImaginationFrame:
        item = self.generate_object(seed, compress=compress)
        frame_hash = hashlib.sha1((seed.seed_id + item.object_id + seed.created_at).encode("utf-8")).hexdigest()[:16]
        return ImaginationFrame(
            frame_id=f"frame_{frame_hash}",
            objects=[item],
            controls=item.metadata.get("controls", {}),
            label="imagination",
            source="procedural",
            proof_only=True,
        )
