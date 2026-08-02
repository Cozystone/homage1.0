from packages.live_selfhood_cycle.freedom_budget import can_request_user_attention, can_run_deliberation, register_action
from packages.live_selfhood_cycle.models import FreedomBudget


def test_freedom_budget_limits_attention_spam():
    budget = FreedomBudget(max_user_attention_requests_per_day=1, current_counts={"user_attention": 1})
    assert can_request_user_attention(budget) is False


def test_register_action_counts_deliberation():
    budget = FreedomBudget()
    updated = register_action(budget, "deliberation")
    assert can_run_deliberation(updated) is True
    assert updated.current_counts["deliberation"] == 1
