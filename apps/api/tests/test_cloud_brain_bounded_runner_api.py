from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_STORE = PROJECT_ROOT / "data" / "cloud_brain" / "verified_store_v0"


def _production_identity() -> tuple[str, str, dict[str, int]]:
    manifest_path = PRODUCTION_STORE / "manifest.json"
    schema_path = PRODUCTION_STORE / "schema.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return (
        hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        hashlib.sha256(schema_path.read_bytes()).hexdigest(),
        {key: int(value) for key, value in manifest.get("counts", {}).items()},
    )


def _payloads(count: int) -> list[dict[str, object]]:
    rows = []
    for index in range(count):
        text = f"후보 실행 {index}는 표면 그래프 후보를 안전하게 생성합니다."
        rows.append(
            {
                "payload_id": f"bounded_api_{index}",
                "source_type": "manual_public_sentence",
                "source_id": f"manual:bounded-api:{index}",
                "source_url_or_path": f"manual://bounded-api/{index}",
                "provenance_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "license_hint": "CC BY-SA 4.0 api test fixture",
                "language": "ko",
                "text": text,
                "is_private": False,
                "is_generated": False,
                "is_eval_row": False,
                "target_store": "verified_store_v0_candidate",
            }
        )
    return rows


def test_run_capped_rejects_caller_payloads_and_destination_even_in_dry_run(tmp_path: Path) -> None:
    response = client.post(
        "/api/cloud-brain/learning/run-capped",
        json={
            "execute": False,
            "dry_run": True,
            "target_candidate_store": str(tmp_path / "candidate"),
            "min_ram_free_gb": 0,
            "min_disk_free_gb": 0,
            "payloads": _payloads(5),
        },
    )
    assert response.status_code == 400
    assert not (tmp_path / "candidate").exists()


def test_run_capped_caller_cannot_write_policy_shaped_rows_to_candidate_store(tmp_path: Path) -> None:
    before = _production_identity()
    response = client.post(
        "/api/cloud-brain/learning/run-capped",
        json={
            "execute": True,
            "dry_run": False,
            "max_payloads": 12,
            "max_seconds": 60,
            "max_store_mb": 64,
            "min_ram_free_gb": 0,
            "min_disk_free_gb": 0,
            "max_cpu_percent": None,
            "max_candidate_files": None,
            "target_candidate_store": str(tmp_path / "candidate"),
            "payloads": _payloads(12),
        },
    )
    after = _production_identity()
    assert response.status_code == 400
    assert not (tmp_path / "candidate").exists()
    assert before == after


def test_run_capped_rejects_production_promotion(tmp_path: Path) -> None:
    response = client.post(
        "/api/cloud-brain/learning/run-capped",
        json={
            "execute": True,
            "dry_run": False,
            "promote_to_verified": True,
            "target_candidate_store": str(tmp_path / "candidate"),
            "payloads": _payloads(1),
        },
    )
    assert response.status_code == 400


def test_run_capped_normal_trigger_uses_server_selected_store(tmp_path: Path, monkeypatch) -> None:
    candidate = tmp_path / "server_candidate"
    monkeypatch.setenv("ATANOR_CANDIDATE_STORE_PATH", str(candidate))

    response = client.post(
        "/api/cloud-brain/learning/run-capped",
        json={
            "execute": False,
            "dry_run": True,
            "min_ram_free_gb": 0,
            "min_disk_free_gb": 0,
            "max_store_mb": 100000,
            "max_cpu_percent": None,
            "max_candidate_files": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["state"] == "dry_run"
    assert not candidate.exists()


def test_learning_status_exposes_bounded_runner_readiness() -> None:
    response = client.get("/api/cloud-brain/learning/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["bounded_runner_available"] is True
    assert "safe_to_start_24h_candidate_run" in payload
    assert "current_resource_pressure" in payload
