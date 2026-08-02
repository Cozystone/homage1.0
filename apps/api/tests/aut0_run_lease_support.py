from __future__ import annotations

import base64
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from packages.autonomy_envelope.operator_trust import (
    ED25519_SCHEME,
    SIGNATURE_FIELD,
    payload_sha256,
)
from packages.autonomy_envelope.run_lease import (
    RUN_LEASE_ACTIVE_RELATIVE_PATH,
    RUN_LEASE_CLAIMS_RELATIVE_PATH,
    RUN_LEASE_LOCK_RELATIVE_PATH,
    RUN_LEASE_PURPOSE,
    RUN_LEASE_REPLAY_IDENTITY_FILENAME,
    RUN_LEASE_REPLAY_IDENTITY_SCHEMA_VERSION,
    RUN_LEASE_SCHEMA_VERSION,
    RUN_LEASE_TRUST_CONFIG_SCHEMA_VERSION,
    RunLeaseBoundaryConfig,
    RunLeaseStore,
)


def _key_id(private: Ed25519PrivateKey) -> str:
    raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return f"ed25519:{hashlib.sha256(raw).hexdigest()[:24]}"


def provision_store(
    tmp_path: Path,
    *,
    repository_root: Path,
) -> tuple[Ed25519PrivateKey, RunLeaseStore]:
    external = tmp_path / "operator-boundary"
    external.mkdir()
    replay_root = external / "replay"
    replay_root.mkdir()
    (replay_root / RUN_LEASE_CLAIMS_RELATIVE_PATH).mkdir()
    (replay_root / RUN_LEASE_ACTIVE_RELATIVE_PATH).mkdir()

    private = Ed25519PrivateKey.generate()
    public_key_path = external / "operator-public.pem"
    public_key_path.write_bytes(
        private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    deployment_id = "atanor-api-test-deployment"
    identity = {
        "schema_version": RUN_LEASE_REPLAY_IDENTITY_SCHEMA_VERSION,
        "ledger_id": "atanor:autonomy-run-ledger:api-test-install-0001",
        "deployment_id": deployment_id,
        "resolved_root_sha256": hashlib.sha256(
            str(replay_root.resolve()).encode("utf-8")
        ).hexdigest(),
        "lock_relative_path": RUN_LEASE_LOCK_RELATIVE_PATH,
        "claims_relative_path": RUN_LEASE_CLAIMS_RELATIVE_PATH,
        "active_relative_path": RUN_LEASE_ACTIVE_RELATIVE_PATH,
    }
    (replay_root / RUN_LEASE_REPLAY_IDENTITY_FILENAME).write_text(
        json.dumps(identity, sort_keys=True),
        encoding="utf-8",
    )
    config_path = external / "run-lease-trust.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": RUN_LEASE_TRUST_CONFIG_SCHEMA_VERSION,
                "operator_public_key_path": str(public_key_path.resolve()),
                "expected_key_id": _key_id(private),
                "operator_boundary_id": "atanor-api-test-boundary",
                "deployment_id": deployment_id,
                "replay_root": str(replay_root.resolve()),
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
        repository_root=repository_root,
    )
    return private, RunLeaseStore(boundary)


def sign_lease(
    private: Ed25519PrivateKey,
    store: RunLeaseStore,
    context: dict[str, Any],
    *,
    lease_id: str,
    nonce: str,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    default_expiry = now + timedelta(
        seconds=max(
            1,
            min(300, int(context["limits"]["max_runtime_sec"]) - 1),
        )
    )
    document = {
        "schema_version": RUN_LEASE_SCHEMA_VERSION,
        "purpose": RUN_LEASE_PURPOSE,
        "lease_id": lease_id,
        **copy.deepcopy(context),
        "issued_at": (
            issued_at or now - timedelta(seconds=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (
            expires_at or default_expiry
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nonce": nonce,
        SIGNATURE_FIELD: {
            "scheme": ED25519_SCHEME,
            "key_id": store.boundary.expected_key_id,
            "payload_sha256": "",
            "signature": "",
        },
    }
    digest = payload_sha256(document)
    unsigned = {
        key: value
        for key, value in document.items()
        if key != SIGNATURE_FIELD
    }
    document[SIGNATURE_FIELD] = {
        "scheme": ED25519_SCHEME,
        "key_id": store.boundary.expected_key_id,
        "payload_sha256": digest,
        "signature": base64.b64encode(
            private.sign(
                json.dumps(
                    unsigned,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            )
        ).decode("ascii"),
    }
    return document
