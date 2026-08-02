from __future__ import annotations

from copy import deepcopy

from packages.graph_hub.cartridge_format import make_graph_cartridge
from packages.graph_hub.cartridge_profiler import profile_cartridge_payload, profile_installed_cartridge
from packages.graph_hub.entitlement import grant_free_entitlement
from packages.graph_hub.installer import install_cartridge


def _sample_cartridge() -> dict:
    return make_graph_cartridge(
        cartridge_id="profiler_test_pack",
        name="Profiler Test Pack",
        subtitle="bounded profiler sample",
        description="test",
        category="test",
        pricing={"model": "free"},
        tags=["testing", "architecture"],
        contents={
            "semantic_graph": {
                "nodes": [
                    {"id": "a", "label": "API"},
                    {"id": "b", "label": "Testing"},
                    {"id": "c", "label": "Deployment"},
                ],
                "edges": [
                    {"id": "e1", "source": "a", "target": "b", "relation": "requires"},
                    {"id": "e2", "source": "b", "target": "c", "relation": "supports"},
                ],
            }
        },
        provenance={"source_type": "test"},
    )


def test_profiler_rejects_broken_manifest() -> None:
    broken = deepcopy(_sample_cartridge())
    broken.pop("contents")
    report = profile_cartridge_payload(broken, full_load_performed=True)
    assert report["inspection_status"] == "rejected"
    assert any(issue["severity"] == "blocker" for issue in report["issues"])
    assert report["pair_edges_sent"] == 0


def test_profiler_detects_excessive_fanout_without_pair_edges() -> None:
    cartridge = _sample_cartridge()
    nodes = [{"id": "hub", "label": "Hub"}] + [{"id": f"n{i}", "label": f"Node {i}"} for i in range(40)]
    edges = [{"id": f"e{i}", "source": "hub", "target": f"n{i}", "relation": "links"} for i in range(40)]
    cartridge["contents"]["semantic_graph"] = {"nodes": nodes, "edges": edges}
    report = profile_cartridge_payload(cartridge, full_load_performed=True)
    assert report["inspection_status"] == "review_required"
    assert any(issue["issue_id"] == "excessive_fanout" for issue in report["issues"])
    assert report["pair_edges_sent"] == 0
    assert all(row["pair_edges_sent"] == 0 for row in report["simulated_queries"])


def test_installed_profile_is_manifest_only() -> None:
    grant_free_entitlement("software_architect_demo")
    install_cartridge("software_architect_demo")
    report = profile_installed_cartridge("software_architect_demo")
    assert report["inspection_status"] in {"passed", "review_required"}
    assert report["full_load_performed"] is False
    assert report["pair_edges_sent"] == 0
    assert report["profile"]["read_only"] is True
    assert report["profile"]["node_count"] > 0
