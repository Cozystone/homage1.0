from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.datagate_service import datagate_service


def _write_fixture(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    clean_text = (
        "DataGate accepts deterministic, source-grounded documents with enough "
        "substance for training or retrieval. "
    ) * 5
    (raw_dir / "clean.md").write_text(clean_text, encoding="utf-8")
    (raw_dir / "short.txt").write_text("too short", encoding="utf-8")


def test_datagate_status_starts_idle() -> None:
    datagate_service.reset_for_tests()
    client = TestClient(app)

    response = client.get("/api/datagate/status")

    assert response.status_code == 200
    assert response.json() == {
        "state": "idle",
        "run_id": None,
        "total": 0,
        "accepted": 0,
        "rejected": 0,
        "rejection_breakdown": {},
        "started_at": None,
        "finished_at": None,
        "error": None,
    }


def test_datagate_run_completes_on_fixture_data(tmp_path: Path) -> None:
    datagate_service.reset_for_tests()
    raw_dir = tmp_path / "data" / "raw"
    _write_fixture(raw_dir)
    client = TestClient(app)

    response = client.post(
        "/api/datagate/run",
        json={"input_dir": str(raw_dir), "min_chars": 200},
    )

    assert response.status_code == 202
    assert response.json()["state"] == "running"

    status = client.get("/api/datagate/status").json()
    assert status["state"] == "completed"
    assert status["total"] == 2
    assert status["accepted"] == 1
    assert status["rejected"] == 1
    assert status["rejection_breakdown"] == {"min_length": 1}

    data_root = raw_dir.parent
    assert (data_root / "cleaned").exists()
    assert (data_root / "rejected").exists()
    assert (data_root / "metadata" / "documents.jsonl").exists()


def test_datagate_run_returns_409_when_already_running(monkeypatch) -> None:
    datagate_service.reset_for_tests()
    client = TestClient(app)
    monkeypatch.setattr(datagate_service, "run_pending", lambda: None)

    first = client.post("/api/datagate/run", json={"input_dir": "data/raw"})
    second = client.post("/api/datagate/run", json={"input_dir": "data/raw"})

    assert first.status_code == 202
    assert second.status_code == 409


def test_pipeline_status_returns_alpha_stages() -> None:
    datagate_service.reset_for_tests()
    client = TestClient(app)

    response = client.get("/api/pipeline/status")

    assert response.status_code == 200
    stages = response.json()["stages"]
    assert len(stages) == 8
    assert [stage["name"] for stage in stages] == [
        "Harvest",
        "DataGate",
        "Ontology Forge",
        "ATANOR Oven",
        "GraphRAG",
        "Knowledge Bakery",
        "Guardrail",
        "GPU Monitor",
    ]
    assert stages[1]["state"] == "idle"
