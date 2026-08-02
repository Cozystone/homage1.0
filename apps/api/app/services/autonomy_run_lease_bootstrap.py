"""Production composition root for AUT-0 run-lease verifiers.

Importing this module has no runtime effect.  FastAPI lifespan startup may call
``bootstrap_autonomy_run_leases`` once.  Unless all three explicit environment
bindings are present and valid, both autonomy runners remain unconfigured and
dormant.  This module loads public verification material only; it has no signer
and never reads an operator private key.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from packages.autonomy_envelope.run_lease import (
    AGENTIC_POLICY_DAEMON_RUNNER_ID,
    CONTINUOUS_SELF_RUNNER_ID,
    RunLeaseBoundaryConfig,
    RunLeaseStore,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
TRUST_CONFIG_ENV = "ATANOR_RUN_LEASE_TRUST_CONFIG"
SCRATCH_ROOT_ENV = "ATANOR_RUN_LEASE_SCRATCH_ROOT"
RUNTIME_INSTANCE_ID_ENV = "ATANOR_RUN_LEASE_RUNTIME_INSTANCE_ID"
BOOTSTRAP_ENV_FIELDS = (
    TRUST_CONFIG_ENV,
    SCRATCH_ROOT_ENV,
    RUNTIME_INSTANCE_ID_ENV,
)
_RUNTIME_INSTANCE_ID_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$"
)


@dataclass(frozen=True)
class AutonomyRunLeaseBootstrap:
    """Safe startup result plus the verifier store needed for shutdown."""

    state: str
    reason: str
    configured: bool
    runtime_instance_id: str | None = None
    deployment_id: str | None = None
    configured_runners: tuple[str, ...] = ()
    missing_environment: tuple[str, ...] = ()
    present_environment: tuple[str, ...] = ()
    error_type: str | None = None
    error_detail: str | None = None
    store: RunLeaseStore | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def public_status(self) -> dict[str, Any]:
        return {
            "schema_version": "atanor.autonomy-run-lease-bootstrap.v1",
            "state": self.state,
            "reason": self.reason,
            "configured": self.configured,
            "runtime_instance_id": self.runtime_instance_id,
            "deployment_id": self.deployment_id,
            "configured_runners": list(self.configured_runners),
            "missing_environment": list(self.missing_environment),
            "present_environment": list(self.present_environment),
            "error_type": self.error_type,
            "error_detail": self.error_detail,
            "default_dormant": True,
            "runners_started_by_bootstrap": False,
            "signer_present_in_api": False,
            "private_key_loaded": False,
            "network_authority_added": False,
            "production_write_authority_added": False,
        }


def _configured_environment(
    environ: Mapping[str, str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    present = tuple(field for field in BOOTSTRAP_ENV_FIELDS if field in environ)
    missing = tuple(
        field for field in BOOTSTRAP_ENV_FIELDS if field not in environ
    )
    return present, missing


def _absolute_existing_directory(value: Any, *, label: str) -> Path:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be an explicit absolute path")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{label} must be an explicit absolute path")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"{label} must be a provisioned directory")
    return resolved


def _absolute_existing_file(value: Any, *, label: str) -> Path:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be an explicit absolute path")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{label} must be an explicit absolute path")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{label} must be a provisioned file")
    return resolved


def _validated_runtime_instance_id(value: Any) -> str:
    if (
        type(value) is not str
        or _RUNTIME_INSTANCE_ID_RE.fullmatch(value) is None
    ):
        raise ValueError(
            "runtime instance id must be explicit, stable, and identifier-safe"
        )
    return value


def _preflight(
    environ: Mapping[str, str],
    *,
    repository_root: Path,
) -> tuple[RunLeaseStore, str, Path]:
    runtime_instance_id = _validated_runtime_instance_id(
        environ[RUNTIME_INSTANCE_ID_ENV]
    )
    scratch_root = _absolute_existing_directory(
        environ[SCRATCH_ROOT_ENV],
        label="run-lease scratch root",
    )
    trust_config_path = _absolute_existing_file(
        environ[TRUST_CONFIG_ENV],
        label="run-lease trust config",
    )
    boundary = RunLeaseBoundaryConfig.from_external_file(
        trust_config_path,
        repository_root=repository_root,
    )
    return RunLeaseStore(boundary), runtime_instance_id, scratch_root


def bootstrap_autonomy_run_leases(
    environ: Mapping[str, str] | None = None,
    *,
    repository_root: str | Path = PROJECT_ROOT,
) -> AutonomyRunLeaseBootstrap:
    """Inject one external verifier store into both dormant AUT-0 runners."""

    environment = os.environ if environ is None else environ
    present, missing = _configured_environment(environment)
    if not present:
        return AutonomyRunLeaseBootstrap(
            state="dormant",
            reason="run_lease_bootstrap_not_requested",
            configured=False,
        )
    if missing:
        return AutonomyRunLeaseBootstrap(
            state="misconfigured",
            reason="run_lease_bootstrap_environment_incomplete",
            configured=False,
            missing_environment=missing,
            present_environment=present,
        )

    try:
        root = Path(repository_root).resolve(strict=True)
        store, runtime_instance_id, scratch_root = _preflight(
            environment,
            repository_root=root,
        )
    except Exception as exc:
        return AutonomyRunLeaseBootstrap(
            state="misconfigured",
            reason="run_lease_bootstrap_configuration_invalid",
            configured=False,
            present_environment=present,
            error_type=type(exc).__name__,
            error_detail=str(exc),
        )

    # Import and mutation happen only after the entire external boundary has
    # passed preflight.  Any injection failure aborts application startup rather
    # than serving with one runner bound and the other unbound.
    from app.routers import agentic_micro_os, continuous_self

    try:
        agentic_micro_os.configure_agentic_run_lease_store(
            store,
            runtime_instance_id=runtime_instance_id,
            scratch_root=scratch_root,
        )
        continuous_self.configure_continuous_self_run_lease(
            store,
            runtime_instance_id=runtime_instance_id,
        )
    except Exception as exc:
        raise RuntimeError(
            "AUT-0 run-lease verifier injection failed; startup aborted"
        ) from exc

    return AutonomyRunLeaseBootstrap(
        state="configured",
        reason="run_lease_verifiers_injected",
        configured=True,
        runtime_instance_id=runtime_instance_id,
        deployment_id=store.boundary.deployment_id,
        configured_runners=(
            AGENTIC_POLICY_DAEMON_RUNNER_ID,
            CONTINUOUS_SELF_RUNNER_ID,
        ),
        present_environment=present,
        store=store,
    )


def shutdown_autonomy_run_lease_runners(
    bootstrap: AutonomyRunLeaseBootstrap,
) -> dict[str, Any]:
    """Stop both runners and finish active leases before process shutdown."""

    if not bootstrap.configured:
        return {
            **bootstrap.public_status(),
            "state": "shutdown",
            "reason": "run_lease_bootstrap_was_dormant",
            "shutdown_requested": False,
            "all_runners_stopped": True,
            "shutdown_errors": [],
        }

    from app.routers import agentic_micro_os, continuous_self

    errors: list[str] = []
    try:
        agentic_micro_os.policy_scheduler_stop(
            agentic_micro_os.PolicySchedulerStopApiRequest(
                reason="api_shutdown"
            )
        )
    except Exception as exc:  # pragma: no cover - defensive shutdown path
        errors.append(f"agentic:{type(exc).__name__}")
    try:
        continuous_self.selfhood_stop()
    except Exception as exc:  # pragma: no cover - defensive shutdown path
        errors.append(f"continuous_self:{type(exc).__name__}")

    agentic_running = bool(
        agentic_micro_os.AUTONOMOUS_DAEMON.is_running()
        or agentic_micro_os.POLICY_SCHEDULER.enabled
    )
    continuous_running = bool(continuous_self._SELF.running)
    all_stopped = (
        not errors
        and not agentic_running
        and not continuous_running
    )
    return {
        **bootstrap.public_status(),
        "state": "shutdown",
        "reason": (
            "run_lease_runners_stopped"
            if all_stopped
            else "run_lease_runner_shutdown_incomplete"
        ),
        "shutdown_requested": True,
        "all_runners_stopped": all_stopped,
        "agentic_running": agentic_running,
        "continuous_self_running": continuous_running,
        "shutdown_errors": errors,
    }
