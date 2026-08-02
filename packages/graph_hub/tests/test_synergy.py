from __future__ import annotations

from packages.graph_hub.entitlement import grant_free_entitlement
from packages.graph_hub.installer import install_cartridge
from packages.graph_hub.synergy import score_cartridge_synergy


def test_synergy_uses_bounded_fingerprints_not_raw_local_graph() -> None:
    grant_free_entitlement("software_architect_demo")
    install_cartridge("software_architect_demo")
    result = score_cartridge_synergy("software_architect_demo", active_context="testing deployment")
    assert 0 <= result["constructive_interference_pct"] <= 100
    assert 0 <= result["conflict_node_pct"] <= 100
    assert 0 <= result["overlap_score"] <= 1
    assert 0 <= result["novelty_score"] <= 1
    assert result["recommended_active_chunks"] >= 1
    assert result["predicted_latency_ms"] > 0
    assert result["raw_local_graph_uploaded"] is False
    assert result["raw_local_graph_included"] is False
    assert result["full_cloud_store_scan"] is False
    assert result["pair_edges_sent"] == 0
