from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import threading
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

from app.routers import continuous_self
from packages.autonomy_envelope.run_lease import (
    RUN_LEASE_PURPOSE,
    RunLeaseFinishResult,
    RunLeaseStore,
)
from packages.autonomy_envelope.tests.test_run_lease import (
    _provision_boundary,
    _signed_lease,
)
from packages.continuous_self import homeostasis
from packages.continuous_self.loop import ContinuousSelf
from packages.continuous_self.self_state import Observation, SelfState
from scripts import issue_autonomy_run_lease as run_lease_issuer


def _limits(cycles: int) -> dict[str, int]:
    return {
        "max_runtime_sec": 60,
        "max_cycles": cycles,
        "max_actions": cycles * 3 + 1,
        "max_external_requests": 0,
        "max_external_response_bytes": 0,
        "max_scratch_write_bytes": cycles
        * (
            continuous_self._STATE_WRITE_RESERVATION_BYTES
            + continuous_self._AUDIT_RECORD_MAX_BYTES
        ),
        "max_child_tasks": 0,
        "max_concurrent_child_tasks": 0,
    }


def _wait_until(predicate, timeout: float = 4.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


@pytest.fixture(autouse=True)
def _isolated_self(monkeypatch, tmp_path):
    continuous_self._SELF.stop(reason="test_reset")
    continuous_self._clear_continuous_self_run_lease_for_tests()
    continuous_self._SELF.state_path = tmp_path / "self.json"
    continuous_self._SELF.shadow_ledger_path = tmp_path / "shadow.jsonl"
    continuous_self._SELF.state = SelfState()
    continuous_self._SELF.obs_provider = lambda: Observation(
        concepts_delta=1,
        uncertainty_signal=0.7,
        resource_pressure=0.2,
    )
    continuous_self._SELF.observe_fn = lambda _kind: {"observed": True}
    continuous_self._SELF.identity_fn = None
    continuous_self._SELF.research_fn = lambda _question: pytest.fail(
        "AUT-0 must not call web research"
    )
    continuous_self._SELF.base_interval = 0.01
    monkeypatch.setattr(
        homeostasis,
        "consume_felt_events",
        lambda _state, **_kwargs: None,
    )
    yield
    continuous_self._SELF.stop(reason="test_reset")
    continuous_self._clear_continuous_self_run_lease_for_tests()


def _configured_lease(tmp_path, *, cycles: int = 3, **lease_kwargs):
    private, boundary, _ = _provision_boundary(tmp_path)
    store = RunLeaseStore(boundary)
    context = continuous_self.configure_continuous_self_run_lease(
        store,
        runtime_instance_id="continuous-self-api-test",
        limits=_limits(cycles),
    )
    if not lease_kwargs:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        lease_kwargs = {
            "issued_at": now - timedelta(seconds=1),
            "expires_at": now + timedelta(seconds=30),
        }
    lease = _signed_lease(
        private,
        boundary,
        context,
        **lease_kwargs,
    )
    return store, context, lease


def test_router_import_and_reads_do_not_start_continuous_self(monkeypatch):
    calls: list[ContinuousSelf] = []

    def forbidden_start(instance: ContinuousSelf) -> bool:
        calls.append(instance)
        raise AssertionError("import and GET routes must remain dormant")

    continuous_self._SELF.stop(reason="test_reset")
    monkeypatch.setattr(ContinuousSelf, "start", forbidden_start)
    reloaded = importlib.reload(continuous_self)

    live = reloaded.selfhood_live()
    consciousness = reloaded.selfhood_consciousness()
    lease_context = reloaded.selfhood_lease_context()
    stream = asyncio.run(reloaded.selfhood_stream())
    deepen = reloaded.selfhood_deepen({})

    assert calls == []
    assert reloaded._SELF.running is False
    assert live["continuous"] is False
    assert consciousness["lifecycle"]["state"] == "dormant"
    assert stream.media_type == "text/event-stream"
    assert lease_context["available"] is False
    assert lease_context["configured"] is False
    assert lease_context["reason"] == "run_lease_store_not_provisioned"
    assert lease_context["purpose"] == RUN_LEASE_PURPOSE
    assert lease_context["live_context"] is None
    assert lease_context["live_context_sha256"] is None
    assert lease_context["context"] is None
    assert lease_context["signer_present_in_api"] is False
    assert lease_context["private_key_required_outside_api"] is True
    assert deepen == {"error": "query_required"}
    assert reloaded.selfhood_lifecycle()["reason"] == (
        "run_lease_store_not_provisioned"
    )


def test_boolean_or_expired_request_cannot_start(tmp_path):
    denied = continuous_self.selfhood_start({"operator_confirmed": True})
    assert denied["started"] is False
    assert denied["reason"] == "run_lease_store_not_provisioned"

    now = datetime.now(timezone.utc).replace(microsecond=0)
    _, _, expired = _configured_lease(
        tmp_path,
        issued_at=now - timedelta(seconds=20),
        expires_at=now - timedelta(seconds=1),
    )
    result = continuous_self.selfhood_start({"run_lease": expired})

    assert result["started"] is False
    assert result["reason"] == "run_lease_expired"
    assert continuous_self._SELF.running is False


def test_valid_lease_advances_state_persists_audit_and_stops(tmp_path):
    store, context, lease = _configured_lease(tmp_path, cycles=3)
    tick_before = continuous_self._SELF.state.ticks
    assert continuous_self.selfhood_lease_context()["context"] == context

    started = continuous_self.selfhood_start({"run_lease": lease})
    assert started["ok"] is True, started
    assert started["started"] is True
    audit_path = (
        continuous_self._SELF.state_path.parent
        / "aut0_cycle_audit.jsonl"
    )
    assert _wait_until(
        lambda: continuous_self._SELF.state_path.is_file()
        and audit_path.is_file()
    )
    assert continuous_self._SELF.state.ticks > tick_before

    stopped = continuous_self.selfhood_stop()
    status = store.status()["runners"][
        continuous_self.CONTINUOUS_SELF_RUNNER_ID
    ]

    assert stopped["ok"] is True
    assert stopped["stopped"] is True
    assert stopped["stop_pending"] is False
    assert continuous_self._SELF.running is False
    assert continuous_self._SELF.state_path.is_file()
    assert audit_path.is_file()
    assert status["status"] == "finished"
    assert status["counters"]["cycles"] >= 1
    assert status["counters"]["actions"] >= 3
    assert status["counters"]["external_requests"] == 0
    assert status["counters"]["child_tasks"] == 0


def test_standard_lease_context_issues_external_lease_and_starts(
    tmp_path,
):
    private, boundary, _ = _provision_boundary(tmp_path)
    store = RunLeaseStore(boundary)
    context = continuous_self.configure_continuous_self_run_lease(
        store,
        runtime_instance_id="continuous-self-issuer-e2e",
        limits=_limits(2),
    )
    wrapper = continuous_self.selfhood_lease_context()

    assert wrapper["available"] is True
    assert wrapper["purpose"] == RUN_LEASE_PURPOSE
    assert wrapper["live_context"] == context
    assert wrapper["context"] == context
    assert wrapper["live_context_sha256"] == (
        continuous_self._canonical_sha256(context)
    )
    assert wrapper["signer_present_in_api"] is False
    assert wrapper["private_key_required_outside_api"] is True
    assert wrapper["expected_key_id"] == boundary.expected_key_id

    context_path = tmp_path / "continuous-self-lease-context.json"
    context_path.write_text(
        json.dumps(wrapper, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    private_path = tmp_path / "operator-private.pem"
    private_path.write_bytes(
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    lease_path = tmp_path / "continuous-self-run-lease.json"
    receipt = run_lease_issuer.issue_run_lease_file(
        input_path=context_path,
        output_path=lease_path,
        private_key_path=private_path.resolve(),
        duration_sec=30,
        lease_id="continuous-self-issuer-e2e-lease",
        nonce="continuous-self-issuer-e2e-nonce",
        trust_config_path=boundary.config_path,
    )
    lease = json.loads(lease_path.read_text(encoding="utf-8"))

    assert receipt["ok"] is True
    started = continuous_self.selfhood_start({"run_lease": lease})
    assert started["started"] is True, started
    assert _wait_until(lambda: continuous_self._SELF.state_path.is_file())
    assert continuous_self.selfhood_stop()["stop_pending"] is False


def test_stop_cannot_be_lost_between_lease_activation_and_worker_start(
    monkeypatch,
    tmp_path,
):
    _, _, lease = _configured_lease(tmp_path, cycles=3)
    armed = threading.Event()
    release_arm = threading.Event()
    stop_returned = threading.Event()
    original_arm = continuous_self._SELF.arm
    results: dict[str, dict] = {}

    def blocking_arm(*args, **kwargs):
        original_arm(*args, **kwargs)
        armed.set()
        assert release_arm.wait(timeout=4.0)

    monkeypatch.setattr(continuous_self._SELF, "arm", blocking_arm)

    start_thread = threading.Thread(
        target=lambda: results.setdefault(
            "start",
            continuous_self.selfhood_start({"run_lease": lease}),
        ),
        name="continuous-self-start-request",
    )
    stop_thread = threading.Thread(
        target=lambda: (
            results.setdefault("stop", continuous_self.selfhood_stop()),
            stop_returned.set(),
        ),
        name="continuous-self-stop-request",
    )
    start_thread.start()
    assert armed.wait(timeout=4.0)
    stop_thread.start()

    assert stop_returned.wait(timeout=0.1) is False
    release_arm.set()
    start_thread.join(timeout=4.0)
    stop_thread.join(timeout=4.0)

    assert start_thread.is_alive() is False
    assert stop_thread.is_alive() is False
    assert results["start"]["started"] is True
    assert results["stop"]["stop_pending"] is False
    assert continuous_self._SELF.running is False
    assert continuous_self._SELF.lease_telemetry()["lease_finalized"] is True


@pytest.mark.parametrize(
    "failure_mode",
    ["arm_exception", "start_exception", "start_false"],
)
def test_activated_lease_is_finished_when_worker_never_starts(
    monkeypatch,
    tmp_path,
    failure_mode,
):
    store, _, lease = _configured_lease(tmp_path, cycles=1)

    if failure_mode == "arm_exception":
        def fail_arm(*_args, **_kwargs):
            raise RuntimeError("injected arm failure")

        monkeypatch.setattr(continuous_self._SELF, "arm", fail_arm)
    elif failure_mode == "start_exception":
        def fail_start():
            raise RuntimeError("injected start failure")

        monkeypatch.setattr(continuous_self._SELF, "start", fail_start)
    else:
        monkeypatch.setattr(
            continuous_self._SELF,
            "start",
            lambda: False,
        )

    refused = continuous_self.selfhood_start({"run_lease": lease})

    assert refused["started"] is False
    assert refused["reason"] == "continuous_self_runner_start_failed"
    runner = store.status()["runners"][
        continuous_self.CONTINUOUS_SELF_RUNNER_ID
    ]
    assert runner["status"] == "finished"
    assert runner["finish_reason"] == "runner_start_failed"
    telemetry = continuous_self._SELF.lease_telemetry()
    assert telemetry["lease_finalized"] is True
    assert telemetry["lease_id"] is None
    assert continuous_self._SELF.running is False
    replay = continuous_self.selfhood_start({"run_lease": lease})
    assert replay["reason"] == "run_lease_replay"
    assert store.status()["consumed_nonce_count"] == 1


def test_failed_start_finish_can_be_retried_from_stop(
    monkeypatch,
    tmp_path,
):
    store, _, lease = _configured_lease(tmp_path, cycles=1)
    original_finish = store.finish
    calls: list[str] = []

    def fail_once(**kwargs):
        calls.append(kwargs["reason"])
        if len(calls) == 1:
            return RunLeaseFinishResult(
                False,
                "injected_finish_failure",
                kwargs["lease_id"],
                kwargs["runner_id"],
            )
        return original_finish(**kwargs)

    monkeypatch.setattr(store, "finish", fail_once)
    monkeypatch.setattr(
        continuous_self._SELF,
        "start",
        lambda: False,
    )

    refused = continuous_self.selfhood_start({"run_lease": lease})

    assert refused["state"] == "termination_pending"
    assert store.status()["runners"][
        continuous_self.CONTINUOUS_SELF_RUNNER_ID
    ]["status"] == "active"
    retried = continuous_self.selfhood_stop()
    assert retried["state"] == "dormant"
    assert retried["lease"]["lease_finalized"] is True
    assert retried["lease"]["lease_id"] is None
    assert calls == ["runner_start_failed", "runner_start_failed"]
    assert store.status()["runners"][
        continuous_self.CONTINUOUS_SELF_RUNNER_ID
    ]["status"] == "finished"


def test_dead_worker_finish_can_be_retried_from_stop(
    monkeypatch,
    tmp_path,
):
    store, _, lease = _configured_lease(tmp_path, cycles=1)
    original_finish = store.finish
    calls: list[tuple[str, str]] = []

    def fail_once(**kwargs):
        calls.append(
            (threading.current_thread().name, kwargs["reason"])
        )
        if len(calls) == 1:
            return RunLeaseFinishResult(
                False,
                "injected_finish_failure",
                kwargs["lease_id"],
                kwargs["runner_id"],
            )
        return original_finish(**kwargs)

    monkeypatch.setattr(store, "finish", fail_once)
    started = continuous_self.selfhood_start({"run_lease": lease})
    assert started["started"] is True
    assert _wait_until(lambda: not continuous_self._SELF.running)

    pending = continuous_self.selfhood_lifecycle()
    assert pending["state"] == "termination_pending"
    assert pending["lease"]["pending_finish_reason"] == "authority_denied"
    assert pending["lease_store_runner"]["status"] == "active"

    retried = continuous_self.selfhood_stop()

    assert retried["state"] == "dormant"
    assert retried["lease"]["lease_finalized"] is True
    assert retried["lease"]["termination_reason"] == "authority_denied"
    assert calls == [
        ("atanor-continuous-self", "authority_denied"),
        ("MainThread", "authority_denied"),
    ]
    assert store.status()["runners"][
        continuous_self.CONTINUOUS_SELF_RUNNER_ID
    ]["status"] == "finished"
    continuous_self.selfhood_stop()
    assert len(calls) == 2


def test_dead_worker_finish_exception_does_not_leave_running_stuck(
    monkeypatch,
    tmp_path,
):
    store, _, lease = _configured_lease(tmp_path, cycles=1)
    original_finish = store.finish
    calls: list[str] = []

    def raise_once(**kwargs):
        calls.append(kwargs["reason"])
        if len(calls) == 1:
            raise OSError("injected finish I/O failure")
        return original_finish(**kwargs)

    monkeypatch.setattr(store, "finish", raise_once)
    started = continuous_self.selfhood_start({"run_lease": lease})
    assert started["started"] is True
    assert _wait_until(
        lambda: not continuous_self._SELF.running
    ), continuous_self._SELF.lease_telemetry()

    pending = continuous_self.selfhood_lifecycle()
    assert pending["state"] == "termination_pending"
    assert pending["lease"]["thread_alive"] is False
    assert pending["lease"]["last_finish"]["reason"] == (
        "run_lease_finish_exception"
    )
    assert pending["lease"]["last_finish"]["exception_type"] == "OSError"
    assert pending["lease"]["pending_finish_reason"] == "authority_denied"

    retried = continuous_self.selfhood_stop()

    assert retried["state"] == "dormant"
    assert retried["lease"]["lease_finalized"] is True
    assert retried["lease"]["termination_reason"] == "authority_denied"
    assert calls == ["authority_denied", "authority_denied"]


def test_failed_audit_rolls_state_back_with_worst_case_bytes_charged(
    monkeypatch,
    tmp_path,
):
    state_path = continuous_self._SELF.state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)
    before_payload = json.dumps(
        asdict(continuous_self._SELF.state),
        ensure_ascii=False,
    ).encode("utf-8")
    state_path.write_bytes(before_payload)
    store, _, lease = _configured_lease(tmp_path, cycles=1)

    def fail_audit(_path, _payload):
        raise continuous_self._PhysicalWriteError(
            "injected audit failure",
            bytes_written=0,
        )

    monkeypatch.setattr(
        continuous_self,
        "_append_fsync_bytes",
        fail_audit,
    )
    started = continuous_self.selfhood_start({"run_lease": lease})
    assert started["started"] is True
    assert _wait_until(lambda: not continuous_self._SELF.running)

    lifecycle = continuous_self.selfhood_lifecycle()
    attempt = lifecycle["lease"]["last_commit_attempt"]
    scratch_counter = lifecycle["lease_store_runner"]["counters"][
        "scratch_write_bytes"
    ]

    assert attempt["status"] == "rolled_back"
    assert attempt["rollback_succeeded"] is True
    assert attempt["rollback_state_bytes"] == len(before_payload)
    assert attempt["physical_state_write_bytes"] == (
        attempt["attempted_state_bytes"]
    )
    assert attempt["physical_rollback_write_bytes"] == len(
        before_payload
    )
    assert attempt["physical_write_bytes"] <= scratch_counter
    assert scratch_counter == attempt["authorized_scratch_write_bytes"]
    assert state_path.read_bytes() == before_payload
    assert not (
        state_path.parent / "aut0_cycle_audit.jsonl"
    ).exists()
    assert lifecycle["lease"]["termination_reason"] == (
        "persistence_failed"
    )


def test_failed_state_temp_is_removed_before_rollback_is_reported(
    monkeypatch,
    tmp_path,
):
    state_path = continuous_self._SELF.state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)
    before_payload = json.dumps(
        asdict(continuous_self._SELF.state),
        ensure_ascii=False,
    ).encode("utf-8")
    state_path.write_bytes(before_payload)
    _, _, lease = _configured_lease(tmp_path, cycles=1)
    state_temp_path = state_path.with_suffix(".tmp")

    def fail_after_temp_write(path, payload):
        state_temp_path.write_bytes(payload)
        raise continuous_self._PhysicalWriteError(
            "injected state replace failure",
            bytes_written=len(payload),
        )

    monkeypatch.setattr(
        continuous_self,
        "_atomic_replace_bytes",
        fail_after_temp_write,
    )
    started = continuous_self.selfhood_start({"run_lease": lease})
    assert started["started"] is True
    assert _wait_until(lambda: not continuous_self._SELF.running)

    lifecycle = continuous_self.selfhood_lifecycle()
    attempt = lifecycle["lease"]["last_commit_attempt"]

    assert attempt["status"] == "rolled_back"
    assert attempt["rollback_succeeded"] is True
    assert attempt["actual_state_temp_exists"] is False
    assert attempt["state_temp_changed"] is False
    assert state_temp_path.exists() is False
    assert state_path.read_bytes() == before_payload


def test_unremovable_state_temp_is_reported_as_rollback_failure(
    monkeypatch,
    tmp_path,
):
    state_path = continuous_self._SELF.state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)
    before_payload = json.dumps(
        asdict(continuous_self._SELF.state),
        ensure_ascii=False,
    ).encode("utf-8")
    state_path.write_bytes(before_payload)
    _, _, lease = _configured_lease(tmp_path, cycles=1)
    state_temp_path = state_path.with_suffix(".tmp")
    original_unlink = Path.unlink

    def fail_after_temp_write(path, payload):
        state_temp_path.write_bytes(payload)
        raise continuous_self._PhysicalWriteError(
            "injected state replace failure",
            bytes_written=len(payload),
        )

    def deny_temp_unlink(path, *args, **kwargs):
        if path == state_temp_path:
            raise OSError("injected temp cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(
        continuous_self,
        "_atomic_replace_bytes",
        fail_after_temp_write,
    )
    monkeypatch.setattr(Path, "unlink", deny_temp_unlink)
    started = continuous_self.selfhood_start({"run_lease": lease})
    assert started["started"] is True
    assert _wait_until(lambda: not continuous_self._SELF.running)

    lifecycle = continuous_self.selfhood_lifecycle()
    attempt = lifecycle["lease"]["last_commit_attempt"]

    assert attempt["status"] == "rollback_failed"
    assert attempt["rollback_succeeded"] is False
    assert attempt["actual_state_temp_exists"] is True
    assert attempt["state_temp_changed"] is True
    assert "state_temp:OSError" in attempt["rollback_errors"]
    assert lifecycle["lease"]["termination_reason"] == (
        "persistence_rollback_failed"
    )


def test_rollback_failure_reports_persisted_state_without_audit(
    monkeypatch,
    tmp_path,
):
    state_path = continuous_self._SELF.state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)
    before_payload = json.dumps(
        asdict(continuous_self._SELF.state),
        ensure_ascii=False,
    ).encode("utf-8")
    state_path.write_bytes(before_payload)
    store, _, lease = _configured_lease(tmp_path, cycles=1)
    original_atomic_replace = continuous_self._atomic_replace_bytes
    atomic_calls = 0

    def fail_rollback(path, payload):
        nonlocal atomic_calls
        atomic_calls += 1
        if atomic_calls == 2:
            raise continuous_self._PhysicalWriteError(
                "injected rollback failure",
                bytes_written=0,
            )
        return original_atomic_replace(path, payload)

    def fail_audit(_path, _payload):
        raise continuous_self._PhysicalWriteError(
            "injected audit failure",
            bytes_written=0,
        )

    monkeypatch.setattr(
        continuous_self,
        "_atomic_replace_bytes",
        fail_rollback,
    )
    monkeypatch.setattr(
        continuous_self,
        "_append_fsync_bytes",
        fail_audit,
    )
    started = continuous_self.selfhood_start({"run_lease": lease})
    assert started["started"] is True
    assert _wait_until(lambda: not continuous_self._SELF.running)

    lifecycle = continuous_self.selfhood_lifecycle()
    attempt = lifecycle["lease"]["last_commit_attempt"]
    scratch_counter = lifecycle["lease_store_runner"]["counters"][
        "scratch_write_bytes"
    ]
    actual_payload = state_path.read_bytes()

    assert attempt["status"] == "rollback_failed"
    assert attempt["rollback_succeeded"] is False
    assert attempt["state_changed"] is True
    assert attempt["state_persisted_without_complete_audit"] is True
    assert attempt["actual_state_sha256"] == (
        attempt["attempted_state_sha256"]
    )
    assert hashlib.sha256(actual_payload).hexdigest() == (
        attempt["attempted_state_sha256"]
    )
    assert actual_payload != before_payload
    assert attempt["physical_write_bytes"] <= scratch_counter
    assert scratch_counter == attempt["authorized_scratch_write_bytes"]
    assert lifecycle["lease"]["last_authorization_reason"] == (
        "continuous_self_cycle_rollback_failed"
    )
    assert lifecycle["lease"]["termination_reason"] == (
        "persistence_rollback_failed"
    )
    assert not (
        state_path.parent / "aut0_cycle_audit.jsonl"
    ).exists()


