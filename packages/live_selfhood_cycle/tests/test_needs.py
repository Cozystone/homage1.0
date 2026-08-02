from packages.live_selfhood_cycle.clock import make_tick
from packages.live_selfhood_cycle.needs import append_operator_confirmation_need, needs_from_observations
from packages.live_selfhood_cycle.sensors import observe_all


def test_needs_from_observations_detect_review_and_repo_hygiene():
    observations = observe_all({"candidate_backlog": 2, "git_dirty": True, "dirty_files": 2})
    needs = needs_from_observations(observations, make_tick("manual_ping", "test"))
    assert {need.need_type for need in needs} >= {"promotion_review_needed", "repo_hygiene_needed"}


def test_operator_confirmation_need_can_be_appended():
    needs = append_operator_confirmation_need([], True)
    assert needs[0].need_type == "operator_confirmation_needed"
