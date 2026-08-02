from packages.splatra_turbovec.emotion_mapping import map_emotion_to_splatra_controls


def test_emotion_mapping_bounded_and_directional():
    calm = map_emotion_to_splatra_controls(0.0, 0.1)
    high = map_emotion_to_splatra_controls(0.8, 1.0)
    negative = map_emotion_to_splatra_controls(-1.0, 0.7)
    speaking = map_emotion_to_splatra_controls(0.2, 0.5, audio_energy=1.0)
    assert high["shell_ripple_amplitude"] > calm["shell_ripple_amplitude"]
    assert high["particle_velocity_multiplier"] > calm["particle_velocity_multiplier"]
    assert high["color_warmth"] > negative["color_warmth"]
    assert speaking["audio_deformation_strength"] > calm["audio_deformation_strength"]
    for controls in (calm, high, negative, speaking):
        assert all(0.0 <= value <= 2.0 for value in controls.values())
