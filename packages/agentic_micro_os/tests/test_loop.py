from packages.agentic_micro_os.loop import BoundedAgentLoop, compress_trajectory, draft_skill_from_loop


def test_loop_stops_and_drafts_not_promoted():
    state = BoundedAgentLoop("test", max_cycles=2).run()
    assert state.stopped_reason == "max_cycles"
    assert len(state.proposed_actions) == 2
    assert state.patch_proposals[0].requires_human_approval is True
    skill = draft_skill_from_loop(state)
    assert skill.status == "draft"
    assert skill.promotion_required is True
    trajectory = compress_trajectory(["public", "private raw memory"])
    assert trajectory.no_private_raw_data is True
    assert "[private-redacted]" in trajectory.compressed_summary
