"""FastAPI boot injects AUT-0 verifiers without starting either runner."""

from __future__ import annotations

import asyncio
import gc
import json
import os
import threading
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

from app.routers import agentic_micro_os, continuous_self
from app.services import autonomy_run_lease_bootstrap as bootstrap_module
from app.services.autonomy_run_lease_bootstrap import (
    RUNTIME_INSTANCE_ID_ENV,
    SCRATCH_ROOT_ENV,
    TRUST_CONFIG_ENV,
    AutonomyRunLeaseBootstrap,
    bootstrap_autonomy_run_leases,
    shutdown_autonomy_run_lease_runners,
)
from aut0_run_lease_support import provision_store


REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _reset_runner_bindings() -> None:
    agentic_micro_os._reset_agentic_run_lease_runtime_for_tests()
    continuous_self._clear_continuous_self_run_lease_for_tests()
    yield
    agentic_micro_os._reset_agentic_run_lease_runtime_for_tests()
    continuous_self._clear_continuous_self_run_lease_for_tests()


def _complete_environment(tmp_path: Path) -> tuple[dict[str, str], str]:
    _, provisioned = provision_store(
        tmp_path,
        repository_root=REPO_ROOT,
    )
    runtime_instance_id = "atanor-api-instance-stable-0001"
    environment = {
        TRUST_CONFIG_ENV: str(provisioned.boundary.config_path.resolve()),
        SCRATCH_ROOT_ENV: str((REPO_ROOT / "runtime").resolve()),
        RUNTIME_INSTANCE_ID_ENV: runtime_instance_id,
    }
    return environment, runtime_instance_id


def test_absent_or_partial_environment_stays_dormant_and_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        agentic_micro_os,
        "configure_agentic_run_lease_store",
        lambda *args, **kwargs: calls.append("agentic"),
    )
    monkeypatch.setattr(
        continuous_self,
        "configure_continuous_self_run_lease",
        lambda *args, **kwargs: calls.append("continuous"),
    )

    dormant = bootstrap_autonomy_run_leases({})
    assert dormant.public_status() == {
        "schema_version": "atanor.autonomy-run-lease-bootstrap.v1",
        "state": "dormant",
        "reason": "run_lease_bootstrap_not_requested",
        "configured": False,
        "runtime_instance_id": None,
        "deployment_id": None,
        "configured_runners": [],
        "missing_environment": [],
        "present_environment": [],
        "error_type": None,
        "error_detail": None,
        "default_dormant": True,
        "runners_started_by_bootstrap": False,
        "signer_present_in_api": False,
        "private_key_loaded": False,
        "network_authority_added": False,
        "production_write_authority_added": False,
    }

    environment, _ = _complete_environment(tmp_path)
    environment.pop(SCRATCH_ROOT_ENV)
    partial = bootstrap_autonomy_run_leases(environment)
    assert partial.state == "misconfigured"
    assert partial.reason == "run_lease_bootstrap_environment_incomplete"
    assert partial.missing_environment == (SCRATCH_ROOT_ENV,)
    assert partial.configured is False
    assert calls == []


def test_complete_external_environment_injects_both_but_starts_neither(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment, runtime_instance_id = _complete_environment(tmp_path)
    for field, value in environment.items():
        monkeypatch.setenv(field, value)
    ambient_before = dict(environment)

    result = bootstrap_autonomy_run_leases()

    assert result.configured is True
    assert result.runtime_instance_id == runtime_instance_id
    assert os.environ.get(TRUST_CONFIG_ENV) == ambient_before[TRUST_CONFIG_ENV]
    assert os.environ.get(SCRATCH_ROOT_ENV) == ambient_before[SCRATCH_ROOT_ENV]
    assert (
        os.environ.get(RUNTIME_INSTANCE_ID_ENV)
        == ambient_before[RUNTIME_INSTANCE_ID_ENV]
    )
    assert Path(environment[TRUST_CONFIG_ENV]).is_absolute()
    assert Path(environment[SCRATCH_ROOT_ENV]).is_absolute()
    assert agentic_micro_os._agentic_run_lease_status()["configured"] is True
    continuous_context = continuous_self.continuous_self_run_lease_context()
    assert continuous_context is not None
    assert continuous_context["runtime_instance_id"] == runtime_instance_id
    assert agentic_micro_os.AUTONOMOUS_DAEMON.is_running() is False
    assert continuous_self._SELF.running is False
    encoded_status = json.dumps(result.public_status(), sort_keys=True)
    assert "PRIVATE KEY" not in encoded_status
    assert result.public_status()["signer_present_in_api"] is False


def test_invalid_complete_configuration_never_injects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment, _ = _complete_environment(tmp_path)
    environment[SCRATCH_ROOT_ENV] = "relative/scratch"
    calls: list[str] = []
    monkeypatch.setattr(
        agentic_micro_os,
        "configure_agentic_run_lease_store",
        lambda *args, **kwargs: calls.append("agentic"),
    )
    monkeypatch.setattr(
        continuous_self,
        "configure_continuous_self_run_lease",
        lambda *args, **kwargs: calls.append("continuous"),
    )

    result = bootstrap_autonomy_run_leases(environment)

    assert result.configured is False
    assert result.reason == "run_lease_bootstrap_configuration_invalid"
    assert result.error_type == "ValueError"
    assert calls == []


def test_injection_error_aborts_instead_of_serving_partial_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment, _ = _complete_environment(tmp_path)
    monkeypatch.setattr(
        continuous_self,
        "configure_continuous_self_run_lease",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("injected failure")
        ),
    )

    with pytest.raises(RuntimeError, match="startup aborted"):
        bootstrap_autonomy_run_leases(environment)


