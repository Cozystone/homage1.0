from __future__ import annotations

import base64
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import agentic_micro_os as router_module
from app.routers.agentic_micro_os import router
from packages.agentic_micro_os.review_queue import ReviewQueue
from packages.autonomy_envelope.operator_trust import SIGNATURE_FIELD
from packages.candidate_promotion_gate import CandidatePromotionGate
from packages.neural_emotion.event_bus import EVENT_BUS
from packages.autonomy_envelope.run_lease import RunLeaseFinishResult

from aut0_run_lease_support import provision_store, sign_lease


@pytest.fixture
def leased_api(tmp_path, monkeypatch):
    router_module.AUTONOMOUS_DAEMON.stop(reason="test_setup")
    router_module._reset_agentic_run_lease_runtime_for_tests()
    EVENT_BUS.reset(clear_events=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    queue = ReviewQueue()
    monkeypatch.setattr(router_module, "REVIEW_QUEUE", queue)
    monkeypatch.setattr(
        router_module,
        "REVIEW_QUEUE_PATH",
        scratch / "review_queue.json",
    )
    monkeypatch.setattr(
        router_module,
        "CANDIDATE_PROMOTION_GATE",
        CandidatePromotionGate(staging_dir=scratch / "candidate_intents"),
    )
    monkeypatch.setattr(router_module, "AUTO_STAGED_INTENT_IDS", set())
    private, store = provision_store(
        tmp_path,
        repository_root=router_module.PROJECT_ROOT,
    )
    router_module.configure_agentic_run_lease_store(
        store,
        runtime_instance_id="api-test-runtime-0001",
        scratch_root=scratch,
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    yield client, private, store, scratch
    router_module.AUTONOMOUS_DAEMON.stop(reason="test_teardown")
    router_module._reset_agentic_run_lease_runtime_for_tests()


def _lease_request(
    client: TestClient,
    private,
    store,
    *,
    lease_id: str,
    nonce: str,
    **overrides,
):
    request = {
        "scheduler_id": "aut0_signed_scheduler",
        "max_runtime_sec": 60,
        "max_cycles": 2,
        "max_actions": 8,
        "max_scratch_write_bytes": 2 * 1024 * 1024,
        "min_interval_sec": 0.1,
        "max_interval_sec": 0.1,
        "allow_web_explorer": False,
        "allow_review_import": False,
        "allow_splatra_generation": False,
        "allow_host_executor_status_only": False,
        "live_web": False,
    }
    request.update(overrides)
    preview = client.post(
        "/api/agentic-os/policy-scheduler/lease-context",
        json=request,
    ).json()
    assert preview["available"] is True
    request["run_lease"] = sign_lease(
        private,
        store,
        preview["live_context"],
        lease_id=lease_id,
        nonce=nonce,
    )
    return request


def test_signed_lease_context_starts_and_ticks_real_scheduler(
    leased_api,
) -> None:
    client, private, store, _ = leased_api
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-happy-lease-0001",
        nonce="api-happy-nonce-0001",
    )

    started = client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=request,
    ).json()
    ticked = client.post(
        "/api/agentic-os/policy-scheduler/tick"
    ).json()
    stopped = client.post(
        "/api/agentic-os/policy-scheduler/stop",
        json={"reason": "api_happy_complete"},
    ).json()

    assert started["allowed"] is True
    assert started["run_lease_activation"]["reason"] == "run_lease_activated"
    assert ticked["ran"] is True
    assert ticked["cycle_count"] == 1
    assert ticked["run_lease_authorization"]["allowed"] is True
    assert stopped["enabled"] is False
    assert stopped["run_lease"]["active"] is False
    runner = store.status()["runners"]["agentic-policy-daemon-v1"]
    assert runner["status"] == "finished"
    assert runner["counters"]["cycles"] == 1


