import pytest

from packages.splatra_turbovec.models import Particle, SplatChunk


def test_particle_bounds():
    particle = Particle(x=0, y=0, z=0, r=0.5, g=0.6, b=0.7, a=0.8, radius=0.01)
    assert particle.material_id == "default"
    with pytest.raises(ValueError):
        Particle(x=0, y=0, z=0, r=1.2)


def test_chunk_particle_count():
    chunk = SplatChunk("c0", (0, 0, 0), 1.0, 0, [Particle(x=0, y=0, z=0)])
    assert chunk.particle_count == 1
    assert chunk.to_dict()["particle_count"] == 1