def test_shutdown_calls_both_stop_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment, _ = _complete_environment(tmp_path)
    result = bootstrap_autonomy_run_leases(environment)
    calls: list[str] = []
    original_agentic_stop = agentic_micro_os.policy_scheduler_stop
    original_self_stop = continuous_self.selfhood_stop

    def agentic_stop(request):
        calls.append(f"agentic:{request.reason}")
        return original_agentic_stop(request)

    def self_stop():
        calls.append("continuous")
        return original_self_stop()

    monkeypatch.setattr(
        agentic_micro_os,
        "policy_scheduler_stop",
        agentic_stop,
    )
    monkeypatch.setattr(continuous_self, "selfhood_stop", self_stop)

    status = shutdown_autonomy_run_lease_runners(result)

    assert calls == ["agentic:api_shutdown", "continuous"]
    assert status["all_runners_stopped"] is True
    assert status["reason"] == "run_lease_runners_stopped"


def test_fastapi_lifespan_records_boot_and_shutdown_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main

    boot = AutonomyRunLeaseBootstrap(
        state="configured",
        reason="test_boot",
        configured=True,
        runtime_instance_id="test-runtime",
    )
    shutdown_status = {
        "state": "shutdown",
        "reason": "test_shutdown",
        "all_runners_stopped": True,
    }
    events: list[str] = []
    monkeypatch.setattr(
        main,
        "bootstrap_autonomy_run_leases",
        lambda: events.append("boot") or boot,
    )
    monkeypatch.setattr(
        main,
        "shutdown_autonomy_run_lease_runners",
        lambda value: (
            events.append(f"shutdown:{value.reason}") or shutdown_status
        ),
    )
    monkeypatch.setattr(main, "create_boot_shadow_backups", lambda: None)
    monkeypatch.setattr(main, "build_hardware_benchmark", lambda config: {})
    monkeypatch.setattr(
        main.cleaned_directory_watcher,
        "start",
        lambda: events.append("watcher_start"),
    )
    monkeypatch.setattr(
        main.cleaned_directory_watcher,
        "stop",
        AsyncMock(side_effect=lambda: events.append("watcher_stop")),
    )
    monkeypatch.setattr(
        main.graph_event_hub,
        "publish_snapshot",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(gc, "collect", lambda: 0)
    monkeypatch.setattr(gc, "freeze", lambda: None)
    monkeypatch.setattr(gc, "set_threshold", lambda *args: None)

    class DormantThread:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def start(self) -> None:
            events.append("warmup_not_started")

    monkeypatch.setattr(threading, "Thread", DormantThread)
    monkeypatch.setenv("ATANOR_AUTO_START_DAEMON", "0")
    monkeypatch.setenv("ATANOR_AUTOSTART_DAEMON", "0")
    monkeypatch.setenv("HOMAGE_AUTO_START_DAEMON", "0")
    monkeypatch.setenv("ATANOR_AUTO_LEARN", "0")
    application = FastAPI()

    async def exercise() -> None:
        async with main.lifespan(application):
            assert application.state.autonomy_run_lease_bootstrap[
                "reason"
            ] == "test_boot"
            assert events[0] == "boot"
        assert application.state.autonomy_run_lease_bootstrap is (
            shutdown_status
        )

    asyncio.run(exercise())
    assert "shutdown:test_boot" in events
    assert events[-1] == "watcher_stop"
