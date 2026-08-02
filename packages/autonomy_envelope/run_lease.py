"""Purpose-specific, externally signed authority for one bounded autonomy run.

This module is deliberately narrower than a general host-authority session.  It
authorizes one exact runner artifact, configuration, input, capability manifest,
scratch boundary, and budget for one time-bounded run.  It does not contain a
signer and cannot turn a phrase, boolean, environment variable, or API identity
claim into authority.

The trust configuration, Ed25519 public key, replay ledger, and emergency stop
must be provisioned outside the mutable repository.  A lease is consumed before
the runner starts.  Every side effect must then pass ``RunLeaseStore.authorize``;
an activation result is an audit value, not a bearer capability.

Honest maturity: this is cooperative M1 enforcement.  It makes accidental and
remote-request authority escalation fail closed, but it cannot defeat a local
principal that can patch this verifier, replace the running process, alter the
system clock, or bypass OS ACLs on the externally provisioned ledger.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Iterator, Mapping

from packages.autonomy_envelope.operator_trust import (
    ED25519_SCHEME,
    SIGNATURE_FIELD,
    OperatorTrustRoot,
    payload_sha256,
)


RUN_LEASE_PURPOSE = "atanor.autonomy-run-lease.v1"
RUN_LEASE_SCHEMA_VERSION = "atanor.autonomy-run-lease-document.v1"
RUN_LEASE_CAPABILITY_SCHEMA_VERSION = (
    "atanor.autonomy-capability-manifest.v1"
)
RUN_LEASE_REPLAY_DOMAIN_SCHEMA_VERSION = (
    "atanor.autonomy-run-replay-domain.v1"
)
RUN_LEASE_REPLAY_IDENTITY_SCHEMA_VERSION = (
    "atanor.autonomy-run-replay-identity.v1"
)
RUN_LEASE_TRUST_CONFIG_SCHEMA_VERSION = (
    "atanor.autonomy-run-trust-config.v1"
)
RUN_LEASE_ACTIVE_STATE_SCHEMA_VERSION = (
    "atanor.autonomy-run-active-state.v1"
)
RUN_LEASE_NONCE_CLAIM_SCHEMA_VERSION = (
    "atanor.autonomy-run-nonce-claim.v1"
)

RUN_LEASE_REPLAY_IDENTITY_FILENAME = "run-lease-replay-identity.json"
RUN_LEASE_LOCK_RELATIVE_PATH = ".autonomy-run-lease.lock"
RUN_LEASE_CLAIMS_RELATIVE_PATH = "claims"
RUN_LEASE_ACTIVE_RELATIVE_PATH = "active"

CONTINUOUS_SELF_RUNNER_ID = "continuous-self-v1"
AGENTIC_POLICY_DAEMON_RUNNER_ID = "agentic-policy-daemon-v1"
GENERAL_INTERACTION_RUNNER_ID = "general-interaction-loop-v1"

_CONTINUOUS_SELF_ACTIONS = frozenset(
    {
        "self.audit_append",
        "self.observe_local",
        "self.proposal_write",
        "self.state_write",
    }
)
_AGENTIC_POLICY_ACTIONS = frozenset(
    {
        "agentic.audit_append",
        "agentic.candidate_write",
        "agentic.review_read",
        "agentic.scratch_write",
        "agentic.tick",
    }
)
_GENERAL_INTERACTION_ACTIONS = frozenset({"interaction.step"})
RUN_LEASE_ACTIONS_BY_RUNNER = {
    CONTINUOUS_SELF_RUNNER_ID: _CONTINUOUS_SELF_ACTIONS,
    AGENTIC_POLICY_DAEMON_RUNNER_ID: _AGENTIC_POLICY_ACTIONS,
    GENERAL_INTERACTION_RUNNER_ID: _GENERAL_INTERACTION_ACTIONS,
}
RUN_LEASE_ACTION_CLASSES = frozenset().union(
    *RUN_LEASE_ACTIONS_BY_RUNNER.values()
)

_LIMIT_FIELDS = (
    "max_runtime_sec",
    "max_cycles",
    "max_actions",
    "max_external_requests",
    "max_external_response_bytes",
    "max_scratch_write_bytes",
    "max_child_tasks",
    "max_concurrent_child_tasks",
)
_COUNTER_FIELDS = (
    "cycles",
    "actions",
    "external_requests",
    "external_response_bytes",
    "scratch_write_bytes",
    "child_tasks",
    "concurrent_child_tasks",
)
_COST_TO_LIMIT = {
    counter: f"max_{counter}" for counter in _COUNTER_FIELDS
}
_RUNNER_LIMIT_CEILINGS = {
    CONTINUOUS_SELF_RUNNER_ID: {
        "max_runtime_sec": 3_600,
        "max_cycles": 1_800,
        "max_actions": 20_000,
        "max_external_requests": 0,
        "max_external_response_bytes": 0,
        "max_scratch_write_bytes": 16 * 1024 * 1024,
        "max_child_tasks": 0,
        "max_concurrent_child_tasks": 0,
    },
    AGENTIC_POLICY_DAEMON_RUNNER_ID: {
        "max_runtime_sec": 3_600,
        "max_cycles": 2_000,
        "max_actions": 30_000,
        "max_external_requests": 0,
        "max_external_response_bytes": 0,
        "max_scratch_write_bytes": 64 * 1024 * 1024,
        "max_child_tasks": 0,
        "max_concurrent_child_tasks": 0,
    },
    GENERAL_INTERACTION_RUNNER_ID: {
        "max_runtime_sec": 3_600,
        "max_cycles": 1_000,
        "max_actions": 1_000,
        "max_external_requests": 0,
        "max_external_response_bytes": 0,
        "max_scratch_write_bytes": 0,
        "max_child_tasks": 0,
        "max_concurrent_child_tasks": 0,
    },
}
_CYCLE_ACTION_CLASSES = frozenset(
    {"self.observe_local", "agentic.tick", "interaction.step"}
)
_WRITE_ACTION_CLASSES = frozenset(
    {
        "self.audit_append",
        "self.proposal_write",
        "self.state_write",
        "agentic.audit_append",
        "agentic.candidate_write",
        "agentic.scratch_write",
    }
)
# Construction marker only.  This is deliberately not treated as authority:
# module-level objects are importable and dataclasses.replace() preserves them.
# RunLeaseStore rehydrates the external configuration and pinned key instead.
_VALIDATED_BOUNDARY_TOKEN = object()

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
)
_IDENTIFIER_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$"
)
_NONCE_RE = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")
_LEDGER_ID_RE = re.compile(
    r"^atanor:autonomy-run-ledger:"
    r"[A-Za-z0-9][A-Za-z0-9._-]{15,127}$"
)

_SIGNATURE_FIELDS = frozenset(
    {"scheme", "key_id", "payload_sha256", "signature"}
)
_CAPABILITY_FIELDS = frozenset(
    {
        "schema_version",
        "action_classes",
        "filesystem_policy_sha256",
        "network_policy_sha256",
        "child_task_policy_sha256",
    }
)
_SCRATCH_BOUNDARY_FIELDS = frozenset(
    {
        "boundary_id",
        "resolved_root_sha256",
        "identity_manifest_sha256",
    }
)
_REPLAY_DOMAIN_FIELDS = frozenset(
    {
        "schema_version",
        "ledger_id",
        "deployment_id",
        "resolved_root_sha256",
        "identity_manifest_sha256",
        "lock_relative_path",
        "claims_relative_path",
        "active_relative_path",
    }
)
_REPLAY_IDENTITY_FIELDS = frozenset(
    {
        "schema_version",
        "ledger_id",
        "deployment_id",
        "resolved_root_sha256",
        "lock_relative_path",
        "claims_relative_path",
        "active_relative_path",
    }
)
_TRUST_CONFIG_FIELDS = frozenset(
    {
        "schema_version",
        "operator_public_key_path",
        "expected_key_id",
        "operator_boundary_id",
        "deployment_id",
        "replay_root",
        "emergency_stop_path",
    }
)
_LIVE_CONTEXT_FIELD_ORDER = (
    "runner_id",
    "deployment_id",
    "runtime_instance_id",
    "runner_artifact_sha256",
    "config_sha256",
    "input_manifest_sha256",
    "capability_manifest",
    "limits",
    "scratch_boundary",
    "operator_boundary_id",
    "operator_boundary_config_sha256",
    "nonce_replay_domain",
)
_LIVE_CONTEXT_FIELDS = frozenset(_LIVE_CONTEXT_FIELD_ORDER)
_LEASE_FIELDS = frozenset(
    {
        "schema_version",
        "purpose",
        "lease_id",
        *_LIVE_CONTEXT_FIELDS,
        "issued_at",
        "expires_at",
        "nonce",
        SIGNATURE_FIELD,
    }
)
_ACTIVE_STATE_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "lease_id",
        "runner_id",
        "key_id",
        "payload_sha256",
        "nonce",
        "activated_at",
        "finished_at",
        "finish_reason",
        "lease_document",
        "live_context",
        "counters",
        "authorization_count",
        "last_authorized_at",
    }
)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _snapshot_mapping(value: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        snapshot = json.loads(_canonical_bytes(value))
    except Exception:
        return None
    return snapshot if type(snapshot) is dict else None


def _is_sha256(value: Any) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _is_identifier(value: Any) -> bool:
    return (
        type(value) is str
        and _IDENTIFIER_RE.fullmatch(value) is not None
    )


def _is_exact_int(value: Any, *, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _parse_utc(value: Any) -> datetime | None:
    if (
        type(value) is not str
        or _UTC_TIMESTAMP_RE.fullmatch(value) is None
    ):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _resolved_path_outside_repository(
    path: Path,
    *,
    repository_root: Path,
    must_exist: bool,
) -> Path:
    if not path.is_absolute():
        raise ValueError("run-lease boundary paths must be absolute")
    if must_exist:
        resolved = path.resolve(strict=True)
    else:
        parent = path.parent.resolve(strict=True)
        resolved = parent / path.name
    try:
        resolved.relative_to(repository_root)
    except ValueError:
        return resolved
    raise ValueError("run-lease boundary must be outside the repository")


def _path_identity_sha256(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def _validate_capability_manifest(
    value: Any,
    *,
    runner_id: Any,
) -> str | None:
    if (
        type(value) is not dict
        or frozenset(value.keys()) != _CAPABILITY_FIELDS
    ):
        return "run_lease_capability_manifest_invalid"
    if (
        value.get("schema_version")
        != RUN_LEASE_CAPABILITY_SCHEMA_VERSION
    ):
        return "run_lease_capability_manifest_invalid"
    action_classes = value.get("action_classes")
    if (
        type(action_classes) is not list
        or not action_classes
        or any(type(item) is not str for item in action_classes)
        or action_classes != sorted(action_classes)
        or len(action_classes) != len(set(action_classes))
    ):
        return "run_lease_action_classes_invalid"
    allowed_for_runner = RUN_LEASE_ACTIONS_BY_RUNNER.get(runner_id)
    if (
        allowed_for_runner is None
        or not set(action_classes).issubset(allowed_for_runner)
        or not set(action_classes).issubset(RUN_LEASE_ACTION_CLASSES)
    ):
        return "run_lease_action_classes_invalid"
    for field in (
        "filesystem_policy_sha256",
        "network_policy_sha256",
        "child_task_policy_sha256",
    ):
        if not _is_sha256(value.get(field)):
            return "run_lease_capability_manifest_invalid"
    return None


def _validate_limits(value: Any, *, runner_id: Any) -> str | None:
    if (
        type(value) is not dict
        or frozenset(value.keys()) != frozenset(_LIMIT_FIELDS)
    ):
        return "run_lease_limits_invalid"
    ceilings = _RUNNER_LIMIT_CEILINGS.get(runner_id)
    if ceilings is None:
        return "run_lease_runner_id_invalid"
    for field in _LIMIT_FIELDS:
        minimum = 1 if field in {
            "max_runtime_sec",
            "max_cycles",
            "max_actions",
        } else 0
        if not _is_exact_int(
            value.get(field),
            minimum=minimum,
            maximum=ceilings[field],
        ):
            return "run_lease_limits_invalid"
    if value["max_actions"] < value["max_cycles"]:
        return "run_lease_limits_invalid"
    # AUT-0 V1 intentionally has no network or child-task action class.
    for forbidden_budget in (
        "max_external_requests",
        "max_external_response_bytes",
        "max_child_tasks",
        "max_concurrent_child_tasks",
    ):
        if value[forbidden_budget] != 0:
            return "run_lease_limits_invalid"
    return None


def _validate_scratch_boundary(value: Any) -> str | None:
    if (
        type(value) is not dict
        or frozenset(value.keys()) != _SCRATCH_BOUNDARY_FIELDS
        or not _is_identifier(value.get("boundary_id"))
        or not _is_sha256(value.get("resolved_root_sha256"))
        or not _is_sha256(value.get("identity_manifest_sha256"))
    ):
        return "run_lease_scratch_boundary_invalid"
    return None


def _validate_replay_domain(
    value: Any,
    *,
    deployment_id: Any,
) -> str | None:
    if (
        type(value) is not dict
        or frozenset(value.keys()) != _REPLAY_DOMAIN_FIELDS
        or value.get("schema_version")
        != RUN_LEASE_REPLAY_DOMAIN_SCHEMA_VERSION
        or type(value.get("ledger_id")) is not str
        or _LEDGER_ID_RE.fullmatch(value["ledger_id"]) is None
        or value.get("deployment_id") != deployment_id
        or not _is_sha256(value.get("resolved_root_sha256"))
        or not _is_sha256(value.get("identity_manifest_sha256"))
        or value.get("lock_relative_path")
        != RUN_LEASE_LOCK_RELATIVE_PATH
        or value.get("claims_relative_path")
        != RUN_LEASE_CLAIMS_RELATIVE_PATH
        or value.get("active_relative_path")
        != RUN_LEASE_ACTIVE_RELATIVE_PATH
    ):
        return "run_lease_replay_domain_invalid"
    return None


def _validate_bound_context(
    value: Mapping[str, Any],
    *,
    exact_fields: bool,
) -> str | None:
    if exact_fields and frozenset(value.keys()) != _LIVE_CONTEXT_FIELDS:
        return "run_lease_live_context_fields_mismatch"
    runner_id = value.get("runner_id")
    if runner_id not in RUN_LEASE_ACTIONS_BY_RUNNER:
        return "run_lease_runner_id_invalid"
    for identifier_field in (
        "deployment_id",
        "runtime_instance_id",
        "operator_boundary_id",
    ):
        if not _is_identifier(value.get(identifier_field)):
            return f"run_lease_{identifier_field}_invalid"
    for digest_field in (
        "runner_artifact_sha256",
        "config_sha256",
        "input_manifest_sha256",
        "operator_boundary_config_sha256",
    ):
        if not _is_sha256(value.get(digest_field)):
            return f"run_lease_{digest_field}_invalid"
    capability_error = _validate_capability_manifest(
        value.get("capability_manifest"),
        runner_id=runner_id,
    )
    if capability_error is not None:
        return capability_error
    limits_error = _validate_limits(value.get("limits"), runner_id=runner_id)
    if limits_error is not None:
        return limits_error
    scratch_error = _validate_scratch_boundary(value.get("scratch_boundary"))
    if scratch_error is not None:
        return scratch_error
    return _validate_replay_domain(
        value.get("nonce_replay_domain"),
        deployment_id=value.get("deployment_id"),
    )


def _validate_lease_schema(
    document: Mapping[str, Any],
    *,
    now: datetime,
) -> str | None:
    if frozenset(document.keys()) != _LEASE_FIELDS:
        return "run_lease_fields_mismatch"
    signature = document.get(SIGNATURE_FIELD)
    if (
        type(signature) is not dict
        or frozenset(signature.keys()) != _SIGNATURE_FIELDS
    ):
        return "run_lease_signature_fields_mismatch"
    if document.get("schema_version") != RUN_LEASE_SCHEMA_VERSION:
        return "run_lease_schema_version_mismatch"
    if document.get("purpose") != RUN_LEASE_PURPOSE:
        return "run_lease_purpose_mismatch"
    if not _is_identifier(document.get("lease_id")):
        return "run_lease_lease_id_invalid"
    context_error = _validate_bound_context(document, exact_fields=False)
    if context_error is not None:
        return context_error
    issued_at = _parse_utc(document.get("issued_at"))
    if issued_at is None:
        return "run_lease_issued_at_invalid"
    expires_at = _parse_utc(document.get("expires_at"))
    if expires_at is None:
        return "run_lease_expires_at_invalid"
    if expires_at <= issued_at:
        return "run_lease_time_order_invalid"
    limits = document["limits"]
    if (expires_at - issued_at).total_seconds() > limits["max_runtime_sec"]:
        return "run_lease_duration_exceeds_policy"
    if now < issued_at:
        return "run_lease_not_yet_valid"
    if now >= expires_at:
        return "run_lease_expired"
    nonce = document.get("nonce")
    if type(nonce) is not str or _NONCE_RE.fullmatch(nonce) is None:
        return "run_lease_nonce_invalid"
    return None


@dataclass(frozen=True)
class RunLeaseVerification:
    """Fail-closed lease verification receipt; never itself execution authority."""

    ok: bool
    reason: str
    key_id: str | None = None
    payload_sha256: str | None = None
    lease_id: str | None = None
    runner_id: str | None = None
    nonce: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _verification_failure(
    reason: str,
    *,
    key_id: str | None = None,
    digest: str | None = None,
) -> RunLeaseVerification:
    return RunLeaseVerification(
        ok=False,
        reason=reason,
        key_id=key_id,
        payload_sha256=digest,
    )


def verify_run_lease(
    document: Mapping[str, Any],
    *,
    trust_root: OperatorTrustRoot,
    live_context: Mapping[str, Any] | None,
) -> RunLeaseVerification:
    """Verify a strict signed lease against independently reconstructed context."""
    document_snapshot = _snapshot_mapping(document)
    if document_snapshot is None:
        return _verification_failure("run_lease_unreadable")
    context_snapshot = (
        _snapshot_mapping(live_context)
        if isinstance(live_context, Mapping)
        else None
    )
    now = datetime.now(timezone.utc)
    schema_error = _validate_lease_schema(document_snapshot, now=now)
    if schema_error is not None:
        return _verification_failure(schema_error)
    if context_snapshot is None:
        return _verification_failure("run_lease_live_context_required")
    context_error = _validate_bound_context(
        context_snapshot,
        exact_fields=True,
    )
    if context_error is not None:
        return _verification_failure(context_error)
    for field in _LIVE_CONTEXT_FIELD_ORDER:
        if document_snapshot.get(field) != context_snapshot.get(field):
            return _verification_failure(
                f"run_lease_live_{field}_mismatch"
            )

    signed = trust_root.verify_document(
        document_snapshot,
        required_purpose=RUN_LEASE_PURPOSE,
    )
    if not signed.ok:
        reason_map = {
            "purpose_mismatch": "run_lease_purpose_mismatch",
            "operator_signature_missing": (
                "run_lease_operator_signature_missing"
            ),
            "unsupported_signature_scheme": (
                "run_lease_signature_scheme_unsupported"
            ),
            "operator_key_mismatch": "run_lease_operator_key_mismatch",
            "payload_not_canonicalizable": "run_lease_unreadable",
            "payload_digest_mismatch": "run_lease_payload_digest_mismatch",
            "signature_bytes_missing": (
                "run_lease_signature_bytes_missing"
            ),
            "signature_encoding_invalid": (
                "run_lease_signature_encoding_invalid"
            ),
            "signature_invalid": "run_lease_signature_invalid",
            "signature_verifier_error": (
                "run_lease_signature_verifier_error"
            ),
        }
        return _verification_failure(
            reason_map.get(
                signed.reason,
                f"run_lease_{signed.reason}",
            ),
            key_id=signed.key_id,
            digest=signed.payload_sha256,
        )
    return RunLeaseVerification(
        ok=True,
        reason="run_lease_valid",
        key_id=signed.key_id,
        payload_sha256=signed.payload_sha256,
        lease_id=document_snapshot["lease_id"],
        runner_id=document_snapshot["runner_id"],
        nonce=document_snapshot["nonce"],
    )


@dataclass(frozen=True)
class RunLeaseBoundaryConfig:
    """Installation-fixed external trust configuration and replay identity."""

    config_path: Path
    repository_root: Path
    operator_public_key_path: Path
    expected_key_id: str
    operator_boundary_id: str
    deployment_id: str
    replay_root: Path
    emergency_stop_path: Path
    operator_boundary_config_sha256: str
    replay_domain: dict[str, Any]
    trust_root: OperatorTrustRoot
    _validation_token: object = field(repr=False, compare=False)

    @classmethod
    def from_external_file(
        cls,
        path: str | Path,
        *,
        repository_root: str | Path,
    ) -> "RunLeaseBoundaryConfig":
        repo = Path(repository_root).resolve(strict=True)
        config_path = _resolved_path_outside_repository(
            Path(path),
            repository_root=repo,
            must_exist=True,
        )
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("run-lease trust config is unreadable") from exc
        if (
            type(raw) is not dict
            or frozenset(raw.keys()) != _TRUST_CONFIG_FIELDS
            or raw.get("schema_version")
            != RUN_LEASE_TRUST_CONFIG_SCHEMA_VERSION
        ):
            raise ValueError("run-lease trust config schema is invalid")
        for identifier_field in (
            "operator_boundary_id",
            "deployment_id",
        ):
            if not _is_identifier(raw.get(identifier_field)):
                raise ValueError(
                    f"run-lease trust config {identifier_field} is invalid"
                )
        expected_key_id = raw.get("expected_key_id")
        if type(expected_key_id) is not str or not expected_key_id:
            raise ValueError("run-lease operator key pin is required")
        key_path = _resolved_path_outside_repository(
            Path(raw.get("operator_public_key_path", "")),
            repository_root=repo,
            must_exist=True,
        )
        replay_root = _resolved_path_outside_repository(
            Path(raw.get("replay_root", "")),
            repository_root=repo,
            must_exist=True,
        )
        if not replay_root.is_dir():
            raise ValueError("run-lease replay root must be a directory")
        emergency_path = _resolved_path_outside_repository(
            Path(raw.get("emergency_stop_path", "")),
            repository_root=repo,
            must_exist=False,
        )
        identity_path = replay_root / RUN_LEASE_REPLAY_IDENTITY_FILENAME
        try:
            identity = json.loads(identity_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "run-lease replay identity is unreadable"
            ) from exc
        if (
            type(identity) is not dict
            or frozenset(identity.keys()) != _REPLAY_IDENTITY_FIELDS
            or identity.get("schema_version")
            != RUN_LEASE_REPLAY_IDENTITY_SCHEMA_VERSION
            or type(identity.get("ledger_id")) is not str
            or _LEDGER_ID_RE.fullmatch(identity["ledger_id"]) is None
            or identity.get("deployment_id") != raw["deployment_id"]
            or identity.get("resolved_root_sha256")
            != _path_identity_sha256(replay_root)
            or identity.get("lock_relative_path")
            != RUN_LEASE_LOCK_RELATIVE_PATH
            or identity.get("claims_relative_path")
            != RUN_LEASE_CLAIMS_RELATIVE_PATH
            or identity.get("active_relative_path")
            != RUN_LEASE_ACTIVE_RELATIVE_PATH
        ):
            raise ValueError("run-lease replay identity is invalid")
        claims_dir = replay_root / RUN_LEASE_CLAIMS_RELATIVE_PATH
        active_dir = replay_root / RUN_LEASE_ACTIVE_RELATIVE_PATH
        if not claims_dir.is_dir() or not active_dir.is_dir():
            raise ValueError(
                "run-lease replay claims and active directories "
                "must be externally provisioned"
            )
        identity_digest = hashlib.sha256(_canonical_bytes(identity)).hexdigest()
        replay_domain = {
            "schema_version": RUN_LEASE_REPLAY_DOMAIN_SCHEMA_VERSION,
            "ledger_id": identity["ledger_id"],
            "deployment_id": identity["deployment_id"],
            "resolved_root_sha256": identity["resolved_root_sha256"],
            "identity_manifest_sha256": identity_digest,
            "lock_relative_path": identity["lock_relative_path"],
            "claims_relative_path": identity["claims_relative_path"],
            "active_relative_path": identity["active_relative_path"],
        }
        trust_root = OperatorTrustRoot.from_external_file(
            key_path,
            repository_root=repo,
            expected_key_id=expected_key_id,
        )
        config_digest = hashlib.sha256(_canonical_bytes(raw)).hexdigest()
        return cls(
            config_path=config_path,
            repository_root=repo,
            operator_public_key_path=key_path,
            expected_key_id=expected_key_id,
            operator_boundary_id=raw["operator_boundary_id"],
            deployment_id=raw["deployment_id"],
            replay_root=replay_root,
            emergency_stop_path=emergency_path,
            operator_boundary_config_sha256=config_digest,
            replay_domain=replay_domain,
            trust_root=trust_root,
            _validation_token=_VALIDATED_BOUNDARY_TOKEN,
        )


@dataclass(frozen=True)
class RunLeaseActivationResult:
    allowed: bool
    reason: str
    lease_id: str | None = None
    runner_id: str | None = None
    payload_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunLeaseAuthorization:
    allowed: bool
    reason: str
    lease_id: str | None
    runner_id: str | None
    action_class: str | None
    counters: dict[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunLeaseFinishResult:
    finished: bool
    reason: str
    lease_id: str | None
    runner_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    """Serialize replay and budget transitions across local processes."""
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        if os.name == "nt":  # pragma: no cover - exercised on Windows host
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:  # pragma: no cover - exercised in Linux CI
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class RunLeaseStore:
    """Durable single-use lease activation and per-action budget gate."""

    def __init__(
        self,
        boundary: RunLeaseBoundaryConfig,
        *,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        if type(boundary) is not RunLeaseBoundaryConfig:
            raise TypeError(
                "externally validated RunLeaseBoundaryConfig is required"
            )
        if boundary._validation_token is not _VALIDATED_BOUNDARY_TOKEN:
            raise ValueError(
                "externally validated RunLeaseBoundaryConfig is required"
            )
        try:
            rehydrated = RunLeaseBoundaryConfig.from_external_file(
                boundary.config_path,
                repository_root=boundary.repository_root,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError(
                "externally validated RunLeaseBoundaryConfig is required"
            ) from exc
        binding_fields = (
            "config_path",
            "repository_root",
            "operator_public_key_path",
            "expected_key_id",
            "operator_boundary_id",
            "deployment_id",
            "replay_root",
            "emergency_stop_path",
            "operator_boundary_config_sha256",
            "replay_domain",
        )
        if any(
            getattr(boundary, name) != getattr(rehydrated, name)
            for name in binding_fields
        ):
            raise ValueError(
                "RunLeaseBoundaryConfig does not match its external source"
            )
        # Ignore the caller-held trust_root object.  A self-consistent boundary
        # receipt is not a bearer capability; the pinned external source is.
        self.boundary = rehydrated
        self.lock_path = (
            boundary.replay_root / RUN_LEASE_LOCK_RELATIVE_PATH
        )
        self.claims_dir = (
            boundary.replay_root / RUN_LEASE_CLAIMS_RELATIVE_PATH
        )
        self.active_dir = (
            boundary.replay_root / RUN_LEASE_ACTIVE_RELATIVE_PATH
        )
        replay_domain = _snapshot_mapping(boundary.replay_domain)
        if replay_domain is None:
            raise ValueError("run_lease_replay_domain_identity_mismatch")
        self._replay_domain = replay_domain
        self._monotonic_clock = monotonic_clock
        self._local_started: dict[str, float] = {}
        boundary_error = self._boundary_state_error()
        if boundary_error is not None:
            raise ValueError(boundary_error)

    def _pinned_operator_trust_root(self) -> OperatorTrustRoot:
        """Rehydrate the independently pinned key; never trust a supplied object."""
        return OperatorTrustRoot.from_external_file(
            self.boundary.operator_public_key_path,
            repository_root=self.boundary.repository_root,
            expected_key_id=self.boundary.expected_key_id,
        )

    def _boundary_state_error(self) -> str | None:
        """Recheck the externally provisioned replay identity fail-closed."""
        try:
            config = json.loads(
                self.boundary.config_path.read_text(encoding="utf-8")
            )
            if (
                type(config) is not dict
                or frozenset(config.keys()) != _TRUST_CONFIG_FIELDS
                or hashlib.sha256(_canonical_bytes(config)).hexdigest()
                != self.boundary.operator_boundary_config_sha256
            ):
                return "run_lease_trust_config_invalid"
            trust_root = self._pinned_operator_trust_root()
            if trust_root.key_id != self.boundary.expected_key_id:
                return "run_lease_trust_config_invalid"
            if self.boundary.replay_root.resolve(strict=True) != (
                self.boundary.replay_root
            ):
                return "run_lease_replay_domain_identity_mismatch"
            identity_path = (
                self.boundary.replay_root
                / RUN_LEASE_REPLAY_IDENTITY_FILENAME
            )
            identity = json.loads(identity_path.read_text(encoding="utf-8"))
            if (
                type(identity) is not dict
                or frozenset(identity.keys()) != _REPLAY_IDENTITY_FIELDS
                or hashlib.sha256(_canonical_bytes(identity)).hexdigest()
                != self._replay_domain[
                    "identity_manifest_sha256"
                ]
                or identity.get("resolved_root_sha256")
                != _path_identity_sha256(self.boundary.replay_root)
                or identity.get("ledger_id")
                != self._replay_domain["ledger_id"]
                or identity.get("deployment_id")
                != self.boundary.deployment_id
                or not self.claims_dir.is_dir()
                or not self.active_dir.is_dir()
                or self.claims_dir.resolve(strict=True).parent
                != self.boundary.replay_root
                or self.active_dir.resolve(strict=True).parent
                != self.boundary.replay_root
            ):
                return "run_lease_replay_domain_identity_mismatch"
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            KeyError,
            ValueError,
        ):
            return "run_lease_replay_domain_identity_mismatch"
        return None

    def _active_path(self, runner_id: str) -> Path:
        digest = hashlib.sha256(runner_id.encode("utf-8")).hexdigest()
        return self.active_dir / f"{digest}.json"

    def _claim_path(
        self,
        *,
        key_id: str,
        nonce: str,
    ) -> Path:
        claim_id = hashlib.sha256(
            (
                f"{key_id}|{nonce}|{self.boundary.deployment_id}"
            ).encode("utf-8")
        ).hexdigest()
        return self.claims_dir / f"{claim_id}.json"

    @staticmethod
    def _write_atomic(path: Path, value: Mapping[str, Any]) -> None:
        payload = _canonical_bytes(value) + b"\n"
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return value if type(value) is dict else None

    def _boundary_matches_context(
        self,
        context: Mapping[str, Any],
    ) -> str | None:
        if context.get("deployment_id") != self.boundary.deployment_id:
            return "run_lease_live_deployment_id_mismatch"
        if (
            context.get("operator_boundary_id")
            != self.boundary.operator_boundary_id
        ):
            return "run_lease_live_operator_boundary_id_mismatch"
        if (
            context.get("operator_boundary_config_sha256")
            != self.boundary.operator_boundary_config_sha256
        ):
            return (
                "run_lease_live_operator_boundary_config_sha256_mismatch"
            )
        if (
            context.get("nonce_replay_domain")
            != self._replay_domain
        ):
            return "run_lease_live_nonce_replay_domain_mismatch"
        return None

    def activate(
        self,
        *,
        document: Mapping[str, Any],
        live_context: Mapping[str, Any],
    ) -> RunLeaseActivationResult:
        """Verify, durably consume, and activate a lease before thread creation."""
        document_snapshot = _snapshot_mapping(document)
        context_snapshot = _snapshot_mapping(live_context)
        if document_snapshot is None or context_snapshot is None:
            return RunLeaseActivationResult(
                False,
                "run_lease_unreadable",
            )
        boundary_state_error = self._boundary_state_error()
        if boundary_state_error is not None:
            return RunLeaseActivationResult(False, boundary_state_error)
        boundary_error = self._boundary_matches_context(context_snapshot)
        if boundary_error is not None:
            return RunLeaseActivationResult(False, boundary_error)
        try:
            trust_root = self._pinned_operator_trust_root()
        except (OSError, ValueError):
            return RunLeaseActivationResult(
                False,
                "run_lease_trust_config_invalid",
            )
        verified = verify_run_lease(
            document_snapshot,
            trust_root=trust_root,
            live_context=context_snapshot,
        )
        if not verified.ok:
            return RunLeaseActivationResult(False, verified.reason)
        assert verified.key_id is not None
        assert verified.payload_sha256 is not None
        assert verified.lease_id is not None
        assert verified.runner_id is not None
        assert verified.nonce is not None

        active_path = self._active_path(verified.runner_id)
        claim_path = self._claim_path(
            key_id=verified.key_id,
            nonce=verified.nonce,
        )
        now = datetime.now(timezone.utc).replace(microsecond=0)
        now_text = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        with _exclusive_file_lock(self.lock_path):
            if active_path.exists():
                prior = self._read_json(active_path)
                if prior is None:
                    return RunLeaseActivationResult(
                        False,
                        "run_lease_active_state_invalid",
                    )
                prior_lease_id = prior.get("lease_id")
                if (
                    type(prior_lease_id) is not str
                    or prior.get("runner_id") != verified.runner_id
                ):
                    return RunLeaseActivationResult(
                        False,
                        "run_lease_active_state_invalid",
                    )
                prior_error, _ = self._validate_active_state(
                    prior,
                    lease_id=prior_lease_id,
                    runner_id=verified.runner_id,
                )
                if (
                    prior_error is not None
                    and prior_error != "run_lease_runtime_expired"
                ):
                    return RunLeaseActivationResult(
                        False,
                        "run_lease_active_state_invalid",
                    )
                if prior.get("status") == "active":
                    prior_document = prior.get("lease_document")
                    prior_expiry = (
                        _parse_utc(prior_document.get("expires_at"))
                        if type(prior_document) is dict
                        else None
                    )
                    if prior_expiry is None:
                        return RunLeaseActivationResult(
                            False,
                            "run_lease_active_state_invalid",
                        )
                    if now < prior_expiry:
                        return RunLeaseActivationResult(
                            False,
                            "run_lease_runner_already_active",
                            lease_id=str(prior.get("lease_id") or ""),
                            runner_id=verified.runner_id,
                        )

            claim = {
                "schema_version": RUN_LEASE_NONCE_CLAIM_SCHEMA_VERSION,
                "key_id": verified.key_id,
                "nonce": verified.nonce,
                "deployment_id": self.boundary.deployment_id,
                "lease_id": verified.lease_id,
                "runner_id": verified.runner_id,
                "payload_sha256": verified.payload_sha256,
                "claimed_at": now_text,
            }
            try:
                with claim_path.open("x", encoding="utf-8") as handle:
                    handle.write(
                        _canonical_bytes(claim).decode("utf-8") + "\n"
                    )
                    handle.flush()
                    os.fsync(handle.fileno())
            except FileExistsError:
                return RunLeaseActivationResult(
                    False,
                    "run_lease_replay",
                    lease_id=verified.lease_id,
                    runner_id=verified.runner_id,
                    payload_sha256=verified.payload_sha256,
                )
            except OSError:
                return RunLeaseActivationResult(
                    False,
                    "run_lease_claim_persistence_failed",
                    lease_id=verified.lease_id,
                    runner_id=verified.runner_id,
                    payload_sha256=verified.payload_sha256,
                )

            state = {
                "schema_version": RUN_LEASE_ACTIVE_STATE_SCHEMA_VERSION,
                "status": "active",
                "lease_id": verified.lease_id,
                "runner_id": verified.runner_id,
                "key_id": verified.key_id,
                "payload_sha256": verified.payload_sha256,
                "nonce": verified.nonce,
                "activated_at": now_text,
                "finished_at": "",
                "finish_reason": "",
                "lease_document": document_snapshot,
                "live_context": context_snapshot,
                "counters": {field: 0 for field in _COUNTER_FIELDS},
                "authorization_count": 0,
                "last_authorized_at": "",
            }
            try:
                self._write_atomic(active_path, state)
            except OSError:
                return RunLeaseActivationResult(
                    False,
                    "run_lease_active_state_persistence_failed",
                    lease_id=verified.lease_id,
                    runner_id=verified.runner_id,
                    payload_sha256=verified.payload_sha256,
                )
        self._local_started[verified.lease_id] = self._monotonic_clock()
        return RunLeaseActivationResult(
            True,
            "run_lease_activated",
            lease_id=verified.lease_id,
            runner_id=verified.runner_id,
            payload_sha256=verified.payload_sha256,
        )

    def _validate_active_state(
        self,
        state: Any,
        *,
        lease_id: str,
        runner_id: str,
    ) -> tuple[str | None, RunLeaseVerification | None]:
        if (
            type(state) is not dict
            or frozenset(state.keys()) != _ACTIVE_STATE_FIELDS
            or state.get("schema_version")
            != RUN_LEASE_ACTIVE_STATE_SCHEMA_VERSION
            or state.get("lease_id") != lease_id
            or state.get("runner_id") != runner_id
            or state.get("status") not in {"active", "finished"}
            or type(state.get("lease_document")) is not dict
            or type(state.get("live_context")) is not dict
            or type(state.get("counters")) is not dict
            or frozenset(state["counters"].keys())
            != frozenset(_COUNTER_FIELDS)
            or any(
                type(value) is not int or value < 0
                for value in state["counters"].values()
            )
            or type(state.get("authorization_count")) is not int
            or state["authorization_count"] < 0
        ):
            return "run_lease_active_state_invalid", None
        boundary_error = self._boundary_matches_context(
            state["live_context"]
        )
        if boundary_error is not None:
            return "run_lease_active_state_invalid", None
        try:
            trust_root = self._pinned_operator_trust_root()
        except (OSError, ValueError):
            return "run_lease_active_state_invalid", None
        verified = verify_run_lease(
            state["lease_document"],
            trust_root=trust_root,
            live_context=state["live_context"],
        )
        if not verified.ok:
            if verified.reason == "run_lease_expired":
                return "run_lease_runtime_expired", verified
            return "run_lease_active_state_invalid", verified
        if (
            verified.lease_id != lease_id
            or verified.runner_id != runner_id
            or verified.key_id != state.get("key_id")
            or verified.payload_sha256 != state.get("payload_sha256")
            or verified.nonce != state.get("nonce")
        ):
            return "run_lease_active_state_invalid", verified
        return None, verified

    @staticmethod
    def _validate_costs(
        action_class: str,
        value: Mapping[str, Any] | None,
    ) -> dict[str, int] | None:
        if value is None:
            snapshot = {
                "cycles": 0,
                "actions": 1,
                "external_requests": 0,
                "external_response_bytes": 0,
                "scratch_write_bytes": 0,
                "child_tasks": 0,
                "concurrent_child_tasks": 0,
            }
            if action_class in _CYCLE_ACTION_CLASSES:
                snapshot["cycles"] = 1
            if action_class in _WRITE_ACTION_CLASSES:
                snapshot["scratch_write_bytes"] = 1
        else:
            snapshot = _snapshot_mapping(value)
            if (
                snapshot is None
                or frozenset(snapshot.keys())
                != frozenset(_COUNTER_FIELDS)
                or any(
                    type(item) is not int or item < 0
                    for item in snapshot.values()
                )
                or snapshot["actions"] < 1
            ):
                return None
        if (
            action_class in _CYCLE_ACTION_CLASSES
            and snapshot["cycles"] != 1
        ):
            return None
        if (
            action_class in _WRITE_ACTION_CLASSES
            and snapshot["scratch_write_bytes"] < 1
        ):
            return None
        if (
            snapshot["external_requests"] != 0
            or snapshot["external_response_bytes"] != 0
            or snapshot["child_tasks"] != 0
            or snapshot["concurrent_child_tasks"] != 0
        ):
            return None
        return snapshot

    def authorize(
        self,
        *,
        lease_id: str,
        runner_id: str,
        action_class: str,
        costs: Mapping[str, Any] | None = None,
    ) -> RunLeaseAuthorization:
        """Atomically authorize and charge one exact action before it executes."""
        if (
            not _is_identifier(lease_id)
            or runner_id not in RUN_LEASE_ACTIONS_BY_RUNNER
            or type(action_class) is not str
        ):
            return RunLeaseAuthorization(
                False,
                "run_lease_authorization_request_invalid",
                lease_id if type(lease_id) is str else None,
                runner_id if type(runner_id) is str else None,
                action_class if type(action_class) is str else None,
            )
        boundary_state_error = self._boundary_state_error()
        if boundary_state_error is not None:
            return RunLeaseAuthorization(
                False,
                boundary_state_error,
                lease_id,
                runner_id,
                action_class,
            )
        cost_snapshot = self._validate_costs(action_class, costs)
        if cost_snapshot is None:
            return RunLeaseAuthorization(
                False,
                "run_lease_action_cost_invalid",
                lease_id,
                runner_id,
                action_class,
            )
        active_path = self._active_path(runner_id)
        with _exclusive_file_lock(self.lock_path):
            state = self._read_json(active_path)
            if state is None:
                return RunLeaseAuthorization(
                    False,
                    "run_lease_not_active",
                    lease_id,
                    runner_id,
                    action_class,
                )
            state_error, _ = self._validate_active_state(
                state,
                lease_id=lease_id,
                runner_id=runner_id,
            )
            if state_error is not None:
                return RunLeaseAuthorization(
                    False,
                    state_error,
                    lease_id,
                    runner_id,
                    action_class,
                    dict(state.get("counters") or {}),
                )
            if state["status"] != "active":
                return RunLeaseAuthorization(
                    False,
                    "run_lease_stopped",
                    lease_id,
                    runner_id,
                    action_class,
                    dict(state["counters"]),
                )
            if self.boundary.emergency_stop_path.exists():
                return RunLeaseAuthorization(
                    False,
                    "run_lease_emergency_stop",
                    lease_id,
                    runner_id,
                    action_class,
                    dict(state["counters"]),
                )
            local_start = self._local_started.get(lease_id)
            max_runtime = state["lease_document"]["limits"][
                "max_runtime_sec"
            ]
            if (
                local_start is not None
                and self._monotonic_clock() - local_start >= max_runtime
            ):
                return RunLeaseAuthorization(
                    False,
                    "run_lease_runtime_expired",
                    lease_id,
                    runner_id,
                    action_class,
                    dict(state["counters"]),
                )
            action_classes = state["lease_document"][
                "capability_manifest"
            ]["action_classes"]
            if action_class not in action_classes:
                return RunLeaseAuthorization(
                    False,
                    "run_lease_action_class_denied",
                    lease_id,
                    runner_id,
                    action_class,
                    dict(state["counters"]),
                )
            counters = dict(state["counters"])
            limits = state["lease_document"]["limits"]
            for counter, amount in cost_snapshot.items():
                next_value = counters[counter] + amount
                if next_value > limits[_COST_TO_LIMIT[counter]]:
                    return RunLeaseAuthorization(
                        False,
                        f"run_lease_budget_exhausted:{counter}",
                        lease_id,
                        runner_id,
                        action_class,
                        counters,
                    )
                counters[counter] = next_value
            now_text = datetime.now(timezone.utc).replace(
                microsecond=0
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            state["counters"] = counters
            state["authorization_count"] += 1
            state["last_authorized_at"] = now_text
            try:
                self._write_atomic(active_path, state)
            except OSError:
                return RunLeaseAuthorization(
                    False,
                    "run_lease_active_state_persistence_failed",
                    lease_id,
                    runner_id,
                    action_class,
                    dict(state["counters"]),
                )
            return RunLeaseAuthorization(
                True,
                "run_lease_action_authorized",
                lease_id,
                runner_id,
                action_class,
                counters,
            )

    def finish(
        self,
        *,
        lease_id: str,
        runner_id: str,
        reason: str,
    ) -> RunLeaseFinishResult:
        """Irreversibly close one active run; the consumed nonce stays consumed."""
        if (
            not _is_identifier(lease_id)
            or runner_id not in RUN_LEASE_ACTIONS_BY_RUNNER
            or not _is_identifier(reason)
        ):
            return RunLeaseFinishResult(
                False,
                "run_lease_finish_request_invalid",
                lease_id if type(lease_id) is str else None,
                runner_id if type(runner_id) is str else None,
            )
        boundary_state_error = self._boundary_state_error()
        if boundary_state_error is not None:
            return RunLeaseFinishResult(
                False,
                boundary_state_error,
                lease_id,
                runner_id,
            )
        active_path = self._active_path(runner_id)
        with _exclusive_file_lock(self.lock_path):
            state = self._read_json(active_path)
            if state is None:
                return RunLeaseFinishResult(
                    False,
                    "run_lease_not_active",
                    lease_id,
                    runner_id,
                )
            state_error, _ = self._validate_active_state(
                state,
                lease_id=lease_id,
                runner_id=runner_id,
            )
            if (
                state_error is not None
                and state_error != "run_lease_runtime_expired"
            ):
                return RunLeaseFinishResult(
                    False,
                    state_error,
                    lease_id,
                    runner_id,
                )
            if state.get("status") != "active":
                return RunLeaseFinishResult(
                    False,
                    "run_lease_stopped",
                    lease_id,
                    runner_id,
                )
            state["status"] = "finished"
            state["finished_at"] = datetime.now(timezone.utc).replace(
                microsecond=0
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            state["finish_reason"] = reason
            try:
                self._write_atomic(active_path, state)
            except OSError:
                return RunLeaseFinishResult(
                    False,
                    "run_lease_active_state_persistence_failed",
                    lease_id,
                    runner_id,
                )
        self._local_started.pop(lease_id, None)
        return RunLeaseFinishResult(
            True,
            "run_lease_finished",
            lease_id,
            runner_id,
        )

    def status(self) -> dict[str, Any]:
        """Return bounded, revalidated state without exposing signed documents.

        A field-complete active-state file is not evidence that its embedded
        lease is authentic.  Re-run the same external-boundary, pinned-key,
        signature, and live-context validation used by ``authorize`` before
        reporting a runner as healthy.  Callers may use the bounded projection
        for observability, but a shape-valid state with an altered signed lease
        or live-context binding cannot become ``state_ok=True``.
        """
        boundary_state_error = self._boundary_state_error()
        if boundary_state_error is not None:
            return {
                "schema_version": RUN_LEASE_ACTIVE_STATE_SCHEMA_VERSION,
                "deployment_id": self.boundary.deployment_id,
                "operator_boundary_id": (
                    self.boundary.operator_boundary_id
                ),
                "state_ok": False,
                "state_error": boundary_state_error,
                "runner_count": 0,
                "runners": {},
                "consumed_nonce_count": 0,
                "emergency_stop_active": (
                    self.boundary.emergency_stop_path.exists()
                ),
                "authority_mechanism": (
                    "externally_signed_bounded_run_lease"
                ),
                "capability_claim": False,
                "e4_claim": False,
                "e5_claim": False,
            }
        runners: dict[str, Any] = {}
        with _exclusive_file_lock(self.lock_path):
            for runner_id in sorted(RUN_LEASE_ACTIONS_BY_RUNNER):
                path = self._active_path(runner_id)
                if not path.exists():
                    runners[runner_id] = {
                        "state_ok": True,
                        "state_error": None,
                        "status": "inactive",
                    }
                    continue
                state = self._read_json(path)
                if state is None:
                    runners[runner_id] = {
                        "state_ok": False,
                        "state_error": "run_lease_active_state_invalid",
                        "status": "invalid",
                    }
                    continue
                lease_id = state.get("lease_id")
                state_error = (
                    "run_lease_active_state_invalid"
                    if type(lease_id) is not str
                    else self._validate_active_state(
                        state,
                        lease_id=lease_id,
                        runner_id=runner_id,
                    )[0]
                )
                runners[runner_id] = {
                    "state_ok": state_error is None,
                    "state_error": state_error,
                    "status": state.get("status"),
                    "lease_id": state.get("lease_id"),
                    "counters": state.get("counters"),
                    "authorization_count": state.get(
                        "authorization_count"
                    ),
                    "activated_at": state.get("activated_at"),
                    "finished_at": state.get("finished_at"),
                    "finish_reason": state.get("finish_reason"),
                }
        all_states_ok = all(
            runner.get("state_ok") is True for runner in runners.values()
        )
        return {
            "schema_version": RUN_LEASE_ACTIVE_STATE_SCHEMA_VERSION,
            "deployment_id": self.boundary.deployment_id,
            "operator_boundary_id": self.boundary.operator_boundary_id,
            "state_ok": all_states_ok,
            "state_error": (
                None
                if all_states_ok
                else "run_lease_active_state_invalid"
            ),
            "runner_count": len(runners),
            "runners": runners,
            "consumed_nonce_count": sum(
                1
                for path in self.claims_dir.glob("*.json")
                if path.is_file()
            ),
            "emergency_stop_active": (
                self.boundary.emergency_stop_path.exists()
            ),
            "authority_mechanism": "externally_signed_bounded_run_lease",
            "capability_claim": False,
            "e4_claim": False,
            "e5_claim": False,
        }
