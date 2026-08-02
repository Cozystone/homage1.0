from __future__ import annotations

from neuro_efficiency import build_sustained_run_plan


def test_sustained_run_plan_defaults_match_target_hardware() -> None:
    plan = build_sustained_run_plan()

    assert plan["profile_name"] == "ATANOR Sustained Learning Profile"
    assert plan["hardware_profile"]["cpu"] == "AMD Ryzen 9 9950X3D"
    assert plan["hardware_profile"]["vram_gb"] == 16
    assert plan["hardware_profile"]["ram_gb"] == 32
    assert plan["target_workload"]["target_nodes"] == 10_000
    assert plan["target_workload"]["target_edges"] == 40_000
    assert plan["runtime_envelope"]["ram_soft_gb"] == 23.0
    assert plan["runtime_envelope"]["vram_soft_gb"] == 11.8
    assert plan["queue_policy"]["datagate_batch_docs"] == 64
    assert plan["graph_policy"]["storage_model"].startswith("append-only")
    assert plan["graph_policy"]["ui_render_nodes"] < plan["graph_policy"]["hot_window_nodes"]
    assert len(plan["backpressure_policy"]) >= 4


def test_sustained_run_plan_scales_graph_window_without_rendering_all_nodes() -> None:
    plan = build_sustained_run_plan(
        {
            "target_nodes": 500_000,
            "target_edges": 2_400_000,
            "duration_hours": 168,
        }
    )

    assert plan["target_workload"]["duration_hours"] == 168
    assert plan["target_workload"]["expected_relation_density"] == 4.8
    assert plan["graph_policy"]["hot_window_nodes"] == 24_000
    assert plan["graph_policy"]["hot_window_edges"] == 192_000
    assert plan["graph_policy"]["ui_render_nodes"] == 2_000
    assert plan["queue_policy"]["harvest_pending_cap"] == 4_096
    assert plan["checkpoint_policy"]["checkpoint_keep_last"] == 8
