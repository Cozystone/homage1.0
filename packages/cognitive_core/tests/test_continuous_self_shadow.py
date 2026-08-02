from __future__ import annotations

import copy
import threading
import time
import traceback

import pytest

from packages.cognitive_core import CycleLedger, replay_cycle
from packages.cognitive_core import continuous_self_shadow as shadow
from packages.continuous_self.loop import ContinuousSelf
from packages.continuous_self.self_state import Observation, SelfState


def _enable(monkeypatch) -> None:
    monkeypatch.setenv("ATANOR_COGNITIVE_SHADOW", "1")
    monkeypatch.setenv(shadow.CONTINUOUS_SELF_SHADOW_ENV, "1")


def _wait(path) -> None:
    assert shadow.wait_for_continuous_self_shadow(path, timeout=5.0)


def test_exact_flags_and_disabled_span_never_call_path_factory(monkeypatch):
    called = False

    def poison_path():
        nonlocal called
        called = True
        raise AssertionError("disabled observer inspected its ledger path")

    monkeypatch.setenv("ATANOR_COGNITIVE_SHADOW", "true")
    monkeypatch.setenv(shadow.CONTINUOUS_SELF_SHADOW_ENV, "1")
    span = shadow.begin_continuous_self_cycle_shadow(poison_path)
    assert span.enabled is False
    assert span.capture_before_locked(object(), object()) is False
    assert span.capture_after_locked(object()) is False
    assert span.finish(legacy_returned=True) is False
    assert called is False

    monkeypatch.setenv("ATANOR_COGNITIVE_SHADOW", "1")
    monkeypatch.setenv(shadow.CONTINUOUS_SELF_SHADOW_ENV, "yes")
    assert shadow.begin_continuous_self_cycle_shadow(poison_path).enabled is False
    assert called is False


def test_projection_is_an_exact_primitive_allowlist_and_excludes_text():
    first = SelfState()
    first.focus = "FOCUS_SECRET"
    first.current_thought = "THOUGHT_SECRET"
    first.meta_thought = "META_SECRET"
    first.self_question = "QUESTION_SECRET"
    first.self_understanding = "UNDERSTANDING_SECRET"
    first.self_understanding_source = "https://SECRET.invalid"
    first.inquiry_driver = "DRIVER_SECRET"
    first.awareness = "AWARENESS_SECRET"
    first.last_action = {"payload": "ACTION_SECRET"}
    first.attention_bid = {"text": "ATTENTION_SECRET"}
    first.hormones = {"private": "HORMONE_SECRET"}
    first.narrative = [{"text": "NARRATIVE_SECRET"}]

    second = copy.deepcopy(first)
    second.born_at += 999
    second.updated_at += 999
    second.focus = "another focus"
    second.current_thought = "another thought"
    second.meta_thought = "another meta"
    second.self_question = "another question"
    second.self_understanding = "another understanding"
    second.self_understanding_source = "another source"
    second.inquiry_driver = "another driver"
    second.awareness = "another awareness"
    second.last_action = {"payload": "another action"}
    second.attention_bid = {"text": "another attention"}
    second.hormones = {"private": "another hormone"}
    second.narrative = [{"text": "another narrative"}]

    projection = shadow.project_continuous_self_state(first).to_dict()
    assert set(projection) == {
        "collection_lengths",
        "introspection",
        "mode",
        "projection_schema",
        "resumed_count",
        "ticks",
        "vitals",
    }
    assert shadow.continuous_self_projection_digest(
        shadow.project_continuous_self_state(first)
    ) == shadow.continuous_self_projection_digest(
        shadow.project_continuous_self_state(second)
    )

    second.energy = 0.123456
    assert shadow.continuous_self_projection_digest(
        shadow.project_continuous_self_state(first)
    ) != shadow.continuous_self_projection_digest(
        shadow.project_continuous_self_state(second)
    )


def test_unsampled_tick_creates_no_ledger(monkeypatch, tmp_path):
    _enable(monkeypatch)
    ledger_path = tmp_path / "continuous.jsonl"
    continuous = ContinuousSelf(
        tmp_path / "self.json",
        lambda: Observation(),
        shadow_ledger_path=ledger_path,
    )
    continuous.state.ticks = 1
    result = continuous.step()
    assert result is continuous.state
    assert not ledger_path.exists()


