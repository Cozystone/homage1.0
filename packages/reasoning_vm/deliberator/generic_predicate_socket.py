"""Read-only, graph-native predicate contexts over staged TripleStore roots.

This module is an adapter, not a compiler and not an answerer.  It exposes the
predicate names that are actually present on one subject's ``p.col`` rows.  A
predicate is always named in the ATANOR internal-graph namespace; an internal
name such as ``country`` is never relabelled as a Wikidata PID.

The socket has deliberately narrow I/O:

* every TripleStore is opened with ``read_only=True``;
* a complete subject index is required, so a missing/stale index cannot fall
  back to a full-column scan;
* both examined rows and returned facts are capped per stage;
* an overflow returns no partial facts (fail closed);
* stage and source digests are exact hashes of the stage descriptor and source
  registry bytes, while a separately named identity digest detects local
  artifact replacement without claiming a full content attestation.

B1 entity and S1 literal roots are peers in one composite context.  Their rows
remain provenance-distinct even when they contain the same internal predicate.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import threading
from typing import Any, Literal
import urllib.parse

import numpy as np

from packages.cognitive_core.canonical import FrozenMap, canonical_digest
from packages.graph_scale.triple_store import TripleStore


SCHEMA_VERSION = "atanor.deliberator.generic-predicate-context.v1"
STAGE_BINDING_SCHEMA_VERSION = "atanor.triplestore-stage-binding.v1"
PREDICATE_NAMESPACE = "atanor.internal_graph"

DEFAULT_MAX_FACTS_PER_STAGE = 256
DEFAULT_MAX_ROWS_EXAMINED_PER_STAGE = 4096
MAX_STAGES = 8
MAX_FACTS_PER_STAGE = 4096
MAX_ROWS_EXAMINED_PER_STAGE = 65_536
MAX_SUBJECT_CHARS = 2048
MAX_TERM_CHARS = 8192
MAX_DESCRIPTOR_BYTES = 8 * 1024 * 1024
MAX_SOURCE_REGISTRY_BYTES = 4 * 1024 * 1024
MAX_TOMBSTONE_BYTES = 4 * 1024 * 1024
MAX_QID_PID_SIDECAR_BYTES = 256 * 1024 * 1024

QID_PID_RECORD_FORMAT = (
    "little-endian uint64 QID number + uint32 PID number"
)
QID_PID_RECORD_BYTES = 12
_QID_PID_DTYPE = np.dtype([("qid", "<u8"), ("pid", "<u4")], align=False)

StageRole = Literal["entity", "literal", "generic"]
ContextStatus = Literal["ready", "not_found", "overflow"]
ObjectKind = Literal["entity", "literal", "unknown"]

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_STAGE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_QID = re.compile(r"Q[1-9]\d{0,19}\Z")
_PID = re.compile(r"P[1-9]\d{0,9}\Z")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_AUTHORITY_CLAIMS = FrozenMap(
    {
        "capability_established": False,
        "e4_established": False,
        "e5_established": False,
        "external_authenticity_established": False,
        "independent_evaluation_established": False,
        "wikidata_pid_binding_established": False,
    }
)


class PredicateSocketError(RuntimeError):
    """Base class for read-only socket failures."""


class StageBindingError(PredicateSocketError):
    """A stage cannot satisfy the bounded read-only binding contract."""


class StageChangedError(PredicateSocketError):
    """A bound stage changed before or during a subject lookup."""


def _is_sha256(value: Any) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _validate_text(value: Any, *, name: str, max_chars: int) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > max_chars
        or _CONTROL.search(value) is not None
    ):
        raise ValueError(f"{name} is invalid")
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file_bounded(path: Path, *, cap: int, label: str) -> str:
    try:
        before = path.stat()
    except OSError as exc:
        raise StageBindingError(f"{label} is unavailable: {path}") from exc
    if before.st_size > cap:
        raise StageBindingError(f"{label} exceeds the bounded hash cap")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    try:
        after = path.stat()
    except OSError as exc:
        raise StageChangedError(f"{label} changed while it was hashed") from exc
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise StageChangedError(f"{label} changed while it was hashed")
    return digest.hexdigest()


def _read_bounded(path: Path, *, cap: int, label: str) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise StageBindingError(f"{label} is unavailable: {path}") from exc
    if size > cap:
        raise StageBindingError(f"{label} exceeds the bounded read cap")
    raw = path.read_bytes()
    if len(raw) != size:
        raise StageChangedError(f"{label} changed while it was read")
    return raw


@dataclass(frozen=True, slots=True)
class PredicateStageSpec:
    """One staged graph root to bind into the composite socket.

    ``manifest_name`` is optional for B1/S1 roots because their canonical names
    are discovered.  An explicit name is useful for other staged stores.
    Expected digests, when supplied, are fail-closed attestation checks.
    """

    stage_id: str
    role: StageRole
    root: Path
    manifest_name: str | None = None
    expected_stage_digest_sha256: str | None = None
    expected_source_digest_sha256: str | None = None
    expected_qid_pid_sidecar_digest_sha256: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.stage_id) is not str
            or _STAGE_ID.fullmatch(self.stage_id) is None
            or self.role not in ("entity", "literal", "generic")
        ):
            raise ValueError("predicate stage identity is invalid")
        root = Path(self.root).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"predicate stage root is unavailable: {root}")
        object.__setattr__(self, "root", root)
        if self.manifest_name is not None:
            if (
                type(self.manifest_name) is not str
                or not self.manifest_name
                or Path(self.manifest_name).name != self.manifest_name
            ):
                raise ValueError("manifest_name must be one local file name")
        for value in (
            self.expected_stage_digest_sha256,
            self.expected_source_digest_sha256,
            self.expected_qid_pid_sidecar_digest_sha256,
        ):
            if value is not None and not _is_sha256(value):
                raise ValueError("expected stage/source digest is invalid")


@dataclass(frozen=True, slots=True)
class BoundPredicateStage:
    """Immutable digest and scale binding for one open TripleStore stage."""

    stage_id: str
    role: StageRole
    root: str
    descriptor_name: str
    source_registry_name: str
    stage_digest_sha256: str
    source_digest_sha256: str
    artifact_identity_digest_sha256: str
    row_count: int
    index_generation: str
    qid_pid_sidecar_digest_sha256: str | None
    qid_pid_sidecar_records: int | None
    qid_pid_sidecar_record_format: str | None

    def __post_init__(self) -> None:
        if (
            type(self.stage_id) is not str
            or _STAGE_ID.fullmatch(self.stage_id) is None
            or self.role not in ("entity", "literal", "generic")
            or type(self.root) is not str
            or not self.root
            or type(self.descriptor_name) is not str
            or not self.descriptor_name
            or type(self.source_registry_name) is not str
            or not self.source_registry_name
            or not _is_sha256(self.stage_digest_sha256)
            or not _is_sha256(self.source_digest_sha256)
            or not _is_sha256(self.artifact_identity_digest_sha256)
            or type(self.row_count) is not int
            or self.row_count < 0
            or type(self.index_generation) is not str
            or not self.index_generation
        ):
            raise ValueError("bound predicate stage is invalid")
        sidecar_values = (
            self.qid_pid_sidecar_digest_sha256,
            self.qid_pid_sidecar_records,
            self.qid_pid_sidecar_record_format,
        )
        if any(value is not None for value in sidecar_values):
            if (
                not _is_sha256(self.qid_pid_sidecar_digest_sha256)
                or type(self.qid_pid_sidecar_records) is not int
                or self.qid_pid_sidecar_records != self.row_count
                or self.qid_pid_sidecar_record_format
                != QID_PID_RECORD_FORMAT
            ):
                raise ValueError("bound QID/PID sidecar is invalid")

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            "stage_id": self.stage_id,
            "role": self.role,
            "root": self.root,
            "descriptor_name": self.descriptor_name,
            "source_registry_name": self.source_registry_name,
            "stage_digest_sha256": self.stage_digest_sha256,
            "source_digest_sha256": self.source_digest_sha256,
            "artifact_identity_digest_sha256": (
                self.artifact_identity_digest_sha256
            ),
            "row_count": self.row_count,
            "index_generation": self.index_generation,
            "qid_pid_sidecar_digest_sha256": (
                self.qid_pid_sidecar_digest_sha256
            ),
            "qid_pid_sidecar_records": self.qid_pid_sidecar_records,
            "qid_pid_sidecar_record_format": (
                self.qid_pid_sidecar_record_format
            ),
        }


@dataclass(frozen=True, slots=True)
class InternalPredicateRef:
    """A predicate term read from ``p.col`` in the internal graph namespace."""

    name: str
    namespace: str = PREDICATE_NAMESPACE
    wikidata_property_id: None = None

    @property
    def canonical_id(self) -> str:
        return f"stage:{self.name}"

    def __post_init__(self) -> None:
        _validate_text(
            self.name,
            name="internal predicate name",
            max_chars=MAX_TERM_CHARS,
        )
        if (
            self.namespace != PREDICATE_NAMESPACE
            or self.wikidata_property_id is not None
        ):
            raise ValueError("internal predicate cannot claim a Wikidata PID")

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            "canonical_id": self.canonical_id,
            "namespace": self.namespace,
            "name": self.name,
            "wikidata_property_id": None,
        }


def _fact_payload(
    *,
    subject: str,
    predicate: InternalPredicateRef,
    object_value: str,
    object_kind: ObjectKind,
    stage_id: str,
    stage_role: StageRole,
    row_index: int,
    source_name: str,
    source_url: str,
    stage_digest_sha256: str,
    source_registry_digest_sha256: str,
    source_record_digest_sha256: str,
    source_subject_entity_id: str | None,
    source_property_id: str | None,
    source_qid_pid_sidecar_digest_sha256: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "subject": subject,
        "predicate": predicate.to_dict(),
        "object_value": object_value,
        "object_kind": object_kind,
        "stage_id": stage_id,
        "stage_role": stage_role,
        "row_index": row_index,
        "source_name": source_name,
        "source_url": source_url,
        "stage_digest_sha256": stage_digest_sha256,
        "source_registry_digest_sha256": source_registry_digest_sha256,
        "source_record_digest_sha256": source_record_digest_sha256,
        "source_subject_entity_id": source_subject_entity_id,
        "source_property_id": source_property_id,
        "source_qid_pid_sidecar_digest_sha256": (
            source_qid_pid_sidecar_digest_sha256
        ),
    }


@dataclass(frozen=True, slots=True)
class GenericPredicateFact:
    """One provenance-bound row from a staged TripleStore."""

    subject: str
    predicate: InternalPredicateRef
    object_value: str
    object_kind: ObjectKind
    stage_id: str
    stage_role: StageRole
    row_index: int
    source_name: str
    source_url: str
    stage_digest_sha256: str
    source_registry_digest_sha256: str
    source_record_digest_sha256: str
    source_subject_entity_id: str | None
    source_property_id: str | None
    source_qid_pid_sidecar_digest_sha256: str | None
    fact_digest_sha256: str

    def __post_init__(self) -> None:
        _validate_text(
            self.subject,
            name="fact subject",
            max_chars=MAX_SUBJECT_CHARS,
        )
        _validate_text(
            self.object_value,
            name="fact object",
            max_chars=MAX_TERM_CHARS,
        )
        _validate_text(
            self.source_name,
            name="fact source name",
            max_chars=MAX_TERM_CHARS,
        )
        if self.source_url:
            _validate_text(
                self.source_url,
                name="fact source URL",
                max_chars=MAX_TERM_CHARS,
            )
        if type(self.predicate) is not InternalPredicateRef:
            raise ValueError("fact predicate is invalid")
        self.predicate.__post_init__()
        if (
            self.object_kind not in ("entity", "literal", "unknown")
            or type(self.stage_id) is not str
            or _STAGE_ID.fullmatch(self.stage_id) is None
            or self.stage_role not in ("entity", "literal", "generic")
            or type(self.row_index) is not int
            or self.row_index < 0
            or type(self.source_url) is not str
            or not _is_sha256(self.stage_digest_sha256)
            or not _is_sha256(self.source_registry_digest_sha256)
            or not _is_sha256(self.source_record_digest_sha256)
            or not _is_sha256(self.fact_digest_sha256)
        ):
            raise ValueError("generic predicate fact is invalid")
        source_binding_values = (
            self.source_subject_entity_id,
            self.source_property_id,
            self.source_qid_pid_sidecar_digest_sha256,
        )
        if any(value is not None for value in source_binding_values):
            if (
                type(self.source_subject_entity_id) is not str
                or _QID.fullmatch(self.source_subject_entity_id) is None
                or type(self.source_property_id) is not str
                or _PID.fullmatch(self.source_property_id) is None
                or not _is_sha256(
                    self.source_qid_pid_sidecar_digest_sha256
                )
            ):
                raise ValueError("fact QID/PID source binding is invalid")
        expected_source_record = canonical_digest(
            {
                "stage_id": self.stage_id,
                "source_registry_digest_sha256": (
                    self.source_registry_digest_sha256
                ),
                "source_name": self.source_name,
                "source_url": self.source_url,
            }
        )
        if expected_source_record != self.source_record_digest_sha256:
            raise ValueError("fact source record digest is invalid")
        expected_fact = canonical_digest(
            _fact_payload(
                subject=self.subject,
                predicate=self.predicate,
                object_value=self.object_value,
                object_kind=self.object_kind,
                stage_id=self.stage_id,
                stage_role=self.stage_role,
                row_index=self.row_index,
                source_name=self.source_name,
                source_url=self.source_url,
                stage_digest_sha256=self.stage_digest_sha256,
                source_registry_digest_sha256=(
                    self.source_registry_digest_sha256
                ),
                source_record_digest_sha256=(
                    self.source_record_digest_sha256
                ),
                source_subject_entity_id=self.source_subject_entity_id,
                source_property_id=self.source_property_id,
                source_qid_pid_sidecar_digest_sha256=(
                    self.source_qid_pid_sidecar_digest_sha256
                ),
            )
        )
        if expected_fact != self.fact_digest_sha256:
            raise ValueError("fact digest is invalid")

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            **_fact_payload(
                subject=self.subject,
                predicate=self.predicate,
                object_value=self.object_value,
                object_kind=self.object_kind,
                stage_id=self.stage_id,
                stage_role=self.stage_role,
                row_index=self.row_index,
                source_name=self.source_name,
                source_url=self.source_url,
                stage_digest_sha256=self.stage_digest_sha256,
                source_registry_digest_sha256=(
                    self.source_registry_digest_sha256
                ),
                source_record_digest_sha256=(
                    self.source_record_digest_sha256
                ),
                source_subject_entity_id=self.source_subject_entity_id,
                source_property_id=self.source_property_id,
                source_qid_pid_sidecar_digest_sha256=(
                    self.source_qid_pid_sidecar_digest_sha256
                ),
            ),
            "fact_digest_sha256": self.fact_digest_sha256,
        }


def _context_payload(
    *,
    subject: str,
    status: ContextStatus,
    facts: tuple[GenericPredicateFact, ...],
    predicate_vocabulary: tuple[InternalPredicateRef, ...],
    stage_bindings: tuple[BoundPredicateStage, ...],
    overflow_stage_ids: tuple[str, ...],
    max_facts_per_stage: int,
    max_rows_examined_per_stage: int,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "subject": subject,
        "status": status,
        "facts": [row.to_dict() for row in facts],
        "predicate_vocabulary": [
            row.to_dict() for row in predicate_vocabulary
        ],
        "stage_bindings": [row.to_dict() for row in stage_bindings],
        "overflow_stage_ids": list(overflow_stage_ids),
        "max_facts_per_stage": max_facts_per_stage,
        "max_rows_examined_per_stage": max_rows_examined_per_stage,
        "authority_claims": _AUTHORITY_CLAIMS.to_dict(),
    }


@dataclass(frozen=True, slots=True)
class GenericPredicateContext:
    """Detached immutable context suitable for a later generic compiler."""

    subject: str
    status: ContextStatus
    facts: tuple[GenericPredicateFact, ...]
    predicate_vocabulary: tuple[InternalPredicateRef, ...]
    stage_bindings: tuple[BoundPredicateStage, ...]
    overflow_stage_ids: tuple[str, ...]
    max_facts_per_stage: int
    max_rows_examined_per_stage: int
    authority_claims: FrozenMap
    context_digest_sha256: str

    def __post_init__(self) -> None:
        self.assert_validated()

    @property
    def complete(self) -> bool:
        return self.status != "overflow"

    def assert_validated(self) -> None:
        _validate_text(
            self.subject,
            name="context subject",
            max_chars=MAX_SUBJECT_CHARS,
        )
        if (
            self.status not in ("ready", "not_found", "overflow")
            or type(self.facts) is not tuple
            or type(self.predicate_vocabulary) is not tuple
            or type(self.stage_bindings) is not tuple
            or not 1 <= len(self.stage_bindings) <= MAX_STAGES
            or type(self.overflow_stage_ids) is not tuple
            or type(self.max_facts_per_stage) is not int
            or not 1 <= self.max_facts_per_stage <= MAX_FACTS_PER_STAGE
            or type(self.max_rows_examined_per_stage) is not int
            or not self.max_facts_per_stage
            <= self.max_rows_examined_per_stage
            <= MAX_ROWS_EXAMINED_PER_STAGE
            or type(self.authority_claims) is not FrozenMap
            or self.authority_claims != _AUTHORITY_CLAIMS
            or not _is_sha256(self.context_digest_sha256)
        ):
            raise ValueError("generic predicate context is invalid")
        for row in self.facts:
            if type(row) is not GenericPredicateFact:
                raise ValueError("generic predicate context fact is invalid")
            row.__post_init__()
        for row in self.predicate_vocabulary:
            if type(row) is not InternalPredicateRef:
                raise ValueError("generic predicate vocabulary is invalid")
            row.__post_init__()
        for row in self.stage_bindings:
            if type(row) is not BoundPredicateStage:
                raise ValueError("generic predicate stage binding is invalid")
            row.__post_init__()
        stage_ids = tuple(row.stage_id for row in self.stage_bindings)
        if len(set(stage_ids)) != len(stage_ids):
            raise ValueError("duplicate generic predicate stage")
        expected_predicates = tuple(
            InternalPredicateRef(name)
            for name in sorted({row.predicate.name for row in self.facts})
        )
        bound = {row.stage_id: row for row in self.stage_bindings}
        if any(
            row.stage_id not in bound
            or row.subject not in (self.subject, self.subject.lower())
            or row.stage_role != bound[row.stage_id].role
            or row.stage_digest_sha256
            != bound[row.stage_id].stage_digest_sha256
            or row.source_registry_digest_sha256
            != bound[row.stage_id].source_digest_sha256
            or (
                bound[row.stage_id].qid_pid_sidecar_digest_sha256 is None
                and (
                    row.source_subject_entity_id is not None
                    or row.source_property_id is not None
                    or row.source_qid_pid_sidecar_digest_sha256 is not None
                )
            )
            or (
                bound[row.stage_id].qid_pid_sidecar_digest_sha256 is not None
                and (
                    row.source_subject_entity_id is None
                    or row.source_property_id is None
                    or row.source_qid_pid_sidecar_digest_sha256
                    != bound[
                        row.stage_id
                    ].qid_pid_sidecar_digest_sha256
                )
            )
            for row in self.facts
        ):
            raise ValueError("fact is not bound to its declared stage")
        if (
            self.predicate_vocabulary != expected_predicates
            or tuple(sorted(set(self.overflow_stage_ids)))
            != self.overflow_stage_ids
            or any(value not in bound for value in self.overflow_stage_ids)
            or (
                self.status == "ready"
                and (not self.facts or self.overflow_stage_ids)
            )
            or (
                self.status == "not_found"
                and (self.facts or self.overflow_stage_ids)
            )
            or (
                self.status == "overflow"
                and (self.facts or not self.overflow_stage_ids)
            )
        ):
            raise ValueError("generic predicate context status is inconsistent")
        expected_digest = canonical_digest(
            _context_payload(
                subject=self.subject,
                status=self.status,
                facts=self.facts,
                predicate_vocabulary=self.predicate_vocabulary,
                stage_bindings=self.stage_bindings,
                overflow_stage_ids=self.overflow_stage_ids,
                max_facts_per_stage=self.max_facts_per_stage,
                max_rows_examined_per_stage=(
                    self.max_rows_examined_per_stage
                ),
            )
        )
        if expected_digest != self.context_digest_sha256:
            raise ValueError("generic predicate context digest is invalid")

    def predicates_for_subject(
        self,
        subject: Any,
    ) -> tuple[InternalPredicateRef, ...]:
        self.assert_validated()
        if type(subject) is not str or subject != self.subject:
            return ()
        return self.predicate_vocabulary

    def facts_for_subject(
        self,
        subject: Any,
        predicate: Any = None,
    ) -> tuple[GenericPredicateFact, ...]:
        self.assert_validated()
        if type(subject) is not str or subject != self.subject:
            return ()
        if predicate is None:
            return self.facts
        if type(predicate) is InternalPredicateRef:
            name = predicate.name
        elif type(predicate) is str:
            name = predicate
        else:
            return ()
        return tuple(row for row in self.facts if row.predicate.name == name)

    def to_dict(self) -> dict[str, Any]:
        self.assert_validated()
        return {
            **_context_payload(
                subject=self.subject,
                status=self.status,
                facts=self.facts,
                predicate_vocabulary=self.predicate_vocabulary,
                stage_bindings=self.stage_bindings,
                overflow_stage_ids=self.overflow_stage_ids,
                max_facts_per_stage=self.max_facts_per_stage,
                max_rows_examined_per_stage=(
                    self.max_rows_examined_per_stage
                ),
            ),
            "context_digest_sha256": self.context_digest_sha256,
        }


@dataclass(slots=True)
class _OpenedStage:
    spec: PredicateStageSpec
    binding: BoundPredicateStage
    store: TripleStore
    source_lines: tuple[str, ...]
    tombstones: frozenset[tuple[str, str, str]]
    qid_pid_column: Any | None
    property_predicates: dict[int, str]


@dataclass(frozen=True, slots=True)
class _QidPidBinding:
    digest_sha256: str
    records: int
    record_format: str
    column: Any
    property_predicates: dict[int, str]


def _descriptor_path(spec: PredicateStageSpec) -> Path:
    if spec.manifest_name is not None:
        path = spec.root / spec.manifest_name
        if not path.is_file():
            raise StageBindingError(
                f"stage descriptor is unavailable: {spec.manifest_name}"
            )
        return path
    preferred: tuple[str, ...]
    if spec.role == "entity":
        preferred = ("B1_WIKIDATA_MANIFEST.json",)
    elif spec.role == "literal":
        preferred = (
            "S1_WIKIDATA_LITERAL_MANIFEST.json",
            "S1_WIKIDATA_LITERAL_PARTIAL.json",
        )
    else:
        preferred = ()
    found = [spec.root / name for name in preferred if (spec.root / name).is_file()]
    if len(found) == 1:
        return found[0]
    manifests = tuple(sorted(spec.root.glob("*MANIFEST*.json")))
    if len(manifests) == 1:
        return manifests[0]
    if len(manifests) > 1 or len(found) > 1:
        raise StageBindingError(
            "stage descriptor is ambiguous; set manifest_name explicitly"
        )
    meta = spec.root / "meta.json"
    if meta.is_file():
        return meta
    raise StageBindingError("stage has no manifest or meta.json descriptor")


def _artifact_inventory(root: Path) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    try:
        entries = tuple(sorted(root.iterdir(), key=lambda path: path.name))
    except OSError as exc:
        raise StageBindingError(f"cannot inventory stage root: {root}") from exc
    for path in entries:
        try:
            stat = path.stat()
        except OSError as exc:
            raise StageChangedError(
                f"stage artifact changed during inventory: {path.name}"
            ) from exc
        rows.append(
            {
                "path": path.name,
                "kind": "dir" if path.is_dir() else "file",
                "size": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
                "inode": int(stat.st_ino),
            }
        )
        if path.name == "term_shards" and path.is_dir():
            try:
                shards = tuple(
                    sorted(path.iterdir(), key=lambda item: item.name)
                )
            except OSError as exc:
                raise StageChangedError(
                    "term shard directory changed during inventory"
                ) from exc
            for shard in shards:
                try:
                    shard_stat = shard.stat()
                except OSError as exc:
                    raise StageChangedError(
                        "term shard changed during inventory"
                    ) from exc
                rows.append(
                    {
                        "path": f"term_shards/{shard.name}",
                        "kind": "dir" if shard.is_dir() else "file",
                        "size": int(shard_stat.st_size),
                        "mtime_ns": int(shard_stat.st_mtime_ns),
                        "inode": int(shard_stat.st_ino),
                    }
                )
    return tuple(rows)


def _artifact_identity(root: Path) -> str:
    return canonical_digest(
        {
            "schema_version": STAGE_BINDING_SCHEMA_VERSION,
            "root": str(root),
            "inventory": list(_artifact_inventory(root)),
        }
    )


def _load_source_registry(
    root: Path,
) -> tuple[tuple[str, ...], str, str]:
    path = root / "sources.txt"
    if not path.exists():
        raw = b"curated:legacy|\n"
        return ("curated:legacy|",), _sha256_bytes(raw), "<implicit-legacy>"
    raw = _read_bounded(
        path,
        cap=MAX_SOURCE_REGISTRY_BYTES,
        label="source registry",
    )
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise StageBindingError("source registry is not valid UTF-8") from exc
    lines = tuple(line for line in text.splitlines() if line.strip())
    if not lines:
        lines = ("curated:legacy|",)
    return lines, _sha256_bytes(raw), path.name


def _load_tombstones(
    root: Path,
) -> frozenset[tuple[str, str, str]]:
    path = root / "retractions.jsonl"
    if not path.exists():
        return frozenset()
    raw = _read_bounded(
        path,
        cap=MAX_TOMBSTONE_BYTES,
        label="retraction sidecar",
    )
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise StageBindingError("retraction sidecar is not valid UTF-8") from exc
    rows: set[tuple[str, str, str]] = set()
    for line in text.splitlines():
        try:
            value = json.loads(line)
            triple = (value["s"], value["p"], value["o"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if all(type(item) is str for item in triple):
            rows.add(triple)
    return frozenset(rows)


def _load_qid_pid_binding(
    *,
    spec: PredicateStageSpec,
    descriptor_raw: bytes,
    row_count: int,
) -> _QidPidBinding | None:
    path = spec.root / "qid_pid.col"
    try:
        descriptor = json.loads(descriptor_raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        if spec.role == "literal" or path.exists():
            raise StageBindingError(
                "QID/PID stage descriptor is not valid JSON"
            ) from exc
        return None
    if not isinstance(descriptor, dict):
        if spec.role == "literal" or path.exists():
            raise StageBindingError("QID/PID stage descriptor is not an object")
        return None
    declaration = descriptor.get("qid_pid_sidecar")
    needs_binding = (
        spec.role == "literal"
        or path.exists()
        or declaration is not None
    )
    if not needs_binding:
        return None
    if descriptor.get("completion_state") != "complete":
        raise StageBindingError("QID/PID stage is partial or incomplete")
    if (
        spec.role == "literal"
        and descriptor.get("promotion_eligible") is not True
    ):
        raise StageBindingError("literal QID/PID stage is not promotion eligible")
    if not isinstance(declaration, dict):
        raise StageBindingError("QID/PID sidecar declaration is missing")
    if (
        declaration.get("path") != "qid_pid.col"
        or declaration.get("record_format") != QID_PID_RECORD_FORMAT
        or declaration.get("record_bytes") != QID_PID_RECORD_BYTES
        or declaration.get("records") != row_count
    ):
        raise StageBindingError("QID/PID sidecar declaration is inconsistent")
    if not path.is_file():
        raise StageBindingError("QID/PID sidecar is missing")
    size = path.stat().st_size
    if (
        size % QID_PID_RECORD_BYTES
        or size // QID_PID_RECORD_BYTES != row_count
    ):
        raise StageBindingError("QID/PID sidecar is torn or row-misaligned")
    digest = _sha256_file_bounded(
        path,
        cap=MAX_QID_PID_SIDECAR_BYTES,
        label="QID/PID sidecar",
    )
    declared_digests = {
        value
        for key in ("sha256", "digest_sha256", "sha256_digest")
        if (value := declaration.get(key)) is not None
    }
    if len(declared_digests) > 1:
        raise StageBindingError("QID/PID sidecar declares conflicting digests")
    if declared_digests:
        declared_digest = next(iter(declared_digests))
        if not _is_sha256(declared_digest) or declared_digest != digest:
            raise StageBindingError("QID/PID sidecar digest does not match")
    property_predicates: dict[int, str] = {}
    profile = descriptor.get("property_profile")
    if profile is not None:
        if not isinstance(profile, dict):
            raise StageBindingError("literal property profile is invalid")
        for property_id, value in profile.items():
            if (
                type(property_id) is not str
                or _PID.fullmatch(property_id) is None
                or not isinstance(value, dict)
                or type(value.get("predicate")) is not str
            ):
                raise StageBindingError("literal property profile row is invalid")
            predicate_name = value["predicate"]
            _validate_text(
                predicate_name,
                name="literal property predicate",
                max_chars=MAX_TERM_CHARS,
            )
            property_predicates[int(property_id[1:])] = predicate_name
    if spec.role == "literal" and not property_predicates:
        raise StageBindingError("literal stage has no property profile binding")
    column = (
        np.memmap(
            str(path),
            dtype=_QID_PID_DTYPE,
            mode="r",
            shape=(row_count,),
        )
        if row_count
        else np.zeros(0, dtype=_QID_PID_DTYPE)
    )
    return _QidPidBinding(
        digest_sha256=digest,
        records=row_count,
        record_format=QID_PID_RECORD_FORMAT,
        column=column,
        property_predicates=property_predicates,
    )


def _open_stage(spec: PredicateStageSpec) -> _OpenedStage:
    identity_before = _artifact_identity(spec.root)
    descriptor = _descriptor_path(spec)
    descriptor_raw = _read_bounded(
        descriptor,
        cap=MAX_DESCRIPTOR_BYTES,
        label="stage descriptor",
    )
    stage_digest = _sha256_bytes(descriptor_raw)
    source_lines, source_digest, source_name = _load_source_registry(spec.root)
    if (
        spec.expected_stage_digest_sha256 is not None
        and stage_digest != spec.expected_stage_digest_sha256
    ):
        raise StageBindingError("stage descriptor digest does not match expectation")
    if (
        spec.expected_source_digest_sha256 is not None
        and source_digest != spec.expected_source_digest_sha256
    ):
        raise StageBindingError("source registry digest does not match expectation")
    store: TripleStore | None = None
    try:
        store = TripleStore(spec.root, read_only=True)
        if getattr(store, "_read_only", False) is not True:
            raise StageBindingError("TripleStore did not enter read-only mode")
        for name in ("s", "p", "o"):
            path = spec.root / f"{name}.col"
            if path.exists() and path.stat().st_size % 4:
                raise StageBindingError(
                    f"stage {name}.col is not int32-aligned"
                )
        columns = store.open_columns()
        row_counts = tuple(len(columns[name]) for name in ("s", "p", "o"))
        if len(set(row_counts)) != 1:
            raise StageBindingError("stage s/p/o columns have unequal row counts")
        row_count = row_counts[0]
        if len(store) != row_count:
            raise StageBindingError("stage metadata count does not match columns")
        source_path = spec.root / "src.col"
        if source_path.exists():
            source_size = source_path.stat().st_size
            if source_size % 4 or source_size // 4 != row_count:
                raise StageBindingError("stage source column is not row-aligned")
        index = store._index()
        if index is None:
            raise StageBindingError(
                "stage has no subject index; refusing full-column fallback"
            )
        permutation, sorted_subjects = index
        if len(permutation) != row_count or len(sorted_subjects) != row_count:
            raise StageBindingError(
                "subject index does not cover the complete stage"
            )
        meta = json.loads((spec.root / "meta.json").read_text(encoding="utf-8"))
        generation_value = meta.get("index_ts")
        index_generation = (
            str(generation_value) if generation_value is not None else "legacy"
        )
        qid_pid = _load_qid_pid_binding(
            spec=spec,
            descriptor_raw=descriptor_raw,
            row_count=row_count,
        )
        expected_qid_pid_digest = (
            spec.expected_qid_pid_sidecar_digest_sha256
        )
        if expected_qid_pid_digest is not None and (
            qid_pid is None
            or qid_pid.digest_sha256 != expected_qid_pid_digest
        ):
            raise StageBindingError(
                "QID/PID sidecar digest does not match expectation"
            )
        tombstones = _load_tombstones(spec.root)
        identity_after = _artifact_identity(spec.root)
        if identity_after != identity_before:
            raise StageChangedError("stage changed while it was bound")
        binding = BoundPredicateStage(
            stage_id=spec.stage_id,
            role=spec.role,
            root=str(spec.root),
            descriptor_name=descriptor.name,
            source_registry_name=source_name,
            stage_digest_sha256=stage_digest,
            source_digest_sha256=source_digest,
            artifact_identity_digest_sha256=identity_after,
            row_count=row_count,
            index_generation=index_generation,
            qid_pid_sidecar_digest_sha256=(
                qid_pid.digest_sha256 if qid_pid is not None else None
            ),
            qid_pid_sidecar_records=(
                qid_pid.records if qid_pid is not None else None
            ),
            qid_pid_sidecar_record_format=(
                qid_pid.record_format if qid_pid is not None else None
            ),
        )
        return _OpenedStage(
            spec=spec,
            binding=binding,
            store=store,
            source_lines=source_lines,
            tombstones=tombstones,
            qid_pid_column=(
                qid_pid.column if qid_pid is not None else None
            ),
            property_predicates=(
                qid_pid.property_predicates if qid_pid is not None else {}
            ),
        )
    except Exception:
        if store is not None:
            store.close()
        raise


def _resolve_source(
    source_lines: tuple[str, ...],
    source_id: int,
    subject: str,
) -> tuple[str, str]:
    line = (
        source_lines[source_id]
        if 0 <= source_id < len(source_lines)
        else source_lines[0]
    )
    name, _, pattern = line.partition("|")
    url = (
        pattern.replace(
            "{s}",
            urllib.parse.quote(subject.replace(" ", "_")),
        )
        if pattern
        else ""
    )
    return name, url


def _object_kind(role: StageRole) -> ObjectKind:
    if role == "entity":
        return "entity"
    if role == "literal":
        return "literal"
    return "unknown"


def _make_fact(
    *,
    stage: _OpenedStage,
    subject: str,
    predicate_name: str,
    object_value: str,
    row_index: int,
    source_name: str,
    source_url: str,
    source_subject_entity_id: str | None,
    source_property_id: str | None,
) -> GenericPredicateFact:
    predicate = InternalPredicateRef(predicate_name)
    source_record_digest = canonical_digest(
        {
            "stage_id": stage.binding.stage_id,
            "source_registry_digest_sha256": (
                stage.binding.source_digest_sha256
            ),
            "source_name": source_name,
            "source_url": source_url,
        }
    )
    payload = _fact_payload(
        subject=subject,
        predicate=predicate,
        object_value=object_value,
        object_kind=_object_kind(stage.binding.role),
        stage_id=stage.binding.stage_id,
        stage_role=stage.binding.role,
        row_index=row_index,
        source_name=source_name,
        source_url=source_url,
        stage_digest_sha256=stage.binding.stage_digest_sha256,
        source_registry_digest_sha256=stage.binding.source_digest_sha256,
        source_record_digest_sha256=source_record_digest,
        source_subject_entity_id=source_subject_entity_id,
        source_property_id=source_property_id,
        source_qid_pid_sidecar_digest_sha256=(
            stage.binding.qid_pid_sidecar_digest_sha256
        ),
    )
    return GenericPredicateFact(
        subject=subject,
        predicate=predicate,
        object_value=object_value,
        object_kind=_object_kind(stage.binding.role),
        stage_id=stage.binding.stage_id,
        stage_role=stage.binding.role,
        row_index=row_index,
        source_name=source_name,
        source_url=source_url,
        stage_digest_sha256=stage.binding.stage_digest_sha256,
        source_registry_digest_sha256=stage.binding.source_digest_sha256,
        source_record_digest_sha256=source_record_digest,
        source_subject_entity_id=source_subject_entity_id,
        source_property_id=source_property_id,
        source_qid_pid_sidecar_digest_sha256=(
            stage.binding.qid_pid_sidecar_digest_sha256
        ),
        fact_digest_sha256=canonical_digest(payload),
    )


def _query_stage(
    stage: _OpenedStage,
    subject: str,
    *,
    max_facts: int,
    max_rows: int,
) -> tuple[tuple[GenericPredicateFact, ...], bool]:
    store = stage.store
    resolved_subject = subject
    subject_id = store.terms.lookup(resolved_subject)
    lowered = subject.lower()
    if subject_id is None and lowered != subject:
        resolved_subject = lowered
        subject_id = store.terms.lookup(resolved_subject)
    if subject_id is None:
        return (), False
    columns = store.open_columns()
    subject_rows = store._subject_rows(subject_id, columns["s"])
    if len(subject_rows) > max_rows:
        return (), True
    source_column = None
    source_path = stage.spec.root / "src.col"
    if source_path.exists() and stage.binding.row_count:
        source_column = np.memmap(
            str(source_path),
            dtype="<i4",
            mode="r",
            shape=(stage.binding.row_count,),
        )
    facts: list[GenericPredicateFact] = []
    for start in range(0, len(subject_rows), 256):
        chunk = subject_rows[start : start + 256]
        kept = store._verdict_keep(chunk, columns["p"])
        for raw_index in kept:
            row_index = int(raw_index)
            predicate_name = store.terms.term(
                int(columns["p"][row_index])
            )
            object_value = store.terms.term(int(columns["o"][row_index]))
            triple = (resolved_subject, predicate_name, object_value)
            if triple in stage.tombstones:
                continue
            _validate_text(
                predicate_name,
                name="stored predicate",
                max_chars=MAX_TERM_CHARS,
            )
            _validate_text(
                object_value,
                name="stored object",
                max_chars=MAX_TERM_CHARS,
            )
            source_id = (
                int(source_column[row_index])
                if source_column is not None
                else 0
            )
            source_name, source_url = _resolve_source(
                stage.source_lines,
                source_id,
                resolved_subject,
            )
            source_subject_entity_id = None
            source_property_id = None
            if stage.qid_pid_column is not None:
                record = stage.qid_pid_column[row_index]
                qid_number = int(record["qid"])
                pid_number = int(record["pid"])
                if qid_number <= 0 or pid_number <= 0:
                    raise StageBindingError(
                        "QID/PID sidecar contains a zero identifier"
                    )
                expected_predicate = stage.property_predicates.get(pid_number)
                if (
                    stage.binding.role == "literal"
                    and expected_predicate != predicate_name
                ):
                    raise StageBindingError(
                        "QID/PID row does not match the staged predicate"
                    )
                source_subject_entity_id = f"Q{qid_number}"
                source_property_id = f"P{pid_number}"
            facts.append(
                _make_fact(
                    stage=stage,
                    subject=resolved_subject,
                    predicate_name=predicate_name,
                    object_value=object_value,
                    row_index=row_index,
                    source_name=source_name,
                    source_url=source_url,
                    source_subject_entity_id=source_subject_entity_id,
                    source_property_id=source_property_id,
                )
            )
            if len(facts) > max_facts:
                return (), True
    return tuple(facts), False


def _build_context(
    *,
    subject: str,
    status: ContextStatus,
    facts: tuple[GenericPredicateFact, ...],
    stage_bindings: tuple[BoundPredicateStage, ...],
    overflow_stage_ids: tuple[str, ...],
    max_facts_per_stage: int,
    max_rows_examined_per_stage: int,
) -> GenericPredicateContext:
    predicates = tuple(
        InternalPredicateRef(name)
        for name in sorted({row.predicate.name for row in facts})
    )
    payload = _context_payload(
        subject=subject,
        status=status,
        facts=facts,
        predicate_vocabulary=predicates,
        stage_bindings=stage_bindings,
        overflow_stage_ids=overflow_stage_ids,
        max_facts_per_stage=max_facts_per_stage,
        max_rows_examined_per_stage=max_rows_examined_per_stage,
    )
    return GenericPredicateContext(
        subject=subject,
        status=status,
        facts=facts,
        predicate_vocabulary=predicates,
        stage_bindings=stage_bindings,
        overflow_stage_ids=overflow_stage_ids,
        max_facts_per_stage=max_facts_per_stage,
        max_rows_examined_per_stage=max_rows_examined_per_stage,
        authority_claims=_AUTHORITY_CLAIMS,
        context_digest_sha256=canonical_digest(payload),
    )


class CompositePredicateSocket:
    """Read-only composite over one or more independently digested stages."""

    def __init__(
        self,
        opened: tuple[_OpenedStage, ...],
        *,
        max_facts_per_stage: int,
        max_rows_examined_per_stage: int,
    ) -> None:
        self._opened = opened
        self.max_facts_per_stage = max_facts_per_stage
        self.max_rows_examined_per_stage = max_rows_examined_per_stage
        self._closed = False
        self._lock = threading.RLock()

    @classmethod
    def open(
        cls,
        stages: tuple[PredicateStageSpec, ...],
        *,
        max_facts_per_stage: int = DEFAULT_MAX_FACTS_PER_STAGE,
        max_rows_examined_per_stage: int = (
            DEFAULT_MAX_ROWS_EXAMINED_PER_STAGE
        ),
    ) -> "CompositePredicateSocket":
        if (
            type(stages) is not tuple
            or not 1 <= len(stages) <= MAX_STAGES
            or any(type(stage) is not PredicateStageSpec for stage in stages)
            or len({stage.stage_id for stage in stages}) != len(stages)
            or type(max_facts_per_stage) is not int
            or not 1 <= max_facts_per_stage <= MAX_FACTS_PER_STAGE
            or type(max_rows_examined_per_stage) is not int
            or not max_facts_per_stage
            <= max_rows_examined_per_stage
            <= MAX_ROWS_EXAMINED_PER_STAGE
        ):
            raise ValueError("composite predicate socket inputs are invalid")
        opened: list[_OpenedStage] = []
        try:
            for spec in sorted(stages, key=lambda item: item.stage_id):
                opened.append(_open_stage(spec))
        except Exception:
            for stage in reversed(opened):
                stage.store.close()
            raise
        return cls(
            tuple(opened),
            max_facts_per_stage=max_facts_per_stage,
            max_rows_examined_per_stage=max_rows_examined_per_stage,
        )

    @property
    def stage_bindings(self) -> tuple[BoundPredicateStage, ...]:
        return tuple(stage.binding for stage in self._opened)

    def context_for_subject(self, subject: str) -> GenericPredicateContext:
        _validate_text(
            subject,
            name="context subject",
            max_chars=MAX_SUBJECT_CHARS,
        )
        with self._lock:
            if self._closed:
                raise PredicateSocketError("composite predicate socket is closed")
            facts: list[GenericPredicateFact] = []
            overflow: list[str] = []
            for stage in self._opened:
                before = _artifact_identity(stage.spec.root)
                if (
                    before
                    != stage.binding.artifact_identity_digest_sha256
                ):
                    raise StageChangedError(
                        f"stage changed after binding: {stage.binding.stage_id}"
                    )
                stage_facts, stage_overflow = _query_stage(
                    stage,
                    subject,
                    max_facts=self.max_facts_per_stage,
                    max_rows=self.max_rows_examined_per_stage,
                )
                after = _artifact_identity(stage.spec.root)
                if after != before:
                    raise StageChangedError(
                        f"stage changed during lookup: {stage.binding.stage_id}"
                    )
                if stage_overflow:
                    overflow.append(stage.binding.stage_id)
                    break
                facts.extend(stage_facts)
            bindings = self.stage_bindings
            if overflow:
                return _build_context(
                    subject=subject,
                    status="overflow",
                    facts=(),
                    stage_bindings=bindings,
                    overflow_stage_ids=tuple(sorted(overflow)),
                    max_facts_per_stage=self.max_facts_per_stage,
                    max_rows_examined_per_stage=(
                        self.max_rows_examined_per_stage
                    ),
                )
            canonical_facts = tuple(
                sorted(
                    facts,
                    key=lambda row: (
                        row.stage_id,
                        row.row_index,
                        row.predicate.name,
                        row.object_value,
                    ),
                )
            )
            return _build_context(
                subject=subject,
                status="ready" if canonical_facts else "not_found",
                facts=canonical_facts,
                stage_bindings=bindings,
                overflow_stage_ids=(),
                max_facts_per_stage=self.max_facts_per_stage,
                max_rows_examined_per_stage=(
                    self.max_rows_examined_per_stage
                ),
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            for stage in reversed(self._opened):
                stage.store.close()
            self._closed = True

    def __enter__(self) -> "CompositePredicateSocket":
        if self._closed:
            raise PredicateSocketError("composite predicate socket is closed")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
