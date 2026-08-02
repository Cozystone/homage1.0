from packages.neural_emotion.models import EmotionVector
from packages.neural_emotion.surface_bridge import apply_surface_bias_metadata, surface_bias


def test_surface_bias_is_bounded_and_not_template_answering() -> None:
    controls = surface_bias(EmotionVector(valence=0.8, arousal=0.5, curiosity=0.9, caution=0.2))

    for key in ("warmth", "safety_weight", "brevity", "exploratory_suggestion_weight", "calmness", "formality"):
        assert 0.0 <= controls[key] <= 1.0
    assert controls["fixed_prompt_answer_template"] is False
    assert controls["internal_vector_exposed"] is False


def test_surface_metadata_denies_overclaims() -> None:
    payload = apply_surface_bias_metadata({"answer_engine": "asm_v0"}, EmotionVector())

    assert payload["answer_engine"] == "asm_v0"
    assert payload["real_emotion_claim"] is False
    assert payload["consciousness_claim"] is False
