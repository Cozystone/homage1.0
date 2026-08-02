from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_factory_build_start_marks_target_as_long_run_budget() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/factory/build/start",
        json={"learning_volume": "lite", "target_nodes": 3_000},
    )

    assert response.status_code == 200
    body = response.json()
    gate = body["training_gate"]
    assert body["mode"] == "alpha-live-harvest"
    assert body["learning_profile"]["target_nodes"] == 3_000
    assert gate["target_nodes"] == 3_000
    assert gate["target_semantics"] == "long_run_storage_goal"
    assert gate["representative_node_count"] == len(body["graph_3d"]["nodes"])
    assert gate["representative_node_count"] < gate["target_nodes"]
    assert gate["target_realized"] is False
    assert "representative sample" in gate["sampling_explanation"]
    assert body["web_search"]["provider"] == "static"
    assert body["harvest_docs"][0]["search_provider"]


def test_factory_standard_uses_representative_render_budget() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/factory/build/start",
        json={"learning_volume": "standard", "target_nodes": 10_000},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["learning_profile"]["visual_node_budget"] == 480
    assert body["training_gate"]["representative_node_count"] == 413
    assert body["training_gate"]["visual_node_budget"] == 480
    assert body["training_gate"]["target_nodes"] == 10_000


def test_factory_max_accepts_500k_long_run_budget() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/factory/build/start",
        json={"learning_volume": "max", "target_nodes": 500_000},
    )

    assert response.status_code == 200
    body = response.json()
    gate = body["training_gate"]
    assert body["learning_profile"]["target_nodes"] == 500_000
    assert body["learning_profile"]["visual_node_budget"] == 2_000
    assert gate["target_nodes"] == 500_000
    assert gate["representative_node_count"] == 1_720
    assert gate["target_realized"] is False
    assert gate["chunk_count"] == 4_096
    nodes = body["graph_3d"]["nodes"]
    edges = body["graph_3d"]["edges"]
    node_map = {node["id"]: node for node in nodes}
    max_radius = max((node["x"] ** 2 + node["y"] ** 2 + node["z"] ** 2) ** 0.5 for node in nodes)
    z_span = max(node["z"] for node in nodes) - min(node["z"] for node in nodes)
    max_edge_length = max(
        (
            (node_map[edge["source"]]["x"] - node_map[edge["target"]]["x"]) ** 2
            + (node_map[edge["source"]]["y"] - node_map[edge["target"]]["y"]) ** 2
            + (node_map[edge["source"]]["z"] - node_map[edge["target"]]["z"]) ** 2
        )
        ** 0.5
        for edge in edges
    )
    assert max_radius < 13
    assert z_span > 6
    assert max_edge_length < 11.5


def test_harvest_web_search_static_contract() -> None:
    client = TestClient(app)

    status = client.get("/api/harvest/web-search/status")
    assert status.status_code == 200
    assert status.json()["raw_result_providers"]["static"] is True
    assert status.json()["microsoft_grounding_with_bing"]["native_homage_default"] is False

    response = client.post(
        "/api/harvest/web-search",
        json={"query": "Grounding with Bing Search", "count": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "static"
    assert body["results"]
    assert body["bing_query_url"].startswith("https://www.bing.com/search")
