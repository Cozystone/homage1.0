from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .generator import select_archetype
from .models import Archetype, ImaginationSeed


@dataclass
class ImaginationScheduler:
    seed_prefix: str = "atanor_imagination"
    tick: int = 0

    def next_seed(
        self,
        *,
        state: str = "imagining",
        valence: float = 0.0,
        arousal: float = 0.45,
        curiosity: float = 0.5,
        speaking_energy: float = 0.0,
        particle_budget: int = 1600,
        archetype: Archetype | None = None,
    ) -> ImaginationSeed:
        seed_id = f"{self.seed_prefix}_{self.tick:06d}"
        self.tick += 1
        selected = archetype or select_archetype(seed_id, curiosity)
        return ImaginationSeed(
            seed_id=seed_id,
            archetype=selected,
            randomness=curiosity,
            valence=valence,
            arousal=arousal,
            curiosity=curiosity,
            speaking_energy=speaking_energy,
            state=state,  # type: ignore[arg-type]
            particle_budget=particle_budget,
            lod_target=0,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
