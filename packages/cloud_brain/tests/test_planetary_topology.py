from __future__ import annotations

from collections import Counter
import math

from packages.cloud_brain.planetary_topology import MAX_DIRECT_EDGES, planetize_graph_sample, semantic_domain_for_node


def test_planetary_topology_splits_super_node_degree() -> None:
    hub = {"id": "hub", "label": "semantic routing shard"}
    nodes = [hub] + [{"id": f"node-{index}", "label": f"AtanorSeedConcept{index:06d}"} for index in range(64)]
    edges = [
        {
            "id": f"edge-{index}",
            "source": "hub",
            "target": f"node-{index}",
            "relation": "supports",
            "weight": 0.7,
        }
        for index in range(64)
    ]

    result = planetize_graph_sample(nodes, edges, max_direct_edges=MAX_DIRECT_EDGES)
    degree = Counter()
    for edge in result["edges"]:
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1

    assert result["topology"]["mode"] == "planetary_galaxy"
    assert result["topology"]["super_nodes_split"] == 1
    assert result["topology"]["semantic_aggregate_nodes_used"] is False
    assert result["topology"]["materialization_containers_used"] is True
    assert degree["hub"] <= MAX_DIRECT_EDGES
    assert max(degree.values()) <= MAX_DIRECT_EDGES
    assert result["topology"]["rewired_edges"] == 64


def test_planetary_topology_assigns_stable_domains() -> None:
    first = {"id": "a", "label": "AtanorSeedConcept000008"}
    second = {"id": "b", "label": "AtanorSeedConcept000008"}

    assert semantic_domain_for_node(first) == semantic_domain_for_node(second)

    result_a = planetize_graph_sample([first], [], max_direct_edges=MAX_DIRECT_EDGES)
    result_b = planetize_graph_sample([second], [], max_direct_edges=MAX_DIRECT_EDGES)

    assert result_a["nodes"][0]["planetary_domain"] == result_b["nodes"][0]["planetary_domain"]
    assert result_a["nodes"][0]["metadata"]["is_semantic_node"] is True


def test_planetary_topology_places_materialized_nodes_in_volumetric_sphere() -> None:
    nodes = [{"id": f"node-{index}", "label": f"AtanorSeedConcept{index:06d}"} for index in range(160)]

    first = planetize_graph_sample(nodes, [], max_direct_edges=MAX_DIRECT_EDGES)["nodes"]
    second = planetize_graph_sample(nodes, [], max_direct_edges=MAX_DIRECT_EDGES)["nodes"]

    first_positions = [(node["x"], node["y"], node["z"]) for node in first]
    second_positions = [(node["x"], node["y"], node["z"]) for node in second]
    radii = [math.sqrt((x * x) + (y * y) + (z * z)) for x, y, z in first_positions]
    z_values = [z for _, _, z in first_positions]
    y_values = [y for _, y, _ in first_positions]

    assert first_positions == second_positions
    assert max(radii) - min(radii) > 2.5
    assert max(z_values) - min(z_values) > 8.0
    assert max(y_values) - min(y_values) > 8.0
    assert all(node["metadata"]["is_semantic_node"] is True for node in first)
    assert all(node["metadata"]["is_materialization_container"] is False for node in first)
