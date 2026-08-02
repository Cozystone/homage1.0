"""The operator CLI creates only exact, externally signed run leases."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = Path(__file__).resolve().parents[2]
for entry in (str(REPO_ROOT), str(REPO_ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import issue_autonomy_run_lease as issuer
from packages.autonomy_envelope.run_lease import (
    AGENTIC_POLICY_DAEMON_RUNNER_ID,
    RUN_LEASE_ACTIVE_RELATIVE_PATH,
    RUN_LEASE_CAPABILITY_SCHEMA_VERSION,
    RUN_LEASE_CLAIMS_RELATIVE_PATH,
    RUN_LEASE_LOCK_RELATIVE_PATH,
    RUN_LEASE_REPLAY_IDENTITY_FILENAME,
    RUN_LEASE_REPLAY_IDENTITY_SCHEMA_VERSION,
    RUN_LEASE_TRUST_CONFIG_SCHEMA_VERSION,
    RunLeaseBoundaryConfig,
    RunLeaseStore,
)


def _key_id(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return f"ed25519:{hashlib.sha256(raw).hexdigest()[:24]}"


def _write_private_key(
    root: Path,
    private_key: Ed25519PrivateKey,
    *,
    name: str = "operator-private.pem",
) -> Path:
    path = root / name
    path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return path


def _provision(
    tmp_path: Path,
) -> tuple[Ed25519PrivateKey, Path, RunLeaseBoundaryConfig]:
    external = tmp_path / "external-operator-boundary"
    external.mkdir()
    replay = external / "replay"
    replay.mkdir()
    (replay / RUN_LEASE_CLAIMS_RELATIVE_PATH).mkdir()
    (replay / RUN_LEASE_ACTIVE_RELATIVE_PATH).mkdir()

    private_key = Ed25519PrivateKey.generate()
    private_path = _write_private_key(external, private_key)
    public_path = external / "operator-public.pem"
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    deployment_id = "atanor-issuer-test-deployment"
    identity = {
        "schema_version": RUN_LEASE_REPLAY_IDENTITY_SCHEMA_VERSION,
        "ledger_id": "atanor:autonomy-run-ledger:issuer-test-0001",
        "deployment_id": deployment_id,
        "resolved_root_sha256": hashlib.sha256(
            str(replay.resolve()).encode("utf-8")
        ).hexdigest(),
        "lock_relative_path": RUN_LEASE_LOCK_RELATIVE_PATH,
        "claims_relative_path": RUN_LEASE_CLAIMS_RELATIVE_PATH,
        "active_relative_path": RUN_LEASE_ACTIVE_RELATIVE_PATH,
    }
    (replay / RUN_LEASE_REPLAY_IDENTITY_FILENAME).write_text(
        json.dumps(identity, sort_keys=True),
        encoding="utf-8",
    )
    config_path = external / "run-lease-trust.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": RUN_LEASE_TRUST_CONFIG_SCHEMA_VERSION,
                "operator_public_key_path": str(public_path.resolve()),
                "expected_key_id": _key_id(private_key),
                "operator_boundary_id": "atanor-issuer-test-boundary",
                "deployment_id": deployment_id,
                "replay_root": str(replay.resolve()),
                "emergency_stop_path": str(
                    (external / "EMERGENCY_STOP").resolve()
                ),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    boundary = RunLeaseBoundaryConfig.from_external_file(
        config_path,
        repository_root=REPO_ROOT,
    )
    return private_key, private_path, boundary


def _live_context(boundary: RunLeaseBoundaryConfig) -> dict:
    return {
        "runner_id": AGENTIC_POLICY_DAEMON_RUNNER_ID,
        "deployment_id": boundary.deployment_id,
        "runtime_instance_id": "issuer-test-runtime-0001",
        "runner_artifact_sha256": "1" * 64,
        "config_sha256": "2" * 64,
        "input_manifest_sha256": "3" * 64,
        "capability_manifest": {
            "schema_version": RUN_LEASE_CAPABILITY_SCHEMA_VERSION,
            "action_classes": [
                "agentic.audit_append",
                "agentic.candidate_write",
                "agentic.review_read",
                "agentic.scratch_write",
                "agentic.tick",
            ],
            "filesystem_policy_sha256": "4" * 64,
            "network_policy_sha256": "5" * 64,
            "child_task_policy_sha256": "6" * 64,
        },
        "limits": {
            "max_runtime_sec": 60,
            "max_cycles": 2,
            "max_actions": 5,
            "max_external_requests": 0,
            "max_external_response_bytes": 0,
            "max_scratch_write_bytes": 4096,
            "max_child_tasks": 0,
            "max_concurrent_child_tasks": 0,
        },
        "scratch_boundary": {
            "boundary_id": "atanor-issuer-test-scratch",
            "resolved_root_sha256": "7" * 64,
            "identity_manifest_sha256": "8" * 64,
        },
        "operator_boundary_id": boundary.operator_boundary_id,
        "operator_boundary_config_sha256": (
            boundary.operator_boundary_config_sha256
        ),
        "nonce_replay_domain": boundary.replay_domain,
    }


def _write_context(path: Path, context: dict) -> None:
    path.write_text(
        json.dumps(context, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def test_cli_issued_lease_activates_in_exact_external_store(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, private_path, boundary = _provision(tmp_path)
    context = _live_context(boundary)
    context_path = tmp_path / "live-context.json"
    output_path = tmp_path / "run-lease.json"
    _write_context(context_path, context)

    result = issuer.main(
        [
            "--input",
            str(context_path),
            "--output",
            str(output_path),
            "--private-key",
            str(private_path.resolve()),
            "--duration-sec",
            "30",
            "--lease-id",
            "issuer-test-lease-0001",
            "--nonce",
            "issuer-test-nonce-0001",
            "--trust-config",
            str(boundary.config_path),
        ]
    )

    assert result == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["ok"] is True
    assert "signature" not in receipt
    document = json.loads(output_path.read_text(encoding="utf-8"))
    assert "PRIVATE KEY" not in output_path.read_text(encoding="utf-8")
    activated = RunLeaseStore(boundary).activate(
        document=document,
        live_context=context,
    )
    assert activated.allowed is True
    assert activated.reason == "run_lease_activated"


def test_tampered_issued_document_is_rejected(tmp_path: Path) -> None:
    _, private_path, boundary = _provision(tmp_path)
    context = _live_context(boundary)
    document = issuer.build_signed_run_lease(
        context,
        private_key_path=private_path,
        duration_sec=30,
        lease_id="issuer-test-lease-0002",
        nonce="issuer-test-nonce-0002",
        trust_config_path=boundary.config_path,
    )
    document["config_sha256"] = "9" * 64

    activated = RunLeaseStore(boundary).activate(
        document=document,
        live_context=context,
    )
    assert activated.allowed is False
    assert activated.reason == "run_lease_live_config_sha256_mismatch"


def test_endpoint_response_digest_and_key_metadata_are_checked(
    tmp_path: Path,
) -> None:
    _, private_path, boundary = _provision(tmp_path)
    context = _live_context(boundary)
    context_digest = hashlib.sha256(
        json.dumps(
            context,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    response_path = tmp_path / "lease-context-response.json"
    response = {
        "available": True,
        "purpose": "atanor.autonomy-run-lease.v1",
        "live_context": context,
        "live_context_sha256": context_digest,
        "signer_present_in_api": False,
        "private_key_required_outside_api": True,
        "expected_key_id": boundary.expected_key_id,
    }
    response_path.write_text(json.dumps(response), encoding="utf-8")
    output = tmp_path / "wrapper-issued.json"

    receipt = issuer.issue_run_lease_file(
        input_path=response_path,
        output_path=output,
        private_key_path=private_path,
        duration_sec=30,
        trust_config_path=boundary.config_path,
    )
    assert receipt["ok"] is True

    response["live_context_sha256"] = "0" * 64
    bad_response = tmp_path / "bad-lease-context-response.json"
    bad_response.write_text(json.dumps(response), encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        issuer.issue_run_lease_file(
            input_path=bad_response,
            output_path=tmp_path / "must-not-exist.json",
            private_key_path=private_path,
            duration_sec=30,
            trust_config_path=boundary.config_path,
        )


def test_wrong_key_and_overlong_duration_fail_without_output(
    tmp_path: Path,
) -> None:
    _, _, boundary = _provision(tmp_path)
    context = _live_context(boundary)
    context_path = tmp_path / "live-context.json"
    _write_context(context_path, context)
    wrong_private = _write_private_key(
        tmp_path,
        Ed25519PrivateKey.generate(),
        name="wrong-private.pem",
    )

    wrong_output = tmp_path / "wrong-key-lease.json"
    assert issuer.main(
        [
            "--input",
            str(context_path),
            "--output",
            str(wrong_output),
            "--private-key",
            str(wrong_private.resolve()),
            "--duration-sec",
            "30",
            "--trust-config",
            str(boundary.config_path),
        ]
    ) == 2
    assert not wrong_output.exists()

    overlong_output = tmp_path / "overlong-lease.json"
    assert issuer.main(
        [
            "--input",
            str(context_path),
            "--output",
            str(overlong_output),
            "--private-key",
            str(wrong_private.resolve()),
            "--duration-sec",
            "61",
        ]
    ) == 2
    assert not overlong_output.exists()


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    _, private_path, boundary = _provision(tmp_path)
    context_path = tmp_path / "live-context.json"
    _write_context(context_path, _live_context(boundary))
    output = tmp_path / "existing.json"
    output.write_text("operator-owned sentinel", encoding="utf-8")

    result = issuer.main(
        [
            "--input",
            str(context_path),
            "--output",
            str(output),
            "--private-key",
            str(private_path.resolve()),
            "--duration-sec",
            "30",
            "--trust-config",
            str(boundary.config_path),
        ]
    )

    assert result == 2
    assert output.read_text(encoding="utf-8") == "operator-owned sentinel"
    assert not list(tmp_path.glob(".existing.json.*.tmp"))
