from packages.live_selfhood_cycle.autonomy_level import can_apply_irreversible_action, permits_action


def test_level_zero_blocks_autonomous_actions():
    assert permits_action("LEVEL_0_OFF", "observe_status") is False


def test_level_three_allows_sandbox_planning_not_operator_gate():
    assert permits_action("LEVEL_3_SANDBOX_PLANNER", "prepare_memory_review") is True
    assert permits_action("LEVEL_3_SANDBOX_PLANNER", "prepare_operator_confirmation_request") is False


def test_level_four_still_cannot_apply():
    assert permits_action("LEVEL_4_GATED_OPERATOR", "prepare_operator_confirmation_request") is True
    assert can_apply_irreversible_action("LEVEL_4_GATED_OPERATOR") is False
