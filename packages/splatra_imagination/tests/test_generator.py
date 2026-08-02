from __future__ import annotations

from packages.splatra_imagination.generator import ImaginationGenerator
from packages.splatra_imagination.models import ARCHETYPES, ImaginationSeed


def _seed() -> ImaginationSeed:
    return ImaginationSeed(
        seed_id="deterministic",
        archetype="orb",
        randomness=0.42,
        valence=0.2,
        arousal=0.6,
        curiosity=0.5,
        particle_budget=500,
        created_at="2026-01-01T00:00:00Z",
    )


def test_deterministic_seed_output() -> None:
    generator = ImaginationGenerator(max_particle_budget=1000)

    a = generator.generate_frame(_seed())
    b = generator.generate_frame(_seed())

    assert a.frame_id == b.frame_id
    assert a.objects[0].particle_count == b.objects[0].particle_count
    assert a.objects[0].particles[0].to_dict() == b.objects[0].particles[0].to_dict()


def test_particle_budget_respected_and_not_verified_knowledge() -> None:
    frame = ImaginationGenerator(max_particle_budget=1000).generate_frame(_seed())
    item = frame.objects[0]

    assert 0 < item.particle_count <= 500
    assert item.is_verified_knowledge is False
    assert frame.label == "imagination"
    assert frame.source == "procedural"
    assert item.safety_flags["local_brain_write"] is False


def test_product_frame_reports_visible_object_and_clear_radius() -> None:
    frame = ImaginationGenerator(max_particle_budget=1000).generate_frame(_seed())
    metadata = frame.objects[0].metadata

    assert metadata["visible_object"] is True
    assert metadata["product_visible"] is True
    assert metadata["input_overlay_blocked"] is False
    assert metadata["clear_radius"] == 0.34
    assert metadata["visual_intensity"] >= 0.34


def test_each_archetype_reports_recognizable_projected_geometry() -> None:
    generator = ImaginationGenerator(max_particle_budget=500)

    for archetype in ARCHETYPES:
        seed = ImaginationSeed(seed_id=f"visible_{archetype}", archetype=archetype, particle_budget=220)
        item = generator.generate_object(seed)
        geometry = item.metadata["projected_geometry"]

        assert geometry["kind"] == "procedural_particle_archetype"
        assert geometry["recognizable"] is True
        assert len(geometry["features"]) >= 2


def test_reduced_motion_resting_seed_marks_static_frame() -> None:
    seed = ImaginationSeed(seed_id="static", archetype="constellation", state="resting", particle_budget=120)
    item = ImaginationGenerator(max_particle_budget=500).generate_object(seed)

    assert item.metadata["reduced_motion_static_frame"] is True
