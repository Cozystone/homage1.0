"""Immutable, base-bound graph mutation proposals and lifecycle evidence.

This module does not mutate the shipped graph.  It turns additions and
retractions into one deterministic, write-once proposal whose identity is bound
to the exact shipped-store base digest.  Lifecycle receipts deliberately keep
mechanism separate from authority:

``detected -> proposed -> staged`` all state that production is unchanged.
``applied`` is accepted only after an operator-signed promotion journal has
reached ``COMMITTED`` and binds this exact mutation manifest.

The files are tamper-evident, not tamper-proof.  Operator signatures and the
fixed landing boundary remain the production authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping

from packages.cognitive_core.canonical import canonical_digest, canonical_json

from .graph_paths import (
    SHIPPED_STORE_TARGET_ID,
    create_mutation_batch_root,
    mutation_batch_root,
    same_graph_path,
)


MANIFEST_SCHEMA_VERSION = "atanor.graph-scale.mutation-batch.v1"
SEAL_SCHEMA_VERSION = "atanor.graph-scale.mutation-batch-seal.v1"
RECEIPT_SCHEMA_VERSION = "atanor.graph-scale.mutation-receipt.v1"
BASE_DIGEST_ALGORITHM = "atanor.store-tree-sha256.v1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BATCH_ID_RE = re.compile(r"^gmb_[0-9a-f]{32}$")
_PRODUCER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127}$")
_RECEIPT_FILE_RE = re.compile(
    r"^(?P<sequence>\d{4})\."
    r"(?P<stage>detected|proposed|staged|applied)\.json$"
)

_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "batch_id",
        "producer_id",
        "producer_run_id",
        "created_at",
        "target_store_id",
        "base_digest_algorithm",
        "base_digest_sha256",
        "additions",
        "retractions",
        "counts",
        "production_store_mutated",
    }
)
_ADDITION_FIELDS = frozenset(
    {"subject", "predicate", "object", "provenance", "source_refs"}
)
_RETRACTION_FIELDS = frozenset(
    {"subject", "predicate", "object", "reason", "evidence_refs"}
)
_SEAL_FIELDS = frozenset(
    {"schema_version", "batch_id", "manifest_sha256", "sealed_at"}
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "batch_id",
        "manifest_sha256",
        "sequence",
        "stage",
        "occurred_at",
        "previous_receipt_sha256",
        "evidence",
        "production_store_mutated",
    }
)
_STAGE_ORDER = ("detected", "proposed", "staged", "applied")


class MutationBatchError(ValueError):
    """The immutable mutation-batch contract was violated."""


class MutationStage(str, Enum):
    DETECTED = "detected"
    PROPOSED = "proposed"
    STAGED = "staged"
    APPLIED = "applied"


@dataclass(frozen=True, order=True)
class GraphAddition:
    subject: str
    predicate: str
    object: str
    provenance: str
    source_refs: tuple[str, ...] = ()


@dataclass(frozen=True, order=True)
class GraphRetraction:
    subject: str
    predicate: str
    object: str
    reason: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class MutationBatchRef:
    batch_id: str
    root: Path
    manifest_path: Path
    seal_path: Path
    manifest_sha256: str
    base_digest_sha256: str
    addition_count: int
    retraction_count: int


@dataclass(frozen=True)
class BatchValidation:
    ok: bool
    errors: tuple[str, ...]
    batch_id: str | None
    manifest_sha256: str | None
    latest_stage: MutationStage | None


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def _strict_json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {token}")
            ),
        )
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise MutationBatchError(f"{label} is not strict JSON") from exc
    if type(value) is not dict:
        raise MutationBatchError(f"{label} must be a JSON object")
    return value


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _required_text(value: Any, *, field: str, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\x00" in value
        or len(value) > maximum
    ):
        raise MutationBatchError(f"{field} must be non-blank portable text")
    return value


def _portable_refs(
    values: Any,
    *,
    field: str,
) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise MutationBatchError(f"{field} must be a sequence")
    normalized = tuple(
        _required_text(value, field=field, maximum=1024) for value in values
    )
    if len(set(normalized)) != len(normalized):
        raise MutationBatchError(f"{field} contains duplicates")
    return tuple(sorted(normalized))


def _normalize_addition(value: GraphAddition) -> dict[str, Any]:
    if not isinstance(value, GraphAddition):
        raise MutationBatchError("additions must contain GraphAddition values")
    return {
        "subject": _required_text(value.subject, field="addition subject"),
        "predicate": _required_text(value.predicate, field="addition predicate"),
        "object": _required_text(value.object, field="addition object"),
        "provenance": _required_text(
            value.provenance,
            field="addition provenance",
        ),
        "source_refs": list(
            _portable_refs(value.source_refs, field="addition source_refs")
        ),
    }


def _normalize_retraction(value: GraphRetraction) -> dict[str, Any]:
    if not isinstance(value, GraphRetraction):
        raise MutationBatchError(
            "retractions must contain GraphRetraction values"
        )
    return {
        "subject": _required_text(value.subject, field="retraction subject"),
        "predicate": _required_text(
            value.predicate,
            field="retraction predicate",
        ),
        "object": _required_text(value.object, field="retraction object"),
        "reason": _required_text(value.reason, field="retraction reason"),
        "evidence_refs": list(
            _portable_refs(
                value.evidence_refs,
                field="retraction evidence_refs",
            )
        ),
    }


def _triple(value: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(value["subject"]),
        str(value["predicate"]),
        str(value["object"]),
    )


def _normalized_mutations(
    additions: Iterable[GraphAddition],
    retractions: Iterable[GraphRetraction],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_additions = [_normalize_addition(value) for value in additions]
    normalized_retractions = [
        _normalize_retraction(value) for value in retractions
    ]
    if not normalized_additions and not normalized_retractions:
        raise MutationBatchError("a mutation batch cannot be empty")

    addition_triples = [_triple(value) for value in normalized_additions]
    retraction_triples = [_triple(value) for value in normalized_retractions]
    if len(set(addition_triples)) != len(addition_triples):
        raise MutationBatchError("duplicate addition triple")
    if len(set(retraction_triples)) != len(retraction_triples):
        raise MutationBatchError("duplicate retraction triple")
    if set(addition_triples) & set(retraction_triples):
        raise MutationBatchError(
            "one triple cannot be both added and retracted"
        )

    normalized_additions.sort(key=canonical_json)
    normalized_retractions.sort(key=canonical_json)
    return normalized_additions, normalized_retractions


def _identity_payload(
    *,
    producer_id: str,
    producer_run_id: str,
    base_digest_sha256: str,
    additions: list[dict[str, Any]],
    retractions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "producer_id": producer_id,
        "producer_run_id": producer_run_id,
        "target_store_id": SHIPPED_STORE_TARGET_ID,
        "base_digest_algorithm": BASE_DIGEST_ALGORITHM,
        "base_digest_sha256": base_digest_sha256,
        "additions": additions,
        "retractions": retractions,
    }


def _batch_id(identity: Mapping[str, Any]) -> str:
    return f"gmb_{canonical_digest(identity)[:32]}"


def _exclusive_write(path: Path, value: Mapping[str, Any]) -> None:
    raw = _canonical_bytes(value)
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise MutationBatchError(
            f"immutable mutation batch file already exists: {path.name}"
        ) from exc


def _sync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def create_mutation_batch(
    *,
    producer_id: str,
    producer_run_id: str,
    base_digest_sha256: str,
    additions: Iterable[GraphAddition] = (),
    retractions: Iterable[GraphRetraction] = (),
    created_at: str | None = None,
    sealed_at: str | None = None,
    batches_root: str | Path | None = None,
) -> MutationBatchRef:
    """Create a deterministic, sealed, production-inert mutation proposal."""

    if (
        not isinstance(producer_id, str)
        or _PRODUCER_ID_RE.fullmatch(producer_id) is None
    ):
        raise MutationBatchError("producer_id is invalid")
    if (
        not isinstance(producer_run_id, str)
        or _RUN_ID_RE.fullmatch(producer_run_id) is None
    ):
        raise MutationBatchError("producer_run_id is invalid")
    if not _is_sha256(base_digest_sha256):
        raise MutationBatchError("base_digest_sha256 is invalid")
    created = _utc_now() if created_at is None else created_at
    sealed = _utc_now() if sealed_at is None else sealed_at
    if not _valid_timestamp(created):
        raise MutationBatchError("created_at is invalid")
    if not _valid_timestamp(sealed):
        raise MutationBatchError("sealed_at is invalid")

    normalized_additions, normalized_retractions = _normalized_mutations(
        additions,
        retractions,
    )
    identity = _identity_payload(
        producer_id=producer_id,
        producer_run_id=producer_run_id,
        base_digest_sha256=base_digest_sha256,
        additions=normalized_additions,
        retractions=normalized_retractions,
    )
    batch_id = _batch_id(identity)
    manifest = {
        **identity,
        "batch_id": batch_id,
        "created_at": created,
        "counts": {
            "additions": len(normalized_additions),
            "retractions": len(normalized_retractions),
        },
        "production_store_mutated": False,
    }
    manifest_raw = _canonical_bytes(manifest)
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    seal = {
        "schema_version": SEAL_SCHEMA_VERSION,
        "batch_id": batch_id,
        "manifest_sha256": manifest_sha256,
        "sealed_at": sealed,
    }

    try:
        root = create_mutation_batch_root(
            batch_id,
            batches_root=batches_root,
        )
    except (FileExistsError, ValueError) as exc:
        raise MutationBatchError(
            "mutation batch root already exists or is unsafe"
        ) from exc
    manifest_path = root / "manifest.json"
    seal_path = root / "seal.json"
    try:
        _exclusive_write(manifest_path, manifest)
        _exclusive_write(seal_path, seal)
        (root / "receipts").mkdir(exist_ok=False)
        _sync_directory(root)
        _sync_directory(root.parent)
    except Exception:
        # A crash or failed write leaves the unique partial root visible.  It is
        # deliberately never repaired or overwritten automatically.
        raise

    validation = validate_mutation_batch(
        root,
        expected_base_digest_sha256=base_digest_sha256,
    )
    if not validation.ok:
        raise MutationBatchError(
            "new mutation batch failed validation: "
            + "; ".join(validation.errors)
        )
    return MutationBatchRef(
        batch_id=batch_id,
        root=root,
        manifest_path=manifest_path,
        seal_path=seal_path,
        manifest_sha256=manifest_sha256,
        base_digest_sha256=base_digest_sha256,
        addition_count=len(normalized_additions),
        retraction_count=len(normalized_retractions),
    )


def _validate_manifest(
    manifest: dict[str, Any],
    *,
    root_batch_id: str,
    expected_base_digest_sha256: str | None,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if frozenset(manifest) != _MANIFEST_FIELDS:
        return manifest, ["manifest fields mismatch"]
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append("manifest schema version invalid")
    if manifest.get("batch_id") != root_batch_id:
        errors.append("manifest batch id mismatch")
    producer_id = manifest.get("producer_id")
    if (
        not isinstance(producer_id, str)
        or _PRODUCER_ID_RE.fullmatch(producer_id) is None
    ):
        errors.append("manifest producer id invalid")
    producer_run_id = manifest.get("producer_run_id")
    if (
        not isinstance(producer_run_id, str)
        or _RUN_ID_RE.fullmatch(producer_run_id) is None
    ):
        errors.append("manifest producer run id invalid")
    if not _valid_timestamp(manifest.get("created_at")):
        errors.append("manifest timestamp invalid")
    if manifest.get("target_store_id") != SHIPPED_STORE_TARGET_ID:
        errors.append("manifest target store invalid")
    if manifest.get("base_digest_algorithm") != BASE_DIGEST_ALGORITHM:
        errors.append("manifest base digest algorithm invalid")
    base_digest = manifest.get("base_digest_sha256")
    if not _is_sha256(base_digest):
        errors.append("manifest base digest invalid")
    if (
        expected_base_digest_sha256 is not None
        and base_digest != expected_base_digest_sha256
    ):
        errors.append("manifest base digest does not match expected base")
    if manifest.get("production_store_mutated") is not False:
        errors.append("mutation proposal claims production mutation")

    additions_raw = manifest.get("additions")
    retractions_raw = manifest.get("retractions")
    if not isinstance(additions_raw, list):
        errors.append("manifest additions invalid")
        additions_raw = []
    if not isinstance(retractions_raw, list):
        errors.append("manifest retractions invalid")
        retractions_raw = []

    additions: list[dict[str, Any]] = []
    for index, value in enumerate(additions_raw):
        if type(value) is not dict or frozenset(value) != _ADDITION_FIELDS:
            errors.append(f"addition {index} fields invalid")
            continue
        try:
            normalized = _normalize_addition(
                GraphAddition(
                    subject=value.get("subject"),
                    predicate=value.get("predicate"),
                    object=value.get("object"),
                    provenance=value.get("provenance"),
                    source_refs=tuple(value.get("source_refs", ())),
                )
            )
        except (MutationBatchError, TypeError):
            errors.append(f"addition {index} invalid")
            continue
        if normalized != value:
            errors.append(f"addition {index} is not normalized")
        additions.append(normalized)

    retractions: list[dict[str, Any]] = []
    for index, value in enumerate(retractions_raw):
        if type(value) is not dict or frozenset(value) != _RETRACTION_FIELDS:
            errors.append(f"retraction {index} fields invalid")
            continue
        try:
            normalized = _normalize_retraction(
                GraphRetraction(
                    subject=value.get("subject"),
                    predicate=value.get("predicate"),
                    object=value.get("object"),
                    reason=value.get("reason"),
                    evidence_refs=tuple(value.get("evidence_refs", ())),
                )
            )
        except (MutationBatchError, TypeError):
            errors.append(f"retraction {index} invalid")
            continue
        if normalized != value:
            errors.append(f"retraction {index} is not normalized")
        retractions.append(normalized)

    try:
        normalized_additions, normalized_retractions = _normalized_mutations(
            [
                GraphAddition(
                    subject=value["subject"],
                    predicate=value["predicate"],
                    object=value["object"],
                    provenance=value["provenance"],
                    source_refs=tuple(value["source_refs"]),
                )
                for value in additions
            ],
            [
                GraphRetraction(
                    subject=value["subject"],
                    predicate=value["predicate"],
                    object=value["object"],
                    reason=value["reason"],
                    evidence_refs=tuple(value["evidence_refs"]),
                )
                for value in retractions
            ],
        )
    except (MutationBatchError, KeyError):
        errors.append("manifest mutations overlap, duplicate, or are empty")
        normalized_additions, normalized_retractions = additions, retractions
    if additions_raw != normalized_additions:
        errors.append("manifest additions order invalid")
    if retractions_raw != normalized_retractions:
        errors.append("manifest retractions order invalid")

    counts = manifest.get("counts")
    if (
        type(counts) is not dict
        or frozenset(counts) != {"additions", "retractions"}
        or type(counts.get("additions")) is not int
        or type(counts.get("retractions")) is not int
        or counts.get("additions") != len(additions_raw)
        or counts.get("retractions") != len(retractions_raw)
    ):
        errors.append("manifest mutation counts invalid")

    if (
        isinstance(producer_id, str)
        and isinstance(producer_run_id, str)
        and isinstance(base_digest, str)
    ):
        expected_id = _batch_id(
            _identity_payload(
                producer_id=producer_id,
                producer_run_id=producer_run_id,
                base_digest_sha256=base_digest,
                additions=normalized_additions,
                retractions=normalized_retractions,
            )
        )
        if manifest.get("batch_id") != expected_id:
            errors.append("manifest identity digest mismatch")
    return manifest, errors


def _validated_receipts(
    receipts_root: Path,
    *,
    batch_id: str,
    manifest_sha256: str,
) -> tuple[MutationStage | None, list[str]]:
    errors: list[str] = []
    if not receipts_root.is_dir() or receipts_root.is_symlink():
        return None, ["receipt directory is unavailable or linked"]
    entries = sorted(receipts_root.iterdir(), key=lambda path: path.name)
    previous_digest: str | None = None
    latest_stage: MutationStage | None = None
    for expected_sequence, path in enumerate(entries, start=1):
        match = _RECEIPT_FILE_RE.fullmatch(path.name)
        if match is None or not path.is_file() or path.is_symlink():
            errors.append("receipt directory contains an invalid entry")
            continue
        if int(match.group("sequence")) != expected_sequence:
            errors.append("receipt sequence is not contiguous")
        try:
            raw = path.read_bytes()
            receipt = _strict_json_object(raw, label="lifecycle receipt")
        except (OSError, MutationBatchError):
            errors.append(f"receipt {path.name} is unreadable")
            continue
        if raw != _canonical_bytes(receipt):
            errors.append(f"receipt {path.name} is not canonical JSON")
        if frozenset(receipt) != _RECEIPT_FIELDS:
            errors.append(f"receipt {path.name} fields mismatch")
            continue
        expected_stage = (
            _STAGE_ORDER[expected_sequence - 1]
            if expected_sequence <= len(_STAGE_ORDER)
            else None
        )
        stage = receipt.get("stage")
        if (
            receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION
            or receipt.get("batch_id") != batch_id
            or receipt.get("manifest_sha256") != manifest_sha256
            or type(receipt.get("sequence")) is not int
            or receipt.get("sequence") != expected_sequence
            or stage != match.group("stage")
            or stage != expected_stage
            or not _valid_timestamp(receipt.get("occurred_at"))
            or receipt.get("previous_receipt_sha256") != previous_digest
            or type(receipt.get("evidence")) is not dict
        ):
            errors.append(f"receipt {path.name} chain contract invalid")
        should_mutate = stage == MutationStage.APPLIED.value
        if receipt.get("production_store_mutated") is not should_mutate:
            errors.append(f"receipt {path.name} mutation truth invalid")
        previous_digest = hashlib.sha256(raw).hexdigest()
        try:
            latest_stage = MutationStage(str(stage))
        except ValueError:
            errors.append(f"receipt {path.name} stage invalid")
    if len(entries) > len(_STAGE_ORDER):
        errors.append("too many lifecycle receipts")
    return latest_stage, errors


def validate_mutation_batch(
    root: str | Path,
    *,
    expected_base_digest_sha256: str | None = None,
) -> BatchValidation:
    """Validate canonical bytes, seal, identity, and receipt chain."""

    errors: list[str] = []
    batch_root = Path(root)
    batch_id = batch_root.name if _BATCH_ID_RE.fullmatch(batch_root.name) else None
    if (
        expected_base_digest_sha256 is not None
        and not _is_sha256(expected_base_digest_sha256)
    ):
        errors.append("expected base digest is invalid")
    if batch_id is None:
        errors.append("batch root name is invalid")
    try:
        if batch_id is not None:
            expected_root = mutation_batch_root(
                batch_id,
                batches_root=batch_root.parent,
            )
            if not same_graph_path(expected_root, batch_root):
                errors.append("batch root escapes its parent")
    except ValueError:
        errors.append("batch root is unsafe")
    if not batch_root.is_dir() or batch_root.is_symlink():
        errors.append("batch root is unavailable or linked")
        return BatchValidation(False, tuple(errors), batch_id, None, None)
    allowed_entries = {"manifest.json", "seal.json", "receipts"}
    try:
        if {path.name for path in batch_root.iterdir()} != allowed_entries:
            errors.append("batch root entries mismatch")
    except OSError:
        errors.append("batch root cannot be enumerated")

    manifest: dict[str, Any] | None = None
    manifest_sha256: str | None = None
    try:
        manifest_raw = (batch_root / "manifest.json").read_bytes()
        manifest = _strict_json_object(manifest_raw, label="mutation manifest")
        manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
        if manifest_raw != _canonical_bytes(manifest):
            errors.append("manifest is not canonical JSON")
    except (OSError, MutationBatchError, TypeError, ValueError):
        errors.append("manifest is unreadable")
    if manifest is not None and batch_id is not None:
        _, manifest_errors = _validate_manifest(
            manifest,
            root_batch_id=batch_id,
            expected_base_digest_sha256=expected_base_digest_sha256,
        )
        errors.extend(manifest_errors)

    try:
        seal_raw = (batch_root / "seal.json").read_bytes()
        seal = _strict_json_object(seal_raw, label="mutation seal")
        if seal_raw != _canonical_bytes(seal):
            errors.append("seal is not canonical JSON")
        if (
            frozenset(seal) != _SEAL_FIELDS
            or seal.get("schema_version") != SEAL_SCHEMA_VERSION
            or seal.get("batch_id") != batch_id
            or seal.get("manifest_sha256") != manifest_sha256
            or not _valid_timestamp(seal.get("sealed_at"))
        ):
            errors.append("seal contract invalid")
    except (OSError, MutationBatchError, TypeError, ValueError):
        errors.append("seal is unreadable")

    latest_stage: MutationStage | None = None
    if batch_id is not None and manifest_sha256 is not None:
        latest_stage, receipt_errors = _validated_receipts(
            batch_root / "receipts",
            batch_id=batch_id,
            manifest_sha256=manifest_sha256,
        )
        errors.extend(receipt_errors)
    return BatchValidation(
        ok=not errors,
        errors=tuple(errors),
        batch_id=batch_id,
        manifest_sha256=manifest_sha256,
        latest_stage=latest_stage,
    )


def validate_sealed_manifest_bytes(
    manifest_raw: bytes,
    seal_raw: bytes,
    *,
    expected_base_digest_sha256: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Validate a self-contained manifest/seal pair embedded in a candidate."""

    manifest = _strict_json_object(
        manifest_raw,
        label="embedded mutation manifest",
    )
    if manifest_raw != _canonical_bytes(manifest):
        raise MutationBatchError(
            "embedded mutation manifest is not canonical JSON"
        )
    batch_id = manifest.get("batch_id")
    if not isinstance(batch_id, str) or _BATCH_ID_RE.fullmatch(batch_id) is None:
        raise MutationBatchError("embedded mutation batch id is invalid")
    _, errors = _validate_manifest(
        manifest,
        root_batch_id=batch_id,
        expected_base_digest_sha256=expected_base_digest_sha256,
    )
    if errors:
        raise MutationBatchError(
            "embedded mutation manifest is invalid: " + "; ".join(errors)
        )
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    seal = _strict_json_object(seal_raw, label="embedded mutation seal")
    if (
        seal_raw != _canonical_bytes(seal)
        or frozenset(seal) != _SEAL_FIELDS
        or seal.get("schema_version") != SEAL_SCHEMA_VERSION
        or seal.get("batch_id") != batch_id
        or seal.get("manifest_sha256") != manifest_sha256
        or not _valid_timestamp(seal.get("sealed_at"))
    ):
        raise MutationBatchError("embedded mutation seal is invalid")
    return manifest, manifest_sha256


