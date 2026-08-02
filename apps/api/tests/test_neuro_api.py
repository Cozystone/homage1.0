from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_neuro_plan_api() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/neuro/plan",
        json={
            "text": "SNN event neuromorphic modular continual few-shot masking pruning quantization guardrail",
            "target_device": "low-power edge",
            "module_budget": 4,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["architecture"] == "ATANOR Neuro-Efficiency Layer"
    assert body["event_gate"]["sparsity"] > 0
    assert len(body["module_routing"]["active_modules"]) <= 4
    assert body["energy_estimate"]["reduction_ratio"] > 0.5


def test_neuro_stability_api() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/neuro/stability",
        json={
            "target_nodes": 500_000,
            "target_edges": 2_400_000,
            "duration_hours": 168,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["hardware_profile"]["gpu"].startswith("ZOTAC GAMING GeForce RTX 5080")
    assert body["runtime_envelope"]["ram_soft_gb"] == 23.0
    assert body["runtime_envelope"]["vram_soft_gb"] == 11.8
    assert body["runtime_envelope"]["disk_budget"]["status"] in {"safe", "caution", "constrained", "critical"}
    assert body["target_workload"]["target_nodes"] == 500_000
    assert body["graph_policy"]["hot_window_nodes"] == 24_000
    assert body["graph_policy"]["ui_render_nodes"] == 2_000
    assert body["queue_policy"]["edge_write_batch"] == 2_000
    assert body["checkpoint_policy"]["checkpoint_keep_last"] == 8
    assert body["backpressure_policy"]


def test_neuro_benchmark_api() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/neuro/benchmark",
        json={
            "run_probes": False,
            "hardware_profile": {
                "cpu": "AMD Ryzen 9 9950X3D",
                "cpu_logical": 32,
                "gpu": "ZOTAC GAMING GeForce RTX 5080 AMP EXTREME INFINITY",
                "vram_gb": 16,
                "ram_gb": 32,
                "storage_gb": 1000,
                "disk_total_gb": 1000,
                "disk_free_gb": 500,
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["can_read_local_hardware"] is True
    assert body["recommended_learning_volume"] == "max"
    assert body["execution_tier"] == "tier_1_m"
    assert body["max_chunk_nodes"] == 5_000
    assert body["continuous_threading_enabled"] is True
    assert body["recommended_stability_payload"]["target_nodes"] == 500_000
    assert body["recommended_stability_payload"]["target_edges"] == 2_400_000
    assert body["ontology_tuning"]["hot_window_nodes"] == 24_000
    assert body["ontology_tuning"]["ui_render_nodes"] == 2_000
    assert body["training_tuning"]["precision"] == "bf16-preferred"


def test_neuro_disk_budget_does_not_treat_reserve_as_hard_failure() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/neuro/stability",
        json={
            "target_nodes": 500_000,
            "target_edges": 2_400_000,
            "hardware_profile": {
                "storage_gb": 930.5,
                "disk_free_gb": 108.5,
            },
        },
    )

    assert response.status_code == 200
    budget = response.json()["runtime_envelope"]["disk_budget"]
    assert budget["desired_reserve_gb"] == 186.1
    assert budget["status"] == "caution"
    assert budget["action"] == "slow_growth"
    assert "Normal operation is safe" in budget["message"]
