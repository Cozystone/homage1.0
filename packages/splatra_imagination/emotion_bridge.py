from __future__ import annotations

from typing import Any

from packages.splatra_turbovec.emotion_mapping import map_emotion_to_splatra_controls


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def imagination_controls(
    *,
    valence: float,
    arousal: float,
    curiosity: float,
    speaking_energy: float = 0.0,
    state: str = "imagining",
) -> dict[str, Any]:
    """Map bounded selfhood state to visual controls; this is not a claim of real emotion."""

    valence = clamp(valence, -1.0, 1.0)
    arousal = clamp(arousal, 0.0, 1.0)
    curiosity = clamp(curiosity, 0.0, 1.0)
    speaking_energy = clamp(speaking_energy, 0.0, 1.0)
    base = map_emotion_to_splatra_controls(valence, arousal, speaking_energy)
    resting = state == "resting"
    return {
        **base,
        "visual_state": state,
        "roundness": clamp(0.35 + ((valence + 1.0) / 2.0) * 0.45 - arousal * 0.08, 0.0, 1.0),
        "fragmentation": clamp(0.12 + arousal * 0.68 + curiosity * 0.18, 0.0, 1.0),
        "archetype_switch_probability": clamp(0.02 + curiosity * 0.28, 0.0, 0.35),
        "motion_multiplier": 0.18 if resting else clamp(0.3 + arousal * 1.2 + speaking_energy * 0.3, 0.0, 1.8),
        "density_multiplier": 0.55 if resting else clamp(0.55 + arousal * 0.25 + curiosity * 0.2, 0.25, 1.0),
        "shell_ripple_amplitude": 0.025 if resting else base["shell_ripple_amplitude"],
        "speaking_energy": speaking_energy,
        "not_real_emotion": True,
    }