def test_cycle_budget_exhaustion_stops_and_reports_exact_reason(tmp_path):
    _, _, lease = _configured_lease(tmp_path, cycles=1)

    started = continuous_self.selfhood_start({"run_lease": lease})
    assert started["started"], started
    assert _wait_until(lambda: not continuous_self._SELF.running)

    lifecycle = continuous_self.selfhood_lifecycle()
    assert lifecycle["lease"]["termination_reason"] == "authority_denied"
    assert lifecycle["lease"]["last_authorization_reason"] == (
        "run_lease_budget_exhausted:cycles"
    )
    assert lifecycle["lease_store_runner"]["counters"]["cycles"] == 1
    assert lifecycle["lease_store_runner"]["status"] == "finished"


def test_outer_runner_exception_is_not_misattributed_to_operator_stop(
    monkeypatch,
    tmp_path,
):
    store, _, lease = _configured_lease(tmp_path, cycles=1)

    def fail_authorize(**_kwargs):
        raise OSError("injected authorization I/O failure")

    monkeypatch.setattr(store, "authorize", fail_authorize)
    started = continuous_self.selfhood_start({"run_lease": lease})
    assert started["started"] is True
    assert _wait_until(lambda: not continuous_self._SELF.running)

    lifecycle = continuous_self.selfhood_lifecycle()

    assert lifecycle["lease"]["termination_reason"] == "runner_error"
    assert lifecycle["lease"]["last_authorization_reason"] == (
        "continuous_self_runner_exception:OSError"
    )
    assert lifecycle["lease_store_runner"]["finish_reason"] == "runner_error"


