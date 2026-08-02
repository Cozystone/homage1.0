from packages.live_selfhood_cycle.clock import make_tick
from packages.live_selfhood_cycle.impulse import rank_impulses
from packages.live_selfhood_cycle.models import LifeCycleConfig, Need
from packages.live_selfhood_cycle.scheduler import LifeCycleScheduler


def test_scheduler_limits_actions_and_blocks_level_zero():
    impulses = rank_impulses([Need("n", "promotion_review_needed", "review")])
    scheduler = LifeCycleScheduler()
    assert scheduler.schedule(make_tick("manual_ping", "test", "LEVEL_0_OFF"), LifeCycleConfig("LEVEL_0_OFF"), impulses) == []
    actions = scheduler.schedule(make_tick("manual_ping", "test"), LifeCycleConfig(max_actions_per_tick=2), impulses)
    assert len(actions) <= 2
    assert actions[0].action_type == "observe_status"


def test_scheduler_allows_operator_gate_only_at_level_four():
    impulses = rank_impulses([Need("n", "operator_confirmation_needed", "operator")])
    scheduler = LifeCycleScheduler()
    level3 = scheduler.schedule(make_tick("manual_ping", "test"), LifeCycleConfig("LEVEL_3_SANDBOX_PLANNER"), impulses)
    level4 = scheduler.schedule(make_tick("manual_ping", "test", "LEVEL_4_GATED_OPERATOR"), LifeCycleConfig("LEVEL_4_GATED_OPERATOR"), impulses)
    assert all(action.action_type != "prepare_operator_confirmation_request" for action in level3)
    assert any(action.action_type == "prepare_operator_confirmation_request" for action in level4)
