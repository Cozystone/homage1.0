from __future__ import annotations

from packages.digital_life_kernel.scheduler import plan_cycle


def test_plan_cycle_reaches_awaiting_review():
    state, stream = plan_cycle({"answer_quality_gap": 0.4})

    assert state.state == "awaiting_review"
    assert any(event.event_type == "life.user_approval_required" for event in stream.list_events())
    assert all(proposal.safe_by_default for proposal in state.active_proposals)
