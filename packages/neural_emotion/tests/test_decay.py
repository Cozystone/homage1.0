from packages.neural_emotion.decay import decay_toward_baseline
from packages.neural_emotion.models import EmotionVector
from packages.neural_emotion.personality import default_profile


def test_decay_moves_toward_profile_baseline() -> None:
    profile = default_profile()
    baseline = profile.baseline_vector()
    vector = EmotionVector(valence=0.9, arousal=0.9, curiosity=0.9, caution=0.9, fatigue=0.9, updated_at=100.0)

    decayed = decay_toward_baseline(vector, profile, now=100.0 + 960.0, half_life_seconds=480.0)

    assert abs(decayed.valence - baseline.valence) < abs(vector.valence - baseline.valence)
    assert abs(decayed.arousal - baseline.arousal) < abs(vector.arousal - baseline.arousal)
    assert decayed.fatigue < vector.fatigue