def test_signed_scheduler_max_cycles_stops_and_finishes_lease(
    leased_api,
) -> None:
    client, private, store, _ = leased_api
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-max-cycles-lease-0001",
        nonce="api-max-cycles-nonce-0001",
        max_cycles=1,
    )
    assert client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=request,
    ).json()["allowed"] is True

    payload = client.post(
        "/api/agentic-os/policy-scheduler/tick"
    ).json()

    assert payload["ran"] is True
    assert payload["cycle_count"] == 1
    assert payload["enabled"] is False
    assert payload["stopped_reason"] == "max_cycles"
    assert payload["reason"] == "max_cycles"
    assert payload["run_lease"]["active"] is False
    assert (
        payload["run_lease"]["last_run"]["finish_reason"]
        == "max_cycles"
    )
    runner = store.status()["runners"]["agentic-policy-daemon-v1"]
    assert runner["status"] == "finished"
    assert runner["counters"]["cycles"] == 1


def test_signed_scheduler_run_lookup_returns_recorded_cycle(
    leased_api,
) -> None:
    client, private, store, _ = leased_api
    scheduler_id = "api_signed_scheduler_lookup"
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-run-lookup-lease-0001",
        nonce="api-run-lookup-nonce-0001",
        scheduler_id=scheduler_id,
        max_cycles=2,
    )
    assert client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=request,
    ).json()["allowed"] is True
    ticked = client.post(
        "/api/agentic-os/policy-scheduler/tick"
    ).json()

    lookup = client.get(
        f"/api/agentic-os/policy-scheduler/runs/{scheduler_id}"
    ).json()

    assert ticked["ran"] is True
    assert lookup["run"]["scheduler_id"] == scheduler_id
    assert lookup["run"]["cycle_count"] == 1
    assert lookup["run"]["last_result"]["cycles_completed"] == 1
    assert (
        lookup["run"]["last_result"]["loop_id"]
        == f"{scheduler_id}_cycle_1"
    )
    client.post(
        "/api/agentic-os/policy-scheduler/stop",
        json={"reason": "run_lookup_complete"},
    )


def test_signed_scheduler_review_pressure_pauses_exploration(
    leased_api,
) -> None:
    client, private, store, _ = leased_api
    sources = [
        {
            "title": f"pressure source {index}",
            "url": f"https://example.test/pressure/{index}",
            "snippet": f"distinct review evidence {index}",
            "provider": "signed-pressure-fixture",
        }
        for index in range(8)
    ]
    imported = client.post(
        "/api/agentic-os/review/import-web-run",
        json={
            "run_payload": {
                "run_id": "signed-pressure-seed",
                "sources": sources,
            }
        },
    ).json()
    assert imported["imported"] == 8
    assert imported["pending"] == 8

    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-review-pressure-lease-0001",
        nonce="api-review-pressure-nonce-0001",
        max_cycles=3,
        allow_web_explorer=True,
        allow_review_import=True,
    )
    assert client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=request,
    ).json()["allowed"] is True

    payload = client.post(
        "/api/agentic-os/policy-scheduler/tick"
    ).json()

    result = payload["last_result"]
    assert payload["ran"] is True
    assert result["stopped_reason"] == "review_requested"
    assert result["candidate_drafts"] == 0
    assert result["states"][0]["actions_taken"] == [
        "review_queue_pressure_request_review"
    ]
    assert (
        payload["last_policy"]["review"]["should_request_review"]
        is True
    )
    assert payload["last_policy"]["review"]["strictness"] > 0.65
    client.post(
        "/api/agentic-os/policy-scheduler/stop",
        json={"reason": "review_pressure_probe_complete"},
    )


