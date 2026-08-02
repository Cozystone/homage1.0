"""Strict proof membrane for the timeboxed P17 relation diagnostic.

The loader accepts only a complete, canonical, locally bound generation.  It
preserves the original Wikidata property identifier and the exact source-row
bytes used for every entity binding, entity type, and relation claim.  It does
not authenticate Wikidata, access a network, rank choices, or read an answer.

This is intentionally not a generic ``located_in`` store.  V1 exposes only
positive country/nation objects backed by original ``P17`` rows plus explicit
``P31`` object-type evidence.  ``located_in`` remains multivalued: a subject
may yield zero, one, or many proof candidates.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import Any
import unicodedata

from packages.cognitive_core.canonical import canonical_digest, canonical_json
from packages.reasoning_vm.deliberator.science_relation_goal import (
    SCIENCE_RELATION_GOAL_FAMILY,
    SCIENCE_RELATION_STAGE_SCHEMA,
    RelationGoalCompilation,
)


MANIFEST_NAME = "manifest.json"
ENTITIES_NAME = "entities.jsonl"
RELATIONS_NAME = "relations.jsonl"
EVIDENCE_NAME = "evidence.jsonl"
SOURCE_ROWS_NAME = "wikidata_truthy_rows.nt"

MAX_BOUND_FILE_BYTES = 2 * 1024 * 1024
MAX_LINE_BYTES = 8 * 1024
MAX_ENTITY_ROWS = 128
MAX_RELATION_ROWS = 256
MAX_EVIDENCE_ROWS = 768
MAX_ALIASES_PER_ENTITY = 8

RELATION_PROPERTY_ID = "P17"
FORBIDDEN_RELATION_PROPERTY_IDS = ("P30", "P131", "P159", "P276")
OBJECT_ANSWER_TYPES = frozenset({"country", "nation"})

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_QID = re.compile(r"Q[1-9]\d{0,11}\Z")
_STAGE_ID = re.compile(
    r"science-relation-stage-[a-z0-9-]+-v[1-9]\d*\Z"
)
_ENTITY_ROW_ID = re.compile(r"relation-entity-row-(\d{3,})\Z")
_RELATION_ROW_ID = re.compile(r"relation-fact-row-(\d{3,})\Z")
_EVIDENCE_ID = re.compile(r"relation-evidence-(\d{3,})\Z")
_REVISION = re.compile(r"[1-9]\d{0,19}\Z")
_SOURCE_URL = re.compile(
    r"https://www\.wikidata\.org/wiki/Special:EntityData/"
    r"(Q[1-9]\d{0,11})\.json\?revision=([1-9]\d{0,19})\Z"
)
_SOURCE_RECORD_ID = re.compile(
    r"Wikidata:(Q[1-9]\d{0,11}):"
    r"(?:label:en|P31:Q[1-9]\d{0,11}|P17:Q[1-9]\d{0,11})\Z"
)
_LABEL = re.compile(r"[A-Za-z][A-Za-z0-9 .,'()-]{0,95}\Z")

_TYPE_PROFILES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "Q515": ("city",),
        "Q3624078": ("country", "nation"),
    }
)
_VALIDATION_KEY = os.urandom(32)

_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "stage_id",
        "classification",
        "completion_state",
        "evaluation_only",
        "promotion_eligible",
        "entity_count",
        "relation_count",
        "evidence_count",
        "relation_profile",
        "entities_file",
        "relations_file",
        "evidence_file",
        "source_rows_file",
        "provenance_policy",
        "source_dataset",
        "claims",
        "manifest_checksum_sha256",
    }
)
_FILE_FIELDS = frozenset({"path", "bytes", "sha256"})
_PROFILE_FIELDS = frozenset(
    {
        "goal_family",
        "predicate",
        "polarity",
        "object_answer_types",
        "source_property_id",
        "located_in_cardinality",
    }
)
_POLICY_FIELDS = frozenset(
    {
        "canonical_source_rows",
        "one_to_one_claim_evidence",
        "entity_binding_evidence_required",
        "answer_type_evidence_required",
        "original_property_id_required",
        "exact_source_statement_required",
        "source_file_digest_required",
        "source_revision_required",
        "license_required",
        "quarantined_rows_allowed",
        "network_access_allowed",
        "external_authentication_required",
    }
)
_SOURCE_FIELDS = frozenset(
    {
        "name",
        "snapshot_kind",
        "source_file_name",
        "relation_property_id",
        "forbidden_relation_property_ids",
        "license",
    }
)
_CLAIM_FIELDS = frozenset(
    {
        "capability_claimed",
        "e4_claimed",
        "e5_claimed",
        "independent_evaluator_claimed",
        "os_isolation_claimed",
        "external_authenticity_established",
    }
)
_ENTITY_FIELDS = frozenset(
    {
        "row_id",
        "entity_id",
        "label",
        "aliases",
        "answer_types",
        "type_entity_id",
        "binding_evidence_id",
        "type_evidence_id",
        "quarantined",
    }
)
_RELATION_FIELDS = frozenset(
    {
        "row_id",
        "subject_entity_id",
        "predicate",
        "polarity",
        "source_property_id",
        "object_entity_id",
        "evidence_id",
        "quarantined",
    }
)
_EVIDENCE_FIELDS = frozenset(
    {
        "evidence_id",
        "claim_kind",
        "claim_digest_sha256",
        "property_id",
        "source_url",
        "source_record_id",
        "source_revision",
        "license",
        "source_file_name",
        "source_file_sha256",
        "source_row_number",
        "source_statement",
        "source_statement_bytes",
        "source_statement_sha256",
        "externally_authenticated",
    }
)


class ScienceRelationStageError(RuntimeError):
    """Raised when relation-stage bytes or proof bindings are untrustworthy."""


def _is_link_or_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attrs = getattr(os.lstat(path), "st_file_attributes", 0)
        flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return bool(flag and attrs & flag)
    except OSError:
        return True


def _read_stable(path: Path) -> bytes:
    if _is_link_or_reparse(path) or not path.is_file():
        raise ScienceRelationStageError(
            f"bound relation-stage file is not regular: {path.name}"
        )
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if not 0 < before.st_size <= MAX_BOUND_FILE_BYTES:
                raise ScienceRelationStageError(
                    f"bound relation-stage file size invalid: {path.name}"
                )
            payload = handle.read()
            after = os.fstat(handle.fileno())
    except ScienceRelationStageError:
        raise
    except OSError as exc:
        raise ScienceRelationStageError(
            f"bound relation-stage file unreadable: {path.name}"
        ) from exc
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise ScienceRelationStageError(
            f"bound relation-stage file changed while reading: {path.name}"
        )
    return payload


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ScienceRelationStageError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise ScienceRelationStageError(f"non-finite JSON number: {token}")


def _strict_object(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_nonfinite,
        )
    except ScienceRelationStageError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ScienceRelationStageError(
            f"{label} is not strict readable JSON: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise ScienceRelationStageError(f"{label} root must be an object")
    return value


def _require_fields(
    value: Any,
    expected: frozenset[str],
    *,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != expected:
        raise ScienceRelationStageError(f"{label} fields mismatch")
    return value


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest_checksum(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_checksum_sha256", None)
    return _sha256(canonical_json(unsigned).encode("utf-8"))


def _validate_file_binding(
    value: Any,
    *,
    expected_path: str,
    payload: bytes,
    label: str,
) -> None:
    record = _require_fields(value, _FILE_FIELDS, label=label)
    if record["path"] != expected_path:
        raise ScienceRelationStageError(f"{label}.path mismatch")
    if type(record["bytes"]) is not int or record["bytes"] != len(payload):
        raise ScienceRelationStageError(f"{label}.bytes mismatch")
    digest = record["sha256"]
    if (
        type(digest) is not str
        or _SHA256.fullmatch(digest) is None
        or digest != _sha256(payload)
    ):
        raise ScienceRelationStageError(f"{label}.sha256 mismatch")


def _parse_jsonl(
    payload: bytes,
    *,
    label: str,
    maximum: int,
) -> list[dict[str, Any]]:
    if not payload.endswith(b"\n") or b"\r" in payload:
        raise ScienceRelationStageError(
            f"{label} must be LF-terminated canonical JSONL"
        )
    lines = payload.splitlines()
    if not 1 <= len(lines) <= maximum:
        raise ScienceRelationStageError(f"{label} row count out of bounds")
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if not line or len(line) > MAX_LINE_BYTES:
            raise ScienceRelationStageError(f"{label}[{index}] size invalid")
        row = _strict_object(line, label=f"{label}[{index}]")
        if canonical_json(row).encode("utf-8") != line:
            raise ScienceRelationStageError(
                f"{label}[{index}] is not canonical JSON"
            )
        rows.append(row)
    return rows


def _parse_source_rows(payload: bytes) -> tuple[bytes, ...]:
    if not payload.endswith(b"\n") or b"\r" in payload:
        raise ScienceRelationStageError(
            "source rows must be exact LF-terminated UTF-8 lines"
        )
    rows = tuple(payload.splitlines())
    if not 1 <= len(rows) <= MAX_EVIDENCE_ROWS:
        raise ScienceRelationStageError("source row count out of bounds")
    for index, row in enumerate(rows):
        if not row or len(row) > MAX_LINE_BYTES:
            raise ScienceRelationStageError(
                f"source_rows[{index}] size invalid"
            )
        try:
            decoded = row.decode("utf-8")
        except UnicodeError as exc:
            raise ScienceRelationStageError(
                f"source_rows[{index}] is not UTF-8"
            ) from exc
        if decoded != decoded.strip() or "\x00" in decoded:
            raise ScienceRelationStageError(
                f"source_rows[{index}] text invalid"
            )
    return rows


def _normalize_alias(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _qid_uri(qid: str) -> str:
    return f"<http://www.wikidata.org/entity/{qid}>"


def _label_statement(entity_id: str, label: str) -> str:
    return (
        f"{_qid_uri(entity_id)} "
        '<http://www.w3.org/2000/01/rdf-schema#label> '
        f'"{label}"@en .'
    )


def _direct_statement(subject_id: str, property_id: str, object_id: str) -> str:
    return (
        f"{_qid_uri(subject_id)} "
        f"<http://www.wikidata.org/prop/direct/{property_id}> "
        f"{_qid_uri(object_id)} ."
    )


@dataclass(frozen=True, slots=True)
class RelationEvidenceRef:
    evidence_id: str
    claim_kind: str
    claim_digest_sha256: str
    property_id: str
    source_url: str
    source_record_id: str
    source_revision: str
    license: str
    source_file_name: str
    source_file_sha256: str
    source_row_number: int
    source_statement: str
    source_statement_bytes: int
    source_statement_sha256: str
    externally_authenticated: bool

    @property
    def exact_source_statement_bytes(self) -> bytes:
        return self.source_statement.encode("utf-8")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StagedRelationEntity:
    row_id: str
    entity_id: str
    label: str
    aliases: tuple[str, ...]
    answer_types: tuple[str, ...]
    type_entity_id: str
    binding_evidence: RelationEvidenceRef
    type_evidence: RelationEvidenceRef

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "entity_id": self.entity_id,
            "label": self.label,
            "aliases": list(self.aliases),
            "answer_types": list(self.answer_types),
            "type_entity_id": self.type_entity_id,
            "binding_evidence": self.binding_evidence.to_dict(),
            "type_evidence": self.type_evidence.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class StagedRelationFact:
    row_id: str
    subject_entity_id: str
    predicate: str
    polarity: str
    source_property_id: str
    object_entity_id: str
    evidence: RelationEvidenceRef

    @property
    def proof_fact(self) -> tuple[str, str, str]:
        return (
            self.subject_entity_id,
            self.source_property_id,
            self.object_entity_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "subject_entity_id": self.subject_entity_id,
            "predicate": self.predicate,
            "polarity": self.polarity,
            "source_property_id": self.source_property_id,
            "object_entity_id": self.object_entity_id,
            "evidence": self.evidence.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class RelationProofCandidate:
    """One unranked choice whose P17 and type leaves are fully bound."""

    choice_key: str
    answer_type: str
    subject: StagedRelationEntity
    object: StagedRelationEntity
    relation: StagedRelationFact
    evidence: tuple[RelationEvidenceRef, ...]
    provenance_digest_sha256: str

    @property
    def proof_fact(self) -> tuple[str, str, str]:
        return self.relation.proof_fact

    def to_dict(self) -> dict[str, Any]:
        return {
            "choice_key": self.choice_key,
            "answer_type": self.answer_type,
            "semantic_fact": [
                self.subject.entity_id,
                "located_in",
                self.object.entity_id,
            ],
            "original_property_fact": list(self.proof_fact),
            "evidence": [row.to_dict() for row in self.evidence],
            "provenance_digest_sha256": self.provenance_digest_sha256,
        }


def _snapshot_tag(
    *,
    stage_id: str,
    stage_digest_sha256: str,
    manifest_checksum_sha256: str,
    bound_bytes: int,
    entities: tuple[StagedRelationEntity, ...],
    relations: tuple[StagedRelationFact, ...],
) -> str:
    payload = {
        "stage_id": stage_id,
        "stage_digest_sha256": stage_digest_sha256,
        "manifest_checksum_sha256": manifest_checksum_sha256,
        "bound_bytes": bound_bytes,
        "entities": [row.to_dict() for row in entities],
        "relations": [row.to_dict() for row in relations],
    }
    return hmac.new(
        _VALIDATION_KEY,
        canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class ScienceRelationStageSnapshot:
    """Detached immutable snapshot of one validated P17 generation."""

    stage_id: str
    stage_digest_sha256: str
    manifest_checksum_sha256: str
    bound_bytes: int
    entities: tuple[StagedRelationEntity, ...]
    relations: tuple[StagedRelationFact, ...]
    authority_claims: Mapping[str, bool]
    _entity_by_alias: Mapping[str, StagedRelationEntity]
    _entity_by_id: Mapping[str, StagedRelationEntity]
    _relations_by_subject: Mapping[str, tuple[StagedRelationFact, ...]]
    _validation_seal: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        self.assert_validated()

    def assert_validated(self) -> None:
        expected = _snapshot_tag(
            stage_id=self.stage_id,
            stage_digest_sha256=self.stage_digest_sha256,
            manifest_checksum_sha256=self.manifest_checksum_sha256,
            bound_bytes=self.bound_bytes,
            entities=self.entities,
            relations=self.relations,
        )
        if (
            type(self._validation_seal) is not str
            or not hmac.compare_digest(expected, self._validation_seal)
        ):
            raise ScienceRelationStageError(
                "relation-stage validation seal does not bind content"
            )
        expected_ids = {row.entity_id: row for row in self.entities}
        expected_aliases = {
            _normalize_alias(alias): row
            for row in self.entities
            for alias in row.aliases
        }
        grouped: dict[str, list[StagedRelationFact]] = {}
        for row in self.relations:
            grouped.setdefault(row.subject_entity_id, []).append(row)
        expected_relations = {
            key: tuple(sorted(rows, key=lambda item: item.row_id))
            for key, rows in sorted(grouped.items())
        }
        if (
            dict(self._entity_by_id) != expected_ids
            or dict(self._entity_by_alias) != expected_aliases
            or dict(self._relations_by_subject) != expected_relations
            or set(self.authority_claims.values()) != {False}
            or frozenset(self.authority_claims) != _CLAIM_FIELDS
        ):
            raise ScienceRelationStageError(
                "relation-stage indexes or authority do not bind snapshot"
            )

    def entity_for_alias(self, alias: Any) -> StagedRelationEntity | None:
        if type(alias) is not str:
            return None
        normalized = _normalize_alias(alias)
        if not normalized:
            return None
        return self._entity_by_alias.get(normalized)

    def relations_for_subject(
        self,
        subject_entity_id: Any,
    ) -> tuple[StagedRelationFact, ...]:
        if type(subject_entity_id) is not str:
            return ()
        return self._relations_by_subject.get(subject_entity_id, ())

    def proof_candidates(
        self,
        compilation: RelationGoalCompilation,
    ) -> tuple[RelationProofCandidate, ...]:
        """Return all matching P17 proofs without selecting or ranking one."""

        self.assert_validated()
        if type(compilation) is not RelationGoalCompilation:
            raise TypeError(
                "relation stage requires an exact RelationGoalCompilation"
            )
        compilation.__post_init__()
        if not compilation.compiled:
            return ()
        goal = compilation.goal
        if goal is None or goal.answer_type not in OBJECT_ANSWER_TYPES:
            return ()
        requirement = compilation.required_evidence[0]
        if (
            requirement.stage_schema != SCIENCE_RELATION_STAGE_SCHEMA
            or requirement.evidence_kind
            != "typed_positive_relation_fact"
            or requirement.predicate != "located_in"
            or requirement.object_answer_type != goal.answer_type
            or requirement.object_answer_type_source != "goal_answer_type"
            or requirement.polarity != "positive"
            or requirement.original_property_id_required is not True
            or requirement.object_type_evidence_required is not True
            or requirement.exact_row_provenance is not True
            or requirement.quarantined_allowed is not False
        ):
            raise ScienceRelationStageError(
                "compiler evidence requirement is incompatible with P17 stage"
            )

        subject = self.entity_for_alias(goal.subject)
        if subject is None:
            return ()
        choice_by_entity: dict[str, str] = {}
        for choice in compilation.choice_items:
            entity = self.entity_for_alias(choice.normalized_entity)
            if entity is None or goal.answer_type not in entity.answer_types:
                continue
            if entity.entity_id in choice_by_entity:
                raise ScienceRelationStageError(
                    "multiple choices bind the same staged entity"
                )
            choice_by_entity[entity.entity_id] = choice.key

        candidates: list[RelationProofCandidate] = []
        for relation in self.relations_for_subject(subject.entity_id):
            choice_key = choice_by_entity.get(relation.object_entity_id)
            if choice_key is None:
                continue
            obj = self._entity_by_id[relation.object_entity_id]
            evidence = (
                subject.binding_evidence,
                subject.type_evidence,
                obj.binding_evidence,
                obj.type_evidence,
                relation.evidence,
            )
            if len({row.evidence_id for row in evidence}) != len(evidence):
                raise ScienceRelationStageError(
                    "proof candidate evidence is not one-to-one"
                )
            evidence = tuple(
                sorted(evidence, key=lambda row: row.evidence_id)
            )
            digest = canonical_digest(
                {
                    "choice_key": choice_key,
                    "answer_type": goal.answer_type,
                    "semantic_fact": [
                        subject.entity_id,
                        "located_in",
                        obj.entity_id,
                    ],
                    "original_property_fact": list(relation.proof_fact),
                    "evidence": [row.to_dict() for row in evidence],
                }
            )
            candidates.append(
                RelationProofCandidate(
                    choice_key=choice_key,
                    answer_type=goal.answer_type,
                    subject=subject,
                    object=obj,
                    relation=relation,
                    evidence=evidence,
                    provenance_digest_sha256=digest,
                )
            )
        return tuple(
            sorted(
                candidates,
                key=lambda row: (row.choice_key, row.relation.row_id),
            )
        )


def _validate_evidence_rows(
    rows: list[dict[str, Any]],
    *,
    source_rows: tuple[bytes, ...],
    source_file_sha256: str,
) -> dict[str, RelationEvidenceRef]:
    evidence: dict[str, RelationEvidenceRef] = {}
    used_source_rows: set[int] = set()
    allowed_kinds = {
        "entity_binding": "rdfs:label",
        "answer_type": "P31",
        "typed_positive_relation_fact": "P17",
    }
    for index, row in enumerate(rows):
        _require_fields(row, _EVIDENCE_FIELDS, label=f"evidence[{index}]")
        evidence_id = row["evidence_id"]
        match = (
            _EVIDENCE_ID.fullmatch(evidence_id)
            if type(evidence_id) is str
            else None
        )
        if match is None or int(match.group(1)) != index + 1:
            raise ScienceRelationStageError(
                f"evidence[{index}].evidence_id invalid"
            )
        claim_kind = row["claim_kind"]
        if (
            type(claim_kind) is not str
            or claim_kind not in allowed_kinds
            or row["property_id"] != allowed_kinds[claim_kind]
        ):
            raise ScienceRelationStageError(
                f"evidence[{index}] kind/property invalid"
            )
        claim_digest = row["claim_digest_sha256"]
        if (
            type(claim_digest) is not str
            or _SHA256.fullmatch(claim_digest) is None
        ):
            raise ScienceRelationStageError(
                f"evidence[{index}].claim_digest invalid"
            )
        source_url = row["source_url"]
        url_match = (
            _SOURCE_URL.fullmatch(source_url)
            if type(source_url) is str
            else None
        )
        revision = row["source_revision"]
        record_id = row["source_record_id"]
        record_match = (
            _SOURCE_RECORD_ID.fullmatch(record_id)
            if type(record_id) is str
            else None
        )
        if (
            url_match is None
            or type(revision) is not str
            or _REVISION.fullmatch(revision) is None
            or revision != url_match.group(2)
            or record_match is None
            or record_match.group(1) != url_match.group(1)
            or row["license"] != "CC0-1.0"
        ):
            raise ScienceRelationStageError(
                f"evidence[{index}] provenance identity invalid"
            )
        source_row_number = row["source_row_number"]
        statement = row["source_statement"]
        statement_bytes = (
            statement.encode("utf-8")
            if type(statement) is str
            else b""
        )
        if (
            row["source_file_name"] != SOURCE_ROWS_NAME
            or row["source_file_sha256"] != source_file_sha256
            or type(source_row_number) is not int
            or source_row_number != index + 1
            or source_row_number > len(source_rows)
            or source_row_number in used_source_rows
            or not statement_bytes
            or source_rows[source_row_number - 1] != statement_bytes
            or type(row["source_statement_bytes"]) is not int
            or row["source_statement_bytes"] != len(statement_bytes)
            or type(row["source_statement_sha256"]) is not str
            or row["source_statement_sha256"] != _sha256(statement_bytes)
        ):
            raise ScienceRelationStageError(
                f"evidence[{index}] exact source-row binding invalid"
            )
        if row["externally_authenticated"] is not False:
            raise ScienceRelationStageError(
                "diagnostic stage cannot assert external authentication"
            )
        for forbidden in FORBIDDEN_RELATION_PROPERTY_IDS:
            if (
                row["property_id"] == forbidden
                or f"/{forbidden}>" in statement
                or f":{forbidden}:" in record_id
            ):
                raise ScienceRelationStageError(
                    "forbidden relation property reached P17 stage"
                )
        used_source_rows.add(source_row_number)
        evidence[evidence_id] = RelationEvidenceRef(
            evidence_id=evidence_id,
            claim_kind=claim_kind,
            claim_digest_sha256=claim_digest,
            property_id=row["property_id"],
            source_url=source_url,
            source_record_id=record_id,
            source_revision=revision,
            license=row["license"],
            source_file_name=row["source_file_name"],
            source_file_sha256=row["source_file_sha256"],
            source_row_number=source_row_number,
            source_statement=statement,
            source_statement_bytes=row["source_statement_bytes"],
            source_statement_sha256=row["source_statement_sha256"],
            externally_authenticated=False,
        )
    if used_source_rows != set(range(1, len(source_rows) + 1)):
        raise ScienceRelationStageError(
            "source rows are not exactly consumed by evidence"
        )
    return evidence


def load_science_relation_stage(
    root: str | Path,
) -> ScienceRelationStageSnapshot:
    """Load one all-or-nothing, property-preserving P17 stage."""

    stage_root = Path(root)
    if _is_link_or_reparse(stage_root) or not stage_root.is_dir():
        raise ScienceRelationStageError(
            "relation-stage root must be a regular directory"
        )
    expected_files = {
        MANIFEST_NAME,
        ENTITIES_NAME,
        RELATIONS_NAME,
        EVIDENCE_NAME,
        SOURCE_ROWS_NAME,
    }
    try:
        present = {entry.name for entry in stage_root.iterdir()}
    except OSError as exc:
        raise ScienceRelationStageError(
            "relation-stage directory is unreadable"
        ) from exc
    if present != expected_files:
        raise ScienceRelationStageError("relation-stage file set mismatch")

    manifest_bytes = _read_stable(stage_root / MANIFEST_NAME)
    entities_bytes = _read_stable(stage_root / ENTITIES_NAME)
    relations_bytes = _read_stable(stage_root / RELATIONS_NAME)
    evidence_bytes = _read_stable(stage_root / EVIDENCE_NAME)
    source_bytes = _read_stable(stage_root / SOURCE_ROWS_NAME)

    manifest = _strict_object(
        manifest_bytes,
        label="relation-stage manifest",
    )
    if manifest_bytes != canonical_json(manifest).encode("utf-8") + b"\n":
        raise ScienceRelationStageError(
            "relation-stage manifest is not canonical JSON"
        )
    _require_fields(
        manifest,
        _ROOT_FIELDS,
        label="relation-stage manifest",
    )
    if manifest["schema_version"] != SCIENCE_RELATION_STAGE_SCHEMA:
        raise ScienceRelationStageError("relation-stage schema mismatch")
    if (
        type(manifest["stage_id"]) is not str
        or _STAGE_ID.fullmatch(manifest["stage_id"]) is None
    ):
        raise ScienceRelationStageError("relation-stage id invalid")
    if (
        manifest["classification"]
        != "frozen_timeboxed_relation_diagnostic_not_e4_or_e5"
        or manifest["completion_state"] != "complete"
        or manifest["evaluation_only"] is not True
        or manifest["promotion_eligible"] is not False
    ):
        raise ScienceRelationStageError(
            "relation-stage authority or completion state invalid"
        )

    profile = _require_fields(
        manifest["relation_profile"],
        _PROFILE_FIELDS,
        label="relation_profile",
    )
    expected_profile = {
        "goal_family": SCIENCE_RELATION_GOAL_FAMILY,
        "predicate": "located_in",
        "polarity": "positive",
        "object_answer_types": ["country", "nation"],
        "source_property_id": RELATION_PROPERTY_ID,
        "located_in_cardinality": "multivalued",
    }
    if profile != expected_profile:
        raise ScienceRelationStageError(
            "relation-stage profile invalid"
        )
    policy = _require_fields(
        manifest["provenance_policy"],
        _POLICY_FIELDS,
        label="provenance_policy",
    )
    expected_policy = {
        "canonical_source_rows": True,
        "one_to_one_claim_evidence": True,
        "entity_binding_evidence_required": True,
        "answer_type_evidence_required": True,
        "original_property_id_required": True,
        "exact_source_statement_required": True,
        "source_file_digest_required": True,
        "source_revision_required": True,
        "license_required": True,
        "quarantined_rows_allowed": False,
        "network_access_allowed": False,
        "external_authentication_required": False,
    }
    if (
        any(type(policy[key]) is not bool for key in expected_policy)
        or policy != expected_policy
    ):
        raise ScienceRelationStageError(
            "relation-stage provenance policy invalid"
        )
    source = _require_fields(
        manifest["source_dataset"],
        _SOURCE_FIELDS,
        label="source_dataset",
    )
    expected_source = {
        "name": "Wikidata",
        "snapshot_kind": "property_preserving_truthy_rows",
        "source_file_name": SOURCE_ROWS_NAME,
        "relation_property_id": RELATION_PROPERTY_ID,
        "forbidden_relation_property_ids": list(
            FORBIDDEN_RELATION_PROPERTY_IDS
        ),
        "license": "CC0-1.0",
    }
    if source != expected_source:
        raise ScienceRelationStageError(
            "relation-stage source dataset invalid"
        )
    claims = _require_fields(
        manifest["claims"],
        _CLAIM_FIELDS,
        label="claims",
    )
    if (
        any(type(claims[key]) is not bool for key in _CLAIM_FIELDS)
        or any(claims.values())
    ):
        raise ScienceRelationStageError(
            "relation-stage authority claims must all remain false"
        )
    checksum = manifest["manifest_checksum_sha256"]
    if (
        type(checksum) is not str
        or _SHA256.fullmatch(checksum) is None
        or checksum != _manifest_checksum(manifest)
    ):
        raise ScienceRelationStageError(
            "relation-stage manifest checksum mismatch"
        )

    for field_name, filename, payload in (
        ("entities_file", ENTITIES_NAME, entities_bytes),
        ("relations_file", RELATIONS_NAME, relations_bytes),
        ("evidence_file", EVIDENCE_NAME, evidence_bytes),
        ("source_rows_file", SOURCE_ROWS_NAME, source_bytes),
    ):
        _validate_file_binding(
            manifest[field_name],
            expected_path=filename,
            payload=payload,
            label=field_name,
        )

    entity_rows = _parse_jsonl(
        entities_bytes,
        label="entities",
        maximum=MAX_ENTITY_ROWS,
    )
    relation_rows = _parse_jsonl(
        relations_bytes,
        label="relations",
        maximum=MAX_RELATION_ROWS,
    )
    evidence_rows = _parse_jsonl(
        evidence_bytes,
        label="evidence",
        maximum=MAX_EVIDENCE_ROWS,
    )
    source_rows = _parse_source_rows(source_bytes)
    for count_name, rows in (
        ("entity_count", entity_rows),
        ("relation_count", relation_rows),
        ("evidence_count", evidence_rows),
    ):
        count = manifest[count_name]
        if type(count) is not int or count != len(rows):
            raise ScienceRelationStageError(
                "relation-stage row counts do not align"
            )
    if len(source_rows) != len(evidence_rows):
        raise ScienceRelationStageError(
            "source and evidence rows do not align"
        )

    evidence = _validate_evidence_rows(
        evidence_rows,
        source_rows=source_rows,
        source_file_sha256=_sha256(source_bytes),
    )
    used_evidence: set[str] = set()
    staged_entities: list[StagedRelationEntity] = []
    entity_ids: set[str] = set()
    normalized_aliases: set[str] = set()
    for index, row in enumerate(entity_rows):
        _require_fields(row, _ENTITY_FIELDS, label=f"entities[{index}]")
        row_match = (
            _ENTITY_ROW_ID.fullmatch(row["row_id"])
            if type(row["row_id"]) is str
            else None
        )
        entity_id = row["entity_id"]
        label = row["label"]
        aliases = row["aliases"]
        answer_types = row["answer_types"]
        type_entity_id = row["type_entity_id"]
        if (
            row_match is None
            or int(row_match.group(1)) != index + 1
            or type(entity_id) is not str
            or _QID.fullmatch(entity_id) is None
            or entity_id in entity_ids
            or type(label) is not str
            or _LABEL.fullmatch(label) is None
            or label != " ".join(label.split())
            or type(aliases) is not list
            or not 1 <= len(aliases) <= MAX_ALIASES_PER_ENTITY
            or any(type(alias) is not str for alias in aliases)
            or aliases != sorted(set(aliases))
            or aliases != [label]
            or type(answer_types) is not list
            or any(type(item) is not str for item in answer_types)
            or type(type_entity_id) is not str
            or tuple(answer_types) != _TYPE_PROFILES.get(type_entity_id)
            or row["quarantined"] is not False
        ):
            raise ScienceRelationStageError(
                f"entities[{index}] contract invalid"
            )
        alias_keys = [_normalize_alias(alias) for alias in aliases]
        if (
            any(not key for key in alias_keys)
            or len(alias_keys) != len(set(alias_keys))
            or any(key in normalized_aliases for key in alias_keys)
        ):
            raise ScienceRelationStageError(
                f"entities[{index}] alias binding is ambiguous"
            )

        binding = evidence.get(row["binding_evidence_id"])
        type_ref = evidence.get(row["type_evidence_id"])
        binding_claim = canonical_digest(
            {
                "kind": "entity_binding",
                "entity_id": entity_id,
                "label": label,
                "aliases": aliases,
                "normalized_aliases": alias_keys,
            }
        )
        type_claim = canonical_digest(
            {
                "kind": "answer_type",
                "entity_id": entity_id,
                "answer_types": answer_types,
                "type_entity_id": type_entity_id,
            }
        )
        if (
            binding is None
            or binding.claim_kind != "entity_binding"
            or binding.property_id != "rdfs:label"
            or binding.claim_digest_sha256 != binding_claim
            or binding.source_statement != _label_statement(entity_id, label)
            or type_ref is None
            or type_ref.claim_kind != "answer_type"
            or type_ref.property_id != "P31"
            or type_ref.claim_digest_sha256 != type_claim
            or type_ref.source_statement
            != _direct_statement(entity_id, "P31", type_entity_id)
            or binding.evidence_id in used_evidence
            or type_ref.evidence_id in used_evidence
            or binding.evidence_id == type_ref.evidence_id
        ):
            raise ScienceRelationStageError(
                f"entities[{index}] proof binding invalid"
            )
        entity_ids.add(entity_id)
        normalized_aliases.update(alias_keys)
        used_evidence.update(
            {binding.evidence_id, type_ref.evidence_id}
        )
        staged_entities.append(
            StagedRelationEntity(
                row_id=row["row_id"],
                entity_id=entity_id,
                label=label,
                aliases=tuple(aliases),
                answer_types=tuple(answer_types),
                type_entity_id=type_entity_id,
                binding_evidence=binding,
                type_evidence=type_ref,
            )
        )

    staged_relations: list[StagedRelationFact] = []
    relation_triples: set[tuple[str, str, str]] = set()
    for index, row in enumerate(relation_rows):
        _require_fields(
            row,
            _RELATION_FIELDS,
            label=f"relations[{index}]",
        )
        row_match = (
            _RELATION_ROW_ID.fullmatch(row["row_id"])
            if type(row["row_id"]) is str
            else None
        )
        subject_id = row["subject_entity_id"]
        object_id = row["object_entity_id"]
        if (
            row_match is None
            or int(row_match.group(1)) != index + 1
            or type(subject_id) is not str
            or subject_id not in entity_ids
            or type(object_id) is not str
            or object_id not in entity_ids
            or row["predicate"] != "located_in"
            or row["polarity"] != "positive"
            or row["source_property_id"] != RELATION_PROPERTY_ID
            or row["quarantined"] is not False
        ):
            raise ScienceRelationStageError(
                f"relations[{index}] P17 contract invalid"
            )
        obj = next(
            entity
            for entity in staged_entities
            if entity.entity_id == object_id
        )
        if not OBJECT_ANSWER_TYPES.issubset(obj.answer_types):
            raise ScienceRelationStageError(
                f"relations[{index}] object lacks country/nation proof"
            )
        triple = (subject_id, RELATION_PROPERTY_ID, object_id)
        if triple in relation_triples:
            raise ScienceRelationStageError(
                f"relations[{index}] duplicates a P17 proof"
            )
        ref = evidence.get(row["evidence_id"])
        claim_digest = canonical_digest(
            {
                "kind": "typed_positive_relation_fact",
                "subject_entity_id": subject_id,
                "predicate": "located_in",
                "polarity": "positive",
                "source_property_id": RELATION_PROPERTY_ID,
                "object_entity_id": object_id,
                "object_answer_types": list(obj.answer_types),
            }
        )
        if (
            ref is None
            or ref.claim_kind != "typed_positive_relation_fact"
            or ref.property_id != RELATION_PROPERTY_ID
            or ref.claim_digest_sha256 != claim_digest
            or ref.source_statement
            != _direct_statement(
                subject_id,
                RELATION_PROPERTY_ID,
                object_id,
            )
            or ref.evidence_id in used_evidence
        ):
            raise ScienceRelationStageError(
                f"relations[{index}] proof binding invalid"
            )
        relation_triples.add(triple)
        used_evidence.add(ref.evidence_id)
        staged_relations.append(
            StagedRelationFact(
                row_id=row["row_id"],
                subject_entity_id=subject_id,
                predicate="located_in",
                polarity="positive",
                source_property_id=RELATION_PROPERTY_ID,
                object_entity_id=object_id,
                evidence=ref,
            )
        )
    if used_evidence != set(evidence):
        raise ScienceRelationStageError(
            "relation-stage contains orphan or reused evidence"
        )

    entities_tuple = tuple(staged_entities)
    relations_tuple = tuple(staged_relations)
    by_id = MappingProxyType(
        {row.entity_id: row for row in entities_tuple}
    )
    by_alias = MappingProxyType(
        {
            _normalize_alias(alias): row
            for row in entities_tuple
            for alias in row.aliases
        }
    )
    grouped: dict[str, list[StagedRelationFact]] = {}
    for row in relations_tuple:
        grouped.setdefault(row.subject_entity_id, []).append(row)
    by_subject = MappingProxyType(
        {
            key: tuple(sorted(rows, key=lambda item: item.row_id))
            for key, rows in sorted(grouped.items())
        }
    )
    stage_digest = canonical_digest(
        {
            "schema_version": SCIENCE_RELATION_STAGE_SCHEMA,
            "stage_id": manifest["stage_id"],
            "manifest_checksum_sha256": checksum,
            "entities_sha256": _sha256(entities_bytes),
            "relations_sha256": _sha256(relations_bytes),
            "evidence_sha256": _sha256(evidence_bytes),
            "source_rows_sha256": _sha256(source_bytes),
            "entity_count": len(entities_tuple),
            "relation_count": len(relations_tuple),
            "evidence_count": len(evidence),
        }
    )
    bound_bytes = sum(
        len(payload)
        for payload in (
            manifest_bytes,
            entities_bytes,
            relations_bytes,
            evidence_bytes,
            source_bytes,
        )
    )
    seal = _snapshot_tag(
        stage_id=manifest["stage_id"],
        stage_digest_sha256=stage_digest,
        manifest_checksum_sha256=checksum,
        bound_bytes=bound_bytes,
        entities=entities_tuple,
        relations=relations_tuple,
    )
    return ScienceRelationStageSnapshot(
        stage_id=manifest["stage_id"],
        stage_digest_sha256=stage_digest,
        manifest_checksum_sha256=checksum,
        bound_bytes=bound_bytes,
        entities=entities_tuple,
        relations=relations_tuple,
        authority_claims=MappingProxyType(dict(sorted(claims.items()))),
        _entity_by_alias=by_alias,
        _entity_by_id=by_id,
        _relations_by_subject=by_subject,
        _validation_seal=seal,
    )
