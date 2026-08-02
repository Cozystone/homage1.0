from __future__ import annotations

from .autonomy_level import permits_action
from .models import ActionType, Impulse, LifeCycleConfig, LifeCycleTick, ScheduledAction, default_safety


_ACTION_FOR_NEED: dict[str, ActionType] = {
    "memory_review_needed": "prepare_memory_review",
    "promotion_review_needed": "prepare_promotion_review",
    "repo_hygiene_needed": "recommend_repo_hygiene",
    "morning_brief_needed": "prepare_morning_brief",
    "quality_audit_needed": "run_mirofish_deliberation",
    "voice_setup_needed": "ask_user_attention",
    "operator_confirmation_needed": "prepare_operator_confirmation_request",
    "user_attention_needed": "ask_user_attention",
    "do_nothing": "do_nothing",
}


def _action_title(action_type: ActionType) -> str:
    return action_type.replace("_", " ").title()


class LifeCycleScheduler:
    def schedule(
        self,
        tick: LifeCycleTick,
        config: LifeCycleConfig,
        impulses: list[Impulse],
        recent_events: list[dict] | None = None,
    ) -> list[ScheduledAction]:
        if config.autonomy_level == "LEVEL_0_OFF":
            return []
        actions: list[ScheduledAction] = [
            ScheduledAction(
                action_id=f"action-{tick.tick_id}-observe",
                action_type="observe_status",
                title="Observe status",
                summary="Read-only lifecycle observation.",
                requires_user_approval=False,
                safety_flags=default_safety(),
            )
        ]
        for impulse in impulses:
            action_type = _ACTION_FOR_NEED[impulse.need_type]
            if action_type == "do_nothing" or not permits_action(config.autonomy_level, action_type):
                continue
            actions.append(
                ScheduledAction(
                    action_id=f"action-{tick.tick_id}-{len(actions):02d}-{action_type}",
                    action_type=action_type,
                    title=_action_title(action_type),
                    summary=impulse.proposed_next_step,
                    requires_user_approval=action_type not in {"prepare_morning_brief", "prepare_evening_brief", "observe_status"},
                    irreversible=False,
                    can_apply_now=False,
                    safety_flags=default_safety(),
                )
            )
            if len(actions) >= config.max_actions_per_tick:
                break
        if tick.tick_type == "evening" and len(actions) < config.max_actions_per_tick and permits_action(config.autonomy_level, "prepare_evening_brief"):
            actions.append(
                ScheduledAction(
                    action_id=f"action-{tick.tick_id}-evening",
                    action_type="prepare_evening_brief",
                    title="Prepare Evening Brief",
                    summary="Prepare non-mutating evening brief.",
                    requires_user_approval=False,
                    safety_flags=default_safety(),
                )
            )
        return actions[: config.max_actions_per_tick]
