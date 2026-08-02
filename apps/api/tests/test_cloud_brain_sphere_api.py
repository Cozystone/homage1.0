from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from seed_research import run_seed_iteration


def test_cloud_brain_sphere_manifest_and_materialize_api(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_seed_iteration("data/seed_research")
    client = TestClient(app)
    proof = client.post("/api/cloud-brain/prove-controlled-self-growth")
    assert proof.status_code == 200

    manifest = client.get("/api/cloud-brain/sphere/manifest")
    assert manifest.status_code == 200
    manifest_payload = manifest.json()
    assert manifest_payload["scale_mode"] == "spherical_chunk_materialization"
    assert isinstance(manifest_payload["logical_total_nodes"], str)
    assert isinstance(manifest_payload["trillion_target"], str)
    assert manifest_payload["compression_used"] is False
    assert manifest_payload["semantic_aggregate_nodes_used"] is False

    tile = client.get("/api/cloud-brain/sphere/tile", params={"level": 0, "x": 0, "y": 0})
    assert tile.status_code == 200
    tile_payload = tile.json()
    assert tile_payload["is_graph_node"] is False
    assert tile_payload["is_semantic_node"] is False

    shell = client.get("/api/cloud-brain/sphere/materialize", params={"tile_id": tile_payload["tile_id"], "zoom": 0, "budget_nodes": 2, "budget_edges": 1})
    actual = client.get("/api/cloud-brain/sphere/materialize", params={"tile_id": tile_payload["tile_id"], "zoom": 5, "budget_nodes": 2, "budget_edges": 1})
    assert shell.status_code == 200
    assert actual.status_code == 200
    assert shell.json()["render_mode"] == "shell"
    actual_payload = actual.json()
    assert actual_payload["render_mode"] == "actual_nodes"
    assert actual_payload["rendered_nodes"] <= 2
    assert actual_payload["rendered_edges"] <= 1
    assert actual_payload["compression_used"] is False
    assert actual_payload["semantic_aggregate_nodes_used"] is False
    node = actual_payload["materialized_nodes"][0]
    assert node["cloud_node_id"].startswith("cbn_")
    assert isinstance(node["logical_ordinal"], str)

    lookup = client.get(f"/api/cloud-brain/sphere/node/{node['cloud_node_id']}")
    assert lookup.status_code == 200
    assert lookup.json()["found"] is True


def test_cloud_brain_sphere_proof_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_seed_iteration("data/seed_research")
    client = TestClient(app)

    response = client.post("/api/cloud-brain/sphere/proof")

    assert response.status_code == 200
    payload = response.json()
    assert payload["proof_passed"] is True
    assert payload["shell_tile_is_graph_node"] is False
    assert payload["shell_tile_is_semantic_node"] is False
    assert payload["compression_used"] is False
    assert payload["semantic_aggregate_nodes_used"] is False
    assert payload["local_brain_state"]["local_total_nodes"] == 0
    assert payload["fake_trillion_population_claimed"] is False
