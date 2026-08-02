from __future__ import annotations

import random

from packages.splatra_imagination.archetypes import generate_archetype
from packages.splatra_imagination.emotion_bridge import imagination_controls
from packages.splatra_imagination.models import ARCHETYPES


def test_each_archetype_returns_particles() -> None:
    controls = imagination_controls(valence=0.1, arousal=0.5, curiosity=0.6)
    for archetype in ARCHETYPES:
        particles = generate_archetype(archetype, 128, random.Random(123), controls)
        assert len(particles) == 128
        assert all(-2.0 <= item.x <= 2.0 for item in particles)
        assert all(item.material_id for item in particles)
