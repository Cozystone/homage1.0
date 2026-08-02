from pathlib import Path

from packages.live_selfhood_cycle.scheduler_config import LiveSelfhoodSchedulerConfig
from packages.live_selfhood_cycle.scheduler_service import create_stop_marker
from packages.live_selfhood_monitor.models import LifeSignsWatchConfig
from packages.live_selfhood_monitor.watch_session import run_watch_session


def test_disabled_watch_does_not_run() -> None:
    result = run_watch_session(LifeSignsWatchConfig(enabled=False))
    assert result.stopped_reason == "disabled"
    assert result.final_snapshot.alive_status == "stopped"
    assert result.events == []


def test_bounded_watch_respects_max_ticks() -> None:
    result = run_watch_session(
        LifeSignsWatchConfig(enabled=True, max_ticks=2),
        LiveSelfhoodSchedulerConfig(enabled=True, max_ticks_per_session=2, max_runtime_seconds=10_000),
        {"candidate_backlog": 4},
    )
    assert result.stopped_reason in {"max_ticks", "completed"}
    assert result.final_snapshot.tick_count <= 2
    assert result.actual_mutations["production_store_mutated"] is False


def test_stop_marker_stops_watch(tmp_path: Path) -> None:
    marker = tmp_path / "stop.marker"
    create_stop_marker(marker)
    result = run_watch_session(
        LifeSignsWatchConfig(enabled=True, max_ticks=3),
        LiveSelfhoodSchedulerConfig(enabled=True, stop_marker_path=str(marker)),
    )
    assert result.stopped_reason == "stop_marker"
    assert result.final_snapshot.tick_count == 0


def test_optional_runtime_log_uses_explicit_path(tmp_path: Path) -> None:
    log_path = tmp_path / "monitor.json"
    result = run_watch_session(LifeSignsWatchConfig(enabled=False, write_runtime_log=True, runtime_log_path=str(log_path)))
    assert log_path.exists()
    assert result.actual_mutations["real_local_brain_write"] is False