def load_validated_mutation_batch(
    root: str | Path,
    *,
    expected_base_digest_sha256: str | None = None,
) -> tuple[MutationBatchRef, dict[str, Any], MutationStage | None]:
    """Load a detached manifest only after validating the full batch root."""

    validation = validate_mutation_batch(
        root,
        expected_base_digest_sha256=expected_base_digest_sha256,
    )
    if (
        not validation.ok
        or validation.batch_id is None
        or validation.manifest_sha256 is None
    ):
        raise MutationBatchError(
            "mutation batch is invalid: " + "; ".join(validation.errors)
        )
    batch_root = Path(root)
    manifest_path = batch_root / "manifest.json"
    seal_path = batch_root / "seal.json"
    manifest_raw = manifest_path.read_bytes()
    manifest, manifest_sha256 = validate_sealed_manifest_bytes(
        manifest_raw,
        seal_path.read_bytes(),
        expected_base_digest_sha256=expected_base_digest_sha256,
    )
    reference = MutationBatchRef(
        batch_id=validation.batch_id,
        root=batch_root,
        manifest_path=manifest_path,
        seal_path=seal_path,
        manifest_sha256=manifest_sha256,
        base_digest_sha256=manifest["base_digest_sha256"],
        addition_count=manifest["counts"]["additions"],
        retraction_count=manifest["counts"]["retractions"],
    )
    return reference, manifest, validation.latest_stage


