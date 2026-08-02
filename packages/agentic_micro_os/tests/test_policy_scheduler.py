from pathlib import Path

from packages.agentic_micro_os.permission_gate import gate_for_test
from packages.agentic_micro_os.policy_scheduler import PolicyDrivenAutonomousScheduler, SchedulerConfig
from packages.agentic_micro_os.review_queue import ReviewQueue
from packages.neural_emotion.event_bus import NeuralEmotionEventBus
from packages.neural_emotion.models import EmotionVector


def _scheduler(tmp_path: Path, *, vector: EmotionVector | None = None, config: SchedulerConfig | None = None, queue: ReviewQueue | None = None):
    bus = NeuralEmotionEventBus()
    if vector is not None:
        bus.engine.vector = vector
    gate = gate_for_test(tmp_path)
    cfg = config or SchedulerConfig(
        scheduler_id="test_scheduler",
        stop_file=str(tmp_path / "STOP"),
        emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
    )
    return PolicyDrivenAutonomousScheduler(cfg, event_bus=bus, review_queue=queue or ReviewQueue(), permission_gate=gate)


def test_disabled_by_default(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path)

    state = scheduler.state().to_dict()

    assert state["enabled"] is False
    assert state["stopped_reason"] == "disabled"
    assert state["safety_flags"]["scheduler_opt_in"] is True


def test_start_requires_explicit_request(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path)

    denied = scheduler.start(operator_confirmed=False)
    allowed = scheduler.start(operator_confirmed=True)

    assert denied["allowed"] is False
    assert allowed["allowed"] is True
    assert scheduler.state().enabled is True


def test_stop_works(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.start(operator_confirmed=True)

    stopped = scheduler.stop(reason="test_stop")

    assert stopped["enabled"] is False
    assert stopped["stopped_reason"] == "test_stop"


def test_tick_runs_one_bounded_policy_loop(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path, vector=EmotionVector(curiosity=0.8))
    scheduler.start(operator_confirmed=True)

    payload = scheduler.tick()

    assert payload["ran"] is True
    assert payload["cycle_count"] == 1
    assert payload["last_result"]["cycles_completed"] == 1
    assert payload["last_result"]["safety_flags"]["local_brain_write"] is False


def test_max_cycles_stops(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path, config=SchedulerConfig(max_cycles=1, stop_file=str(tmp_path / "STOP"), emergency_stop_file=str(tmp_path / "EMERGENCY_STOP")))
    scheduler.start(operator_confirmed=True)

    payload = scheduler.tick()

    assert payload["enabled"] is False
    assert payload["stopped_reason"] == "max_cycles"


def test_max_runtime_stops(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path, config=SchedulerConfig(max_runtime_sec=1, stop_file=str(tmp_path / "STOP"), emergency_stop_file=str(tmp_path / "EMERGENCY_STOP")))
    scheduler.start(operator_confirmed=True)
    assert scheduler.started_monotonic is not None
    scheduler.started_monotonic -= 2

    payload = scheduler.tick()

    assert payload["ran"] is False
    assert payload["stopped_reason"] == "max_runtime_sec"


def test_emergency_stop_stops(tmp_path: Path) -> None:
    emergency = tmp_path / "EMERGENCY_STOP"
    emergency.write_text("stop", encoding="utf-8")
    scheduler = _scheduler(tmp_path, config=SchedulerConfig(stop_file=str(tmp_path / "STOP"), emergency_stop_file=str(emergency)))
    scheduler.start(operator_confirmed=True)

    payload = scheduler.tick()

    assert payload["ran"] is False
    assert payload["stopped_reason"] == "emergency_stop"


def test_fatigue_increases_delay(tmp_path: Path) -> None:
    rested = _scheduler(tmp_path / "r", vector=EmotionVector(curiosity=0.4, fatigue=0.0)).state().next_delay_sec
    tired = _scheduler(tmp_path / "t", vector=EmotionVector(curiosity=0.4, fatigue=0.8)).state().next_delay_sec

    assert tired > rested


def test_curiosity_decreases_delay(tmp_path: Path) -> None:
    low = _scheduler(tmp_path / "l", vector=EmotionVector(curiosity=0.1, fatigue=0.1)).state().next_delay_sec
    high = _scheduler(tmp_path / "h", vector=EmotionVector(curiosity=0.9, fatigue=0.1)).state().next_delay_sec

    assert high < low


def test_review_pressure_pauses_exploration(tmp_path: Path) -> None:
    queue = ReviewQueue()
    for index in range(10):
        queue.import_payload("source_summary", {"title": f"review {index}", "summary": "public source summary with evidence", "source_url": f"https://example.com/{index}"})
    scheduler = _scheduler(tmp_path, queue=queue)
    scheduler.start(operator_confirmed=True)

    payload = scheduler.tick()

    assert payload["last_result"]["stopped_reason"] == "review_requested"
    assert payload["last_result"]["candidate_drafts"] == 0


def test_review_import_flag_prevents_queue_mutation(tmp_path: Path) -> None:
    queue = ReviewQueue()
    scheduler = _scheduler(
        tmp_path,
        config=SchedulerConfig(
            max_cycles=1,
            stop_file=str(tmp_path / "STOP"),
            emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
            allow_web_explorer=True,
            allow_review_import=False,
            allow_splatra_generation=False,
            allow_host_executor_status_only=False,
        ),
        queue=queue,
    )
    scheduler.start(operator_confirmed=True)

    payload = scheduler.tick()

    assert payload["ran"] is True
    assert queue.status()["items_total"] == 0
    assert (
        "review_import_disabled"
        in payload["last_result"]["states"][0]["actions_taken"]
    )


def test_no_mutation_flags(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path, vector=EmotionVector(curiosity=0.8))
    scheduler.start(operator_confirmed=True)

    payload = scheduler.tick()

    assert payload["safety_flags"]["local_brain_write"] is False
    assert payload["safety_flags"]["production_store_mutated"] is False
    assert payload["safety_flags"]["candidate_promotion"] is False
    assert payload["safety_flags"]["auto_commit"] is False
    assert payload["safety_flags"]["auto_push"] is False