def test_sampled_step_records_digest_only_replayable_receipt(monkeypatch, tmp_path):
    _enable(monkeypatch)
    ledger_path = tmp_path / "continuous.jsonl"
    continuous = ContinuousSelf(
        tmp_path / "self.json",
        lambda: Observation(learning_active=True, concepts_delta=2),
        shadow_ledger_path=ledger_path,
    )
    continuous.state.focus = "FOCUS_CANARY_DO_NOT_PERSIST"
    continuous.state.current_thought = "THOUGHT_CANARY_DO_NOT_PERSIST"
    continuous.state.self_question = "QUESTION_CANARY_DO_NOT_PERSIST"
    continuous.state.self_understanding_source = "SOURCE_CANARY_DO_NOT_PERSIST"
    continuous.state.last_action = {"payload": "ACTION_CANARY_DO_NOT_PERSIST"}
    continuous.state.hormones = {"secret": "HORMONE_CANARY_DO_NOT_PERSIST"}

    result = continuous.step()
    assert result is continuous.state
    _wait(ledger_path)

    serialized = ledger_path.read_text(encoding="utf-8")
    assert "CANARY_DO_NOT_PERSIST" not in serialized
    receipts = CycleLedger(
        ledger_path,
        max_bytes=shadow.CONTINUOUS_SELF_LEDGER_MAX_BYTES,
        max_records=shadow.CONTINUOUS_SELF_LEDGER_MAX_RECORDS,
    ).receipts()
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.status.value == "completed"
    assert receipt.selected_route == "observer.continuous_self.step_boundary"
    assert receipt.declared_effects == ("observer_ledger_append",)
    assert receipt.request_cycle.parent_cycle_id is None
    assert receipt.request_cycle.seed == 0
    assert receipt.authoritative is False
    assert receipt.action_authorized is False
    assert "legacy_internal_failures_not_observed" in receipt.limitations
    assert "external_action_authority_unattested" in receipt.limitations
    assert "legacy_effect_set_not_enumerated" in receipt.limitations
    assert "legacy_truth_mutation_unattested" in receipt.limitations
    assert "projection_digests_not_privacy_proof" in receipt.limitations
    assert replay_cycle(receipt).state_hash == receipt.terminal_state_hash


def test_original_exception_object_and_traceback_survive_observer(monkeypatch, tmp_path):
    from packages.continuous_self import loop

    _enable(monkeypatch)
    ledger_path = tmp_path / "failed.jsonl"
    continuous = ContinuousSelf(
        tmp_path / "self.json",
        lambda: Observation(),
        shadow_ledger_path=ledger_path,
    )
    sentinel = RuntimeError("EXCEPTION_SECRET_DO_NOT_PERSIST")

    def raise_original(_state, _observation):
        raise sentinel

    monkeypatch.setattr(loop, "evolve", raise_original)
    with pytest.raises(RuntimeError) as raised:
        continuous.step()
    assert raised.value is sentinel
    frames = [frame.name for frame in traceback.extract_tb(raised.tb)]
    assert "raise_original" in frames
    _wait(ledger_path)
    assert "EXCEPTION_SECRET_DO_NOT_PERSIST" not in ledger_path.read_text(
        encoding="utf-8"
    )
    receipt = CycleLedger(
        ledger_path,
        max_bytes=shadow.CONTINUOUS_SELF_LEDGER_MAX_BYTES,
        max_records=shadow.CONTINUOUS_SELF_LEDGER_MAX_RECORDS,
    ).receipts()[0]
    assert receipt.status.value == "failed"
    assert receipt.output_hash is None


def test_observer_setup_and_capture_faults_never_rerun_step(monkeypatch, tmp_path):
    from packages.cognitive_core import continuous_self_shadow
    from packages.continuous_self import loop

    calls = {"observation": 0, "evolve": 0}

    def observation():
        calls["observation"] += 1
        return Observation()

    original_evolve = loop.evolve

    def counted_evolve(state, obs):
        calls["evolve"] += 1
        return original_evolve(state, obs)

    monkeypatch.setattr(loop, "evolve", counted_evolve)
    monkeypatch.setattr(
        continuous_self_shadow,
        "begin_continuous_self_cycle_shadow",
        lambda _factory: (_ for _ in ()).throw(
            RuntimeError("observer setup failed")
        ),
    )
    continuous = ContinuousSelf(tmp_path / "self.json", observation)
    assert continuous.step() is continuous.state
    assert calls == {"observation": 1, "evolve": 1}

    class BrokenSpan:
        def capture_before_locked(self, _state, _observation):
            raise RuntimeError("capture failed")

        def capture_after_locked(self, _state):
            raise AssertionError("disabled after failed before")

        def finish(self, *, legacy_returned):
            raise AssertionError("disabled finish after failed before")

    monkeypatch.setattr(
        continuous_self_shadow,
        "begin_continuous_self_cycle_shadow",
        lambda _factory: BrokenSpan(),
    )
    assert continuous.step() is continuous.state
    assert calls == {"observation": 2, "evolve": 2}


