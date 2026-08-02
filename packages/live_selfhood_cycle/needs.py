from __future__ import annotations

from .models import LifeCycleTick, Need, Observation


def needs_from_observations(observations: list[Observation], tick: LifeCycleTick | None = None) -> list[Need]:
    """Convert read-only observations into reviewable needs."""

    needs: list[Need] = []
    for observation in observations:
        sensor = observation.sensor
        status = observation.status
        evidence = [observation.observation_id]
        if sensor in {"candidate_backlog", "promotion_review"} and status == "attention":
            needs.append(Need(f"need-{sensor}", "promotion_review_needed", observation.summary, "notice", evidence))
        elif sensor == "memory_approval" and status == "attention":
            needs.append(Need("need-memory-review", "memory_review_needed", observation.summary, "notice", evidence))
        elif sensor in {"git_worktree", "dirty_worktree"} and status == "dirty":
            needs.append(Need(f"need-{sensor}", "repo_hygiene_needed", observation.summary, "warning", evidence))
        elif sensor == "disk_resource" and status == "low":
            needs.append(Need("need-disk-quality", "quality_audit_needed", observation.summary, "warning", evidence))
        elif sensor == "voice_readiness" and status == "available":
            needs.append(Need("need-voice-setup", "voice_setup_needed", observation.summary, "info", evidence))
    if tick and tick.tick_type == "morning":
        needs.append(Need("need-morning-brief", "morning_brief_needed", "Morning brief is due.", "notice", [tick.tick_id]))
    if tick and tick.tick_type in {"manual_ping", "user_returned"}:
        needs.append(Need("need-user-attention", "user_attention_needed", "User attention may be useful for pending proposals.", "notice", [tick.tick_id]))
    if not needs:
        needs.append(Need("need-do-nothing", "do_nothing", "No urgent lifecycle need detected.", "info", []))
    return needs


def append_operator_confirmation_need(needs: list[Need], approved_write_plan_waiting: bool) -> list[Need]:
    if approved_write_plan_waiting:
        return [
            *[need for need in needs if need.need_type != "do_nothing"],
            Need(
                "need-operator-confirmation",
                "operator_confirmation_needed",
                "Approved write preparation is waiting for explicit operator confirmation.",
                "blocked",
                ["context:approved_write_plan_waiting"],
            ),
        ]
    return needs
