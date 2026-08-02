from pathlib import Path

import pytest

from packages.live_selfhood_cycle.scheduler_config import LiveSelfhoodSchedulerConfig


def test_scheduler_config_defaults_are_safe():
    config = LiveSelfhoodSchedulerConfig()
    assert config.enabled is False
    assert config.autonomy_level == "LEVEL_3_SANDBOX_PLANNER"
    assert config.max_ticks_per_session == 10
    assert config.max_runtime_seconds == 60
    assert config.allow_voice_events is False
    assert config.allow_memory_write is False
    assert config.allow_candidate_promotion is False
    assert config.allow_real_p2p is False
    assert config.allow_generated_code_execution is False
    assert config.require_user_approval is True
    assert config.stop_marker_path is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_ticks_per_session", -1),
        ("max_ticks_per_session", 101),
        ("max_runtime_seconds", -1),
        ("max_runtime_seconds", 86_401),
        ("min_delay_seconds", -1),
        ("max_delay_seconds", 86_401),
    ],
)
def test_scheduler_config_rejects_unbounded_values(field: str, value: int):
    with pytest.raises(ValueError):
        LiveSelfhoodSchedulerConfig(**{field: value})


def test_scheduler_config_rejects_delay_inversion():
    with pytest.raises(ValueError):
        LiveSelfhoodSchedulerConfig(min_delay_seconds=10, max_delay_seconds=5)


@pytest.mark.parametrize(
    "field",
    [
        "allow_voice_events",
        "allow_memory_write",
        "allow_candidate_promotion",
        "allow_real_p2p",
        "allow_generated_code_execution",
    ],
)
def test_scheduler_config_rejects_unsafe_allowances(field: str):
    with pytest.raises(ValueError):
        LiveSelfhoodSchedulerConfig(**{field: True})


def test_scheduler_config_rejects_disabled_user_approval():
    with pytest.raises(ValueError):
        LiveSelfhoodSchedulerConfig(require_user_approval=False)


def test_scheduler_config_accepts_tmp_stop_marker_path(tmp_path: Path):
    marker = tmp_path / "stop.marker"
    config = LiveSelfhoodSchedulerConfig(stop_marker_path=str(marker))
    assert config.stop_marker_path == str(marker)
