from packages.live_selfhood_cycle.clock import make_tick
from packages.live_selfhood_cycle.lifecycle import run_life_cycle_tick
from packages.live_selfhood_cycle.models import LifeCycleConfig


def test_lifecycle_runs_without_mutation():
    result = run_life_cycle_tick(LifeCycleConfig(), make_tick("manual_ping", "test"), {"candidate_backlog": 1})
    assert result.observations
    assert result.needs
    assert any(action.action_type == "prepare_promotion_review" for action in result.scheduled_actions)
    assert all(value is False for value in result.actual_mutations.values())
    assert result.next_tick_delay_seconds is not None
    assert result.rhythm_decision is not None


def test_lifecycle_level_zero_has_no_actions():
    result = run_life_cycle_tick(LifeCycleConfig("LEVEL_0_OFF"), make_tick("manual_ping", "test", "LEVEL_0_OFF"), {"candidate_backlog": 1})
    assert result.scheduled_actions == []


def test_no_user_input_backlog_can_create_proposal():
    result = run_life_cycle_tick(LifeCycleConfig(), make_tick("manual_ping", "test"), {"candidate_backlog": 5, "entropy_seed": "no-user"})
    assert any(action.action_type == "prepare_promotion_review" for action in result.scheduled_actions)
    assert all(item.requires_user_approval for item in result.queued_actions if item.action_type != "observe_status")


def test_resource_pressure_rests():
    result = run_life_cycle_tick(LifeCycleConfig(), make_tick("manual_ping", "test"), {"disk_free_gib": 10, "entropy_seed": "resource"})
    assert result.rhythm_decision is not None
    assert result.rhythm_decision.next_mode == "resting"
