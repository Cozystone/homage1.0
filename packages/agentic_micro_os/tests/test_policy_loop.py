from packages.agentic_micro_os.permission_gate import gate_for_test
from packages.agentic_micro_os.policy_loop import PolicyDrivenAutonomousLoop, PolicyLoopConfig
from packages.agentic_micro_os.review_queue import ReviewQueue
from packages.neural_emotion.event_bus import NeuralEmotionEventBus
from packages.neural_emotion.models import EmotionVector


def _loop(vector: EmotionVector, config: PolicyLoopConfig | None = None, *, review_queue: ReviewQueue | None = None, tmp_path=None):
    bus = NeuralEmotionEventBus()
    bus.engine.vector = vector
    gate = gate_for_test(tmp_path) if tmp_path is not None else None
    return PolicyDrivenAutonomousLoop(config or PolicyLoopConfig(), event_bus=bus, review_queue=review_queue, permission_gate=gate)


def test_curiosity_increases_web_budget() -> None:
    low = _loop(EmotionVector(curiosity=0.1), PolicyLoopConfig(base_web_pages=4)).status()
    high = _loop(EmotionVector(curiosity=0.9), PolicyLoopConfig(base_web_pages=4)).status()

    assert high["web_pages_budget"] > low["web_pages_budget"]


def test_caution_reduces_host_action_budget() -> None:
    calm = _loop(EmotionVector(caution=0.05, fatigue=0.0), PolicyLoopConfig(allow_host_executor=True)).status()
    cautious = _loop(EmotionVector(caution=0.95, fatigue=0.0), PolicyLoopConfig(allow_host_executor=True)).status()

    assert calm["host_action_budget"] == 1
    assert cautious["host_action_budget"] == 0


def test_fatigue_stops_and_suggests_rest() -> None:
    result = _loop(EmotionVector(fatigue=0.95), PolicyLoopConfig(max_cycles=3)).run_once().to_dict()

    assert result["stopped_reason"] == "fatigue"
    assert result["final_policy"]["agent_loop"]["should_rest"] is True


def test_review_pressure_triggers_review_request() -> None:
    queue = ReviewQueue()
    queue.import_payload("source_summary", {"title": "Needs review", "summary": "source summary with evidence words", "source_url": "https://example.com"})
    result = _loop(
        EmotionVector(caution=0.5),
        PolicyLoopConfig(max_cycles=3, review_queue_pressure=0.9),
        review_queue=queue,
    ).run_once().to_dict()

    assert result["stopped_reason"] == "review_requested"
    assert result["review_items"] == 1


def test_repeated_failure_throttles() -> None:
    clean = _loop(EmotionVector(fatigue=0.1), PolicyLoopConfig(recent_failures=0)).status()
    failed = _loop(EmotionVector(fatigue=0.1), PolicyLoopConfig(recent_failures=5)).status()

    assert failed["throttle_multiplier"] < clean["throttle_multiplier"]
    assert failed["web_pages_budget"] <= clean["web_pages_budget"]


def test_tier4_does_not_auto_change_tier(tmp_path) -> None:
    loop = _loop(EmotionVector(caution=0.9), PolicyLoopConfig(), tmp_path=tmp_path)
    status = loop.status()

    assert status["policy_decision"]["autonomy_tier_auto_changed"] is False
    assert status["policy_decision"]["permission_gate_bypass"] is False


def test_loop_stops_at_max_cycles() -> None:
    result = _loop(EmotionVector(curiosity=0.3), PolicyLoopConfig(max_cycles=2, base_web_pages=1)).run_once().to_dict()

    assert result["cycles_completed"] == 2
    assert result["stopped_reason"] == "max_cycles"


def test_no_mutation_invariants() -> None:
    result = _loop(EmotionVector(curiosity=0.9), PolicyLoopConfig(max_cycles=1, allow_host_executor=True)).run_once().to_dict()

    assert result["safety_flags"]["local_brain_write"] is False
    assert result["safety_flags"]["production_store_mutated"] is False
    assert result["safety_flags"]["candidate_promotion"] is False
    assert result["safety_flags"]["auto_commit"] is False
    assert result["safety_flags"]["auto_push"] is False
    assert result["safety_flags"]["permission_gate_bypass"] is False


def test_emergency_stop_halts(tmp_path) -> None:
    gate = gate_for_test(tmp_path)
    gate.trigger_emergency_stop(reason="test")
    bus = NeuralEmotionEventBus()
    loop = PolicyDrivenAutonomousLoop(PolicyLoopConfig(max_cycles=3), event_bus=bus, permission_gate=gate)

    result = loop.run_once().to_dict()

    assert result["stopped_reason"] == "emergency_stop"
    assert result["cycles_completed"] == 1


def test_values_bounded() -> None:
    status = _loop(
        EmotionVector(curiosity=1.0, caution=1.0, fatigue=1.0, arousal=1.0),
        PolicyLoopConfig(max_cycles=99, base_web_pages=99, base_review_batch=99, base_splatra_frames=99, base_host_actions=99),
    ).status()

    assert 0 <= status["web_pages_budget"] <= 30
    assert 0 <= status["review_batch_budget"] <= 30
    assert 0 <= status["splatra_frame_budget"] <= 5
    assert 0 <= status["host_action_budget"] <= 1
