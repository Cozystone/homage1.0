from __future__ import annotations

from neuro_efficiency import build_hardware_benchmark


def test_benchmark_recommends_max_for_target_desktop() -> None:
    benchmark = build_hardware_benchmark(
        {
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
        }
    )

    assert benchmark["source"] == "local-hardware-probe"
    assert benchmark["can_read_local_hardware"] is True
    assert benchmark["recommended_learning_volume"] == "max"
    assert benchmark["execution_tier"] == "tier_1_m"
    assert benchmark["max_chunk_nodes"] == 5_000
    assert benchmark["continuous_threading_enabled"] is True
    assert benchmark["recommended_stability_payload"] == {
        "target_nodes": 500_000,
        "target_edges": 2_400_000,
        "duration_hours": 168,
    }
    assert benchmark["ontology_tuning"]["hot_window_nodes"] == 24_000
    assert benchmark["ontology_tuning"]["ui_render_nodes"] == 2_000
    assert benchmark["training_tuning"]["precision"] == "bf16-preferred"
    assert benchmark["training_tuning"]["microbatch_tokens"] == 1280
    assert benchmark["probes"]["ran"] is False


def test_benchmark_recommends_lite_for_small_machine() -> None:
    benchmark = build_hardware_benchmark(
        {
            "run_probes": False,
            "hardware_profile": {
                "cpu": "Small CPU",
                "cpu_logical": 4,
                "gpu": "Unavailable",
                "vram_gb": 0,
                "ram_gb": 8,
                "disk_total_gb": 128,
                "disk_free_gb": 32,
            },
        }
    )

    assert benchmark["recommended_learning_volume"] == "lite"
    assert benchmark["execution_tier"] == "tier_3"
    assert benchmark["max_chunk_nodes"] == 300
    assert benchmark["recommended_stability_payload"]["target_nodes"] == 3_000
    assert benchmark["training_tuning"]["microbatch_tokens"] == 256
    assert benchmark["runtime_envelope"]["ram_soft_gb"] == 5.8
