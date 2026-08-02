from __future__ import annotations

from .models import DeliberationSummary, Impulse, Observation, ScheduledAction


def deliberate_action(
    impulse: Impulse | None,
    observations: list[Observation],
    action: ScheduledAction,
) -> DeliberationSummary:
    """Run deterministic local deliberation without external LLMs or mutation."""

    objections: list[str] = []
    safety_notes = [
        "local only",
        "external_llm_used=false",
        "real_p2p_used=false",
        "can_apply_now=false",
    ]
    if action.requires_user_approval:
        objections.append("Requires explicit user approval before any downstream gate.")
    if action.action_type == "prepare_operator_confirmation_request":
        objections.append("Operator confirmation can prepare a future write only; real apply remains blocked.")
    if any(observation.severity in {"warning", "blocked"} for observation in observations):
        objections.append("At least one warning observation should be reviewed.")
    recommendation = "prepare_review_packet" if action.requires_user_approval else "prepare_brief"
    reason = impulse.reason if impulse else action.summary
    return DeliberationSummary(
        action_id=action.action_id,
        summary=f"{action.title}: {reason}",
        objections=objections,
        safety_notes=safety_notes,
        recommendation=recommendation,
    )


def deliberate_actions(
    impulses: list[Impulse],
    observations: list[Observation],
    actions: list[ScheduledAction],
) -> list[DeliberationSummary]:
    by_need = {impulse.need_type: impulse for impulse in impulses}
    action_to_need = {
        "prepare_memory_review": "memory_review_needed",
        "prepare_promotion_review": "promotion_review_needed",
        "recommend_repo_hygiene": "repo_hygiene_needed",
        "prepare_morning_brief": "morning_brief_needed",
        "prepare_operator_confirmation_request": "operator_confirmation_needed",
        "ask_user_attention": "user_attention_needed",
        "run_mirofish_deliberation": "quality_audit_needed",
    }
    results: list[DeliberationSummary] = []
    for action in actions:
        if action.action_type == "observe_status":
            continue
        need_type = action_to_need.get(action.action_type)
        results.append(deliberate_action(by_need.get(need_type) if need_type else None, observations, action))
    return results
