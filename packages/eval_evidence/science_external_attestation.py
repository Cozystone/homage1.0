"""Strict science bindings for an externally signed evaluation assertion.

This module is deliberately only a binding adapter.  It does not run an
evaluator, hold a private key, authenticate a dataset publisher, or establish
process, UID, network, mount, or filesystem isolation.  It parses two compact
canonical documents, deterministically maps them to the existing generic
evaluation-receipt context, verifies a separately pinned evaluator key, and
uses :class:`EvaluationRatchetStore` for a cooperative local nonce claim.

A valid result therefore establishes only that an evaluator-key signature
asserted the exact live bindings consumed here.  It is not, by itself, an
independent evaluation, canonical E4 evidence, or E5 evidence.

``candidate_manifest_digest_sha256`` is the candidate-variant root and must
already include its source, runtime, and candidate configuration.
``evaluation_config_digest_sha256`` is the stable comparison protocol
configuration; keeping those meanings separate prevents a candidate revision
from opening a fresh no-regression scope.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
from typing import Any, Mapping

from packages.autonomy_envelope.evaluation_trust import (
    EvaluationRatchetStore,
    verify_evaluation_receipt,
)
from packages.autonomy_envelope.operator_trust import OperatorTrustRoot
from packages.eval_evidence.receipt import (
    BenchmarkEvidenceError,
    canonical_json_bytes,
    strict_json_bytes,
)


SCIENCE_PRECOMMIT_SCHEMA_VERSION = (
    "atanor.science-external-evaluation-precommit.v1"
)
SCIENCE_RESULT_ROOT_SCHEMA_VERSION = (
    "atanor.science-external-evaluation-result-root.v1"
)

_MAX_DOCUMENT_BYTES = 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID_RE = re.compile(r"^ed25519:[0-9a-f]{24}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")

_PRECOMMIT_FIELDS = frozenset(
    {
        "schema_version",
        "protocol_id",
        "oracle_spec_digest_sha256",
        "metric_spec_digest_sha256",
        "dataset_manifest_digest_sha256",
        "candidate_manifest_digest_sha256",
        "stage_manifest_digest_sha256",
        "evaluator_manifest_digest_sha256",
        "evaluation_config_digest_sha256",
        "order_digest_sha256",
        "isolation_contract_digest_sha256",
        "evaluator_key_id",
        "promotion_operator_key_id",
    }
)
_RESULT_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "precommit_digest_sha256",
        "run_id",
        "score",
        "executed_order_digest_sha256",
        "result_artifact_digest_sha256",
        "claims",
    }
)
_LIMITED_CLAIM_FIELDS = frozenset(
    {
        "os_isolation_established",
        "independent_evaluation_established",
        "canonical_e4_established",
        "e5_established",
    }
)
_PRECOMMIT_DIGEST_FIELDS = (
    "oracle_spec_digest_sha256",
    "metric_spec_digest_sha256",
    "dataset_manifest_digest_sha256",
    "candidate_manifest_digest_sha256",
    "stage_manifest_digest_sha256",
    "evaluator_manifest_digest_sha256",
    "evaluation_config_digest_sha256",
    "order_digest_sha256",
    "isolation_contract_digest_sha256",
)
_SUITE_BINDING_FIELDS = (
    "schema_version",
    "protocol_id",
    "evaluation_config_digest_sha256",
    "order_digest_sha256",
    "isolation_contract_digest_sha256",
    "evaluator_key_id",
    "promotion_operator_key_id",
)
_NONCE_CLAIMED_RATCHET_REASONS = frozenset(
    {
        "evaluation_holds_line",
        "evaluation_regression_blocked",
        "evaluation_state_persistence_failed",
        "verified_evaluation_scope_bindings_invalid",
    }
)


class ScienceExternalAttestationError(BenchmarkEvidenceError):
    """Raised when a science trust-boundary document fails closed."""


@dataclass(frozen=True)
class ScienceAttestationResult:
    """Bounded result from one signed-assertion and local-nonce attempt."""

    local_ratchet_allowed: bool
    reason: str
    signed_live_binding_valid: bool
    nonce_claimed_by_this_call: bool
    scope_id: str | None
    score: float | None
    baseline_before: float | None
    baseline_after: float | None
    os_isolation_established: bool = False
    independent_evaluation_established: bool = False
    canonical_e4_established: bool = False
    e5_established: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _is_key_id(value: Any) -> bool:
    return isinstance(value, str) and _KEY_ID_RE.fullmatch(value) is not None


def _is_identifier(value: Any) -> bool:
    return (
        isinstance(value, str)
        and _IDENTIFIER_RE.fullmatch(value) is not None
    )


def _is_score(value: Any) -> bool:
    return (
        type(value) in (int, float)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    )


def _document_sha256(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def _suite_digest(precommit: Mapping[str, Any]) -> str:
    """Bind comparable protocol controls without splitting scope by candidate."""

    return _document_sha256(
        {field: precommit[field] for field in _SUITE_BINDING_FIELDS}
    )


def _detached_mapping(value: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ScienceExternalAttestationError(f"{label} must be an object")
    try:
        detached = json.loads(canonical_json_bytes(value))
    except (BenchmarkEvidenceError, json.JSONDecodeError) as exc:
        raise ScienceExternalAttestationError(
            f"{label} is not finite canonical JSON"
        ) from exc
    if not isinstance(detached, dict):
        raise ScienceExternalAttestationError(f"{label} must be an object")
    return detached


def _parse_canonical_document(payload: bytes, *, label: str) -> dict[str, Any]:
    if (
        not isinstance(payload, bytes)
        or not payload
        or len(payload) > _MAX_DOCUMENT_BYTES
    ):
        raise ScienceExternalAttestationError(
            f"{label} canonical byte size is invalid"
        )
    try:
        value = strict_json_bytes(payload, label=label)
        expected = canonical_json_bytes(value) + b"\n"
    except BenchmarkEvidenceError as exc:
        raise ScienceExternalAttestationError(str(exc)) from exc
    if payload != expected:
        raise ScienceExternalAttestationError(
            f"{label} must be canonical JSON with one trailing newline"
        )
    return value


def _validate_precommit(precommit: Mapping[str, Any]) -> dict[str, Any]:
    value = _detached_mapping(precommit, label="science precommit")
    if frozenset(value) != _PRECOMMIT_FIELDS:
        raise ScienceExternalAttestationError(
            "science precommit fields mismatch"
        )
    if value.get("schema_version") != SCIENCE_PRECOMMIT_SCHEMA_VERSION:
        raise ScienceExternalAttestationError(
            "science precommit schema mismatch"
        )
    if not _is_identifier(value.get("protocol_id")):
        raise ScienceExternalAttestationError(
            "science precommit protocol_id invalid"
        )
    for field in _PRECOMMIT_DIGEST_FIELDS:
        if not _is_sha256(value.get(field)):
            raise ScienceExternalAttestationError(
                f"science precommit {field} invalid"
            )
    evaluator_key_id = value.get("evaluator_key_id")
    operator_key_id = value.get("promotion_operator_key_id")
    if not _is_key_id(evaluator_key_id):
        raise ScienceExternalAttestationError(
            "science precommit evaluator_key_id invalid"
        )
    if not _is_key_id(operator_key_id):
        raise ScienceExternalAttestationError(
            "science precommit promotion_operator_key_id invalid"
        )
    if evaluator_key_id == operator_key_id:
        raise ScienceExternalAttestationError(
            "evaluator and promotion operator key IDs must be distinct"
        )
    return value


def _validate_result_root(
    result_root: Mapping[str, Any],
    *,
    precommit: Mapping[str, Any],
) -> dict[str, Any]:
    value = _detached_mapping(result_root, label="science result root")
    if frozenset(value) != _RESULT_ROOT_FIELDS:
        raise ScienceExternalAttestationError(
            "science result root fields mismatch"
        )
    if value.get("schema_version") != SCIENCE_RESULT_ROOT_SCHEMA_VERSION:
        raise ScienceExternalAttestationError(
            "science result root schema mismatch"
        )
    if value.get("precommit_digest_sha256") != _document_sha256(precommit):
        raise ScienceExternalAttestationError(
            "science result root precommit digest mismatch"
        )
    if not _is_identifier(value.get("run_id")):
        raise ScienceExternalAttestationError(
            "science result root run_id invalid"
        )
    if not _is_score(value.get("score")):
        raise ScienceExternalAttestationError(
            "science result root score invalid"
        )
    if (
        value.get("executed_order_digest_sha256")
        != precommit.get("order_digest_sha256")
    ):
        raise ScienceExternalAttestationError(
            "science result root execution order mismatch"
        )
    if not _is_sha256(value.get("result_artifact_digest_sha256")):
        raise ScienceExternalAttestationError(
            "science result artifact digest invalid"
        )
    claims = value.get("claims")
    if (
        not isinstance(claims, dict)
        or frozenset(claims) != _LIMITED_CLAIM_FIELDS
    ):
        raise ScienceExternalAttestationError(
            "science result root claim fields mismatch"
        )
    for field in sorted(_LIMITED_CLAIM_FIELDS):
        if claims.get(field) is not False:
            raise ScienceExternalAttestationError(
                f"science result root {field} must remain false"
            )
    return value


def read_science_precommit(payload: bytes) -> dict[str, Any]:
    """Read one exact canonical precommit without granting authority."""

    return _validate_precommit(
        _parse_canonical_document(payload, label="science precommit")
    )


def read_science_result_root(
    payload: bytes,
    *,
    precommit: Mapping[str, Any],
) -> dict[str, Any]:
    """Read one exact canonical result root bound to ``precommit``."""

    checked_precommit = _validate_precommit(precommit)
    return _validate_result_root(
        _parse_canonical_document(payload, label="science result root"),
        precommit=checked_precommit,
    )


def read_signed_evaluation_receipt(payload: bytes) -> dict[str, Any]:
    """Read canonical signed-receipt bytes; signature checks happen separately."""

    return _parse_canonical_document(
        payload,
        label="signed science evaluation receipt",
    )


def derive_science_evaluation_live_context(
    precommit: Mapping[str, Any],
    result_root: Mapping[str, Any],
) -> dict[str, Any]:
    """Map exact science roots to the existing generic live-context schema."""

    checked_precommit = _validate_precommit(precommit)
    checked_result = _validate_result_root(
        result_root,
        precommit=checked_precommit,
    )
    candidate_and_stage = {
        "candidate_manifest_digest_sha256": checked_precommit[
            "candidate_manifest_digest_sha256"
        ],
        "stage_manifest_digest_sha256": checked_precommit[
            "stage_manifest_digest_sha256"
        ],
    }
    return {
        "oracle_fingerprint": checked_precommit[
            "oracle_spec_digest_sha256"
        ],
        "metric_digest_sha256": checked_precommit[
            "metric_spec_digest_sha256"
        ],
        # Comparison scope binds stable protocol controls and authority
        # identities, but deliberately excludes candidate and stage.  Those
        # remain signed below without creating a fresh ratchet baseline for
        # every candidate revision.
        "suite_digest_sha256": _suite_digest(checked_precommit),
        "dataset_digest_sha256": checked_precommit[
            "dataset_manifest_digest_sha256"
        ],
        "candidate_digest_sha256": _document_sha256(
            candidate_and_stage
        ),
        "evaluator_digest_sha256": checked_precommit[
            "evaluator_manifest_digest_sha256"
        ],
        # The full result root binds the executed order, primary score, run,
        # result artifact, precommit root, and deliberately limited claims.
        "outcome_digest_sha256": _document_sha256(checked_result),
        "score": checked_result["score"],
        "run_id": checked_result["run_id"],
    }


def _failure(
    reason: str,
    *,
    signed_live_binding_valid: bool = False,
    nonce_claimed_by_this_call: bool = False,
    scope_id: str | None = None,
    score: float | None = None,
    baseline_before: float | None = None,
    baseline_after: float | None = None,
) -> ScienceAttestationResult:
    return ScienceAttestationResult(
        local_ratchet_allowed=False,
        reason=reason,
        signed_live_binding_valid=signed_live_binding_valid,
        nonce_claimed_by_this_call=nonce_claimed_by_this_call,
        scope_id=scope_id,
        score=score,
        baseline_before=baseline_before,
        baseline_after=baseline_after,
    )


def consume_science_external_attestation(
    *,
    signed_receipt_bytes: bytes,
    precommit_bytes: bytes,
    result_root_bytes: bytes,
    evaluator_trust_root: OperatorTrustRoot,
    ratchet_store: EvaluationRatchetStore,
    promotion_operator_key_id: str,
) -> ScienceAttestationResult:
    """Verify exact science bindings and attempt one cooperative local nonce claim.

    The evaluator and promotion key IDs must be separately pinned and distinct.
    The supplied ratchet must be dedicated to the same evaluator key and science
    oracle fingerprint.  Even on success, all independence/E4/E5 fields remain
    literal false because this function cannot observe or enforce the external
    execution environment.
    """

    try:
        precommit = read_science_precommit(precommit_bytes)
        result_root = read_science_result_root(
            result_root_bytes,
            precommit=precommit,
        )
        receipt = read_signed_evaluation_receipt(signed_receipt_bytes)
        live_context = derive_science_evaluation_live_context(
            precommit,
            result_root,
        )
    except Exception as exc:
        return _failure(
            "science_attestation_document_invalid:"
            + type(exc).__name__
            + ":"
            + str(exc)
        )

    if type(evaluator_trust_root) is not OperatorTrustRoot:
        return _failure("science_evaluator_trust_root_invalid")
    if not _is_key_id(promotion_operator_key_id):
        return _failure("science_promotion_operator_key_id_invalid")
    if promotion_operator_key_id != precommit["promotion_operator_key_id"]:
        return _failure("science_promotion_operator_key_id_mismatch")
    if evaluator_trust_root.key_id != precommit["evaluator_key_id"]:
        return _failure("science_evaluator_key_id_mismatch")
    if evaluator_trust_root.key_id == promotion_operator_key_id:
        return _failure("science_evaluator_operator_key_reuse")
    if type(ratchet_store) is not EvaluationRatchetStore:
        return _failure("science_evaluation_ratchet_invalid")
    if ratchet_store.oracle_fingerprint != live_context["oracle_fingerprint"]:
        return _failure("science_evaluation_ratchet_oracle_mismatch")
    if (
        type(ratchet_store.trust_root) is not OperatorTrustRoot
        or ratchet_store.trust_root.key_id != evaluator_trust_root.key_id
    ):
        return _failure("science_evaluation_ratchet_key_mismatch")

    try:
        verified = verify_evaluation_receipt(
            receipt,
            trust_root=evaluator_trust_root,
            live_context=live_context,
            live_oracle_fingerprint=live_context["oracle_fingerprint"],
        )
    except Exception as exc:
        return _failure(
            "science_evaluation_verifier_error:" + type(exc).__name__
        )
    if verified.ok is not True:
        return _failure(verified.reason)

    ratchet = ratchet_store.apply(
        receipt=receipt,
        live_context=live_context,
    )
    # EvaluationRatchetStore serializes the claim and returns replay before
    # any later state decision.  Its result therefore identifies this call's
    # nonce transition without a racy process-global file-count delta.
    nonce_claimed = ratchet.reason in _NONCE_CLAIMED_RATCHET_REASONS
    if ratchet.allowed is not True:
        return _failure(
            ratchet.reason,
            signed_live_binding_valid=True,
            nonce_claimed_by_this_call=nonce_claimed,
            scope_id=ratchet.scope_id,
            score=ratchet.score,
            baseline_before=ratchet.baseline_before,
            baseline_after=ratchet.baseline_after,
        )
    return ScienceAttestationResult(
        local_ratchet_allowed=True,
        reason=ratchet.reason,
        signed_live_binding_valid=True,
        nonce_claimed_by_this_call=nonce_claimed,
        scope_id=ratchet.scope_id,
        score=ratchet.score,
        baseline_before=ratchet.baseline_before,
        baseline_after=ratchet.baseline_after,
    )


__all__ = [
    "SCIENCE_PRECOMMIT_SCHEMA_VERSION",
    "SCIENCE_RESULT_ROOT_SCHEMA_VERSION",
    "ScienceAttestationResult",
    "ScienceExternalAttestationError",
    "consume_science_external_attestation",
    "derive_science_evaluation_live_context",
    "read_science_precommit",
    "read_science_result_root",
    "read_signed_evaluation_receipt",
]
