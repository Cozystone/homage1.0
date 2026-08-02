from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_brain_graph_local_view_excludes_cloud_semantic_layer():
    response = client.get("/api/brain/graph?view=local&layers=local_user,working_memory_local,local_base,seed,semantic_cloud")
    assert response.status_code == 200
    payload = response.json()
    assert payload["view"] == "local"
    assert payload["honesty"]["local_view_excludes_semantic_cloud"] is True
    assert "semantic_cloud" not in payload["stats"]["layer_counts"]
    assert any(item["layer"] == "semantic_cloud" for item in payload["layers_missing"])


def test_brain_graph_cloud_view_reports_surface_summary_only():
    response = client.get("/api/brain/graph?view=cloud&layers=semantic_cloud,cloud_attached,working_memory_cloud,surface_trace_summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["view"] == "cloud"
    assert payload["honesty"]["surface_graph_full_render_disabled"] is True
    assert payload["stats"]["cloud_attached_counts_as_local"] is False
    assert payload["performance"]["full_store_scan"] is False
    assert payload["performance"]["index_rebuild_during_request"] is False


def test_brain_overlay_status_is_honest_about_local_write():
    response = client.get("/api/brain/overlay-status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["local_brain_write"] is False
    assert payload["cloud_attached_counts_as_local"] is False


def test_brain_graph_proof_writes_artifacts():
    response = client.post("/api/brain/graph/proof")
    assert response.status_code == 200
    payload = response.json()
    assert payload["passed"] is True
    assert payload["checks"]["missing_layers_reported"] is True
