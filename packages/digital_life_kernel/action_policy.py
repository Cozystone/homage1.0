from __future__ import annotations

from .models import LifeActionProposal, LifeSignal


def proposal_for_signal(signal: LifeSignal) -> LifeActionProposal:
    """Map one life signal to one safe action proposal."""

    common = {
        "requires_user_approval": True,
        "mutates_production": False,
        "mutates_local_brain": False,
        "uses_real_p2p": False,
        "generated_code_executed": False,
        "metadata": {"source_signal": signal.signal_id, "signal_type": signal.signal_type},
    }

    if signal.signal_type == "promotion_candidate":
        return LifeActionProposal(
            f"proposal_{signal.signal_id}",
            "propose_promotion_review",
            "Review candidate learning output",
            "Prepare a human-reviewed promotion checklist for candidate-only knowledge.",
            "medium",
            **common,
        )
    if signal.signal_type == "privacy_risk":
        return LifeActionProposal(
            f"proposal_{signal.signal_id}",
            "privacy_review",
            "Review privacy risk",
            "Route the evidence through a proof-only privacy review before any sharing.",
            "high",
            **common,
        )
    if signal.signal_type == "social_congress_ready":
        return LifeActionProposal(
            f"proposal_{signal.signal_id}",
            "open_atlas_congress_thread",
            "Prepare Atlas Congress topic",
            "Open a local proposal-only congress thread for review.",
            "medium",
            **common,
        )
    if signal.signal_type == "resource_pressure":
        return LifeActionProposal(
            f"proposal_{signal.signal_id}",
            "request_user_approval",
            "Ask for resource decision",
            "Request explicit user approval before cleanup, stop, or archival action.",
            "high",
            **common,
        )
    if signal.signal_type == "knowledge_gap":
        return LifeActionProposal(
            f"proposal_{signal.signal_id}",
            "run_quality_audit",
            "Run answer quality audit",
            "Prepare a bounded quality audit proposal without changing memory.",
            "low",
            **common,
        )
    if signal.signal_type == "voice_event":
        return LifeActionProposal(
            f"proposal_{signal.signal_id}",
            "prepare_morning_brief",
            "Prepare voice-loop brief",
            "Summarize the voice event as a reviewable brief.",
            "low",
            **common,
        )
    if signal.signal_type == "sync_conflict":
        return LifeActionProposal(
            f"proposal_{signal.signal_id}",
            "request_user_approval",
            "Resolve sync conflict",
            "Ask for explicit review before any identity or cartridge merge.",
            "high",
            **common,
        )
    return LifeActionProposal(
        f"proposal_{signal.signal_id}",
        "do_nothing",
        "No safe action",
        "No automatic action is appropriate for this signal.",
        "blocked",
        **common,
    )


def propose_actions(signals: list[LifeSignal]) -> list[LifeActionProposal]:
    if not signals:
        return [
            LifeActionProposal(
                "proposal_idle",
                "do_nothing",
                "Remain idle",
                "No active life signals require action.",
                "low",
                requires_user_approval=True,
            )
        ]
    return [proposal_for_signal(signal) for signal in signals]