def test_missing_invalid_expired_and_replayed_leases_are_rejected(
    leased_api,
) -> None:
    client, private, store, _ = leased_api
    missing = client.post(
        "/api/agentic-os/policy-scheduler/start",
        json={"max_cycles": 1},
    ).json()
    assert missing["reason"] == "signed_operator_run_lease_required"

    invalid_request = _lease_request(
        client,
        private,
        store,
        lease_id="api-invalid-lease-0001",
        nonce="api-invalid-nonce-0001",
        max_cycles=1,
    )
    invalid_request["run_lease"][SIGNATURE_FIELD]["signature"] = (
        base64.b64encode(b"\0" * 64).decode("ascii")
    )
    invalid = client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=invalid_request,
    ).json()
    assert invalid["allowed"] is False
    assert invalid["reason"] == "run_lease_signature_invalid"

    expired_request = _lease_request(
        client,
        private,
        store,
        lease_id="api-expired-lease-0001",
        nonce="api-expired-nonce-0001",
        max_cycles=1,
    )
    preview = client.post(
        "/api/agentic-os/policy-scheduler/lease-context",
        json={key: value for key, value in expired_request.items() if key != "run_lease"},
    ).json()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expired_request["run_lease"] = sign_lease(
        private,
        store,
        preview["live_context"],
        lease_id="api-expired-lease-0001",
        nonce="api-expired-nonce-0001",
        issued_at=now - timedelta(seconds=20),
        expires_at=now - timedelta(seconds=1),
    )
    expired = client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=expired_request,
    ).json()
    assert expired["reason"] == "run_lease_expired"

    replay_request = _lease_request(
        client,
        private,
        store,
        lease_id="api-replay-lease-0001",
        nonce="api-replay-nonce-0001",
        max_cycles=1,
    )
    first = client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=replay_request,
    ).json()
    assert first["allowed"] is True
    client.post(
        "/api/agentic-os/policy-scheduler/stop",
        json={"reason": "close_before_replay"},
    )
    replay = client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=replay_request,
    ).json()
    assert replay["allowed"] is False
    assert replay["reason"] == "run_lease_replay"


def test_scratch_budget_exhaustion_stops_after_authorized_tick(
    leased_api,
) -> None:
    client, private, store, scratch = leased_api
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-budget-lease-0001",
        nonce="api-budget-nonce-0001",
        max_cycles=2,
        max_actions=2,
        max_scratch_write_bytes=1,
        allow_web_explorer=True,
        allow_review_import=True,
    )
    assert client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=request,
    ).json()["allowed"] is True

    ticked = client.post(
        "/api/agentic-os/policy-scheduler/tick"
    ).json()

    assert ticked["ran"] is True
    assert ticked["enabled"] is False
    assert (
        ticked["stopped_reason"]
        == "run_lease_budget_exhausted:scratch_write_bytes"
    )
    assert (
        ticked["reason"]
        == "run_lease_budget_exhausted:scratch_write_bytes"
    )
    assert (
        ticked["review_queue_persistence"]["reason"]
        == "run_lease_budget_exhausted:scratch_write_bytes"
    )
    assert ticked["run_lease"]["active"] is False
    assert not (scratch / "review_queue.json").exists()
    runner = store.status()["runners"]["agentic-policy-daemon-v1"]
    assert runner["status"] == "finished"
    assert runner["counters"]["cycles"] == 1


def test_daemon_executes_leased_tick_without_network_helpers(
    leased_api,
    monkeypatch,
) -> None:
    client, private, store, _ = leased_api

    def forbidden_network_helper(*args, **kwargs):
        raise AssertionError("network helper executed under zero-network lease")

    monkeypatch.setattr(
        router_module,
        "_run_wikipedia_grounded_learning",
        forbidden_network_helper,
    )
    monkeypatch.setattr(
        router_module,
        "_run_abstain_drain",
        forbidden_network_helper,
    )
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-daemon-lease-0001",
        nonce="api-daemon-nonce-0001",
        max_cycles=2,
        max_actions=8,
        execution_mode="daemon",
    )

    started = client.post(
        "/api/agentic-os/policy-scheduler/daemon/start",
        json=request,
    ).json()
    deadline = time.monotonic() + 3
    status = {}
    while time.monotonic() < deadline:
        status = client.get(
            "/api/agentic-os/policy-scheduler/daemon/status"
        ).json()
        if status["activity_log"]:
            break
        time.sleep(0.02)
    stopped = client.post(
        "/api/agentic-os/policy-scheduler/daemon/stop",
        json={"reason": "daemon_test_complete"},
    ).json()

    assert started["allowed"] is True
    assert status["activity_log"][0]["ran"] is True
    assert status["activity_log"][0]["wikipedia_grounded"]["executed"] is False
    assert status["activity_log"][0]["abstain_drain"]["executed"] is False
    assert stopped["daemon_running"] is False


