from packages.neural_emotion.models import EmotionVector, PersonalityProfile, safety_flags


def test_vector_clamps_ranges() -> None:
    vector = EmotionVector(valence=3, arousal=-3, curiosity=4, caution=-1, fatigue=2, speaking_energy=2)

    assert vector.valence == 1.0
    assert vector.arousal == -1.0
    assert vector.curiosity == 1.0
    assert vector.caution == 0.0
    assert vector.fatigue == 1.0
    assert vector.speaking_energy == 1.0


def test_profile_baseline_is_bounded() -> None:
    profile = PersonalityProfile(warmth=2, curiosity_baseline=2, caution_baseline=-1)
    vector = profile.baseline_vector()

    assert 0.0 <= profile.curiosity_baseline <= 1.0
    assert 0.0 <= vector.curiosity <= 1.0
    assert 0.0 <= vector.caution <= 1.0


def test_safety_flags_deny_overclaims_and_mutations() -> None:
    flags = safety_flags()

    assert flags["external_llm"] is False
    assert flags["external_sllm"] is False
    assert flags["real_emotion_claim"] is False
    assert flags["consciousness_claim"] is False
    assert flags["local_brain_write"] is False
    assert flags["production_store_mutated"] is False
    assert flags["proof_only"] is True
