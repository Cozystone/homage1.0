from packages.splatra_turbovec.budget import CLIENT_BUDGETS, estimate_scene_budget
from packages.splatra_turbovec.city_manifest import build_synthetic_city


def test_budget_selector_respects_max_particles():
    hints = estimate_scene_budget(200_000, 10 * 1024 * 1024)
    assert hints["low"]["recommended_particle_budget"] <= CLIENT_BUDGETS["low"]["max_particles"]
    assert hints["ultra"]["fits_full_scene"] is True


def test_city_manifest_fields_exist():
    manifest = build_synthetic_city(count=5000)
    assert manifest.district_id
    assert manifest.tile_id
    assert manifest.lod_tiles
    assert manifest.splat_materials
    assert manifest.estimated_gpu_memory["low"] > 0
