from __future__ import annotations

from dataclasses import replace

from .models import FreedomBudget


def _count(budget: FreedomBudget, key: str) -> int:
    return int(budget.current_counts.get(key, 0))


def can_generate_spark(budget: FreedomBudget) -> bool:
    return _count(budget, "spark") < budget.max_sparks_per_day


def can_request_user_attention(budget: FreedomBudget) -> bool:
    return _count(budget, "user_attention") < budget.max_user_attention_requests_per_day


def can_run_deliberation(budget: FreedomBudget) -> bool:
    return _count(budget, "deliberation") < budget.max_deliberations_per_day


def can_create_brief(budget: FreedomBudget) -> bool:
    return _count(budget, "brief") < budget.max_briefs_per_day


def register_action(budget: FreedomBudget, action_kind: str) -> FreedomBudget:
    counts = dict(budget.current_counts)
    counts[action_kind] = counts.get(action_kind, 0) + 1
    if action_kind in {"prepare_memory_review", "prepare_promotion_review"}:
        counts["sandbox_plan"] = counts.get("sandbox_plan", 0) + 1
    return replace(budget, current_counts=counts)


def can_schedule_action(budget: FreedomBudget, action_kind: str) -> bool:
    if _count(budget, "internal_action") >= budget.max_internal_actions_per_day:
        return False
    if action_kind == "spark":
        return can_generate_spark(budget)
    if action_kind == "user_attention":
        return can_request_user_attention(budget)
    if action_kind == "deliberation":
        return can_run_deliberation(budget)
    if action_kind == "brief":
        return can_create_brief(budget)
    if action_kind == "sandbox_plan":
        return _count(budget, "sandbox_plan") < budget.max_sandbox_plans_per_day
    return True
