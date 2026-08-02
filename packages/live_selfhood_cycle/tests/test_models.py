import pytest

from packages.live_selfhood_cycle.models import LifeCycleConfig, ScheduledAction, default_safety


def test_default_safety_blocks_mutation_flags():
    safety = default_safety()
    assert safety["real_local_brain_write"] is False
    assert safety["requires_user_approval"] is True
    assert safety["text_input_supported"] is True


def test_scheduled_action_cannot_apply_now():
    with pytest.raises(ValueError):
        ScheduledAction(
            action_id="a",
            action_type="prepare_memory_review",
            title="bad",
            summary="bad",
            can_apply_now=True,
            safety_flags=default_safety(),
        )


def test_config_rejects_negative_action_limit():
    with pytest.raises(ValueError):
        LifeCycleConfig(max_actions_per_tick=-1)
