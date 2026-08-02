from packages.splatra_turbovec.chunking import chunk_particles
from packages.splatra_turbovec.lod import build_lod_pyramid, downsample_particles_for_lod
from packages.splatra_turbovec.proof import generate_orb_particles


def test_lod_reduces_particle_counts():
    chunk = chunk_particles(generate_orb_particles(1000), chunk_size=4.0)[0]
    lod = downsample_particles_for_lod(chunk, 0.25)
    assert lod.particle_count < chunk.particle_count
    assert lod.lod_level == 1


def test_lod_pyramid_has_levels():
    chunks = chunk_particles(generate_orb_particles(1500), chunk_size=1.5)
    pyramid = build_lod_pyramid(chunks, levels=3)
    assert {chunk.lod_level for chunk in pyramid} == {0, 1, 2}
