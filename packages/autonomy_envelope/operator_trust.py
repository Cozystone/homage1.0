"""Detached operator-signature verification for production trust decisions.

This module deliberately exposes verification only. ATANOR cannot mint an operator
signature for itself. The Ed25519 private key stays outside the process and repository;
the shipped-graph mutation path obtains its public trust root, key pin, replay-domain
identity, and operator-boundary identity from one installation-fixed external config.

The confirmation-phrase promotion receipt is a reversible staging receipt, not a
cryptographic signature and not merge authority. The final shipped-graph side effect
requires a v3 signature over the exact live context and immutable mutation-batch
manifest. Nonce persistence, locking, journaled
rename, and deployment evidence are enforced by the landing-chain boundary that invokes
this verifier; this module never claims those filesystem effects itself.

Honest maturity: this is an M1 verification primitive. It authenticates an exact
operator assertion but cannot prove that the external deployment channel, filesystem
ACLs, evaluator quality, or resulting graph improve capability.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except Exception:  # pragma: no cover - deployment without verifier support fails closed
    InvalidSignature = Exception  # type: ignore[assignment]
    serialization = None  # type: ignore[assignment]
    Ed25519PublicKey = None  # type: ignore[assignment,misc]


SIGNATURE_FIELD = "operator_signature"
ED25519_SCHEME = "ed25519"
MORAL_POLICY_PURPOSE = "atanor.moral-policy.v1"
SHIPPED_GRAPH_PURPOSE = "atanor.shipped-graph-promotion.v3"
SHIPPED_GRAPH_SCHEMA_VERSION = "atanor.shipped-graph-promotion-document.v3"
LEGACY_SHIPPED_GRAPH_PURPOSE = "atanor.shipped-graph-promotion.v2"
LEGACY_SHIPPED_GRAPH_SCHEMA_VERSION = (
    "atanor.shipped-graph-promotion-document.v2"
)
NONCE_REPLAY_DOMAIN_SCHEMA_VERSION = (
    "atanor.promotion-nonce-replay-domain.v1"
)
NONCE_LEDGER_IDENTITY_SCHEMA_VERSION = (
    "atanor.promotion-nonce-ledger-identity.v1"
)
NONCE_LEDGER_IDENTITY_FILENAME = "promotion-nonce-ledger-identity.json"
NONCE_LEDGER_LOCK_RELATIVE_PATH = ".shipped-store-promotion.lock"
NONCE_LEDGER_CLAIMS_RELATIVE_PATH = "claims"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_LEDGER_ID_RE = re.compile(
    r"^atanor:promotion-ledger:[A-Za-z0-9][A-Za-z0-9._-]{15,127}$"
)
_NONCE_REPLAY_DOMAIN_FIELDS = frozenset(
    {
        "schema_version",
        "ledger_id",
        "target_store_id",
        "resolved_root_sha256",
        "identity_manifest_sha256",
        "lock_relative_path",
        "claims_relative_path",
    }
)
_PROMOTION_FIELDS = frozenset(
    {
        "schema_version",
        "purpose",
        "merge_authorized",
        "production_store_mutated",
        "rollback_required",
        "staging_receipt_sha256",
        "candidate_digest_sha256",
        "mutation_batch_manifest_sha256",
        "item_ids",
        "target_store_id",
        "operator_boundary_id",
        "operator_boundary_config_sha256",
        "base_revision",
        "rollback_artifact_sha256",
        "nonce_replay_domain",
        "issued_at",
        "expires_at",
        "nonce",
        SIGNATURE_FIELD,
    }
)
_LEGACY_PROMOTION_FIELDS = _PROMOTION_FIELDS - {
    "mutation_batch_manifest_sha256"
}
_PROMOTION_SIGNATURE_FIELDS = frozenset(
    {"scheme", "key_id", "payload_sha256", "signature"}
)
_LIVE_PROMOTION_CONTEXT_FIELD_ORDER = (
    "staging_receipt_sha256",
    "candidate_digest_sha256",
    "mutation_batch_manifest_sha256",
    "item_ids",
    "target_store_id",
    "operator_boundary_id",
    "operator_boundary_config_sha256",
    "base_revision",
    "rollback_artifact_sha256",
    "nonce_replay_domain",
)
_LIVE_PROMOTION_CONTEXT_FIELDS = frozenset(
    _LIVE_PROMOTION_CONTEXT_FIELD_ORDER
)
_LEGACY_LIVE_PROMOTION_CONTEXT_FIELD_ORDER = tuple(
    field
    for field in _LIVE_PROMOTION_CONTEXT_FIELD_ORDER
    if field != "mutation_batch_manifest_sha256"
)
_LEGACY_LIVE_PROMOTION_CONTEXT_FIELDS = frozenset(
    _LEGACY_LIVE_PROMOTION_CONTEXT_FIELD_ORDER
)


def canonical_payload_bytes(document: Mapping[str, Any]) -> bytes:
    """Return deterministic bytes while excluding the detached signature envelope."""
    payload = {key: value for key, value in document.items() if key != SIGNATURE_FIELD}
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def payload_sha256(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_payload_bytes(document)).hexdigest()


@dataclass(frozen=True)
class SignatureVerification:
    """Fail-closed verification receipt safe to include in an audit ledger."""

    ok: bool
    reason: str
    key_id: str | None
    payload_sha256: str | None
    purpose: str | None
    scheme: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OperatorTrustRoot:
    """An Ed25519 verifier bound to an independently supplied public-key pin.

    Supplying a key file alone is not an authority boundary: ATANOR could create a
    different key file. The caller must also supply the expected key ID from an
    operator-controlled channel. This object verifies that binding but cannot
    prove the channel or filesystem ACL is operator-controlled.
    """

    def __init__(self, public_key_pem: bytes, *, expected_key_id: str) -> None:
        if not isinstance(expected_key_id, str) or not expected_key_id:
            raise ValueError("an independently supplied operator key pin is required")
        if Ed25519PublicKey is None or serialization is None:
            raise RuntimeError("Ed25519 verification support is unavailable")
        try:
            key = serialization.load_pem_public_key(public_key_pem)
        except Exception as exc:
            raise ValueError("invalid operator public key") from exc
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("operator trust root must be an Ed25519 public key")
        raw = key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        key_id = f"ed25519:{hashlib.sha256(raw).hexdigest()[:24]}"
        if key_id != expected_key_id:
            raise ValueError("operator public key does not match the expected key pin")
        self._key = key
        self._key_id = key_id

    @classmethod
    def from_external_file(
        cls,
        path: str | Path,
        *,
        repository_root: str | Path,
        expected_key_id: str,
    ) -> "OperatorTrustRoot":
        """Load a public key only when it is outside the mutable repository tree."""
        key_path = Path(path).expanduser().resolve(strict=True)
        repo = Path(repository_root).resolve(strict=True)
        try:
            key_path.relative_to(repo)
        except ValueError:
            pass
        else:
            raise ValueError("operator trust root must be outside the repository")
        return cls(key_path.read_bytes(), expected_key_id=expected_key_id)

    @property
    def key_id(self) -> str:
        return self._key_id

    def verify_document(
        self,
        document: Mapping[str, Any],
        *,
        required_purpose: str,
    ) -> SignatureVerification:
        """Verify exact purpose, key binding, payload digest, and Ed25519 signature."""
        purpose = document.get("purpose")
        signature = document.get(SIGNATURE_FIELD)
        digest: str | None = None
        if purpose != required_purpose:
            return self._failure(
                "purpose_mismatch",
                purpose=str(purpose) if purpose is not None else None,
            )
        if not isinstance(signature, Mapping):
            return self._failure("operator_signature_missing", purpose=str(purpose))

        scheme = signature.get("scheme")
        key_id = signature.get("key_id")
        if scheme != ED25519_SCHEME:
            return self._failure(
                "unsupported_signature_scheme",
                key_id=str(key_id) if key_id is not None else None,
                purpose=str(purpose),
                scheme=str(scheme) if scheme is not None else None,
            )
        if key_id != self.key_id:
            return self._failure(
                "operator_key_mismatch",
                key_id=str(key_id) if key_id is not None else None,
                purpose=str(purpose),
                scheme=ED25519_SCHEME,
            )

        try:
            digest = payload_sha256(document)
        except (TypeError, ValueError):
            return self._failure(
                "payload_not_canonicalizable",
                key_id=self.key_id,
                purpose=str(purpose),
                scheme=ED25519_SCHEME,
            )
        if signature.get("payload_sha256") != digest:
            return self._failure(
                "payload_digest_mismatch",
                key_id=self.key_id,
                digest=digest,
                purpose=str(purpose),
                scheme=ED25519_SCHEME,
            )

        encoded = signature.get("signature")
        if not isinstance(encoded, str):
            return self._failure(
                "signature_bytes_missing",
                key_id=self.key_id,
                digest=digest,
                purpose=str(purpose),
                scheme=ED25519_SCHEME,
            )
        try:
            raw_signature = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            return self._failure(
                "signature_encoding_invalid",
                key_id=self.key_id,
                digest=digest,
                purpose=str(purpose),
                scheme=ED25519_SCHEME,
            )
        try:
            self._key.verify(raw_signature, canonical_payload_bytes(document))
        except InvalidSignature:
            return self._failure(
                "signature_invalid",
                key_id=self.key_id,
                digest=digest,
                purpose=str(purpose),
                scheme=ED25519_SCHEME,
            )
        except Exception:
            return self._failure(
                "signature_verifier_error",
                key_id=self.key_id,
                digest=digest,
                purpose=str(purpose),
                scheme=ED25519_SCHEME,
            )
        return SignatureVerification(
            ok=True,
            reason="operator_signature_valid",
            key_id=self.key_id,
            payload_sha256=digest,
            purpose=str(purpose),
            scheme=ED25519_SCHEME,
        )

    def _failure(
        self,
        reason: str,
        *,
        key_id: str | None = None,
        digest: str | None = None,
        purpose: str | None = None,
        scheme: str | None = None,
    ) -> SignatureVerification:
        return SignatureVerification(
            ok=False,
            reason=reason,
            key_id=key_id,
            payload_sha256=digest,
            purpose=purpose,
            scheme=scheme,
        )


def verify_moral_policy(
    document: Mapping[str, Any],
    *,
    live_moral_fingerprint: str,
    trust_root: OperatorTrustRoot,
) -> SignatureVerification:
    """Verify operator signature and bind it to the live moral invariant fingerprint."""
    verified = trust_root.verify_document(
        document,
        required_purpose=MORAL_POLICY_PURPOSE,
    )
    if not verified.ok:
        return verified
    if document.get("moral_fingerprint") != live_moral_fingerprint:
        return SignatureVerification(
            ok=False,
            reason="live_moral_fingerprint_mismatch",
            key_id=verified.key_id,
            payload_sha256=verified.payload_sha256,
            purpose=verified.purpose,
            scheme=verified.scheme,
        )
    return verified


def _same_verification_with_reason(
    verified: SignatureVerification,
    reason: str,
) -> SignatureVerification:
    return SignatureVerification(
        ok=False,
        reason=reason,
        key_id=verified.key_id,
        payload_sha256=verified.payload_sha256,
        purpose=verified.purpose,
        scheme=verified.scheme,
    )


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _is_identifier(value: Any) -> bool:
    return isinstance(value, str) and _IDENTIFIER_RE.fullmatch(value) is not None


def _valid_item_ids(value: Any) -> bool:
    if not isinstance(value, list) or len(value) != 1:
        return False
    if not all(_is_identifier(item_id) for item_id in value):
        return False
    return True


def _validate_nonce_replay_domain(
    value: Any,
    *,
    target_store_id: Any,
) -> bool:
    """Validate the exact signed identity of the durable replay domain."""
    if (
        not isinstance(value, Mapping)
        or frozenset(value.keys()) != _NONCE_REPLAY_DOMAIN_FIELDS
    ):
        return False
    if value.get("schema_version") != NONCE_REPLAY_DOMAIN_SCHEMA_VERSION:
        return False
    ledger_id = value.get("ledger_id")
    if (
        not isinstance(ledger_id, str)
        or _LEDGER_ID_RE.fullmatch(ledger_id) is None
    ):
        return False
    if value.get("target_store_id") != target_store_id:
        return False
    if not _is_sha256(value.get("resolved_root_sha256")):
        return False
    if not _is_sha256(value.get("identity_manifest_sha256")):
        return False
    if (
        value.get("lock_relative_path")
        != NONCE_LEDGER_LOCK_RELATIVE_PATH
    ):
        return False
    if (
        value.get("claims_relative_path")
        != NONCE_LEDGER_CLAIMS_RELATIVE_PATH
    ):
        return False
    return True


def _parse_utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or _UTC_TIMESTAMP_RE.fullmatch(value) is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _validate_promotion_schema(
    document: Mapping[str, Any],
    *,
    now: datetime,
    allow_legacy: bool = False,
) -> str | None:
    """Return the first strict schema violation, or ``None`` when valid."""
    legacy = (
        allow_legacy
        and document.get("schema_version")
        == LEGACY_SHIPPED_GRAPH_SCHEMA_VERSION
        and document.get("purpose") == LEGACY_SHIPPED_GRAPH_PURPOSE
    )
    expected_fields = (
        _LEGACY_PROMOTION_FIELDS if legacy else _PROMOTION_FIELDS
    )
    if frozenset(document.keys()) != expected_fields:
        return "promotion_schema_fields_mismatch"
    signature = document.get(SIGNATURE_FIELD)
    if (
        not isinstance(signature, Mapping)
        or frozenset(signature.keys()) != _PROMOTION_SIGNATURE_FIELDS
    ):
        return "signature_envelope_fields_mismatch"
    expected_schema = (
        LEGACY_SHIPPED_GRAPH_SCHEMA_VERSION
        if legacy
        else SHIPPED_GRAPH_SCHEMA_VERSION
    )
    if document.get("schema_version") != expected_schema:
        return "promotion_schema_version_mismatch"
    if document.get("merge_authorized") is not True:
        return "merge_authority_contract_invalid"
    if document.get("production_store_mutated") is not False:
        return "preverification_mutation_detected"
    if document.get("rollback_required") is not True:
        return "rollback_contract_missing"
    if not _is_sha256(document.get("staging_receipt_sha256")):
        return "staging_receipt_digest_invalid"
    if not _is_sha256(document.get("candidate_digest_sha256")):
        return "candidate_digest_invalid"
    if (
        not legacy
        and not _is_sha256(
            document.get("mutation_batch_manifest_sha256")
        )
    ):
        return "mutation_batch_manifest_digest_invalid"
    if not _valid_item_ids(document.get("item_ids")):
        return "item_ids_invalid"
    if not _is_identifier(document.get("target_store_id")):
        return "target_store_id_invalid"
    if not _is_identifier(document.get("operator_boundary_id")):
        return "operator_boundary_id_invalid"
    if not _is_sha256(document.get("operator_boundary_config_sha256")):
        return "operator_boundary_config_digest_invalid"
    if not _is_identifier(document.get("base_revision")):
        return "base_revision_invalid"
    if not _is_sha256(document.get("rollback_artifact_sha256")):
        return "rollback_artifact_digest_invalid"
    if not _validate_nonce_replay_domain(
        document.get("nonce_replay_domain"),
        target_store_id=document.get("target_store_id"),
    ):
        return "nonce_replay_domain_invalid"

    issued_at = _parse_utc_timestamp(document.get("issued_at"))
    if issued_at is None:
        return "issued_at_invalid"
    expires_at = _parse_utc_timestamp(document.get("expires_at"))
    if expires_at is None:
        return "expires_at_invalid"
    if expires_at <= issued_at:
        return "authorization_time_order_invalid"
    if now < issued_at:
        return "authorization_not_yet_valid"
    if now >= expires_at:
        return "authorization_expired"

    nonce = document.get("nonce")
    if not isinstance(nonce, str) or _NONCE_RE.fullmatch(nonce) is None:
        return "nonce_invalid"
    return None


def _validate_live_promotion_context(
    context: Mapping[str, Any],
    *,
    legacy: bool = False,
) -> str | None:
    expected_fields = (
        _LEGACY_LIVE_PROMOTION_CONTEXT_FIELDS
        if legacy
        else _LIVE_PROMOTION_CONTEXT_FIELDS
    )
    if frozenset(context.keys()) != expected_fields:
        return "live_context_fields_mismatch"
    if not _is_sha256(context.get("staging_receipt_sha256")):
        return "live_context_invalid"
    if not _is_sha256(context.get("candidate_digest_sha256")):
        return "live_context_invalid"
    if (
        not legacy
        and not _is_sha256(
            context.get("mutation_batch_manifest_sha256")
        )
    ):
        return "live_context_invalid"
    if not _valid_item_ids(context.get("item_ids")):
        return "live_context_invalid"
    if not _is_identifier(context.get("target_store_id")):
        return "live_context_invalid"
    if not _is_identifier(context.get("operator_boundary_id")):
        return "live_context_invalid"
    if not _is_sha256(context.get("operator_boundary_config_sha256")):
        return "live_context_invalid"
    if not _is_identifier(context.get("base_revision")):
        return "live_context_invalid"
    if not _is_sha256(context.get("rollback_artifact_sha256")):
        return "live_context_invalid"
    if not _validate_nonce_replay_domain(
        context.get("nonce_replay_domain"),
        target_store_id=context.get("target_store_id"),
    ):
        return "live_context_invalid"
    return None


def verify_shipped_graph_promotion(
    document: Mapping[str, Any],
    *,
    trust_root: OperatorTrustRoot,
    live_context: Mapping[str, Any] | None = None,
) -> SignatureVerification:
    """Verify one strict, time-bounded authorization against the live merge context.

    This is an M1 verification mechanism, not proof that the public-key pin came from a
    production operator channel. The invoking mutation boundary persists and rejects
    consumed nonces; this stateless verifier can validate a nonce's shape but cannot prevent
    replay by itself.
    """
    verified = trust_root.verify_document(
        document,
        required_purpose=SHIPPED_GRAPH_PURPOSE,
    )
    if not verified.ok:
        return verified

    schema_error = _validate_promotion_schema(
        document,
        now=datetime.now(timezone.utc),
    )
    if schema_error is not None:
        return _same_verification_with_reason(verified, schema_error)
    if not isinstance(live_context, Mapping):
        return _same_verification_with_reason(verified, "live_context_required")
    context_error = _validate_live_promotion_context(live_context)
    if context_error is not None:
        return _same_verification_with_reason(verified, context_error)
    for field in _LIVE_PROMOTION_CONTEXT_FIELD_ORDER:
        if document.get(field) != live_context.get(field):
            return _same_verification_with_reason(
                verified,
                f"live_{field}_mismatch",
            )
    return verified


def verify_shipped_graph_promotion_historical(
    document: Mapping[str, Any],
    *,
    trust_root: OperatorTrustRoot,
    live_context: Mapping[str, Any] | None,
    consumption_time: datetime,
) -> SignatureVerification:
    """Verify immutable deployment evidence at its nonce-consumption time.

    This deliberately does not weaken the live mutation verifier or expose a
    caller-selected clock to it.  It is only for a historical receipt whose
    timestamp is itself checked against the signed issuance/expiry window.
    """
    if (
        not isinstance(consumption_time, datetime)
        or consumption_time.tzinfo is None
    ):
        return SignatureVerification(
            ok=False,
            reason="historical_consumption_time_invalid",
            key_id=None,
            payload_sha256=None,
            purpose=None,
            scheme=None,
        )
    legacy = (
        document.get("schema_version")
        == LEGACY_SHIPPED_GRAPH_SCHEMA_VERSION
        and document.get("purpose") == LEGACY_SHIPPED_GRAPH_PURPOSE
    )
    required_purpose = (
        LEGACY_SHIPPED_GRAPH_PURPOSE
        if legacy
        else SHIPPED_GRAPH_PURPOSE
    )
    verified = trust_root.verify_document(
        document,
        required_purpose=required_purpose,
    )
    if not verified.ok:
        return verified
    schema_error = _validate_promotion_schema(
        document,
        now=consumption_time.astimezone(timezone.utc),
        allow_legacy=True,
    )
    if schema_error is not None:
        return _same_verification_with_reason(verified, schema_error)
    if not isinstance(live_context, Mapping):
        return _same_verification_with_reason(
            verified,
            "live_context_required",
        )
    context_error = _validate_live_promotion_context(
        live_context,
        legacy=legacy,
    )
    if context_error is not None:
        return _same_verification_with_reason(verified, context_error)
    context_fields = (
        _LEGACY_LIVE_PROMOTION_CONTEXT_FIELD_ORDER
        if legacy
        else _LIVE_PROMOTION_CONTEXT_FIELD_ORDER
    )
    for field in context_fields:
        if document.get(field) != live_context.get(field):
            return _same_verification_with_reason(
                verified,
                f"live_{field}_mismatch",
            )
    return verified