def test_cycle_exception_restores_in_memory_state_before_finishing(
    monkeypatch,
    tmp_path,
):
    store, _, lease = _configured_lease(tmp_path, cycles=1)
    before_state = asdict(continuous_self._SELF.state)
    state_path = continuous_self._SELF.state_path
    audit_path = state_path.parent / "aut0_cycle_audit.jsonl"

    def mutate_then_raise(**_kwargs):
        continuous_self._SELF.state.ticks += 1
        raise TypeError("injected cycle serialization failure")

    monkeypatch.setattr(continuous_self._SELF, "step", mutate_then_raise)
    started = continuous_self.selfhood_start({"run_lease": lease})
    assert started["started"] is True
    assert _wait_until(lambda: not continuous_self._SELF.running)

    lifecycle = continuous_self.selfhood_lifecycle()

    assert asdict(continuous_self._SELF.state) == before_state
    assert state_path.exists() is False
    assert audit_path.exists() is False
    assert lifecycle["lease"]["termination_reason"] == "runner_error"
    assert lifecycle["lease"]["last_authorization_reason"] == (
        "continuous_self_runner_exception:TypeError"
    )
    assert lifecycle["lease_store_runner"]["finish_reason"] == "runner_error"
    assert lifecycle["lease_store_runner"]["counters"][
        "scratch_write_bytes"
    ] == 0


