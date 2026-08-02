from __future__ import annotations

import math
from time import time

from .models import EmotionVector, PersonalityProfile, clamp


def decay_toward_baseline(
    vector: EmotionVector,
    profile: PersonalityProfile,
    *,
    now: float | None = None,
    half_life_seconds: float = 480.0,
) -> EmotionVector:
    """Exponentially decay renderer/control state toward personality baseline."""

    current_time = time() if now is None else float(now)
    elapsed = max(0.0, current_time - vector.updated_at)
    if half_life_seconds <= 0:
        retention = 0.0
    else:
        retention = math.pow(0.5, elapsed / half_life_seconds)
    baseline = profile.baseline_vector()

    def mix(current: float, target: float) -> float:
        return target + (current - target) * retention

    return EmotionVector(
        valence=clamp(mix(vector.valence, baseline.valence), -1.0, 1.0),
        arousal=clamp(mix(vector.arousal, baseline.arousal), -1.0, 1.0),
        curiosity=clamp(mix(vector.curiosity, baseline.curiosity), 0.0, 1.0),
        caution=clamp(mix(vector.caution, baseline.caution), 0.0, 1.0),
        fatigue=clamp(mix(vector.fatigue, baseline.fatigue), 0.0, 1.0),
        speaking_energy=clamp(mix(vector.speaking_energy, 0.0), 0.0, 1.0),
        updated_at=current_time,
    )
