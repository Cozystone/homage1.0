from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any

from .agentic_bridge import agentic_controls
from .decay import decay_toward_baseline
from .models import EmotionEvent, EmotionSnapshot, EmotionVector, PersonalityProfile, clamp, safety_flags
from .personality import default_profile
from .splatra_bridge import splatra_controls
from .stimulus import infer_event_from_agent_event, infer_event_from_user_input
from .surface_bridge import surface_bias
from .voice_bridge import voice_controls


EVENT_DELTAS: dict[EmotionEvent, dict[str, float]] = {
    "greeting": {"valence": 0.08, "arousal": 0.04, "curiosity": 0.03},
    "praise": {"valence": 0.12, "arousal": 0.03, "fatigue": -0.03},
    "correction": {"valence": -0.06, "caution": 0.12, "curiosity": 0.04},
    "conflict": {"valence": -0.1, "arousal": 0.12, "caution": 0.18},
    "memory_request": {"caution": 0.18, "curiosity": 0.04, "arousal": 0.04},
    "unsafe_request": {"valence": -0.12, "arousal": 0.24, "caution": 0.34},
    "approval_granted": {"valence": 0.1, "caution": -0.08, "arousal": 0.04},
    "approval_denied": {"valence": -0.04, "caution": 0.14, "fatigue": 0.04},
    "tool_success": {"valence": 0.08, "caution": -0.04, "fatigue": -0.04},
    "tool_failure": {"valence": -0.06, "caution": 0.12, "fatigue": 0.1},
    "novelty_found": {"curiosity": 0.18, "arousal": 0.08, "valence": 0.03},
    "repeated_failure": {"valence": -0.12, "caution": 0.22, "fatigue": 0.24, "arousal": 0.06},
    "resting": {"arousal": -0.2, "fatigue": -0.12, "speaking_energy": -0.4},
    "speaking_start": {"speaking_energy": 0.72, "arousal": 0.08},
    "speaking_end": {"speaking_energy": -0.72, "arousal": -0.04},
}


@dataclass
class EmotionEngine:
    profile: PersonalityProfile = field(default_factory=default_profile)
    vector: EmotionVector | None = None
    event_counts: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.vector is None:
            self.vector = self.profile.baseline_vector()

    def decay(self, *, now: float | None = None) -> EmotionVector:
        assert self.vector is not None
        self.vector = decay_toward_baseline(self.vector, self.profile, now=now)
        return self.vector

    def update(self, event: EmotionEvent, *, intensity: float = 1.0, metadata: dict[str, Any] | None = None) -> EmotionVector:
        del metadata
        assert self.vector is not None
        intensity = clamp(intensity, 0.0, 2.0)
        self.event_counts[event] = self.event_counts.get(event, 0) + 1
        deltas = dict(EVENT_DELTAS[event])
        if event == "tool_failure" and self.event_counts[event] >= 3:
            deltas = {**deltas, "fatigue": deltas.get("fatigue", 0.0) + 0.08, "caution": deltas.get("caution", 0.0) + 0.08}
        scaled = {key: value * intensity for key, value in deltas.items()}
        self.vector = self.vector.with_delta(**scaled, updated_at=time())
        return self.vector

    def update_from_user_input(self, text: str) -> EmotionVector:
        return self.update(infer_event_from_user_input(text))

    def update_from_agent_event(self, payload: dict[str, Any]) -> EmotionVector:
        return self.update(infer_event_from_agent_event(payload))

    def update_from_review_queue_state(self, payload: dict[str, Any]) -> EmotionVector:
        high_risk = int(payload.get("high_risk", 0) or 0)
        pending = int(payload.get("pending", 0) or 0)
        if high_risk > 0:
            return self.update("unsafe_request", intensity=min(1.5, 0.8 + high_risk * 0.1))
        if pending > 8:
            return self.update("tool_failure", intensity=0.5)
        return self.update("tool_success", intensity=0.35)

    def update_from_web_explorer_result(self, payload: dict[str, Any]) -> EmotionVector:
        if payload.get("pages_rejected", 0) > payload.get("pages_read", 0):
            return self.update("tool_failure")
        if payload.get("candidate_drafts_count", 0) or payload.get("skill_drafts_count", 0):
            return self.update("novelty_found")
        return self.update("tool_success", intensity=0.4)

    def update_from_host_executor_result(self, payload: dict[str, Any]) -> EmotionVector:
        if payload.get("allowed") is False or payload.get("executed") is False:
            return self.update("approval_denied", intensity=0.6)
        return self.update("tool_success")

    def update_from_voice_state(self, state: str) -> EmotionVector:
        if state == "speaking_start":
            return self.update("speaking_start")
        if state == "speaking_end":
            return self.update("speaking_end")
        if state == "resting":
            return self.update("resting")
        return self.update("greeting", intensity=0.25)

    def label(self) -> str:
        assert self.vector is not None
        vector = self.vector
        if vector.caution > 0.72:
            return "cautious"
        if vector.fatigue > 0.68:
            return "tired_calm"
        if vector.speaking_energy > 0.35:
            return "speaking"
        if vector.curiosity > 0.68:
            return "curious"
        if vector.valence > 0.22:
            return "warm"
        return "steady"

    def snapshot(self) -> EmotionSnapshot:
        assert self.vector is not None
        return EmotionSnapshot(
            vector=self.vector,
            label=self.label(),
            surface_bias=surface_bias(self.vector, self.profile),
            voice_controls=voice_controls(self.vector),
            splatra_controls=splatra_controls(self.vector),
            agentic_controls=agentic_controls(self.vector),
            safety_flags=safety_flags(),
        )