def test_stop_stays_pending_until_worker_exits_and_blocks_late_writes(
    monkeypatch,
    tmp_path,
):
    entered = threading.Event()
    release = threading.Event()

    def blocked_observation():
        entered.set()
        release.wait(timeout=3.0)
        return Observation(resource_pressure=0.2)

    continuous_self._SELF.obs_provider = blocked_observation
    monkeypatch.setattr(continuous_self, "_STOP_JOIN_TIMEOUT_SEC", 0.05)
    store, _, lease = _configured_lease(tmp_path, cycles=1)
    finish_threads: list[str] = []
    original_finish = store.finish

    def tracked_finish(**kwargs):
        finish_threads.append(threading.current_thread().name)
        return original_finish(**kwargs)

    monkeypatch.setattr(store, "finish", tracked_finish)
    started = continuous_self.selfhood_start({"run_lease": lease})
    assert started["started"], started
    assert entered.wait(timeout=5.0)

    stopping = continuous_self.selfhood_stop()

    assert stopping["stopped"] is False
    assert stopping["stop_pending"] is True
    assert stopping["state"] == "stopping"
    assert stopping["running"] is True
    assert stopping["lease"]["lease_finalized"] is False
    assert stopping["lease"]["thread_alive"] is True
    assert store.status()["runners"][
        continuous_self.CONTINUOUS_SELF_RUNNER_ID
    ]["status"] == "active"
    assert not continuous_self._SELF.state_path.exists()

    release.set()
    assert _wait_until(lambda: not continuous_self._SELF.running)

    lifecycle = continuous_self.selfhood_lifecycle()
    assert lifecycle["state"] == "dormant"
    assert lifecycle["lease"]["lease_finalized"] is True
    assert not continuous_self._SELF.state_path.exists()
    assert not (
        continuous_self._SELF.state_path.parent
        / "aut0_cycle_audit.jsonl"
    ).exists()
    assert finish_threads == ["atanor-continuous-self"]


