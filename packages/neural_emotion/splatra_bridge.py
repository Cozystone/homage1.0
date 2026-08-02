from __future__ import annotations

from typing import Any

from .models import EmotionVector, clamp


def splatra_controls(vector: EmotionVector) -> dict[str, Any]:
    valence01 = (clamp(vector.valence, -1.0, 1.0) + 1.0) / 2.0
    arousal01 = (clamp(vector.arousal, -1.0, 1.0) + 1.0) / 2.0
    motion_reduction = 1.0 - vector.fatigue * 0.55
    return {
        "valence": round(vector.valence, 4),
        "arousal": round(arousal01, 4),
        "curiosity": round(vector.curiosity, 4),
        "speaking_energy": round(vector.speaking_energy, 4),
        "color_warmth": round(clamp(0.24 + valence01 * 0.58, 0.0, 1.0), 4),
        "brightness": round(clamp(0.42 + valence01 * 0.28 + arousal01 * 0.14 - vector.fatigue * 0.18, 0.0, 1.0), 4),
        "roundness": round(clamp(0.38 + valence01 * 0.42 - arousal01 * 0.08, 0.0, 1.0), 4),
        "particle_velocity_multiplier": round(clamp((0.26 + arousal01 * 1.1 + vector.speaking_energy * 0.4) * motion_reduction, 0.0, 1.8), 4),
        "shell_ripple_amplitude": round(clamp(0.03 + arousal01 * 0.24 + vector.speaking_energy * 0.22, 0.0, 0.62), 4),
        "fragmentation": round(clamp(0.08 + arousal01 * 0.46 + vector.curiosity * 0.28, 0.0, 1.0), 4),
        "archetype_switch_probability": round(clamp(0.02 + vector.curiosity * 0.32 - vector.caution * 0.08, 0.0, 0.38), 4),
        "motion_multiplier": round(clamp((0.22 + arousal01 * 1.1 + vector.speaking_energy * 0.22) * motion_reduction, 0.0, 1.8), 4),
        "density_multiplier": round(clamp(0.35 + arousal01 * 0.28 + vector.curiosity * 0.2 - vector.fatigue * 0.24, 0.18, 1.0), 4),
        "pulse_amplitude": round(clamp(0.02 + vector.speaking_energy * 0.34, 0.0, 0.42), 4),
        "not_real_emotion": True,
    }


def splatra_seed_kwargs(vector: EmotionVector) -> dict[str, Any]:
    controls = splatra_controls(vector)
    return {
        "valence": controls["valence"],
        "arousal": controls["arousal"],
        "curiosity": controls["curiosity"],
        "speaking_energy": controls["speaking_energy"],
        "state": "resting" if vector.fatigue > 0.8 else "speaking" if vector.speaking_energy > 0.25 else "imagining",
    }
