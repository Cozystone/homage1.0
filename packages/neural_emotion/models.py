from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import time
from typing import Any, Literal


EmotionEvent = Literal[
    "greeting",
    "praise",
    "correction",
    "conflict",
    "memory_request",
    "unsafe_request",
    "approval_granted",
    "approval_denied",
    "tool_success",
    "tool_failure",
    "novelty_found",
    "repeated_failure",
    "resting",
    "speaking_start",
    "speaking_end",
]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def safety_flags() -> dict[str, bool]:
    return {
        "external_llm": False,
        "external_sllm": False,
        "real_emotion_claim": False,
        "consciousness_claim": False,
        "local_brain_write": False,
        "production_store_mutated": False,
        "candidate_promotion": False,
        "unrestricted_shell": False,
        "arbitrary_js_eval": False,
        "auto_commit": False,
        "auto_push": False,
        "proof_only": True,
    }


@dataclass(frozen=True)
class EmotionVector:
    valence: float = 0.0
    arousal: float = 0.0
    curiosity: float = 0.45
    caution: float = 0.35
    fatigue: float = 0.0
    speaking_energy: float = 0.0
    updated_at: float = field(default_factory=time)

    def __post_init__(self) -> None:
        object.__setattr__(self, "valence", clamp(self.valence, -1.0, 1.0))
        object.__setattr__(self, "arousal", clamp(self.arousal, -1.0, 1.0))
        object.__setattr__(self, "curiosity", clamp(self.curiosity, 0.0, 1.0))
        object.__setattr__(self, "caution", clamp(self.caution, 0.0, 1.0))
        object.__setattr__(self, "fatigue", clamp(self.fatigue, 0.0, 1.0))
        object.__setattr__(self, "speaking_energy", clamp(self.speaking_energy, 0.0, 1.0))

    def with_delta(self, **delta: float) -> "EmotionVector":
        return EmotionVector(
            valence=clamp(self.valence + delta.get("valence", 0.0), -1.0, 1.0),
            arousal=clamp(self.arousal + delta.get("arousal", 0.0), -1.0, 1.0),
            curiosity=clamp(self.curiosity + delta.get("curiosity", 0.0), 0.0, 1.0),
            caution=clamp(self.caution + delta.get("caution", 0.0), 0.0, 1.0),
            fatigue=clamp(self.fatigue + delta.get("fatigue", 0.0), 0.0, 1.0),
            speaking_energy=clamp(self.speaking_energy + delta.get("speaking_energy", 0.0), 0.0, 1.0),
            updated_at=delta.get("updated_at", time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PersonalityProfile:
    warmth: float = 0.62
    curiosity_baseline: float = 0.45
    caution_baseline: float = 0.35
    energy_baseline: float = 0.28
    formality: float = 0.62
    playfulness: float = 0.24
    operator_mode: str = "proof_only"

    def __post_init__(self) -> None:
        for name in ("warmth", "curiosity_baseline", "caution_baseline", "energy_baseline", "formality", "playfulness"):
            object.__setattr__(self, name, clamp(getattr(self, name), 0.0, 1.0))

    def baseline_vector(self) -> EmotionVector:
        return EmotionVector(
            valence=(self.warmth - 0.5) * 0.25,
            arousal=(self.energy_baseline - 0.5) * 0.3,
            curiosity=self.curiosity_baseline,
            caution=self.caution_baseline,
            fatigue=0.08,
            speaking_energy=0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EmotionSnapshot:
    vector: EmotionVector
    label: str
    surface_bias: dict[str, Any]
    voice_controls: dict[str, Any]
    splatra_controls: dict[str, Any]
    agentic_controls: dict[str, Any]
    safety_flags: dict[str, bool] = field(default_factory=safety_flags)

    def to_dict(self) -> dict[str, Any]:
        return {
            "vector": self.vector.to_dict(),
            "label": self.label,
            "surface_bias": self.surface_bias,
            "voice_controls": self.voice_controls,
            "splatra_controls": self.splatra_controls,
            "agentic_controls": self.agentic_controls,
            "safety_flags": dict(self.safety_flags),
        }
