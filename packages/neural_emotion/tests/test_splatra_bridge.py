from packages.neural_emotion.models import EmotionVector
from packages.neural_emotion.splatra_bridge import splatra_controls, splatra_seed_kwargs


def test_splatra_controls_are_bounded_visual_controls() -> None:
    controls = splatra_controls(EmotionVector(valence=0.7, arousal=0.8, curiosity=0.9, speaking_energy=0.5))

    assert -1.0 <= controls["valence"] <= 1.0
    for key in ("arousal", "curiosity", "speaking_energy", "brightness", "roundness", "fragmentation"):
      assert 0.0 <= controls[key] <= 1.0
    assert controls["not_real_emotion"] is True


def test_splatra_seed_kwargs_selects_state() -> None:
    kwargs = splatra_seed_kwargs(EmotionVector(speaking_energy=0.7))

    assert kwargs["state"] == "speaking"
    assert "valence" in kwargs
