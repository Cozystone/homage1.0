from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_storage_cleanup_plan_is_report_only_and_protects_core_data() -> None:
    client = TestClient(app)

    response = client.get("/api/storage/cleanup-plan")

    assert response.status_code == 200
    body = response.json()
    assert "logs" in body["safe_to_delete"]
    assert "cloud_brain proof store" in body["requires_compaction"]
    assert "payload vault" in body["must_not_delete"]
    assert body["policy"]["auto_delete"] is False
    assert body["estimated_reclaim_gb"] >= 0
