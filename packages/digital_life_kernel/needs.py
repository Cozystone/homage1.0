from __future__ import annotations

from typing import Any

from .models import LifeSignal


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def signals_from_observation(observation: dict[str, Any]) -> list[LifeSignal]:
    """Convert bounded system observations into deterministic life signals.

    This function does not mutate stores, call an LLM, or decide actions. It
    only translates observable deficits into a typed signal list.
    """

    signals: list[LifeSignal] = []
    source = str(observation.get("source") or "observation")

    candidate = observation.get("candidate_run") or {}
    if candidate.get("accepted", 0) or candidate.get("candidate_concepts", 0):
        severity = _clamp((float(candidate.get("accepted") or 0) / 20000.0) + 0.15)
        signals.append(
            LifeSignal(
                "signal_promotion_candidate",
                "promotion_candidate",
                severity,
                [{"kind": "candidate_run", **candidate}],
                source,
            )
        )

    resources = observation.get("resource_state") or {}
    disk_free = resources.get("disk_free_gib")
    ram_free = resources.get("ram_free_gib")
    if (disk_free is not None and float(disk_free) < 40.0) or (ram_free is not None and float(ram_free) < 6.0):
        severity = max(
            _clamp((40.0 - float(disk_free or 40.0)) / 40.0),
            _clamp((6.0 - float(ram_free or 6.0)) / 6.0),
        )
        signals.append(
            LifeSignal(
                "signal_resource_pressure",
                "resource_pressure",
                severity,
                [{"kind": "resource_state", **resources}],
                source,
            )
        )

    quality_gap = observation.get("answer_quality_gap")
    if quality_gap is not None and float(quality_gap) > 0.0:
        signals.append(
            LifeSignal(
                "signal_knowledge_gap",
                "knowledge_gap",
                _clamp(float(quality_gap)),
                [{"kind": "answer_quality_gap", "gap": float(quality_gap)}],
                source,
            )
        )

    promotion_queue_size = int(observation.get("promotion_queue_size") or 0)
    if promotion_queue_size > 0:
        signals.append(
            LifeSignal(
                "signal_promotion_queue",
                "promotion_candidate",
                _clamp(promotion_queue_size / 100.0),
                [{"kind": "promotion_queue", "size": promotion_queue_size}],
                source,
            )
        )

    privacy_risk = observation.get("privacy_risk")
    if privacy_risk is not None and float(privacy_risk) > 0.0:
        signals.append(
            LifeSignal(
                "signal_privacy_risk",
                "privacy_risk",
                _clamp(float(privacy_risk)),
                [{"kind": "privacy_risk", "risk": float(privacy_risk)}],
                source,
            )
        )

    if observation.get("congress_topic"):
        signals.append(
            LifeSignal(
                "signal_social_congress_ready",
                "social_congress_ready",
                0.55,
                [{"kind": "congress_topic", "topic": observation["congress_topic"]}],
                source,
            )
        )

    if observation.get("voice_intent"):
        signals.append(
            LifeSignal(
                "signal_voice_event",
                "voice_event",
                0.4,
                [{"kind": "voice_intent", "intent": observation["voice_intent"]}],
                source,
            )
        )

    if observation.get("sync_conflict"):
        signals.append(
            LifeSignal(
                "signal_sync_conflict",
                "sync_conflict",
                0.85,
                [{"kind": "sync_conflict", "conflict": observation["sync_conflict"]}],
                source,
            )
        )

    if observation.get("stale_goal"):
        signals.append(
            LifeSignal(
                "signal_stale_goal",
                "stale_goal",
                0.35,
                [{"kind": "stale_goal", "goal": observation["stale_goal"]}],
                source,
            )
        )

    return signals
