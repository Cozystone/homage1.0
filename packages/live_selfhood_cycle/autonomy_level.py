from __future__ import annotations

from enum import IntEnum

from .models import ActionType, AutonomyLevelName


class AutonomyLevel(IntEnum):
    LEVEL_0_OFF = 0
    LEVEL_1_OBSERVE = 1
    LEVEL_2_PROACTIVE_BRIEF = 2
    LEVEL_3_SANDBOX_PLANNER = 3
    LEVEL_4_GATED_OPERATOR = 4


DEFAULT_PROOF_LEVEL: AutonomyLevelName = "LEVEL_3_SANDBOX_PLANNER"


def normalize_level(level: AutonomyLevelName | str | AutonomyLevel) -> AutonomyLevel:
    """Return a concrete autonomy level without weakening safety gates."""

    if isinstance(level, AutonomyLevel):
        return level
    try:
        return AutonomyLevel[str(level)]
    except KeyError as exc:
        raise ValueError(f"unknown autonomy level: {level}") from exc


def level_name(level: AutonomyLevelName | str | AutonomyLevel) -> AutonomyLevelName:
    return normalize_level(level).name  # type: ignore[return-value]


def permits_autonomous_cycle(level: AutonomyLevelName | str | AutonomyLevel) -> bool:
    return normalize_level(level) >= AutonomyLevel.LEVEL_1_OBSERVE


def permits_action(level: AutonomyLevelName | str | AutonomyLevel, action_type: ActionType) -> bool:
    """Check proposal permission; this never grants real apply permission."""

    concrete = normalize_level(level)
    if concrete == AutonomyLevel.LEVEL_0_OFF:
        return False
    if action_type == "observe_status":
        return concrete >= AutonomyLevel.LEVEL_1_OBSERVE
    if action_type in {"prepare_morning_brief", "prepare_evening_brief", "ask_user_attention", "do_nothing"}:
        return concrete >= AutonomyLevel.LEVEL_2_PROACTIVE_BRIEF
    if action_type in {
        "run_mirofish_deliberation",
        "prepare_memory_review",
        "prepare_promotion_review",
        "recommend_repo_hygiene",
    }:
        return concrete >= AutonomyLevel.LEVEL_3_SANDBOX_PLANNER
    if action_type == "prepare_operator_confirmation_request":
        return concrete >= AutonomyLevel.LEVEL_4_GATED_OPERATOR
    return False


def can_apply_irreversible_action(_level: AutonomyLevelName | str | AutonomyLevel) -> bool:
    """Irreversible actions always remain blocked in v0."""

    return False
