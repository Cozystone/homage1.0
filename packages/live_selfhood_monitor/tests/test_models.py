import pytest

from packages.live_selfhood_monitor.models import LifeSignEvent, LifeSignsWatchConfig, assert_monitor_safe, default_actual_mutations


def test_event_rejects_mutation() -> None:
    with pytest.raises(ValueError):
        LifeSignEvent("e1", "2026-01-01T00:00:00Z", "heartbeat", "bad", mutating=True)


def test_watch_config_requires_opt_in() -> None:
    with pytest.raises(ValueError):
        LifeSignsWatchConfig(require_user_opt_in=False)


def test_invariants_reject_real_write() -> None:
    flags = default_actual_mutations()
    flags["real_local_brain_write"] = True
    with pytest.raises(ValueError):
        assert_monitor_safe(flags)
