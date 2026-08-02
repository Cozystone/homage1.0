from __future__ import annotations

from .models import ActionQueueItem, Brief, Impulse, LifeCycleTick, Need, Observation, ScheduledAction


def _join(items: list[str], fallback: str) -> str:
    return "; ".join(items[:5]) if items else fallback


def generate_brief(
    tick: LifeCycleTick,
    observations: list[Observation],
    needs: list[Need],
    impulses: list[Impulse],
    actions: list[ScheduledAction],
    queue: list[ActionQueueItem],
) -> Brief | None:
    if tick.tick_type == "morning":
        return morning_brief(tick, observations, needs, impulses, actions, queue)
    if tick.tick_type == "evening":
        return evening_brief(tick, observations, needs, actions, queue)
    if actions:
        return status_brief(tick, observations, needs, actions, queue)
    return None


def morning_brief(
    tick: LifeCycleTick,
    observations: list[Observation],
    needs: list[Need],
    impulses: list[Impulse],
    actions: list[ScheduledAction],
    queue: list[ActionQueueItem],
) -> Brief:
    return Brief(
        brief_id=f"brief-{tick.tick_id}-morning",
        brief_type="morning",
        title="Morning Brief",
        sections={
            "What I noticed": _join([item.summary for item in observations if item.status not in {"empty", "unknown"}], "큰 변화는 아직 보이지 않습니다."),
            "What changed": "읽기 전용 관찰만 수행했고 실제 상태는 변경하지 않았습니다.",
            "What needs review": _join([need.summary for need in needs if need.need_type != "do_nothing"], "검토가 필요한 항목은 없습니다."),
            "What I propose": _join([action.summary for action in actions], "오늘은 관찰만 유지합니다."),
            "What I blocked for safety": "Local Brain write, production mutation, candidate promotion, real P2P, generated code execution, always-on microphone.",
            "What requires your approval": _join([item.title for item in queue if item.requires_user_approval], "현재 사용자 승인이 필요한 제안은 없습니다."),
        },
    )


def evening_brief(
    tick: LifeCycleTick,
    observations: list[Observation],
    needs: list[Need],
    actions: list[ScheduledAction],
    queue: list[ActionQueueItem],
) -> Brief:
    return Brief(
        brief_id=f"brief-{tick.tick_id}-evening",
        brief_type="evening",
        title="Evening Brief",
        sections={
            "What I did not change": "메모리, production store, candidate store, P2P, voice capture는 변경하지 않았습니다.",
            "Open proposals": _join([item.title for item in queue], "열린 제안은 없습니다."),
            "Memory candidates": "메모리 후보는 review packet으로만 남기며 자동 write하지 않습니다.",
            "Promotion candidates": "promotion 후보는 human review와 signed manifest 이후에도 별도 gate가 필요합니다.",
            "Risks": _join([obs.summary for obs in observations if obs.severity in {"warning", "blocked"}], "새 위험 신호는 없습니다."),
            "Suggested next step": _join([action.summary for action in actions], "다음 tick에서 다시 관찰합니다."),
        },
    )


def status_brief(
    tick: LifeCycleTick,
    observations: list[Observation],
    needs: list[Need],
    actions: list[ScheduledAction],
    queue: list[ActionQueueItem],
) -> Brief:
    return Brief(
        brief_id=f"brief-{tick.tick_id}-status",
        brief_type="status",
        title="Status Brief",
        sections={
            "What I noticed": _join([obs.summary for obs in observations if obs.status not in {"empty", "unknown"}], "관찰된 변화가 없습니다."),
            "What needs review": _join([need.summary for need in needs if need.need_type != "do_nothing"], "검토 필요 항목 없음."),
            "What I propose": _join([action.summary for action in actions], "제안 없음."),
            "What requires your approval": _join([item.title for item in queue if item.requires_user_approval], "승인 대기 없음."),
        },
    )
