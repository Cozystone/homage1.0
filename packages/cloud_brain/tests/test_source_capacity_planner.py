from __future__ import annotations

from packages.cloud_brain.source_capacity_planner import plan_source_capacity


def test_capacity_planner_blocks_impossible_six_hour_run() -> None:
    plan = plan_source_capacity(
        source_rows=1126,
        target_duration_seconds=6 * 60 * 60,
        target_payloads_per_second=5.0,
        min_payloads_required=None,
        candidate_store_cap_mb=2048,
    )

    assert plan.can_run_full_duration is False
    assert plan.required_rows_for_duration == 108000
    assert plan.available_rows == 1126
    assert plan.reason == "insufficient_source_rows_for_target_duration"
    assert plan.estimated_duration_at_rate < 300


def test_capacity_planner_allows_enough_rows() -> None:
    plan = plan_source_capacity(
        source_rows=216000,
        target_duration_seconds=6 * 60 * 60,
        target_payloads_per_second=10.0,
        min_payloads_required=None,
        candidate_store_cap_mb=4096,
    )

    assert plan.can_run_full_duration is True
    assert plan.required_rows_for_duration == 216000
    assert plan.recommended_target_rate == 10.0
    assert plan.reason == "enough_rows_for_target_duration"


def test_capacity_planner_reports_candidate_store_cap_limit() -> None:
    plan = plan_source_capacity(
        source_rows=216000,
        target_duration_seconds=6 * 60 * 60,
        target_payloads_per_second=10.0,
        candidate_store_cap_mb=1,
    )

    assert plan.can_run_full_duration is False
    assert plan.reason == "candidate_store_cap_too_small_for_target_duration"