def test_signed_manual_context_cannot_be_redeemed_as_daemon(
    leased_api,
) -> None:
    client, private, store, _ = leased_api
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-mode-bound-lease-0001",
        nonce="api-mode-bound-nonce-0001",
        max_cycles=1,
    )
    request["execution_mode"] = "daemon"

    denied = client.post(
        "/api/agentic-os/policy-scheduler/daemon/start",
        json=request,
    ).json()

    assert denied["allowed"] is False
    assert (
        denied["reason"]
        == "run_lease_live_config_sha256_mismatch"
    )
    assert (
        store.status()["runners"]["agentic-policy-daemon-v1"][
            "status"
        ]
        == "inactive"
    )


def test_daemon_stop_does_not_finish_or_disable_manual_run(
    leased_api,
) -> None:
    client, private, store, _ = leased_api
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-manual-stop-target-lease-0001",
        nonce="api-manual-stop-target-nonce-0001",
        max_cycles=2,
    )
    assert client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=request,
    ).json()["allowed"] is True

    denied = client.post(
        "/api/agentic-os/policy-scheduler/daemon/stop",
        json={"reason": "wrong_stop_target"},
    ).json()

    assert denied["allowed"] is False
    assert denied["reason"] == "daemon_stop_does_not_target_manual_run"
    assert denied["run_lease"]["active"] is True
    assert router_module.POLICY_SCHEDULER.enabled is True
    client.post(
        "/api/agentic-os/policy-scheduler/stop",
        json={"reason": "correct_manual_stop"},
    )


def test_stale_halt_identity_cannot_disable_current_scheduler(
    leased_api,
) -> None:
    client, private, store, _ = leased_api
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-current-halt-target-lease-0001",
        nonce="api-current-halt-target-nonce-0001",
        max_cycles=2,
    )
    assert client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=request,
    ).json()["allowed"] is True

    denied = router_module._halt_agentic_run(
        "stale_halt",
        expected_lease_id="api-stale-halt-target-lease-0001",
        expected_mode="manual",
    )

    assert denied["finished"] is False
    assert denied["reason"] == "run_lease_identity_mismatch"
    assert router_module.POLICY_SCHEDULER.enabled is True
    assert router_module._agentic_run_lease_status()["active"] is True
    client.post(
        "/api/agentic-os/policy-scheduler/stop",
        json={"reason": "correct_manual_stop"},
    )


def test_real_work_daemon_exactly_accounts_review_and_candidate_writes(
    leased_api,
) -> None:
    client, private, store, scratch = leased_api
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-real-work-lease-0001",
        nonce="api-real-work-nonce-0001",
        execution_mode="daemon",
        max_cycles=1,
        max_actions=4,
        allow_web_explorer=True,
        allow_review_import=True,
        allow_splatra_generation=True,
    )

    started = client.post(
        "/api/agentic-os/policy-scheduler/daemon/start",
        json=request,
    ).json()
    deadline = time.monotonic() + 5
    status = {}
    while time.monotonic() < deadline:
        status = client.get(
            "/api/agentic-os/policy-scheduler/daemon/status"
        ).json()
        if status["activity_log"] and not status["daemon_running"]:
            break
        time.sleep(0.02)

    assert started["allowed"] is True
    assert status["daemon_running"] is False
    record = status["activity_log"][0]
    assert record["ran"] is True
    assert record["review_queue_persistence"]["persisted"] is True
    assert record["candidate_intents_staged"] >= 1
    assert record["candidate_staging_mutated"] is True
    assert record["review_queue_staging_persisted"] is True
    review_file = scratch / "review_queue.json"
    manifests = list((scratch / "candidate_intents").glob("*.json"))
    assert review_file.is_file()
    assert len(manifests) == 1
    candidate_reserved = record["candidate_write_reserved_bytes"]
    assert candidate_reserved == (
        manifests[0].stat().st_size + review_file.stat().st_size
    )
    runner = store.status()["runners"]["agentic-policy-daemon-v1"]
    assert runner["status"] == "finished"
    assert runner["counters"]["cycles"] == 1
    assert runner["counters"]["scratch_write_bytes"] == (
        record["review_queue_persistence"][
            "reserved_scratch_write_bytes"
        ]
        + candidate_reserved
    )


