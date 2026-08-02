from __future__ import annotations

from packages.splatra_imagination.emotion_bridge import imagination_controls


def test_emotion_controls_are_bounded_and_not_real_emotion() -> None:
    controls = imagination_controls(valence=5, arousal=8, curiosity=-2, speaking_energy=4, state="speaking")

    assert 0.0 <= controls["brightness"] <= 1.0
    assert 0.0 <= controls["color_warmth"] <= 1.0
    assert 0.0 <= controls["fragmentation"] <= 1.0
    assert controls["speaking_energy"] == 1.0
    assert controls["not_real_emotion"] is True


def test_resting_lowers_motion_and_density() -> None:
    active = imagination_controls(valence=0, arousal=0.8, curiosity=0.8, state="imagining")
    resting = imagination_controls(valence=0, arousal=0.8, curiosity=0.8, state="resting")

    assert resting["motion_multiplier"] < active["motion_multiplier"]
    assert resting["density_multiplier"] < active["density_multiplier"]
