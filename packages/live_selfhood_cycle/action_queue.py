from __future__ import annotations

from dataclasses import replace

from .clock import utc_now_iso
from .models import ActionQueueItem, ActionStatus, ScheduledAction


class ActionQueue:
    """In-memory proposal queue. It never executes queued actions."""

    def __init__(self) -> None:
        self._items: dict[str, ActionQueueItem] = {}

    def enqueue_action(self, action: ScheduledAction, created_at: str | None = None) -> ActionQueueItem:
        item = ActionQueueItem(
            action_id=action.action_id,
            action_type=action.action_type,
            title=action.title,
            summary=action.summary,
            status="waiting_user" if action.requires_user_approval else "proposed",
            requires_user_approval=action.requires_user_approval,
            irreversible=action.irreversible,
            can_apply_now=False,
            safety_flags=action.safety_flags,
            created_at=created_at or utc_now_iso(),
        )
        self._items[item.action_id] = item
        return item

    def list_actions(self) -> list[ActionQueueItem]:
        return list(self._items.values())

    def mark_decision(self, action_id: str, status: ActionStatus) -> ActionQueueItem:
        if status == "approved_for_future_gate":
            # Approval only advances to a future gate; it still does not execute.
            pass
        if action_id not in self._items:
            raise KeyError(action_id)
        item = replace(self._items[action_id], status=status, can_apply_now=False)
        self._items[action_id] = item
        return item

    def summarize_queue(self) -> dict[str, int]:
        summary = {"total": len(self._items), "waiting_user": 0, "proposed": 0, "blocked": 0}
        for item in self._items.values():
            summary[item.status] = summary.get(item.status, 0) + 1
        return summary


def enqueue_actions(actions: list[ScheduledAction]) -> list[ActionQueueItem]:
    queue = ActionQueue()
    return [queue.enqueue_action(action) for action in actions if action.action_type != "do_nothing"]
