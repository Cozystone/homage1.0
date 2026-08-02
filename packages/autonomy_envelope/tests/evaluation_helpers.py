"""Test-only helpers for explicit external evaluation receipts.

Keys generated here are ephemeral fixtures. They are not production authority and are
never written to repository/runtime configuration.
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from packages.autonomy_envelope.evaluation_trust import (
    EVALUATION_PURPOSE,
    EVALUATION_SCHEMA_VERSION,
)
from packages.autonomy_envelope.operator_trust import (
    ED25519_SCHEME,
    SIGNATURE_FIELD,
    OperatorTrustRoot,
    canonical_payload_bytes,
    payload_sha256,
)


def evaluation_keypair() -> tuple[Ed25519PrivateKey, OperatorTrustRoot]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    raw = public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_id = f"ed25519:{hashlib.sha256(raw).hexdigest()[:24]}"
    return private, OperatorTrustRoot(pem, expected_key_id=key_id)


def sign_document(
    document: dict[str, Any],
    private: Ed25519PrivateKey,
    trust_root: OperatorTrustRoot,
) -> dict[str, Any]:
    digest = payload_sha256(document)
    document[SIGNATURE_FIELD] = {
        "scheme": ED25519_SCHEME,
        "key_id": trust_root.key_id,
        "payload_sha256": digest,
        "signature": base64.b64encode(
            private.sign(canonical_payload_bytes(document))
        ).decode("ascii"),
    }
    return document


def signed_evaluation(
    *,
    oracle_fingerprint: str,
    private: Ed25519PrivateKey,
    trust_root: OperatorTrustRoot,
    score: float | int,
    run_id: str,
    nonce: str,
    metric_digest_sha256: str = "1" * 64,
    suite_digest_sha256: str = "2" * 64,
    dataset_digest_sha256: str = "3" * 64,
    candidate_digest_sha256: str = "4" * 64,
    evaluator_digest_sha256: str = "5" * 64,
    outcome_digest_sha256: str = "6" * 64,
    **overrides: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    document: dict[str, Any] = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "purpose": EVALUATION_PURPOSE,
        "oracle_fingerprint": oracle_fingerprint,
        "metric_digest_sha256": metric_digest_sha256,
        "suite_digest_sha256": suite_digest_sha256,
        "dataset_digest_sha256": dataset_digest_sha256,
        "candidate_digest_sha256": candidate_digest_sha256,
        "evaluator_digest_sha256": evaluator_digest_sha256,
        "outcome_digest_sha256": outcome_digest_sha256,
        "score": score,
        "run_id": run_id,
        "issued_at": (now - timedelta(minutes=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "expires_at": (now + timedelta(minutes=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "nonce": nonce,
    }
    document.update(overrides)
    sign_document(document, private, trust_root)
    context = {
        field: document[field]
        for field in (
            "oracle_fingerprint",
            "metric_digest_sha256",
            "suite_digest_sha256",
            "dataset_digest_sha256",
            "candidate_digest_sha256",
            "evaluator_digest_sha256",
            "outcome_digest_sha256",
            "score",
            "run_id",
        )
    }
    return document, context
