from __future__ import annotations

from .models import Impulse, Need


_SCORES = {
    "operator_confirmation_needed": (0.9, 0.95, 1.0, 0.9, 0.2, 1.0, "Ask the user for explicit operator confirmation; do not apply."),
    "memory_review_needed": (0.7, 0.8, 1.0, 0.8, 0.25, 1.0, "Prepare memory review packet only."),
    "promotion_review_needed": (0.7, 0.75, 1.0, 0.75, 0.25, 1.0, "Prepare promotion review packet only."),
    "repo_hygiene_needed": (0.65, 0.8, 1.0, 0.7, 0.3, 1.0, "Recommend cleanup/review without modifying files."),
    "morning_brief_needed": (0.55, 0.65, 1.0, 0.7, 0.15, 1.0, "Prepare concise morning brief."),
    "quality_audit_needed": (0.6, 0.75, 1.0, 0.65, 0.35, 1.0, "Prepare quality audit proposal."),
    "voice_setup_needed": (0.3, 0.35, 1.0, 0.45, 0.2, 1.0, "Offer optional voice mode; keep text primary."),
    "user_attention_needed": (0.45, 0.55, 1.0, 0.7, 0.15, 1.0, "Ask for review on queued proposals."),
    "p2p_blocked_by_gate": (0.3, 0.5, 1.0, 0.3, 0.1, 1.0, "Report that real P2P remains gated."),
    "local_brain_write_blocked": (0.5, 0.8, 1.0, 0.5, 0.1, 1.0, "Explain Local Brain write remains blocked."),
    "do_nothing": (0.0, 0.1, 1.0, 0.1, 0.0, 1.0, "Do nothing."),
}


def rank_impulses(needs: list[Need]) -> list[Impulse]:
    impulses: list[Impulse] = []
    for index, need in enumerate(needs, start=1):
        urgency, importance, reversibility, user_value, cost, safety, step = _SCORES[need.need_type]
        impulses.append(
            Impulse(
                impulse_id=f"impulse-{index:03d}-{need.need_type}",
                need_type=need.need_type,
                urgency=urgency,
                importance=importance,
                reversibility=reversibility,
                user_value=user_value,
                cost=cost,
                safety=safety,
                reason=need.summary,
                proposed_next_step=step,
            )
        )
    return sorted(impulses, key=lambda item: item.score, reverse=True)
