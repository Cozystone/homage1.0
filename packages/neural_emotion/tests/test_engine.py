from packages.neural_emotion import EmotionEngine


def test_engine_updates_from_user_input_without_external_models() -> None:
    engine = EmotionEngine()
    before = engine.snapshot()

    engine.update_from_user_input("안녕, 오늘 새로운 것을 찾아보자")
    after = engine.snapshot()

    assert after.vector.valence >= before.vector.valence
    assert after.safety_flags["external_llm"] is False
    assert after.safety_flags["real_emotion_claim"] is False


def test_engine_unsafe_event_raises_caution() -> None:
    engine = EmotionEngine()
    before = engine.snapshot().vector

    engine.update("unsafe_request")
    after = engine.snapshot().vector

    assert after.caution > before.caution
    assert engine.snapshot().agentic_controls["permission_gate_bypass"] is False
