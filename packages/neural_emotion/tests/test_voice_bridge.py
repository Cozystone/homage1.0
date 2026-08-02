from packages.neural_emotion.models import EmotionVector
from packages.neural_emotion.voice_bridge import attach_voice_plan_metadata, voice_controls


def test_voice_controls_are_plans_when_audio_unavailable() -> None:
    controls = voice_controls(EmotionVector(arousal=0.7, valence=0.4), selected_engine="fallback", audio_available=False)

    assert controls["planned_only"] is True
    assert controls["audio_available"] is False
    assert 0.68 <= controls["speed"] <= 0.96
    assert -0.24 <= controls["pitch_shift"] <= 0.12
    assert controls["fallback_voice_style"] == "soft_warm_local_speech_with_breathing_pauses"
    assert controls["fallback_delivery"] == "short_phrase_breathing_ssml"
    assert controls["real_emotion_claim"] is False


def test_voice_plan_metadata_attaches_without_audio_side_effects() -> None:
    payload = attach_voice_plan_metadata({"text": "hello", "selected_engine": "fish_2", "audio_available": True}, EmotionVector(caution=0.9))

    assert payload["text"] == "hello"
    assert payload["neural_emotion_voice_controls"]["selected_engine"] == "fish_2"
    assert payload["neural_emotion_voice_controls"]["audio_available"] is True
    assert payload["neural_emotion_voice_controls"]["tts_tag"] == "[whispering]"
