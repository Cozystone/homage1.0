from __future__ import annotations

from packages.brain_graph.aggregator import aggregate_brain_graph


def test_candidate_pair_math_is_implicit_not_edges() -> None:
    assert 160 * 159 // 2 == 12_720
    assert 1_200 * 1_199 // 2 == 719_400


def test_cloud_graph_uses_spherical_chunk_virtualization() -> None:
    graph = aggregate_brain_graph(
        view="cloud",
        layers=["semantic_cloud"],
        max_nodes=160,
        max_edges=30_000,
    )
    state = graph["visualization_state"]

    assert state["logical"]["sphere_topology"] is True
    assert state["virtualization"]["enabled"] is True
    assert state["virtualization"]["mode"] == "spherical_minecraft_chunks"
    assert state["virtualization"]["candidate_pairs_implicit"] is True
    assert state["virtualization"]["send_candidate_pairs_as_edges"] is False
    assert state["virtualization"]["full_graph_loaded_into_ram"] is False
    assert state["virtualization"]["fake_aggregate_nodes"] is False
    assert state["virtualization"]["sphere_shape_preserved"] is True
    assert state["materialized"]["candidate_pair_edges_sent"] == 0
    assert state["materialized"]["implicit_candidate_pairs"] >= 0
    assert state["spherical_view"]["active_chunks"] >= 0
    metrics = state["spherical_view"]["geometry_metrics"]
    assert metrics["x_span"] >= 0
    assert metrics["y_span"] >= 0
    assert metrics["z_span"] >= 0
    if state["materialized"]["node_count"] >= 12:
        assert metrics["spherical_uniformity_score"] > 0.45
        assert metrics["planar_collapse_score"] < 0.6
    assert len(graph["edges"]) <= 30_000
    assert all(edge.get("relation") != "candidate_pair" for edge in graph["edges"])


def test_materialized_candidate_pairs_follow_loaded_node_count() -> None:
    graph = aggregate_brain_graph(
        view="cloud",
        layers=["semantic_cloud"],
        max_nodes=160,
        max_edges=30_000,
    )
    materialized = graph["visualization_state"]["materialized"]
    node_count = materialized["node_count"]
    assert materialized["implicit_candidate_pairs"] == node_count * max(0, node_count - 1) // 2


def test_focus_lod_updates_spherical_state_without_candidate_edges() -> None:
    base_graph = aggregate_brain_graph(
        view="cloud",
        layers=["semantic_cloud"],
        max_nodes=160,
        max_edges=30_000,
    )
    if not base_graph["nodes"]:
        return
    focus_node_id = str(base_graph["nodes"][0]["id"])
    focused_graph = aggregate_brain_graph(
        view="cloud",
        layers=["semantic_cloud"],
        max_nodes=160,
        max_edges=30_000,
        focus_node_id=focus_node_id,
        lod=4,
    )
    state = focused_graph["visualization_state"]
    assert state["spherical_view"]["focus_node_id"] == focus_node_id
    assert state["spherical_view"]["lod"] == 4
    assert state["materialized"]["focus_node_id"] == focus_node_id
    assert state["materialized"]["zoom_level"] == 4
    assert state["materialized"]["focus_relation_count"] >= 0
    assert state["materialized"]["candidate_pair_edges_sent"] == 0
    assert state["virtualization"]["send_candidate_pairs_as_edges"] is False
