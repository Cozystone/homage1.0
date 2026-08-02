from pathlib import Path

from packages.live_selfhood_cycle.scheduler_config import LiveSelfhoodSchedulerConfig
from packages.live_selfhood_cycle.scheduler_service import (
    SchedulerSessionState,
    clear_stop_marker,
    create_stop_marker,
    read_stop_marker,
    run_one_tick,
    run_scheduler_session,
    should_stop,
)


def test_disabled_scheduler_runs_zero_ticks():
    result = run_scheduler_session(LiveSelfhoodSchedulerConfig(), {"candidate_backlog": 3})
    assert result.enabled is False
    assert result.ticks_run == 0
    assert result.stopped_reason == "disabled"
    assert result.safety["scheduler_enabled_by_default"] is False
    assert all(value is False for value in result.actual_mutations.values())


def test_enabled_scheduler_is_bounded_by_tick_count():
    result = run_scheduler_session(
        LiveSelfhoodSchedulerConfig(enabled=True, max_ticks_per_session=3, max_runtime_seconds=10_000),
        {"candidate_backlog": 3},
    )
    assert result.enabled is True
    assert result.ticks_run == 3
    assert result.stopped_reason == "max_ticks_reached"
    assert len(result.results) == 3
    assert all(value is False for value in result.actual_mutations.values())
    assert all(not any(item.actual_mutations.values()) for item in result.results)


def test_enabled_scheduler_respects_simulated_runtime_bound():
    result = run_scheduler_session(
        LiveSelfhoodSchedulerConfig(
            enabled=True,
            max_ticks_per_session=10,
            max_runtime_seconds=5,
            min_delay_seconds=5,
            max_delay_seconds=5,
        ),
        {"candidate_backlog": 3},
    )
    assert result.ticks_run == 1
    assert result.stopped_reason == "max_runtime_reached"
    assert result.simulated_elapsed_seconds == 5


def test_stop_marker_support(tmp_path: Path):
    marker = tmp_path / "live-selfhood.stop"
    assert read_stop_marker(marker) is False
    create_stop_marker(marker)
    assert read_stop_marker(marker) is True
    result = run_scheduler_session(
        LiveSelfhoodSchedulerConfig(enabled=True, stop_marker_path=str(marker)),
        {"candidate_backlog": 3},
    )
    assert result.ticks_run == 0
    assert result.stopped_reason == "stop_marker"
    clear_stop_marker(marker)
    assert read_stop_marker(marker) is False


def test_should_stop_reports_bounds_and_stop_marker(tmp_path: Path):
    config = LiveSelfhoodSchedulerConfig(enabled=True, max_ticks_per_session=2, max_runtime_seconds=10)
    assert should_stop(config, SchedulerSessionState()) is None
    assert should_stop(config, SchedulerSessionState(ticks_run=2)) == "max_ticks_reached"
    assert should_stop(config, SchedulerSessionState(simulated_elapsed_seconds=10)) == "max_runtime_reached"
    marker = tmp_path / "stop"
    create_stop_marker(marker)
    assert should_stop(LiveSelfhoodSchedulerConfig(enabled=True, stop_marker_path=str(marker)), SchedulerSessionState()) == "stop_marker"


def test_run_one_tick_uses_rhythm_delay_and_remains_proposal_only():
    result = run_one_tick(
        LiveSelfhoodSchedulerConfig(enabled=True, min_delay_seconds=5, max_delay_seconds=3600),
        {"candidate_backlog": 5},
    )
    assert result.next_tick_delay_seconds is not None
    assert result.next_tick_delay_seconds >= 5
    assert result.safety["requires_user_approval"] is True
    assert all(value is False for value in result.actual_mutations.values())