def _load_valid_batch(root: str | Path) -> tuple[Path, dict[str, Any], str]:
    validation = validate_mutation_batch(root)
    if not validation.ok or validation.manifest_sha256 is None:
        raise MutationBatchError(
            "mutation batch is invalid: " + "; ".join(validation.errors)
        )
    batch_root = Path(root)
    manifest = _strict_json_object(
        (batch_root / "manifest.json").read_bytes(),
        label="mutation manifest",
    )
    return batch_root, manifest, validation.manifest_sha256


def record_lifecycle_receipt(
    root: str | Path,
    *,
    stage: Literal["detected", "proposed", "staged"],
    occurred_at: str | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> Path:
    """Append one non-production lifecycle transition to a valid batch."""

    if stage not in _STAGE_ORDER[:3]:
        raise MutationBatchError(
            "record_lifecycle_receipt accepts detected, proposed, or staged"
        )
    batch_root, manifest, manifest_sha256 = _load_valid_batch(root)
    validation = validate_mutation_batch(batch_root)
    next_index = (
        0
        if validation.latest_stage is None
        else _STAGE_ORDER.index(validation.latest_stage.value) + 1
    )
    if next_index >= 3 or _STAGE_ORDER[next_index] != stage:
        expected = (
            _STAGE_ORDER[next_index]
            if next_index < len(_STAGE_ORDER)
            else "no further stage"
        )
        raise MutationBatchError(
            f"invalid lifecycle transition; expected {expected}"
        )
    timestamp = _utc_now() if occurred_at is None else occurred_at
    if not _valid_timestamp(timestamp):
        raise MutationBatchError("receipt timestamp is invalid")
    evidence_value = {} if evidence is None else dict(evidence)
    try:
        _canonical_bytes(evidence_value)
    except (TypeError, ValueError) as exc:
        raise MutationBatchError("receipt evidence is not canonical JSON") from exc

    sequence = next_index + 1
    receipts_root = batch_root / "receipts"
    previous_sha256: str | None = None
    if sequence > 1:
        previous_stage = _STAGE_ORDER[sequence - 2]
        previous_path = (
            receipts_root / f"{sequence - 1:04d}.{previous_stage}.json"
        )
        previous_sha256 = hashlib.sha256(previous_path.read_bytes()).hexdigest()
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "batch_id": manifest["batch_id"],
        "manifest_sha256": manifest_sha256,
        "sequence": sequence,
        "stage": stage,
        "occurred_at": timestamp,
        "previous_receipt_sha256": previous_sha256,
        "evidence": evidence_value,
        "production_store_mutated": False,
    }
    path = receipts_root / f"{sequence:04d}.{stage}.json"
    _exclusive_write(path, receipt)
    _sync_directory(receipts_root)
    post = validate_mutation_batch(batch_root)
    if not post.ok or post.latest_stage is not MutationStage(stage):
        raise MutationBatchError(
            "lifecycle receipt failed post-write validation"
        )
    return path


