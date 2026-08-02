from packages.live_selfhood_cycle.action_queue import ActionQueue
from packages.live_selfhood_cycle.models import ScheduledAction


def test_action_queue_never_enables_apply():
    queue = ActionQueue()
    item = queue.enqueue_action(
        ScheduledAction(
            action_id="a",
            action_type="prepare_memory_review",
            title="Review",
            summary="Review only",
        )
    )
    assert item.can_apply_now is False
    assert item.status == "waiting_user"
    approved = queue.mark_decision("a", "approved_for_future_gate")
    assert approved.can_apply_now is False
