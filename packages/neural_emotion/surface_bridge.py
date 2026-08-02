from __future__ import annotations

from typing import Any

from .models import EmotionVector, PersonalityProfile, clamp


def surface_bias(vector: EmotionVector, profile: PersonalityProfile | None = None) -> dict[str, Any]:
    """Map internal state to ASM-v0 discourse controls, not answer templates."""

    profile = profile or PersonalityProfile()
    warmth = clamp(profile.warmth + vector.valence * 0.28 - vector.caution * 0.08, 0.0, 1.0)
    safety_weight = clamp(0.22 + vector.caution * 0.68 + max(0.0, -vector.valence) * 0.08, 0.0, 1.0)
    brevity = clamp(0.34 + max(0.0, vector.arousal) * 0.4 + vector.fatigue * 0.18, 0.0, 1.0)
    exploratory = clamp(0.18 + vector.curiosity * 0.68 - vector.caution * 0.2, 0.0, 1.0)
    calmness = clamp(0.78 - max(0.0, vector.arousal) * 0.36 + vector.fatigue * 0.18, 0.0, 1.0)
    return {
        "warmth": round(warmth, 4),
        "safety_weight": round(safety_weight, 4),
        "brevity": round(brevity, 4),
        "exploratory_suggestion_weight": round(exploratory, 4),
        "calmness": round(calmness, 4),
        "formality": round(clamp(profile.formality + vector.caution * 0.16 - vector.valence * 0.04, 0.0, 1.0), 4),
        "internal_vector_exposed": False,
        "fixed_prompt_answer_template": False,
    }


def apply_surface_bias_metadata(result_metadata: dict[str, Any], vector: EmotionVector) -> dict[str, Any]:
    next_metadata = dict(result_metadata)
    next_metadata["neural_emotion_surface_bias"] = surface_bias(vector)
    next_metadata["real_emotion_claim"] = False
    next_metadata["consciousness_claim"] = False
    return next_metadata