def test_runtime_expiry_during_observation_blocks_state_commit(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    clock = [10.0]

    def blocked_observation():
        entered.set()
        release.wait(timeout=3.0)
        return Observation(resource_pressure=0.2)

    continuous_self._SELF.obs_provider = blocked_observation
    private, boundary, _ = _provision_boundary(tmp_path)
    store = RunLeaseStore(boundary, monotonic_clock=lambda: clock[0])
    context = continuous_self.configure_continuous_self_run_lease(
        store,
        runtime_instance_id="continuous-self-mid-step-expiry-test",
        limits=_limits(1),
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    lease = _signed_lease(
        private,
        boundary,
        context,
        issued_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(seconds=30),
    )

    started = continuous_self.selfhood_start({"run_lease": lease})
    assert started["started"], started
    assert entered.wait(timeout=5.0)
    clock[0] += context["limits"]["max_runtime_sec"]
    release.set()
    assert _wait_until(lambda: not continuous_self._SELF.running)

    lifecycle = continuous_self.selfhood_lifecycle()
    assert lifecycle["lease"]["last_authorization_reason"] == (
        "run_lease_runtime_expired"
    )
    assert not continuous_self._SELF.state_path.exists()
    assert not (
        continuous_self._SELF.state_path.parent
        / "aut0_cycle_audit.jsonl"
    ).exists()
    assert lifecycle["lease_store_runner"]["status"] == "finished"


def test_signed_context_binds_mutable_in_memory_state(tmp_path):
    _, _, lease = _configured_lease(tmp_path, cycles=1)
    continuous_self._SELF.state.ticks += 1

    denied = continuous_self.selfhood_start({"run_lease": lease})

    assert denied["started"] is False
    assert denied["reason"] == (
        "run_lease_live_input_manifest_sha256_mismatch"
    )
    assert continuous_self._SELF.running is False


def test_signed_context_binds_disk_state(tmp_path):
    _, _, lease = _configured_lease(tmp_path, cycles=1)
    continuous_self._SELF.state_path.write_text(
        "{}",
        encoding="utf-8",
    )

    denied = continuous_self.selfhood_start({"run_lease": lease})

    assert denied["started"] is False
    assert denied["reason"] == (
        "run_lease_live_input_manifest_sha256_mismatch"
    )
    assert continuous_self._SELF.running is False


def test_signed_context_binds_provider_code_not_only_its_name(tmp_path):
    _, _, lease = _configured_lease(tmp_path, cycles=1)
    original = continuous_self._SELF.identity_fn

    def drifted_provider(_question, _topic):
        return "drifted"

    drifted_provider.__module__ = getattr(original, "__module__", "")
    drifted_provider.__qualname__ = getattr(
        original,
        "__qualname__",
        "identity_provider",
    )
    continuous_self._SELF.identity_fn = drifted_provider

    denied = continuous_self.selfhood_start({"run_lease": lease})

    assert denied["started"] is False
    assert denied["reason"] == (
        "run_lease_live_runner_artifact_sha256_mismatch"
    )
    assert continuous_self._SELF.running is False


def test_aut0_identity_provider_does_not_write_metacog(
    monkeypatch,
    tmp_path,
):
    metacog_root = tmp_path / "metacog"
    monkeypatch.setenv("ATANOR_MEC", "1")
    monkeypatch.setenv("ATANOR_METACOG_DIR", str(metacog_root))

    answer = continuous_self._identity_answer(
        "Who am I?",
        "identity",
    )

    assert answer
    assert "ATANOR" in answer
    assert not metacog_root.exists()


def test_runtime_expiry_stops_before_another_cycle(tmp_path):
    clock = [10.0]
    private, boundary, _ = _provision_boundary(tmp_path)
    store = RunLeaseStore(boundary, monotonic_clock=lambda: clock[0])
    context = continuous_self.configure_continuous_self_run_lease(
        store,
        runtime_instance_id="continuous-self-expiry-test",
        limits=_limits(3),
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    lease = _signed_lease(
        private,
        boundary,
        context,
        issued_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(seconds=30),
    )

    started = continuous_self.selfhood_start({"run_lease": lease})
    assert started["started"], started
    assert _wait_until(lambda: continuous_self._SELF.state.ticks >= 1)
    clock[0] += context["limits"]["max_runtime_sec"]
    assert _wait_until(lambda: not continuous_self._SELF.running)

    lifecycle = continuous_self.selfhood_lifecycle()
    assert lifecycle["lease"]["last_authorization_reason"] == (
        "run_lease_runtime_expired"
    )
    assert lifecycle["lease_store_runner"]["status"] == "finished"
