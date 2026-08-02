from __future__ import annotations

import copy
import hashlib
import threading

import packages.cgsr.cgsr.response_workspace as response_workspace
from packages.cgsr.cgsr.comprehension import perceive
from packages.cgsr.cgsr.response_workspace import compose_response
from packages.temporal_reasoning.block_universe import BlockUniverse
from packages.temporal_reasoning.precedence_field import PrecedenceField
from packages.temporal_reasoning.unified_timeline import Timeline
from packages.world4d import BlockUniverseShadowProvider, JsonlReceiptSink
from packages.world4d import World4DShadowDispatcher
from packages.world4d.block_universe_provider import DEFAULT_PRECEDENCE_ARTIFACT
from packages.world4d import shadow as world_shadow


QUESTION = "What typically comes after we grow the crops?"


def _field() -> PrecedenceField:
    return PrecedenceField(
        phase={"plant": -0.9, "grow": -0.3, "harvest": 0.3, "eat": 0.9},
        seen={"plant": 5, "grow": 5, "harvest": 5, "eat": 5},
    )


def _covered_universe(raw_question: str) -> BlockUniverse:
    timeline = Timeline()
    timeline.record("utterance", raw_question, who="user")
    return BlockUniverse(timeline, _field())


def _shadow_provider() -> BlockUniverseShadowProvider:
    return BlockUniverseShadowProvider(
        universe_factory=lambda timeline: BlockUniverse(timeline, _field())
    )


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(
        response_workspace,
        "_shared_block_universe",
        _covered_universe,
    )
    monkeypatch.setattr(world_shadow, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        world_shadow,
        "BlockUniverseShadowProvider",
        _shadow_provider,
    )


def test_default_off_preserves_answer_and_creates_no_world4d_ledger(
    monkeypatch,
    tmp_path,
):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.delenv(world_shadow.SHADOW_ENV, raising=False)

    result = compose_response(perceive(QUESTION, []), QUESTION)

    assert result is not None
    assert result["answer_kind"] == "temporal_projection"
    assert not (tmp_path / world_shadow.SHADOW_LEDGER_RELATIVE).exists()


def test_enabled_sibling_shadow_preserves_exact_answer_and_adds_one_receipt(
    monkeypatch,
    tmp_path,
):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.delenv(world_shadow.SHADOW_ENV, raising=False)
    disabled = compose_response(perceive(QUESTION, []), QUESTION)
    disabled_copy = copy.deepcopy(disabled)

    monkeypatch.setenv(world_shadow.SHADOW_ENV, "1")
    enabled = compose_response(perceive(QUESTION, []), QUESTION)

    assert enabled == disabled_copy
    assert world_shadow.wait_for_temporal_shadow_idle(5.0)
    path = tmp_path / world_shadow.SHADOW_LEDGER_RELATIVE
    sink = JsonlReceiptSink(path)
    receipts = sink.receipts()
    assert len(receipts) == 1
    assert receipts[0].adapter_answer_influenced is False
    assert receipts[0].provider_status == "proposed"
    serialized = path.read_text(encoding="utf-8")
    assert QUESTION not in serialized
    assert "harvest" not in serialized


def test_non_temporal_request_never_invokes_world4d_shadow(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv(world_shadow.SHADOW_ENV, "1")
    question = "What is a cat?"

    compose_response(perceive(question, []), question)

    assert not (tmp_path / world_shadow.SHADOW_LEDGER_RELATIVE).exists()


def test_shadow_failure_cannot_change_legacy_temporal_answer(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.delenv(world_shadow.SHADOW_ENV, raising=False)
    baseline = compose_response(perceive(QUESTION, []), QUESTION)

    def fail_shadow(**_kwargs):
        raise RuntimeError("observer-only failure")

    monkeypatch.setenv(world_shadow.SHADOW_ENV, "1")
    monkeypatch.setattr(world_shadow, "submit_temporal_query_shadow", fail_shadow)
    observed = compose_response(perceive(QUESTION, []), QUESTION)

    assert observed == baseline
    assert not (tmp_path / world_shadow.SHADOW_LEDGER_RELATIVE).exists()


def test_only_exact_one_enables_live_shadow(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv(world_shadow.SHADOW_ENV, "true")

    compose_response(perceive(QUESTION, []), QUESTION)

    assert not (tmp_path / world_shadow.SHADOW_LEDGER_RELATIVE).exists()


def test_live_submission_does_not_wait_for_stalled_observer(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.delenv(world_shadow.SHADOW_ENV, raising=False)
    baseline = compose_response(perceive(QUESTION, []), QUESTION)
    worker_started = threading.Event()
    release_worker = threading.Event()
    response_finished = threading.Event()
    result_box = {}

    def stalled_worker(_query):
        worker_started.set()
        release_worker.wait(2.0)
        return True

    dispatcher = World4DShadowDispatcher(worker=stalled_worker, capacity=1)
    monkeypatch.setattr(world_shadow, "_DISPATCHER", dispatcher)
    monkeypatch.setenv(world_shadow.SHADOW_ENV, "1")

    def call_response():
        try:
            result_box["value"] = compose_response(
                perceive(QUESTION, []),
                QUESTION,
            )
        finally:
            response_finished.set()

    thread = threading.Thread(target=call_response, daemon=True)
    thread.start()
    worker_seen = worker_started.wait(1.0)
    returned_while_blocked = response_finished.wait(0.5)
    release_worker.set()
    assert dispatcher.wait_idle(2.0)
    thread.join(timeout=2.0)

    assert worker_seen is True
    assert returned_while_blocked is True
    assert result_box["value"] == baseline


def test_async_live_path_binds_repository_artifact_digest(monkeypatch, tmp_path):
    monkeypatch.setattr(world_shadow, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(world_shadow, "_DISPATCHER", None)
    monkeypatch.setenv(world_shadow.SHADOW_ENV, "1")
    with DEFAULT_PRECEDENCE_ARTIFACT.open("rb") as handle:
        expected_digest = hashlib.file_digest(handle, "sha256").hexdigest()

    assert world_shadow.submit_temporal_query_shadow(
        question=QUESTION,
        direction="forward",
    )
    assert world_shadow.wait_for_temporal_shadow_idle(5.0)

    dispatcher = world_shadow._DISPATCHER
    assert dispatcher is not None
    assert dispatcher.snapshot()["failed"] == 0
    sink = JsonlReceiptSink(tmp_path / world_shadow.SHADOW_LEDGER_RELATIVE)
    receipts = sink.receipts()
    assert len(receipts) == 1
    assert receipts[0].model_artifact_digest == expected_digest
    assert receipts[0].provider_effects_attested is False
