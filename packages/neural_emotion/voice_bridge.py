from __future__ import annotations

from typing import Any

from .models import EmotionVector, clamp


def voice_controls(vector: EmotionVector, *, selected_engine: str = "fallback", audio_available: bool = False) -> dict[str, Any]:
    energy = clamp(
        0.4
        + max(0.0, vector.arousal) * 0.28
        + vector.speaking_energy * 0.24
        + max(0.0, vector.valence) * 0.06
        + vector.curiosity * 0.06
        - vector.fatigue * 0.14,
        0.0,
        1.0,
    )
    speed = clamp(
        0.8
        + max(0.0, vector.arousal) * 0.055
        + vector.curiosity * 0.014
        + max(0.0, vector.valence) * 0.018
        - vector.fatigue * 0.11,
        0.68,
        0.96,
    )
    pitch_shift = clamp(vector.valence * 0.045 + max(0.0, vector.arousal) * 0.025 - vector.fatigue * 0.06, -0.24, 0.12)
    caution = vector.caution
    tag = "[whispering]" if caution > 0.76 else "[sigh]" if vector.fatigue > 0.68 else "[laugh]" if vector.valence > 0.62 and vector.arousal > 0.35 else ""
    return {
        "selected_engine": selected_engine,
        "audio_available": bool(audio_available),
        "planned_only": not audio_available,
        "speed": round(speed, 4),
        "pitch_shift": round(pitch_shift, 4),
        "energy": round(energy, 4),
        "temperature": round(clamp(0.52 + vector.curiosity * 0.18 - caution * 0.12, 0.25, 0.8), 4),
        "top_p": round(clamp(0.72 + vector.curiosity * 0.12 - caution * 0.14, 0.45, 0.92), 4),
        "emotion_hint": "cautious" if caution > 0.65 else "curious" if vector.curiosity > 0.68 else "warm" if vector.valence > 0.28 else "calm",
        "tts_tag": tag,
        "fallback_voice_style": "soft_warm_local_speech_with_breathing_pauses",
        "fallback_sentence_gap_ms": int(round(clamp(210 + caution * 90 + vector.fatigue * 135 - vector.arousal * 42, 160, 340))),
        "fallback_delivery": "short_phrase_breathing_ssml",
        "fish_unavailable_fallback_valid": selected_engine == "fallback" or not audio_available,
        "real_emotion_claim": False,
    }


def attach_voice_plan_metadata(
    payload: dict[str, Any],
    vector: EmotionVector,
    *,
    selected_engine: str | None = None,
    audio_available: bool | None = None,
) -> dict[str, Any]:
    next_payload = dict(payload)
    next_payload["neural_emotion_voice_controls"] = voice_controls(
        vector,
        selected_engine=selected_engine or str(payload.get("selected_engine") or "fallback"),
        audio_available=bool(payload.get("audio_available")) if audio_available is None else audio_available,
    )
    return next_payload
