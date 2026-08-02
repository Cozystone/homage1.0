from packages.live_selfhood_cycle.sensors import observe_all


def test_sensors_are_read_only_and_detect_backlogs():
    observations = observe_all({"candidate_backlog": 2, "memory_review_backlog": 1, "git_dirty": True, "dirty_files": 3})
    assert all(item.read_only for item in observations)
    statuses = {(item.sensor, item.status) for item in observations}
    assert ("candidate_backlog", "attention") in statuses
    assert ("memory_approval", "attention") in statuses
    assert ("git_worktree", "dirty") in statuses