def test_runner_artifact_digest_covers_executed_package_closure() -> None:
    relative = {
        str(path.relative_to(router_module.PROJECT_ROOT)).replace(
            "\\",
            "/",
        )
        for path in router_module._agentic_runner_artifact_paths()
    }

    assert "packages/agentic_micro_os/web_explorer_loop.py" in relative
    assert "packages/agentic_micro_os/review_queue.py" in relative
    assert "packages/neural_emotion/autonomy_policy.py" in relative
    assert "packages/inner_voice/event_adapter.py" in relative
    assert "packages/splatra_imagination/__init__.py" in relative
    assert "packages/splatra_turbovec/models.py" in relative
    assert "packages/splatra_turbovec/budget.py" in relative
    assert "packages/splatra_turbovec/codec.py" in relative
    assert "packages/splatra_turbovec/lod.py" in relative
    assert "packages/splatra_turbovec/emotion_mapping.py" in relative
    assert "packages/autonomy_envelope/run_lease.py" in relative


def test_splatra_turbovec_drift_denies_per_action_authorization(
    leased_api,
    monkeypatch,
) -> None:
    client, private, store, _ = leased_api
    target = (
        router_module.PROJECT_ROOT
        / "packages"
        / "splatra_turbovec"
        / "models.py"
    ).resolve()
    original_read_bytes = Path.read_bytes
    drift = {"enabled": False}

    def read_bytes_with_drift(path: Path) -> bytes:
        payload = original_read_bytes(path)
        if path.resolve() == target and drift["enabled"]:
            return payload + b"\n# injected test drift\n"
        return payload

    monkeypatch.setattr(Path, "read_bytes", read_bytes_with_drift)
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-turbovec-drift-lease-0001",
        nonce="api-turbovec-drift-nonce-0001",
        max_cycles=2,
    )
    assert client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=request,
    ).json()["allowed"] is True

    drift["enabled"] = True
    denied = client.post(
        "/api/agentic-os/policy-scheduler/tick"
    ).json()

    assert denied["allowed"] is False
    assert denied["ran"] is False
    assert denied["reason"] == "run_lease_runner_artifact_changed"
    assert denied["run_lease"]["active"] is False
    assert router_module.POLICY_SCHEDULER.enabled is False
    runner = store.status()["runners"]["agentic-policy-daemon-v1"]
    assert runner["status"] == "finished"
    assert runner["counters"]["cycles"] == 0


def test_manual_start_exception_finishes_exact_activated_lease(
    leased_api,
    monkeypatch,
) -> None:
    client, private, store, scratch = leased_api
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-manual-start-error-lease-0001",
        nonce="api-manual-start-error-nonce-0001",
        max_cycles=1,
    )
    stop_file = scratch / "policy_scheduler.stop"
    stop_file.write_text("stale_stop", encoding="utf-8")
    original_unlink = Path.unlink

    def fail_stop_file_unlink(
        path: Path,
        *args,
        **kwargs,
    ) -> None:
        if path.resolve() == stop_file.resolve():
            raise OSError("injected stop-file clear failure")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_stop_file_unlink)
    failed = client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=request,
    ).json()

    assert failed["allowed"] is False
    assert failed["reason"] == "policy_scheduler_start_error:OSError"
    assert failed["start_cleanup"]["scheduler_reset"] is True
    assert failed["start_cleanup"]["lease_finish"]["finished"] is True
    assert failed["run_lease"]["active"] is False
    assert router_module.POLICY_SCHEDULER.enabled is False
    runner = store.status()["runners"]["agentic-policy-daemon-v1"]
    assert runner["status"] == "finished"


