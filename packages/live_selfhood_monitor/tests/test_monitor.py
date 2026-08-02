from packages.live_selfhood_cycle.clock import make_tick
from packages.live_selfhood_cycle.lifecycle import run_life_cycle_tick
from packages.live_selfhood_cycle.models import LifeCycleConfig
from packages.live_selfhood_monitor.monitor import build_snapshot_from_lifecycle_result, collect_pending_approvals, events_from_lifecycle_result, summarize_life_signs


def test_build_snapshot_from_lifecycle_result() -> None:
    result = run_life_cycle_tick(LifeCycleConfig(), make_tick("manual_ping", "monitor test", "LEVEL_3_SANDBOX_PLANNER"), {"candidate_backlog": 4})
    events = events_from_lifecycle_result(result)
    snapshot = build_snapshot_from_lifecycle_result(result)
    assert snapshot.alive_status in {"alive", "resting"}
    assert snapshot.tick_count == 1
    assert collect_pending_approvals(events)
    assert summarize_life_signs(snapshot)["actual_mutations"]["production_store_mutated"] is False
