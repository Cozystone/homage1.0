from __future__ import annotations

from .quantization import clamp


def map_emotion_to_splatra_controls(valence: float, arousal: float, audio_energy: float = 0.0) -> dict[str, float]:
    valence = clamp(valence, -1.0, 1.0)
    arousal = clamp(arousal, 0.0, 1.0)
    audio_energy = clamp(audio_energy, 0.0, 1.0)
    positive = (valence + 1.0) / 2.0
    return {
        "particle_velocity_multiplier": clamp(0.35 + arousal * 1.15 + audio_energy * 0.35, 0.1, 2.0),
        "shell_ripple_amplitude": clamp(0.04 + arousal * 0.42 + audio_energy * 0.34, 0.0, 1.0),
        "brightness": clamp(0.45 + positive * 0.35 + arousal * 0.1, 0.0, 1.0),
        "color_warmth": clamp(0.18 + positive * 0.72, 0.0, 1.0),
        "audio_deformation_strength": clamp(audio_energy * (0.35 + arousal * 0.65), 0.0, 1.0),
    }