def test_daemon_thread_start_exception_cleans_lease_and_partial_state(
    leased_api,
    monkeypatch,
) -> None:
    client, private, store, _ = leased_api
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-daemon-thread-error-lease-0001",
        nonce="api-daemon-thread-error-nonce-0001",
        execution_mode="daemon",
        max_cycles=1,
    )

    def fail_thread_start(_thread) -> None:
        raise RuntimeError("injected thread start failure")

    monkeypatch.setattr(
        router_module.threading.Thread,
        "start",
        fail_thread_start,
    )
    failed = router_module.policy_scheduler_daemon_start(
        router_module.PolicySchedulerDaemonStartApiRequest(**request)
    )

    assert failed["allowed"] is False
    assert failed["daemon_running"] is False
    assert failed["reason"] == "daemon_thread_start_error:RuntimeError"
    assert failed["daemon_reset"] is True
    assert failed["start_cleanup"]["scheduler_reset"] is True
    assert failed["start_cleanup"]["lease_finish"]["finished"] is True
    assert failed["run_lease"]["active"] is False
    assert router_module.AUTONOMOUS_DAEMON.is_running() is False
    assert router_module.POLICY_SCHEDULER.enabled is False
    runner = store.status()["runners"]["agentic-policy-daemon-v1"]
    assert runner["status"] == "finished"


def test_review_temp_replace_failure_cleans_temp_and_reports_mutation(
    leased_api,
    monkeypatch,
) -> None:
    client, private, store, scratch = leased_api
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-review-temp-failure-lease-0001",
        nonce="api-review-temp-failure-nonce-0001",
        max_cycles=2,
        allow_web_explorer=True,
        allow_review_import=True,
    )
    assert client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=request,
    ).json()["allowed"] is True
    review_temp = scratch / "review_queue.json.tmp"
    original_replace = Path.replace

    def fail_review_replace(path: Path, target: Path) -> Path:
        if path.resolve() == review_temp.resolve():
            raise OSError("injected review replace failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_review_replace)
    failed = client.post(
        "/api/agentic-os/policy-scheduler/tick"
    ).json()

    persistence = failed["review_queue_persistence"]
    assert failed["reason"] == "review_queue_persistence_failed"
    assert failed["mutation_performed"] is True
    assert persistence["persisted"] is False
    assert persistence["mutation_performed"] is True
    assert persistence["temporary_write_completed"] is True
    assert persistence["temporary_cleanup_attempted"] is True
    assert persistence["temporary_cleanup_succeeded"] is True
    assert persistence["temporary_path_present"] is False
    assert not review_temp.exists()
    assert failed["run_lease"]["active"] is False
    runner = store.status()["runners"]["agentic-policy-daemon-v1"]
    assert runner["status"] == "finished"


def test_unicode_stop_reason_still_finishes_the_durable_lease(
    leased_api,
) -> None:
    client, private, store, _ = leased_api
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-unicode-stop-lease-0001",
        nonce="api-unicode-stop-nonce-0001",
        max_cycles=1,
    )
    assert client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=request,
    ).json()["allowed"] is True

    stopped = client.post(
        "/api/agentic-os/policy-scheduler/stop",
        json={"reason": "사용자 중지"},
    ).json()

    assert stopped["run_lease"]["active"] is False
    assert stopped["run_lease"]["last_run"]["store_finished"] is True
    runner = store.status()["runners"]["agentic-policy-daemon-v1"]
    assert runner["status"] == "finished"
    assert runner["finish_reason"] == "run_stopped"


def test_failed_durable_finish_does_not_forget_the_active_lease(
    leased_api,
    monkeypatch,
) -> None:
    client, private, store, _ = leased_api
    request = _lease_request(
        client,
        private,
        store,
        lease_id="api-finish-failure-lease-0001",
        nonce="api-finish-failure-nonce-0001",
        max_cycles=1,
    )
    assert client.post(
        "/api/agentic-os/policy-scheduler/start",
        json=request,
    ).json()["allowed"] is True
    monkeypatch.setattr(
        store,
        "finish",
        lambda **_kwargs: RunLeaseFinishResult(
            False,
            "run_lease_active_state_persistence_failed",
            "api-finish-failure-lease-0001",
            "agentic-policy-daemon-v1",
        ),
    )

    stopped = client.post(
        "/api/agentic-os/policy-scheduler/stop",
        json={"reason": "finish_failure_probe"},
    ).json()

    assert stopped["run_lease"]["active"] is True
    assert stopped["run_lease"]["last_run"]["store_finished"] is False
    assert (
        stopped["run_lease"]["last_run"]["store_finish_reason"]
        == "run_lease_active_state_persistence_failed"
    )
