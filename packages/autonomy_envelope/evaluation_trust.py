"""Externally signed evaluation receipts and a scope-bound persistent ratchet.

The local :class:`FrozenOracle` seals only a verifier *specification*.  It does not run
that verifier and cannot vouch for a caller-supplied score.  This module is the separate
authority boundary for no-regression decisions:

* an operator-pinned Ed25519 trust root verifies an exact evaluation-receipt schema;
* every score is a literal finite JSON number in ``[0, 1]``;
* the receipt is bound to the live oracle, metric, suite, dataset, candidate,
  evaluator, outcome artifact, and run;
* UTC validity and an exclusively claimed nonce make receipts time-bounded and
  single-use at this boundary; and
* baselines are persisted atomically per comparable evaluation scope.

This remains cooperative filesystem enforcement.  It does not prove that the public-key
pin came from an operator-controlled channel, that the evaluator really computed the
signed outcome, or that the state/nonce directory has OS isolation or remote durability.
Those are deployment obligations, not properties claimed by this module.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from packages.autonomy_envelope.operator_trust import (
    ED25519_SCHEME,
    SIGNATURE_FIELD,
    OperatorTrustRoot,
    payload_sha256,
)


EVALUATION_PURPOSE = "atanor.external-evaluation.v1"
EVALUATION_SCHEMA_VERSION = "atanor.external-evaluation-receipt.v1"
RATCHET_STATE_SCHEMA_VERSION = "atanor.evaluation-ratchet-state.v1"
NONCE_CLAIM_SCHEMA_VERSION = "atanor.evaluation-nonce-claim.v1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")

_DIGEST_FIELDS = (
    "metric_digest_sha256",
    "suite_digest_sha256",
    "dataset_digest_sha256",
    "candidate_digest_sha256",
    "evaluator_digest_sha256",
    "outcome_digest_sha256",
)
_SCOPE_BINDING_FIELDS = (
    "oracle_fingerprint",
    "metric_digest_sha256",
    "suite_digest_sha256",
    "dataset_digest_sha256",
    "evaluator_digest_sha256",
)
_LIVE_CONTEXT_FIELDS = frozenset(
    {
        "oracle_fingerprint",
        *_DIGEST_FIELDS,
        "score",
        "run_id",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "purpose",
        *_LIVE_CONTEXT_FIELDS,
        "issued_at",
        "expires_at",
        "nonce",
        SIGNATURE_FIELD,
    }
)
_SIGNATURE_FIELDS = frozenset(
    {"scheme", "key_id", "payload_sha256", "signature"}
)
_STATE_FIELDS = frozenset(
    {"schema_version", "oracle_fingerprint", "scopes"}
)
_SCOPE_STATE_FIELDS = frozenset(
    {
        "scope_id",
        *_SCOPE_BINDING_FIELDS,
        "baseline",
        "last_receipt_payload_sha256",
        "last_receipt",
        "last_run_id",
        "updated_at",
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


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _is_score(value: Any) -> bool:
    return (
        type(value) in (int, float)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    )


def _parse_utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or _UTC_TIMESTAMP_RE.fullmatch(value) is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def evaluation_scope_id(bindings: Mapping[str, Any]) -> str:
    """Return the deterministic comparison scope for one evaluation receipt."""
    scope = {field: bindings[field] for field in _SCOPE_BINDING_FIELDS}
    return hashlib.sha256(_canonical_bytes(scope)).hexdigest()


@dataclass(frozen=True)
class EvaluationVerification:
    """A fail-closed verification result safe to write to the audit ledger."""

    ok: bool
    reason: str
    key_id: str | None = None
    payload_sha256: str | None = None
    scope_id: str | None = None
    score: float | None = None
    nonce: str | None = None
    run_id: str | None = None
    scope_bindings: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _failure(
    reason: str,
    *,
    key_id: str | None = None,
    digest: str | None = None,
) -> EvaluationVerification:
    return EvaluationVerification(
        ok=False,
        reason=reason,
        key_id=key_id,
        payload_sha256=digest,
    )


def _validate_receipt_schema(
    document: Mapping[str, Any],
    *,
    now: datetime,
) -> str | None:
    if frozenset(document.keys()) != _RECEIPT_FIELDS:
        return "evaluation_receipt_fields_mismatch"
    signature = document.get(SIGNATURE_FIELD)
    if (
        not isinstance(signature, Mapping)
        or frozenset(signature.keys()) != _SIGNATURE_FIELDS
    ):
        return "evaluation_signature_fields_mismatch"
    if document.get("schema_version") != EVALUATION_SCHEMA_VERSION:
        return "evaluation_schema_version_mismatch"
    if document.get("purpose") != EVALUATION_PURPOSE:
        return "evaluation_purpose_mismatch"
    if not _is_sha256(document.get("oracle_fingerprint")):
        return "oracle_fingerprint_invalid"
    for field in _DIGEST_FIELDS:
        if not _is_sha256(document.get(field)):
            return f"{field}_invalid"
    if not _is_score(document.get("score")):
        return "evaluation_score_invalid"
    run_id = document.get("run_id")
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        return "evaluation_run_id_invalid"
    issued_at = _parse_utc_timestamp(document.get("issued_at"))
    if issued_at is None:
        return "evaluation_issued_at_invalid"
    expires_at = _parse_utc_timestamp(document.get("expires_at"))
    if expires_at is None:
        return "evaluation_expires_at_invalid"
    if expires_at <= issued_at:
        return "evaluation_time_order_invalid"
    if now < issued_at:
        return "evaluation_not_yet_valid"
    if now >= expires_at:
        return "evaluation_expired"
    nonce = document.get("nonce")
    if not isinstance(nonce, str) or _NONCE_RE.fullmatch(nonce) is None:
        return "evaluation_nonce_invalid"
    return None


def _validate_live_context(context: Mapping[str, Any]) -> str | None:
    if frozenset(context.keys()) != _LIVE_CONTEXT_FIELDS:
        return "evaluation_live_context_fields_mismatch"
    if not _is_sha256(context.get("oracle_fingerprint")):
        return "evaluation_live_context_invalid"
    for field in _DIGEST_FIELDS:
        if not _is_sha256(context.get(field)):
            return "evaluation_live_context_invalid"
    if not _is_score(context.get("score")):
        return "evaluation_live_context_invalid"
    run_id = context.get("run_id")
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        return "evaluation_live_context_invalid"
    return None


def verify_evaluation_receipt(
    document: Mapping[str, Any],
    *,
    trust_root: OperatorTrustRoot,
    live_context: Mapping[str, Any] | None,
    live_oracle_fingerprint: str,
    now: datetime | None = None,
) -> EvaluationVerification:
    """Verify a strict signed receipt against independently measured live context."""
    if not isinstance(document, Mapping):
        return _failure("evaluation_receipt_required")
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        return _failure("evaluation_verification_time_must_be_utc")
    checked_at = checked_at.astimezone(timezone.utc)

    schema_error = _validate_receipt_schema(document, now=checked_at)
    if schema_error is not None:
        return _failure(schema_error)
    if not isinstance(live_context, Mapping):
        return _failure("evaluation_live_context_required")
    context_error = _validate_live_context(live_context)
    if context_error is not None:
        return _failure(context_error)
    if not _is_sha256(live_oracle_fingerprint):
        return _failure("live_oracle_fingerprint_invalid")
    if document.get("oracle_fingerprint") != live_oracle_fingerprint:
        return _failure("evaluation_live_oracle_fingerprint_mismatch")
    for field in _LIVE_CONTEXT_FIELDS:
        if document.get(field) != live_context.get(field):
            return _failure(f"evaluation_live_{field}_mismatch")

    signed = trust_root.verify_document(
        document,
        required_purpose=EVALUATION_PURPOSE,
    )
    if not signed.ok:
        return _failure(
            f"evaluation_{signed.reason}",
            key_id=signed.key_id,
            digest=signed.payload_sha256,
        )
    try:
        scope_id = evaluation_scope_id(document)
    except (KeyError, TypeError, ValueError):
        return _failure(
            "evaluation_scope_invalid",
            key_id=signed.key_id,
            digest=signed.payload_sha256,
        )
    bindings = tuple(
        (field, str(document[field])) for field in _SCOPE_BINDING_FIELDS
    )
    return EvaluationVerification(
        ok=True,
        reason="external_evaluation_receipt_valid",
        key_id=signed.key_id,
        payload_sha256=signed.payload_sha256,
        scope_id=scope_id,
        score=float(document["score"]),
        nonce=str(document["nonce"]),
        run_id=str(document["run_id"]),
        scope_bindings=bindings,
    )


@dataclass(frozen=True)
class RatchetResult:
    """Result of consuming one already-verified receipt."""

    allowed: bool
    reason: str
    scope_id: str | None
    score: float | None
    baseline_before: float | None
    baseline_after: float | None


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    """Serialize ratchet state transitions across local processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        if os.name == "nt":  # pragma: no cover - exercised on the Windows host
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


