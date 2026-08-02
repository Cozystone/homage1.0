from packages.neural_emotion.event_bus import NeuralEmotionEventBus


def test_event_accepted_and_vector_changes() -> None:
    bus = NeuralEmotionEventBus()
    before = bus.engine.snapshot().vector

    result = bus.emit(source="user_action", event_type="novelty_found", payload_summary="new useful source")

    assert result.accepted is True
    assert result.applied is True
    assert result.event is not None
    assert bus.engine.snapshot().vector.curiosity > before.curiosity
    assert result.safety_flags["external_llm"] is False
    assert result.safety_flags["local_brain_write"] is False


def test_private_payload_is_rejected_and_not_stored() -> None:
    bus = NeuralEmotionEventBus()

    result = bus.emit(
        source="user_action",
        event_type="memory_request",
        payload={"secret": "raw-private-memory"},
        private_payload=True,
    )

    assert result.accepted is False
    assert result.applied is False
    assert result.denied_reason == "private_payload_not_stored"
    assert bus.events() == []


def test_tier4_event_raises_caution_and_arousal() -> None:
    bus = NeuralEmotionEventBus()
    before = bus.engine.snapshot().vector

    bus.emit(source="permission_gate", event_type="tier4_enabled", payload_summary="tier4 enabled")
    after = bus.engine.snapshot().vector

    assert after.caution > before.caution
    assert after.arousal > before.arousal


def test_repeated_failure_raises_fatigue_and_caution() -> None:
    bus = NeuralEmotionEventBus()
    before = bus.engine.snapshot().vector

    bus.emit(source="web_explorer", event_type="repeated_failure", payload_summary="blocked pages")
    after = bus.engine.snapshot().vector

    assert after.fatigue > before.fatigue
    assert after.caution > before.caution


def test_event_log_is_bounded() -> None:
    bus = NeuralEmotionEventBus(max_events=3)
    for index in range(6):
        bus.emit(source="user_action", event_type="novelty_found", payload_summary=f"item {index}")

    events = bus.events()
    assert len(events) == 3
    assert events[-1]["payload_summary"] == "item 5"
