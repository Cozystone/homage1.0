from __future__ import annotations

from neuro_efficiency import build_runtime_config


def test_hardware_adapter_target_tier() -> None:
    config = build_runtime_config({"ram_gb": 32, "vram_gb": 16, "gpu_name": "RTX 5080"})

    assert config.tier == "tier_1_m"
    assert config.max_graph_nodes == 500_000
    assert config.inference_mode == "gpu_native"
    assert config.pruning_aggressiveness == "low"
    assert config.lazy_subgraph_nodes == 5_000
    assert config.max_chunk_nodes == 5_000
    assert config.continuous_threading_enabled is True


def test_hardware_adapter_baseline_tier() -> None:
    config = build_runtime_config({"ram_gb": 16, "vram_gb": 0, "gpu_name": "none"})

    assert config.tier == "tier_2_e"
    assert config.max_graph_nodes == 50_000
    assert config.inference_mode == "cpu_gguf"
    assert config.pruning_aggressiveness == "high"
    assert config.lazy_subgraph_nodes == 800
    assert config.heavy_edge_mesh_enabled is False


def test_hardware_adapter_minimum_tier() -> None:
    config = build_runtime_config({"ram_gb": 8, "vram_gb": 0, "gpu_name": "none"})

    assert config.tier == "tier_3"
    assert config.max_graph_nodes == 10_000
    assert config.inference_mode == "text_fallback"
    assert config.pruning_aggressiveness == "critical"
    assert config.max_chunk_nodes == 300


def test_hardware_adapter_tier0_large_memory() -> None:
    config = build_runtime_config({"ram_gb": 64, "vram_gb": 24, "gpu_name": "large"})

    assert config.tier == "tier_s"
    assert config.lazy_subgraph_nodes == 20_000
    assert config.max_chunk_nodes == 20_000


def test_hardware_adapter_creator_tier() -> None:
    config = build_runtime_config({"ram_gb": 31.15, "vram_gb": 11.5, "gpu_name": "creator"})

    assert config.tier == "tier_1_s"
    assert config.max_chunk_nodes == 3_000


def test_hardware_adapter_developer_tier() -> None:
    config = build_runtime_config({"ram_gb": 15.5, "vram_gb": 8, "gpu_name": "developer"})

    assert config.tier == "tier_2_a"
    assert config.max_chunk_nodes == 1_500