class EvaluationRatchetStore:
    """Atomically persisted, replay-rejecting baselines keyed by evaluation scope."""

    def __init__(
        self,
        root: Path | str,
        *,
        oracle_fingerprint: str,
        trust_root: OperatorTrustRoot | None = None,
    ) -> None:
        if not _is_sha256(oracle_fingerprint):
            raise ValueError("oracle_fingerprint must be a lowercase SHA-256 digest")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "evaluation_ratchet_v1.json"
        self.nonce_dir = self.root / "evaluation_nonces"
        self.lock_path = self.root / ".evaluation_ratchet.lock"
        self.oracle_fingerprint = oracle_fingerprint
        self.trust_root = trust_root

    def _empty_state(self) -> dict[str, Any]:
        return {
            "schema_version": RATCHET_STATE_SCHEMA_VERSION,
            "oracle_fingerprint": self.oracle_fingerprint,
            "scopes": {},
        }

    def _validate_state(self, state: Any) -> str | None:
        if not isinstance(state, dict) or frozenset(state.keys()) != _STATE_FIELDS:
            return "evaluation_state_fields_mismatch"
        if state.get("schema_version") != RATCHET_STATE_SCHEMA_VERSION:
            return "evaluation_state_schema_mismatch"
        if state.get("oracle_fingerprint") != self.oracle_fingerprint:
            return "evaluation_state_oracle_mismatch"
        scopes = state.get("scopes")
        if not isinstance(scopes, dict):
            return "evaluation_state_scopes_invalid"
        for scope_id, entry in scopes.items():
            if not _is_sha256(scope_id):
                return "evaluation_state_scope_id_invalid"
            if (
                not isinstance(entry, dict)
                or frozenset(entry.keys()) != _SCOPE_STATE_FIELDS
            ):
                return "evaluation_state_scope_fields_mismatch"
            if entry.get("scope_id") != scope_id:
                return "evaluation_state_scope_binding_mismatch"
            for field in _SCOPE_BINDING_FIELDS:
                if not _is_sha256(entry.get(field)):
                    return "evaluation_state_scope_binding_invalid"
            if evaluation_scope_id(entry) != scope_id:
                return "evaluation_state_scope_digest_mismatch"
            if not _is_score(entry.get("baseline")):
                return "evaluation_state_baseline_invalid"
            if not _is_sha256(entry.get("last_receipt_payload_sha256")):
                return "evaluation_state_receipt_digest_invalid"
            receipt = entry.get("last_receipt")
            if not isinstance(receipt, Mapping):
                return "evaluation_state_receipt_missing"
            issued_at = _parse_utc_timestamp(receipt.get("issued_at"))
            if issued_at is None:
                return "evaluation_state_receipt_invalid"
            if _validate_receipt_schema(receipt, now=issued_at) is not None:
                return "evaluation_state_receipt_invalid"
            if self.trust_root is None:
                return "evaluation_state_authenticator_missing"
            signed = self.trust_root.verify_document(
                receipt,
                required_purpose=EVALUATION_PURPOSE,
            )
            if signed.ok is not True:
                return "evaluation_state_receipt_signature_invalid"
            if signed.payload_sha256 != entry.get("last_receipt_payload_sha256"):
                return "evaluation_state_receipt_digest_mismatch"
            if receipt.get("oracle_fingerprint") != self.oracle_fingerprint:
                return "evaluation_state_receipt_oracle_mismatch"
            if evaluation_scope_id(receipt) != scope_id:
                return "evaluation_state_receipt_scope_mismatch"
            if float(receipt.get("score")) != float(entry.get("baseline")):
                return "evaluation_state_baseline_not_receipt_attested"
            if receipt.get("run_id") != entry.get("last_run_id"):
                return "evaluation_state_run_id_mismatch"
            for field in _SCOPE_BINDING_FIELDS:
                if receipt.get(field) != entry.get(field):
                    return "evaluation_state_receipt_binding_mismatch"
            run_id = entry.get("last_run_id")
            if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
                return "evaluation_state_run_id_invalid"
            if _parse_utc_timestamp(entry.get("updated_at")) is None:
                return "evaluation_state_timestamp_invalid"
        return None

    def _load_state(self) -> tuple[dict[str, Any] | None, str | None]:
        if not self.state_path.exists():
            return self._empty_state(), None
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None, "evaluation_state_unreadable"
        error = self._validate_state(state)
        if error is not None:
            return None, error
        return state, None

    def _write_state_atomic(self, state: Mapping[str, Any]) -> None:
        payload = _canonical_bytes(state) + b"\n"
        fd, temp_name = tempfile.mkstemp(
            prefix=".evaluation_ratchet.",
            suffix=".tmp",
            dir=str(self.root),
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.state_path)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    def _claim_nonce(self, verified: EvaluationVerification) -> bool:
        assert verified.key_id is not None
        assert verified.nonce is not None
        assert verified.payload_sha256 is not None
        assert verified.scope_id is not None
        self.nonce_dir.mkdir(parents=True, exist_ok=True)
        claim_id = hashlib.sha256(
            f"{verified.key_id}|{verified.nonce}".encode("utf-8")
        ).hexdigest()
        claim_path = self.nonce_dir / f"{claim_id}.json"
        claim = {
            "schema_version": NONCE_CLAIM_SCHEMA_VERSION,
            "key_id": verified.key_id,
            "nonce": verified.nonce,
            "receipt_payload_sha256": verified.payload_sha256,
            "scope_id": verified.scope_id,
        }
        try:
            with claim_path.open("x", encoding="utf-8") as handle:
                handle.write(_canonical_bytes(claim).decode("utf-8") + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            return False
        return True

    def apply(
        self,
        *,
        receipt: Mapping[str, Any],
        live_context: Mapping[str, Any] | None,
    ) -> RatchetResult:
        """Verify live bindings at this public boundary, then consume a receipt.

        Callers cannot pass an ``EvaluationVerification`` as authority. Both
        mappings are detached before verification so a mutable/custom mapping
        cannot change between the live-binding check and persistence. The
        caller remains responsible for measuring ``live_context`` independently;
        this cooperative Python boundary cannot prove the provenance of those
        measurements.
        """
        if self.trust_root is None:
            return RatchetResult(
                False,
                "evaluation_state_authenticator_missing",
                None,
                None,
                None,
                None,
            )
        try:
            receipt_snapshot = json.loads(_canonical_bytes(receipt))
            context_snapshot = json.loads(_canonical_bytes(live_context))
        except Exception:
            return RatchetResult(
                False,
                "evaluation_receipt_or_live_context_unreadable",
                None,
                None,
                None,
                None,
            )
        if not isinstance(receipt_snapshot, dict) or not isinstance(
            context_snapshot,
            dict,
        ):
            return RatchetResult(
                False,
                "evaluation_receipt_or_live_context_unreadable",
                None,
                None,
                None,
                None,
            )
        verified = verify_evaluation_receipt(
            receipt_snapshot,
            trust_root=self.trust_root,
            live_context=context_snapshot,
            live_oracle_fingerprint=self.oracle_fingerprint,
        )
        if verified.ok is not True:
            return RatchetResult(
                False,
                verified.reason,
                verified.scope_id,
                verified.score,
                None,
                None,
            )
        return self._apply_verified(verified, receipt=receipt_snapshot)

    def _apply_verified(
        self,
        verified: EvaluationVerification,
        *,
        receipt: Mapping[str, Any],
    ) -> RatchetResult:
        """Consume one internally verified receipt and atomically ratchet its scope.

        ``EvaluationVerification`` is an audit value, not an unforgeable
        capability. Consequently this internal boundary revalidates a detached
        receipt snapshot and reconstructs every field that may affect state.
        Merely constructing or replacing fields on a verification dataclass
        cannot select a nonce, run, score, or comparison scope.

        Nonce consumption is deliberately at-most-once. If persistence becomes
        uncertain after a nonce is claimed, the nonce remains consumed and an
        external evaluator must issue a fresh receipt; availability never
        reopens replay.
        """
        scope_hint = (
            verified.scope_id
            if type(verified) is EvaluationVerification
            else None
        )
        score_hint = (
            verified.score
            if type(verified) is EvaluationVerification
            else None
        )
        if (
            type(verified) is not EvaluationVerification
            or verified.ok is not True
            or verified.scope_id is None
            or verified.score is None
            or type(verified.score) is not float
            or not _is_score(verified.score)
            or verified.payload_sha256 is None
            or verified.key_id is None
            or verified.nonce is None
            or verified.run_id is None
        ):
            return RatchetResult(
                False,
                "verified_evaluation_receipt_required",
                scope_hint,
                score_hint,
                None,
                None,
            )
        try:
            receipt_snapshot = json.loads(_canonical_bytes(receipt))
        except Exception:
            receipt_snapshot = None
        if not isinstance(receipt_snapshot, dict):
            return RatchetResult(
                False,
                "verified_evaluation_receipt_changed",
                verified.scope_id,
                verified.score,
                None,
                None,
            )
        schema_error = _validate_receipt_schema(
            receipt_snapshot,
            now=datetime.now(timezone.utc),
        )
        if schema_error is not None:
            return RatchetResult(
                False,
                schema_error,
                verified.scope_id,
                verified.score,
                None,
                None,
            )
        if self.trust_root is None:
            return RatchetResult(
                False,
                "evaluation_state_authenticator_missing",
                verified.scope_id,
                verified.score,
                None,
                None,
            )
        signed = self.trust_root.verify_document(
            receipt_snapshot,
            required_purpose=EVALUATION_PURPOSE,
        )
        if (
            signed.ok is not True
            or signed.key_id is None
            or signed.payload_sha256 is None
        ):
            return RatchetResult(
                False,
                "verified_evaluation_signature_invalid",
                verified.scope_id,
                verified.score,
                None,
                None,
            )
        try:
            receipt_scope = evaluation_scope_id(receipt_snapshot)
        except (KeyError, TypeError, ValueError):
            receipt_scope = None
        receipt_score = receipt_snapshot.get("score")
        receipt_nonce = receipt_snapshot.get("nonce")
        receipt_run_id = receipt_snapshot.get("run_id")
        receipt_bindings = tuple(
            (field, str(receipt_snapshot[field]))
            for field in _SCOPE_BINDING_FIELDS
        )
        if (
            receipt_snapshot.get("oracle_fingerprint") != self.oracle_fingerprint
            or receipt_scope != verified.scope_id
            or not _is_score(receipt_score)
            or float(receipt_score) != verified.score
            or signed.key_id != verified.key_id
            or signed.payload_sha256 != verified.payload_sha256
            or receipt_nonce != verified.nonce
            or receipt_run_id != verified.run_id
            or receipt_bindings != verified.scope_bindings
            or verified.reason != "external_evaluation_receipt_valid"
        ):
            return RatchetResult(
                False,
                "verified_evaluation_binding_mismatch",
                verified.scope_id,
                verified.score,
                None,
                None,
            )

        # From this point onward use only values reconstructed from the signed
        # detached snapshot.  The caller-provided verification object has no
        # independent state-selection authority.
        bound = EvaluationVerification(
            ok=True,
            reason="external_evaluation_receipt_valid",
            key_id=signed.key_id,
            payload_sha256=signed.payload_sha256,
            scope_id=receipt_scope,
            score=float(receipt_score),
            nonce=str(receipt_nonce),
            run_id=str(receipt_run_id),
            scope_bindings=receipt_bindings,
        )

        with _exclusive_file_lock(self.lock_path):
            state, state_error = self._load_state()
            if state_error is not None or state is None:
                return RatchetResult(
                    False,
                    state_error or "evaluation_state_invalid",
                    verified.scope_id,
                    verified.score,
                    None,
                    None,
                )
            if not self._claim_nonce(bound):
                return RatchetResult(
                    False,
                    "evaluation_receipt_replay",
                    bound.scope_id,
                    bound.score,
                    None,
                    None,
                )

            scopes = state["scopes"]
            prior = scopes.get(bound.scope_id)
            baseline_before = (
                float(prior["baseline"]) if isinstance(prior, dict) else None
            )
            if (
                baseline_before is not None
                and bound.score < baseline_before - 1e-9
            ):
                return RatchetResult(
                    False,
                    "evaluation_regression_blocked",
                    bound.scope_id,
                    bound.score,
                    baseline_before,
                    baseline_before,
                )

            bindings = dict(bound.scope_bindings)
            if frozenset(bindings.keys()) != frozenset(_SCOPE_BINDING_FIELDS):
                return RatchetResult(
                    False,
                    "verified_evaluation_scope_bindings_invalid",
                    bound.scope_id,
                    bound.score,
                    baseline_before,
                    baseline_before,
                )
            baseline_after = max(
                bound.score,
                baseline_before if baseline_before is not None else bound.score,
            )
            updated_at = datetime.now(timezone.utc).replace(
                microsecond=0
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            scopes[bound.scope_id] = {
                "scope_id": bound.scope_id,
                **bindings,
                "baseline": baseline_after,
                "last_receipt_payload_sha256": bound.payload_sha256,
                "last_receipt": receipt_snapshot,
                "last_run_id": bound.run_id,
                "updated_at": updated_at,
            }
            try:
                self._write_state_atomic(state)
            except OSError:
                return RatchetResult(
                    False,
                    "evaluation_state_persistence_failed",
                    bound.scope_id,
                    bound.score,
                    baseline_before,
                    baseline_before,
                )
            return RatchetResult(
                True,
                "evaluation_holds_line",
                bound.scope_id,
                bound.score,
                baseline_before,
                baseline_after,
            )

    def baseline_for(self, scope_id: str) -> float | None:
        state, error = self._load_state()
        if error is not None or state is None:
            return None
        entry = state["scopes"].get(scope_id)
        return float(entry["baseline"]) if isinstance(entry, dict) else None

    @property
    def baseline(self) -> float | None:
        """Compatibility view: a scalar only when exactly one scope exists."""
        state, error = self._load_state()
        if error is not None or state is None:
            return None
        entries = list(state["scopes"].values())
        if len(entries) != 1:
            return None
        return float(entries[0]["baseline"])

    def status(self) -> dict[str, Any]:
        state, error = self._load_state()
        if error is not None or state is None:
            return {
                "state_ok": False,
                "state_error": error or "evaluation_state_invalid",
                "scope_count": 0,
                "baselines": {},
                "consumed_nonce_count": 0,
            }
        nonce_count = (
            sum(1 for path in self.nonce_dir.glob("*.json") if path.is_file())
            if self.nonce_dir.exists()
            else 0
        )
        return {
            "state_ok": True,
            "state_error": None,
            "scope_count": len(state["scopes"]),
            "baselines": {
                scope_id: float(entry["baseline"])
                for scope_id, entry in state["scopes"].items()
            },
            "consumed_nonce_count": nonce_count,
        }