def _canonical_promotion_payload(document: Mapping[str, Any]) -> bytes:
    payload = {
        key: value
        for key, value in document.items()
        if key != "operator_signature"
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _committed_evidence(
    *,
    manifest: Mapping[str, Any],
    manifest_sha256: str,
    committed_promotion: Mapping[str, Any],
) -> dict[str, Any]:
    required = {
        "swapped",
        "transaction_id",
        "swap_journal",
        "committed_event_sha256",
        "installed_digest_sha256",
        "recovery_digest_sha256",
        "promotion_payload_sha256",
        "mutation_batch_manifest_sha256",
    }
    if (
        not isinstance(committed_promotion, Mapping)
        or not required.issubset(committed_promotion)
        or committed_promotion.get("swapped") is not True
        or committed_promotion.get("mutation_batch_manifest_sha256")
        != manifest_sha256
    ):
        raise MutationBatchError(
            "committed promotion does not bind this mutation batch"
        )
    for field in (
        "transaction_id",
        "committed_event_sha256",
        "installed_digest_sha256",
        "recovery_digest_sha256",
        "promotion_payload_sha256",
        "mutation_batch_manifest_sha256",
    ):
        if not _is_sha256(committed_promotion.get(field)):
            raise MutationBatchError(
                f"committed promotion {field} is invalid"
            )
    if (
        committed_promotion.get("recovery_digest_sha256")
        != manifest.get("base_digest_sha256")
    ):
        raise MutationBatchError(
            "committed promotion recovery digest does not match batch base"
        )

    journal_root = Path(str(committed_promotion.get("swap_journal")))
    if (
        not journal_root.is_dir()
        or journal_root.is_symlink()
        or journal_root.name != committed_promotion.get("transaction_id")
    ):
        raise MutationBatchError("committed promotion journal is invalid")
    committed_paths = sorted(journal_root.glob("*.COMMITTED.json"))
    if len(committed_paths) != 1:
        raise MutationBatchError(
            "committed promotion has no unique COMMITTED event"
        )
    committed_raw = committed_paths[0].read_bytes()
    if (
        hashlib.sha256(committed_raw).hexdigest()
        != committed_promotion.get("committed_event_sha256")
    ):
        raise MutationBatchError("COMMITTED event digest mismatch")
    event = _strict_json_object(committed_raw, label="COMMITTED event")
    if committed_raw != _canonical_bytes(event):
        raise MutationBatchError("COMMITTED event is not canonical JSON")
    live_state = event.get("live")
    previous_state = event.get("previous")
    if (
        event.get("phase") != "COMMITTED"
        or event.get("transaction_id")
        != committed_promotion.get("transaction_id")
        or type(live_state) is not dict
        or type(previous_state) is not dict
        or live_state.get("sha256")
        != committed_promotion.get("installed_digest_sha256")
        or previous_state.get("sha256")
        != committed_promotion.get("recovery_digest_sha256")
    ):
        raise MutationBatchError("COMMITTED event store evidence mismatch")

    intent_raw = (journal_root / "intent.json").read_bytes()
    intent = _strict_json_object(intent_raw, label="promotion intent")
    if (
        intent_raw != _canonical_bytes(intent)
        or hashlib.sha256(intent_raw).hexdigest()
        != event.get("intent_sha256")
    ):
        raise MutationBatchError("promotion intent evidence mismatch")
    document_raw = (journal_root / "promotion_document.json").read_bytes()
    document = _strict_json_object(
        document_raw,
        label="promotion document",
    )
    if (
        document_raw != _canonical_bytes(document)
        or hashlib.sha256(document_raw).hexdigest()
        != intent.get("promotion_document_sha256")
        or document.get("mutation_batch_manifest_sha256")
        != manifest_sha256
        or document.get("base_revision")
        != f"sha256:{manifest.get('base_digest_sha256')}"
        or document.get("candidate_digest_sha256")
        != committed_promotion.get("installed_digest_sha256")
        or document.get("target_store_id") != SHIPPED_STORE_TARGET_ID
        or document.get("merge_authorized") is not True
    ):
        raise MutationBatchError(
            "signed promotion document does not bind batch and installed store"
        )
    signature = document.get("operator_signature")
    payload_digest = hashlib.sha256(
        _canonical_promotion_payload(document)
    ).hexdigest()
    if (
        type(signature) is not dict
        or signature.get("payload_sha256") != payload_digest
        or payload_digest != committed_promotion.get("promotion_payload_sha256")
    ):
        raise MutationBatchError(
            "promotion payload digest evidence is inconsistent"
        )
    return {
        "transaction_id": committed_promotion["transaction_id"],
        "committed_event_sha256": committed_promotion[
            "committed_event_sha256"
        ],
        "promotion_payload_sha256": payload_digest,
        "installed_digest_sha256": committed_promotion[
            "installed_digest_sha256"
        ],
        "recovery_digest_sha256": committed_promotion[
            "recovery_digest_sha256"
        ],
        "mutation_batch_manifest_sha256": manifest_sha256,
        "journal_phase": "COMMITTED",
        "operator_signature_evidence": "verified_by_fixed_landing_boundary",
    }


def record_applied_receipt(
    root: str | Path,
    *,
    committed_promotion: Mapping[str, Any],
    occurred_at: str | None = None,
) -> Path:
    """Record ``applied`` only from a batch-bound signed COMMITTED journal."""

    batch_root, manifest, manifest_sha256 = _load_valid_batch(root)
    validation = validate_mutation_batch(batch_root)
    if validation.latest_stage is not MutationStage.STAGED:
        raise MutationBatchError(
            "applied requires a valid staged lifecycle receipt"
        )
    timestamp = _utc_now() if occurred_at is None else occurred_at
    if not _valid_timestamp(timestamp):
        raise MutationBatchError("receipt timestamp is invalid")
    evidence = _committed_evidence(
        manifest=manifest,
        manifest_sha256=manifest_sha256,
        committed_promotion=committed_promotion,
    )
    receipts_root = batch_root / "receipts"
    previous_path = receipts_root / "0003.staged.json"
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "batch_id": manifest["batch_id"],
        "manifest_sha256": manifest_sha256,
        "sequence": 4,
        "stage": MutationStage.APPLIED.value,
        "occurred_at": timestamp,
        "previous_receipt_sha256": hashlib.sha256(
            previous_path.read_bytes()
        ).hexdigest(),
        "evidence": evidence,
        "production_store_mutated": True,
    }
    path = receipts_root / "0004.applied.json"
    _exclusive_write(path, receipt)
    _sync_directory(receipts_root)
    post = validate_mutation_batch(batch_root)
    if not post.ok or post.latest_stage is not MutationStage.APPLIED:
        raise MutationBatchError("applied receipt failed post-write validation")
    return path


__all__ = [
    "BASE_DIGEST_ALGORITHM",
    "BatchValidation",
    "GraphAddition",
    "GraphRetraction",
    "MANIFEST_SCHEMA_VERSION",
    "MutationBatchError",
    "MutationBatchRef",
    "MutationStage",
    "RECEIPT_SCHEMA_VERSION",
    "SEAL_SCHEMA_VERSION",
    "create_mutation_batch",
    "load_validated_mutation_batch",
    "record_applied_receipt",
    "record_lifecycle_receipt",
    "validate_sealed_manifest_bytes",
    "validate_mutation_batch",
]