def test_ledger_append_is_async_and_outside_self_lock(monkeypatch, tmp_path):
    _enable(monkeypatch)
    ledger_path = tmp_path / "async.jsonl"
    continuous = ContinuousSelf(
        tmp_path / "self.json",
        lambda: Observation(),
        shadow_ledger_path=ledger_path,
    )
    entered = threading.Event()
    release = threading.Event()
    lock_states = []
    original_append = shadow.CycleLedger.append

    def stalled_append(ledger, receipt):
        lock_states.append(continuous._lock.locked())
        entered.set()
        assert release.wait(5.0)
        return original_append(ledger, receipt)

    monkeypatch.setattr(shadow.CycleLedger, "append", stalled_append)
    started = time.perf_counter()
    assert continuous.step() is continuous.state
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0
    assert entered.wait(2.0)
    assert lock_states == [False]
    release.set()
    _wait(ledger_path)
    assert CycleLedger(
        ledger_path,
        max_bytes=shadow.CONTINUOUS_SELF_LEDGER_MAX_BYTES,
        max_records=shadow.CONTINUOUS_SELF_LEDGER_MAX_RECORDS,
    ).verify()["record_count"] == 1


def test_bounded_dispatcher_drops_when_writer_is_stalled(monkeypatch, tmp_path):
    _enable(monkeypatch)
    ledger_path = tmp_path / "bounded.jsonl"
    entered = threading.Event()
    release = threading.Event()
    original_append = shadow.CycleLedger.append

    def stalled_append(ledger, receipt):
        entered.set()
        assert release.wait(5.0)
        return original_append(ledger, receipt)

    monkeypatch.setattr(shadow.CycleLedger, "append", stalled_append)
    state = SelfState(ticks=0)
    observation = Observation()

    def submit_one():
        span = shadow.begin_continuous_self_cycle_shadow(lambda: ledger_path)
        assert span.capture_before_locked(state, observation)
        state.ticks += shadow.CONTINUOUS_SELF_SAMPLE_EVERY
        assert span.capture_after_locked(state)
        return span.finish(legacy_returned=True)

    assert submit_one() is True
    assert entered.wait(2.0)
    accepted = [submit_one() for _ in range(shadow.CONTINUOUS_SELF_QUEUE_CAPACITY + 2)]
    assert accepted.count(False) >= 2
    stats = shadow.continuous_self_dispatcher_stats(ledger_path)
    assert stats["pending"] <= shadow.CONTINUOUS_SELF_QUEUE_CAPACITY + 1
    assert stats["dropped"] >= 2
    release.set()
    _wait(ledger_path)


def test_projection_rejects_proxy_before_accessing_its_dict_property():
    accessed = False

    class Proxy:
        @property
        def __dict__(self):
            nonlocal accessed
            accessed = True
            raise AssertionError("proxy descriptor executed")

    with pytest.raises(TypeError, match="exact SelfState"):
        shadow.project_continuous_self_state(Proxy())
    assert accessed is False


def test_finish_requires_a_literal_boolean(monkeypatch, tmp_path):
    _enable(monkeypatch)
    ledger_path = tmp_path / "strict-bool.jsonl"
    state = SelfState(ticks=0)
    span = shadow.begin_continuous_self_cycle_shadow(lambda: ledger_path)
    assert span.capture_before_locked(state, Observation())
    state.ticks = 1
    assert span.capture_after_locked(state)
    assert span.finish(legacy_returned="false") is False
    assert span.fault_count == 1
    assert not ledger_path.exists()


def test_worker_start_failure_does_not_create_a_false_pending_queue(
    monkeypatch,
    tmp_path,
):
    ledger_path = tmp_path / "worker-retry.jsonl"
    dispatcher = shadow.ContinuousSelfReceiptDispatcher(ledger_path)
    receipt = shadow._make_receipt(
        observation_digest="0" * 64,
        before_state_digest="1" * 64,
        after_state_digest="2" * 64,
        legacy_returned=True,
    )
    original_start = shadow.threading.Thread.start
    starts = 0

    def fail_once(worker):
        nonlocal starts
        starts += 1
        if starts == 1:
            raise RuntimeError("thread start failed")
        return original_start(worker)

    monkeypatch.setattr(shadow.threading.Thread, "start", fail_once)
    assert dispatcher.submit(receipt) is False
    assert dispatcher.stats()["pending"] == 0
    assert dispatcher.stats()["failed"] == 1

    second = shadow._make_receipt(
        observation_digest="3" * 64,
        before_state_digest="4" * 64,
        after_state_digest="5" * 64,
        legacy_returned=True,
    )
    assert dispatcher.submit(second) is True
    assert dispatcher.wait_until_idle(5.0)
    assert dispatcher.stats()["completed"] == 1
