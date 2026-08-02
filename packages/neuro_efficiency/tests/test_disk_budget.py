from __future__ import annotations

from neuro_efficiency import build_disk_budget_state, build_sustained_run_plan


def test_desired_reserve_is_not_a_hard_failure() -> None:
    state = build_disk_budget_state(
        disk_total_gb=930.5,
        disk_free_gb=108.5,
        hard_min_free_gb=15,
        soft_min_free_gb=40,
        desired_reserve_gb=186.1,
    )

    assert state["status"] == "caution"
    assert state["action"] == "slow_growth"
    assert "Normal operation is safe" in state["message"]
    assert "below reserve" not in state["message"]


def test_constrained_disk_slows_growth_and_recommends_compaction() -> None:
    state = build_disk_budget_state(
        disk_total_gb=930.5,
        disk_free_gb=28,
        hard_min_free_gb=15,
        soft_min_free_gb=40,
        desired_reserve_gb=186.1,
    )

    assert state["status"] == "constrained"
    assert state["action"] == "compact"
    assert "compaction" in state["message"]


def test_critical_disk_pauses_growth() -> None:
    state = build_disk_budget_state(
        disk_total_gb=930.5,
        disk_free_gb=8,
        hard_min_free_gb=15,
        soft_min_free_gb=40,
        desired_reserve_gb=186.1,
    )

    assert state["status"] == "critical"
    assert state["action"] == "pause_growth"


def test_sustained_plan_uses_disk_budget_for_growth_batches() -> None:
    plan = build_sustained_run_plan(
        {
            "hardware_profile": {
                "storage_gb": 930.5,
                "disk_free_gb": 108.5,
            },
            "target_nodes": 500_000,
            "target_edges": 2_400_000,
        }
    )

    disk_budget = plan["runtime_envelope"]["disk_budget"]
    assert disk_budget["status"] == "caution"
    assert plan["queue_policy"]["node_write_batch"] == 500
    assert plan["queue_policy"]["edge_write_batch"] == 1_500
    assert all("storage free <= reserve" not in item["condition"] for item in plan["backpressure_policy"])
