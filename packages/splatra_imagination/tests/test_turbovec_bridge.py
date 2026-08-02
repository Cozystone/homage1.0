from __future__ import annotations

from packages.splatra_imagination.generator import ImaginationGenerator
from packages.splatra_imagination.models import ImaginationSeed


def test_turbovec_bridge_reports_compression_and_lod() -> None:
    seed = ImaginationSeed(
        seed_id="bridge",
        archetype="city_block",
        particle_budget=700,
        created_at="2026-01-01T00:00:00Z",
    )
    item = ImaginationGenerator().generate_object(seed)
    bridge = item.metadata["turbovec"]

    assert bridge["adapter_status"] == "connected"
    assert item.compressed_ref is not None
    assert item.compressed_ref["compression_ratio"] > 1.0
    assert bridge["lod_summary"]["levels"] == [0, 1, 2]
    assert "low" in bridge["client_budget_hints"]
