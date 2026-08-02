"""Strict, source-driven Wikidata property catalog for graph auto-binding.

The catalog is a read-only staging boundary.  It derives property identifiers,
English labels, English aliases, and datatypes exclusively from bound
Wikidata-shaped source records.  No relation-name vocabulary is embedded here,
and this module does not write to a graph, access a network, select an answer,
or establish source authenticity or model capability.

V1 deliberately fails closed on normalized label/alias collisions.  Real
Wikidata can contain such collisions; a later linker may preserve and
disambiguate them explicitly, but it must not silently choose one property.

The SQLite adapter also supports dump-bound snapshots whose truthy export does
not carry property revisions.  Such entries retain ``source_revision=None``
and bind instead to the canonical SQLite-view/dump snapshot digest.  A missing
revision is never replaced with a sentinel or inferred value.
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
import sqlite3
import stat
from types import MappingProxyType
from typing import Any
import unicodedata

from packages.cognitive_core.canonical import canonical_digest, canonical_json


SCHEMA_VERSION = "atanor.wikidata-property-catalog-stage.v1"
MANIFEST_NAME = "manifest.json"
PROPERTIES_NAME = "wikidata_property_records.jsonl"

MAX_BOUND_FILE_BYTES = 2 * 1024 * 1024
MAX_PROPERTY_ROWS = 100_000
MAX_LINE_BYTES = 256 * 1024
MAX_ALIASES_PER_PROPERTY = 256
MAX_SURFACE_BYTES = 512

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PID = re.compile(r"P([1-9]\d{0,11})\Z")
_DATATYPE = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_WIKIBASE_DATATYPE_IRI = re.compile(
    r"http://wikiba\.se/ontology#[A-Za-z][A-Za-z0-9]{0,63}\Z"
)
_CATALOG_ID = re.compile(
    r"wikidata-property-catalog-[a-z0-9-]+-v[1-9]\d*\Z"
)
_VALIDATION_KEY = os.urandom(32)

_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "catalog_id",
        "classification",
        "completion_state",
        "evaluation_only",
        "promotion_eligible",
        "property_count",
        "properties_file",
        "source_dataset",
        "provenance_policy",
        "claims",
        "manifest_checksum_sha256",
    }
)
_FILE_FIELDS = frozenset({"path", "bytes", "sha256"})
_SOURCE_FIELDS = frozenset(
    {"name", "snapshot_kind", "language", "license"}
)
_POLICY_FIELDS = frozenset(
    {
        "canonical_jsonl_required",
        "exact_source_record_required",
        "source_file_digest_required",
        "source_revision_required",
        "original_property_id_required",
        "source_driven_predicate_vocabulary",
        "ambiguous_surface_selection_allowed",
        "network_access_allowed",
        "shipped_graph_writes_allowed",
        "external_authentication_required",
    }
)
_CLAIM_FIELDS = frozenset(
    {
        "capability_claimed",
        "e4_claimed",
        "e5_claimed",
        "independent_evaluator_claimed",
        "external_authenticity_established",
        "autonomous_mining_established",
    }
)
_PROPERTY_FIELDS = frozenset(
    {"aliases", "datatype", "id", "labels", "lastrevid", "type"}
)
_LANGUAGE_MAP_FIELDS = frozenset({"en"})
_TERM_FIELDS = frozenset({"language", "value"})

_EXPECTED_SOURCE = {
    "name": "Wikidata",
    "snapshot_kind": "property_entitydata_jsonl",
    "language": "en",
    "license": "CC0-1.0",
}
_EXPECTED_POLICY = {
    "canonical_jsonl_required": True,
    "exact_source_record_required": True,
    "source_file_digest_required": True,
    "source_revision_required": True,
    "original_property_id_required": True,
    "source_driven_predicate_vocabulary": True,
    "ambiguous_surface_selection_allowed": False,
    "network_access_allowed": False,
    "shipped_graph_writes_allowed": False,
    "external_authentication_required": False,
}
_SQLITE_SNAPSHOT_POLICY = {
    **_EXPECTED_POLICY,
    "source_revision_required": False,
}


class WikidataPropertyCatalogError(RuntimeError):
    """Raised when a property-catalog generation cannot be trusted."""


@dataclass(frozen=True, slots=True)
class _FileIdentity:
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int


def _identity_from_stat(value: os.stat_result) -> _FileIdentity:
    return _FileIdentity(
        device=int(getattr(value, "st_dev", 0)),
        inode=int(getattr(value, "st_ino", 0)),
        mode=int(value.st_mode),
        size=int(value.st_size),
        modified_ns=int(value.st_mtime_ns),
        changed_ns=int(value.st_ctime_ns),
    )


def _same_opened_path_identity(
    left: _FileIdentity,
    right: _FileIdentity,
) -> bool:
    """Compare handle/path identity without Windows' incompatible ctime view."""

    return (
        left.device,
        left.inode,
        left.mode,
        left.size,
        left.modified_ns,
    ) == (
        right.device,
        right.inode,
        right.mode,
        right.size,
        right.modified_ns,
    )


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


def _capture_identity(
    path: Path,
    *,
    require_directory: bool = False,
) -> _FileIdentity:
    if _is_link_or_reparse(path):
        raise WikidataPropertyCatalogError(
            f"catalog path is a link or reparse point: {path.name}"
        )
    try:
        value = os.lstat(path)
    except OSError as exc:
        raise WikidataPropertyCatalogError(
            f"catalog path is unreadable: {path.name}"
        ) from exc
    if require_directory:
        valid_kind = stat.S_ISDIR(value.st_mode)
    else:
        valid_kind = stat.S_ISREG(value.st_mode)
    if not valid_kind:
        expected = "directory" if require_directory else "regular file"
        raise WikidataPropertyCatalogError(
            f"catalog path is not a {expected}: {path.name}"
        )
    return _identity_from_stat(value)


def _read_stable(path: Path) -> bytes:
    path_before = _capture_identity(path)
    if not 0 < path_before.size <= MAX_BOUND_FILE_BYTES:
        raise WikidataPropertyCatalogError(
            f"catalog file size invalid: {path.name}"
        )
    try:
        with path.open("rb") as handle:
            opened_before = _identity_from_stat(os.fstat(handle.fileno()))
            if not _same_opened_path_identity(opened_before, path_before):
                raise WikidataPropertyCatalogError(
                    f"catalog file changed before reading: {path.name}"
                )
            payload = handle.read(MAX_BOUND_FILE_BYTES + 1)
            opened_after = _identity_from_stat(os.fstat(handle.fileno()))
    except WikidataPropertyCatalogError:
        raise
    except OSError as exc:
        raise WikidataPropertyCatalogError(
            f"catalog file is unreadable: {path.name}"
        ) from exc
    path_after = _capture_identity(path)
    if (
        len(payload) != path_before.size
        or len(payload) > MAX_BOUND_FILE_BYTES
        or opened_before != opened_after
        or not _same_opened_path_identity(opened_after, path_after)
        or path_before != path_after
    ):
        raise WikidataPropertyCatalogError(
            f"catalog file changed while reading: {path.name}"
        )
    return payload


def _read_generation(root: Path) -> tuple[bytes, bytes]:
    root_before = _capture_identity(root, require_directory=True)
    expected = {MANIFEST_NAME, PROPERTIES_NAME}
    try:
        present = {entry.name for entry in root.iterdir()}
    except OSError as exc:
        raise WikidataPropertyCatalogError(
            "catalog directory is unreadable"
        ) from exc
    if present != expected:
        raise WikidataPropertyCatalogError("catalog file set mismatch")

    paths = (root / MANIFEST_NAME, root / PROPERTIES_NAME)
    files_before = tuple(_capture_identity(path) for path in paths)
    manifest_bytes = _read_stable(paths[0])
    properties_bytes = _read_stable(paths[1])
    files_after = tuple(_capture_identity(path) for path in paths)
    root_after = _capture_identity(root, require_directory=True)
    if root_before != root_after or files_before != files_after:
        raise WikidataPropertyCatalogError(
            "catalog generation changed while reading"
        )
    return manifest_bytes, properties_bytes


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WikidataPropertyCatalogError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise WikidataPropertyCatalogError(f"non-finite JSON number: {token}")


def _strict_object(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_nonfinite,
        )
    except WikidataPropertyCatalogError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise WikidataPropertyCatalogError(
            f"{label} is not strict readable JSON: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise WikidataPropertyCatalogError(f"{label} root must be an object")
    return value


def _require_fields(
    value: Any,
    expected: frozenset[str],
    *,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != expected:
        raise WikidataPropertyCatalogError(f"{label} fields mismatch")
    return value


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest_checksum(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_checksum_sha256", None)
    return _sha256(canonical_json(unsigned).encode("utf-8"))


def _surface_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _validate_surface(value: Any, *, label: str) -> str:
    if type(value) is not str:
        raise WikidataPropertyCatalogError(f"{label} must be exact text")
    if (
        not value
        or len(value.encode("utf-8")) > MAX_SURFACE_BYTES
        or unicodedata.normalize("NFKC", value) != value
        or " ".join(value.split()) != value
        or any(unicodedata.category(char) == "Cc" for char in value)
    ):
        raise WikidataPropertyCatalogError(f"{label} text is not canonical")
    return value


def _canonicalize_sqlite_surface(value: str) -> str | None:
    """Normalize one source surface without fabricating lexical content."""

    canonical = " ".join(unicodedata.normalize("NFKC", value).split())
    if (
        not canonical
        or len(canonical.encode("utf-8")) > MAX_SURFACE_BYTES
        or any(unicodedata.category(char) == "Cc" for char in canonical)
    ):
        return None
    return canonical


def _parse_jsonl(payload: bytes) -> tuple[tuple[dict[str, Any], bytes], ...]:
    if not payload.endswith(b"\n") or b"\r" in payload or payload.startswith(
        b"\xef\xbb\xbf"
    ):
        raise WikidataPropertyCatalogError(
            "property records must be LF-terminated canonical UTF-8 JSONL"
        )
    lines = payload.splitlines()
    if not 1 <= len(lines) <= MAX_PROPERTY_ROWS:
        raise WikidataPropertyCatalogError(
            "property record count is out of bounds"
        )
    rows: list[tuple[dict[str, Any], bytes]] = []
    for index, line in enumerate(lines, start=1):
        if not line or len(line) > MAX_LINE_BYTES:
            raise WikidataPropertyCatalogError(
                f"property record {index} size invalid"
            )
        record = _strict_object(line, label=f"property record {index}")
        if canonical_json(record).encode("utf-8") != line:
            raise WikidataPropertyCatalogError(
                f"property record {index} is not canonical JSON"
            )
        rows.append((record, line))
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class WikidataPropertyEvidence:
    source_artifact_kind: str
    source_file_name: str
    source_file_sha256: str
    source_row_number: int
    source_record: str
    source_record_byte_count: int
    source_record_sha256: str
    source_snapshot_checksum_sha256: str
    source_revision: int | None
    source_revision_status: str
    source_url: str
    license: str
    externally_authenticated: bool

    @property
    def exact_source_record_bytes(self) -> bytes:
        return self.source_record.encode("utf-8")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WikidataProperty:
    property_id: str
    label: str
    aliases: tuple[str, ...]
    datatype: str
    evidence: WikidataPropertyEvidence

    @property
    def surfaces(self) -> tuple[str, ...]:
        return (self.label, *self.aliases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "property_id": self.property_id,
            "label": self.label,
            "aliases": list(self.aliases),
            "datatype": self.datatype,
            "evidence": self.evidence.to_dict(),
        }


def _snapshot_tag(
    *,
    catalog_id: str,
    catalog_digest_sha256: str,
    manifest_checksum_sha256: str,
    bound_bytes: int,
    entries: tuple[WikidataProperty, ...],
    provenance_policy: Mapping[str, bool],
    authority_claims: Mapping[str, bool],
    revision_unavailable_count: int,
    excluded_unlabeled_property_ids: tuple[str, ...],
) -> str:
    payload = {
        "catalog_id": catalog_id,
        "catalog_digest_sha256": catalog_digest_sha256,
        "manifest_checksum_sha256": manifest_checksum_sha256,
        "bound_bytes": bound_bytes,
        "entries": [entry.to_dict() for entry in entries],
        "provenance_policy": dict(provenance_policy),
        "authority_claims": dict(authority_claims),
        "revision_unavailable_count": revision_unavailable_count,
        "excluded_unlabeled_property_ids": list(
            excluded_unlabeled_property_ids
        ),
    }
    return hmac.new(
        _VALIDATION_KEY,
        canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class WikidataPropertyCatalogSnapshot:
    """Detached immutable snapshot of one validated catalog generation."""

    catalog_id: str
    catalog_digest_sha256: str
    manifest_checksum_sha256: str
    bound_bytes: int
    entries: tuple[WikidataProperty, ...]
    provenance_policy: Mapping[str, bool]
    authority_claims: Mapping[str, bool]
    revision_unavailable_count: int
    excluded_unlabeled_property_ids: tuple[str, ...]
    _by_pid: Mapping[str, WikidataProperty]
    _by_surface: Mapping[str, tuple[WikidataProperty, ...]]
    _validation_seal: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        self.assert_validated()

    def assert_validated(self) -> None:
        expected_tag = _snapshot_tag(
            catalog_id=self.catalog_id,
            catalog_digest_sha256=self.catalog_digest_sha256,
            manifest_checksum_sha256=self.manifest_checksum_sha256,
            bound_bytes=self.bound_bytes,
            entries=self.entries,
            provenance_policy=self.provenance_policy,
            authority_claims=self.authority_claims,
            revision_unavailable_count=self.revision_unavailable_count,
            excluded_unlabeled_property_ids=(
                self.excluded_unlabeled_property_ids
            ),
        )
        expected_pid = {entry.property_id: entry for entry in self.entries}
        grouped: dict[str, list[WikidataProperty]] = {}
        for entry in self.entries:
            for surface in entry.surfaces:
                grouped.setdefault(_surface_key(surface), []).append(entry)
        expected_surface = {
            key: tuple(sorted(values, key=lambda item: item.property_id))
            for key, values in grouped.items()
        }
        policy = dict(self.provenance_policy)
        expected_revision_unavailable = sum(
            entry.evidence.source_revision is None
            for entry in self.entries
        )
        evidence_status_valid = all(
            entry.evidence.source_snapshot_checksum_sha256
            == self.manifest_checksum_sha256
            and (
                (
                    entry.evidence.source_revision is None
                    and entry.evidence.source_revision_status
                    == "unavailable_bound_to_snapshot_digest"
                )
                or (
                    type(entry.evidence.source_revision) is int
                    and entry.evidence.source_revision > 0
                    and entry.evidence.source_revision_status
                    == "available"
                )
            )
            for entry in self.entries
        )
        excluded_ids_valid = all(
            type(property_id) is str
            and _PID.fullmatch(property_id) is not None
            for property_id in self.excluded_unlabeled_property_ids
        )
        excluded_ids_canonical = (
            excluded_ids_valid
            and len(set(self.excluded_unlabeled_property_ids))
            == len(self.excluded_unlabeled_property_ids)
            and self.excluded_unlabeled_property_ids
            == tuple(
                sorted(
                    self.excluded_unlabeled_property_ids,
                    key=lambda property_id: int(property_id[1:]),
                )
            )
            and not set(self.excluded_unlabeled_property_ids).intersection(
                expected_pid
            )
        )
        if (
            type(self._validation_seal) is not str
            or not hmac.compare_digest(expected_tag, self._validation_seal)
            or dict(self._by_pid) != expected_pid
            or dict(self._by_surface) != expected_surface
            or policy not in (_EXPECTED_POLICY, _SQLITE_SNAPSHOT_POLICY)
            or frozenset(self.authority_claims) != _CLAIM_FIELDS
            or set(self.authority_claims.values()) != {False}
            or type(self.revision_unavailable_count) is not int
            or self.revision_unavailable_count
            != expected_revision_unavailable
            or (
                policy["source_revision_required"]
                and self.revision_unavailable_count != 0
            )
            or not evidence_status_valid
            or not excluded_ids_canonical
        ):
            raise WikidataPropertyCatalogError(
                "property catalog validation seal does not bind content"
            )

    @property
    def excluded_unlabeled_property_count(self) -> int:
        self.assert_validated()
        return len(self.excluded_unlabeled_property_ids)

    def property_by_id(self, property_id: Any) -> WikidataProperty | None:
        self.assert_validated()
        if type(property_id) is not str:
            return None
        return self._by_pid.get(property_id)

    def resolve_surface(self, surface: Any) -> WikidataProperty | None:
        """Resolve one unambiguous source label/alias, else abstain."""

        self.assert_validated()
        if type(surface) is not str:
            return None
        key = _surface_key(surface)
        if not key:
            return None
        candidates = self._by_surface.get(key, ())
        return candidates[0] if len(candidates) == 1 else None

    def properties_for_surface(
        self,
        surface: Any,
    ) -> tuple[WikidataProperty, ...]:
        """Expose all source candidates for graph-conditioned disambiguation."""

        self.assert_validated()
        if type(surface) is not str:
            return ()
        key = _surface_key(surface)
        if not key:
            return ()
        return self._by_surface.get(key, ())


def _parse_property(
    record: dict[str, Any],
    source_line: bytes,
    *,
    row_number: int,
    source_file_sha256: str,
    source_file_name: str,
    source_artifact_kind: str,
    license_name: str,
    source_snapshot_checksum_sha256: str,
    source_revision_required: bool,
) -> WikidataProperty:
    _require_fields(
        record,
        _PROPERTY_FIELDS,
        label=f"property record {row_number}",
    )
    property_id = record["id"]
    if type(property_id) is not str or _PID.fullmatch(property_id) is None:
        raise WikidataPropertyCatalogError(
            f"property record {row_number} id invalid"
        )
    if record["type"] != "property":
        raise WikidataPropertyCatalogError(
            f"property record {row_number} type invalid"
        )
    datatype = record["datatype"]
    if type(datatype) is not str or (
        _DATATYPE.fullmatch(datatype) is None
        and _WIKIBASE_DATATYPE_IRI.fullmatch(datatype) is None
    ):
        raise WikidataPropertyCatalogError(
            f"property record {row_number} datatype invalid"
        )
    revision = record["lastrevid"]
    if revision is None:
        if source_revision_required:
            raise WikidataPropertyCatalogError(
                f"property record {row_number} revision missing"
            )
    elif type(revision) is not int or not 0 < revision <= 10**20:
        raise WikidataPropertyCatalogError(
            f"property record {row_number} revision invalid"
        )

    labels = _require_fields(
        record["labels"],
        _LANGUAGE_MAP_FIELDS,
        label=f"property record {row_number} labels",
    )
    label_term = _require_fields(
        labels["en"],
        _TERM_FIELDS,
        label=f"property record {row_number} label",
    )
    if label_term["language"] != "en":
        raise WikidataPropertyCatalogError(
            f"property record {row_number} label language invalid"
        )
    label = _validate_surface(
        label_term["value"],
        label=f"property record {row_number} label",
    )

    aliases_map = _require_fields(
        record["aliases"],
        _LANGUAGE_MAP_FIELDS,
        label=f"property record {row_number} aliases",
    )
    alias_terms = aliases_map["en"]
    if (
        type(alias_terms) is not list
        or len(alias_terms) > MAX_ALIASES_PER_PROPERTY
    ):
        raise WikidataPropertyCatalogError(
            f"property record {row_number} aliases invalid"
        )
    aliases: list[str] = []
    seen = {_surface_key(label)}
    for alias_index, raw_term in enumerate(alias_terms):
        term = _require_fields(
            raw_term,
            _TERM_FIELDS,
            label=f"property record {row_number} alias {alias_index}",
        )
        if term["language"] != "en":
            raise WikidataPropertyCatalogError(
                f"property record {row_number} alias language invalid"
            )
        alias = _validate_surface(
            term["value"],
            label=f"property record {row_number} alias {alias_index}",
        )
        key = _surface_key(alias)
        if key in seen:
            raise WikidataPropertyCatalogError(
                f"property record {row_number} has duplicate label or alias"
            )
        seen.add(key)
        aliases.append(alias)
    if aliases != sorted(aliases, key=lambda value: (_surface_key(value), value)):
        raise WikidataPropertyCatalogError(
            f"property record {row_number} aliases are not canonical order"
        )

    source_record = source_line.decode("utf-8")
    evidence = WikidataPropertyEvidence(
        source_artifact_kind=source_artifact_kind,
        source_file_name=source_file_name,
        source_file_sha256=source_file_sha256,
        source_row_number=row_number,
        source_record=source_record,
        source_record_byte_count=len(source_line),
        source_record_sha256=_sha256(source_line),
        source_snapshot_checksum_sha256=(
            source_snapshot_checksum_sha256
        ),
        source_revision=revision,
        source_revision_status=(
            "available"
            if revision is not None
            else "unavailable_bound_to_snapshot_digest"
        ),
        source_url=(
            "https://www.wikidata.org/wiki/Special:EntityData/"
            f"{property_id}.json"
            + (f"?revision={revision}" if revision is not None else "")
        ),
        license=license_name,
        externally_authenticated=False,
    )
    return WikidataProperty(
        property_id=property_id,
        label=label,
        aliases=tuple(aliases),
        datatype=datatype,
        evidence=evidence,
    )


def _assemble_catalog(
    *,
    catalog_id: str,
    manifest_checksum_sha256: str,
    bound_bytes: int,
    source_rows: tuple[tuple[dict[str, Any], bytes], ...],
    source_artifact_name: str,
    source_artifact_kind: str,
    source_artifact_sha256: str,
    license_name: str,
    policy: Mapping[str, bool],
    claims: Mapping[str, bool],
    excluded_unlabeled_property_ids: tuple[str, ...] = (),
) -> WikidataPropertyCatalogSnapshot:
    entries: list[WikidataProperty] = []
    seen_pids: set[str] = set()
    previous_pid_number = 0
    for row_number, (record, source_line) in enumerate(
        source_rows,
        start=1,
    ):
        if (
            not source_line
            or len(source_line) > MAX_LINE_BYTES
            or canonical_json(record).encode("utf-8") != source_line
        ):
            raise WikidataPropertyCatalogError(
                f"property record {row_number} is not canonical"
            )
        entry = _parse_property(
            record,
            source_line,
            row_number=row_number,
            source_file_sha256=source_artifact_sha256,
            source_file_name=source_artifact_name,
            source_artifact_kind=source_artifact_kind,
            license_name=license_name,
            source_snapshot_checksum_sha256=(
                manifest_checksum_sha256
            ),
            source_revision_required=policy[
                "source_revision_required"
            ],
        )
        if entry.property_id in seen_pids:
            raise WikidataPropertyCatalogError(
                f"duplicate property id: {entry.property_id}"
            )
        seen_pids.add(entry.property_id)
        match = _PID.fullmatch(entry.property_id)
        if match is None:  # already checked by _parse_property
            raise WikidataPropertyCatalogError("property id invariant failed")
        pid_number = int(match.group(1))
        if pid_number <= previous_pid_number:
            raise WikidataPropertyCatalogError(
                "property records are not canonical PID order"
            )
        previous_pid_number = pid_number
        entries.append(entry)

    frozen_entries = tuple(entries)
    by_pid = MappingProxyType(
        {entry.property_id: entry for entry in frozen_entries}
    )
    surface_groups: dict[str, list[WikidataProperty]] = {}
    for entry in frozen_entries:
        for surface in entry.surfaces:
            surface_groups.setdefault(_surface_key(surface), []).append(entry)
    by_surface = MappingProxyType(
        {
            key: tuple(sorted(values, key=lambda item: item.property_id))
            for key, values in sorted(surface_groups.items())
        }
    )
    frozen_policy = MappingProxyType(dict(sorted(policy.items())))
    frozen_claims = MappingProxyType(dict(sorted(claims.items())))
    revision_unavailable_count = sum(
        entry.evidence.source_revision is None
        for entry in frozen_entries
    )
    catalog_digest = canonical_digest(
        {
            "catalog_id": catalog_id,
            "manifest_checksum_sha256": manifest_checksum_sha256,
            "source_artifact_kind": source_artifact_kind,
            "source_artifact_name": source_artifact_name,
            "source_artifact_sha256": source_artifact_sha256,
            "entries": [entry.to_dict() for entry in frozen_entries],
            "revision_unavailable_count": revision_unavailable_count,
            "excluded_unlabeled_property_ids": list(
                excluded_unlabeled_property_ids
            ),
        }
    )
    validation_seal = _snapshot_tag(
        catalog_id=catalog_id,
        catalog_digest_sha256=catalog_digest,
        manifest_checksum_sha256=manifest_checksum_sha256,
        bound_bytes=bound_bytes,
        entries=frozen_entries,
        provenance_policy=frozen_policy,
        authority_claims=frozen_claims,
        revision_unavailable_count=revision_unavailable_count,
        excluded_unlabeled_property_ids=(
            excluded_unlabeled_property_ids
        ),
    )
    return WikidataPropertyCatalogSnapshot(
        catalog_id=catalog_id,
        catalog_digest_sha256=catalog_digest,
        manifest_checksum_sha256=manifest_checksum_sha256,
        bound_bytes=bound_bytes,
        entries=frozen_entries,
        provenance_policy=frozen_policy,
        authority_claims=frozen_claims,
        revision_unavailable_count=revision_unavailable_count,
        excluded_unlabeled_property_ids=(
            excluded_unlabeled_property_ids
        ),
        _by_pid=by_pid,
        _by_surface=by_surface,
        _validation_seal=validation_seal,
    )


def load_wikidata_property_catalog(
    root: str | Path,
) -> WikidataPropertyCatalogSnapshot:
    """Load one all-or-nothing, source-driven property catalog generation."""

    stage_root = Path(root)
    manifest_bytes, properties_bytes = _read_generation(stage_root)

    manifest = _strict_object(
        manifest_bytes,
        label="property catalog manifest",
    )
    if manifest_bytes != canonical_json(manifest).encode("utf-8") + b"\n":
        raise WikidataPropertyCatalogError(
            "property catalog manifest is not canonical JSON"
        )
    _require_fields(
        manifest,
        _MANIFEST_FIELDS,
        label="property catalog manifest",
    )
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise WikidataPropertyCatalogError("property catalog schema mismatch")
    catalog_id = manifest["catalog_id"]
    if type(catalog_id) is not str or _CATALOG_ID.fullmatch(catalog_id) is None:
        raise WikidataPropertyCatalogError("property catalog id invalid")
    if (
        manifest["classification"]
        != "fixture_only_auto_binding_mechanism_not_capability"
        or manifest["completion_state"] != "complete"
        or manifest["evaluation_only"] is not True
        or manifest["promotion_eligible"] is not False
    ):
        raise WikidataPropertyCatalogError(
            "property catalog authority or completion state invalid"
        )

    source = _require_fields(
        manifest["source_dataset"],
        _SOURCE_FIELDS,
        label="source_dataset",
    )
    if source != _EXPECTED_SOURCE:
        raise WikidataPropertyCatalogError(
            "property catalog source dataset invalid"
        )
    policy = _require_fields(
        manifest["provenance_policy"],
        _POLICY_FIELDS,
        label="provenance_policy",
    )
    if (
        any(type(policy[key]) is not bool for key in _POLICY_FIELDS)
        or policy != _EXPECTED_POLICY
    ):
        raise WikidataPropertyCatalogError(
            "property catalog provenance policy invalid"
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
        raise WikidataPropertyCatalogError(
            "property catalog authority claims must all remain false"
        )

    checksum = manifest["manifest_checksum_sha256"]
    if (
        type(checksum) is not str
        or _SHA256.fullmatch(checksum) is None
        or checksum != _manifest_checksum(manifest)
    ):
        raise WikidataPropertyCatalogError(
            "property catalog manifest checksum mismatch"
        )
    file_record = _require_fields(
        manifest["properties_file"],
        _FILE_FIELDS,
        label="properties_file",
    )
    if file_record["path"] != PROPERTIES_NAME:
        raise WikidataPropertyCatalogError("properties_file.path mismatch")
    if (
        type(file_record["bytes"]) is not int
        or file_record["bytes"] != len(properties_bytes)
    ):
        raise WikidataPropertyCatalogError("properties_file.bytes mismatch")
    source_digest = file_record["sha256"]
    if (
        type(source_digest) is not str
        or _SHA256.fullmatch(source_digest) is None
        or source_digest != _sha256(properties_bytes)
    ):
        raise WikidataPropertyCatalogError("properties_file.sha256 mismatch")

    source_rows = _parse_jsonl(properties_bytes)
    property_count = manifest["property_count"]
    if type(property_count) is not int or property_count != len(source_rows):
        raise WikidataPropertyCatalogError(
            "property catalog row count does not align"
        )

    return _assemble_catalog(
        catalog_id=catalog_id,
        manifest_checksum_sha256=checksum,
        bound_bytes=len(manifest_bytes) + len(properties_bytes),
        source_rows=source_rows,
        source_artifact_name=PROPERTIES_NAME,
        source_artifact_kind="canonical_jsonl_file",
        source_artifact_sha256=source_digest,
        license_name=source["license"],
        policy=policy,
        claims=claims,
    )


_SQLITE_TABLE_SCHEMAS: Mapping[
    str,
    tuple[tuple[str, str, int, int], ...],
] = MappingProxyType(
    {
        "l": (("k", "INTEGER", 0, 1), ("v", "TEXT", 0, 0)),
        "meta": (("k", "TEXT", 0, 1), ("v", "TEXT", 1, 0)),
        "pa": (("k", "INTEGER", 1, 1), ("v", "TEXT", 1, 2)),
        "pl": (("k", "INTEGER", 0, 1), ("v", "TEXT", 1, 0)),
        "pr": (("k", "INTEGER", 0, 1), ("v", "TEXT", 1, 0)),
        "pt": (("k", "INTEGER", 0, 1), ("v", "TEXT", 1, 0)),
    }
)
_SQLITE_META_FIELDS = frozenset(
    {
        "dump_path",
        "dump_size_bytes",
        "dump_mtime_ns",
        "scope",
        "property_catalog_profile",
        "property_label_count",
        "property_alias_count",
        "property_type_count",
        "property_revision_count",
    }
)


def _sqlite_uri(path: Path) -> str:
    return path.resolve().as_uri() + "?mode=ro"


def _sqlite_sidecars(path: Path) -> tuple[Path, ...]:
    return tuple(
        Path(f"{path}{suffix}")
        for suffix in ("-journal", "-shm", "-wal")
    )


def _assert_no_sqlite_sidecars(path: Path) -> None:
    if any(candidate.exists() for candidate in _sqlite_sidecars(path)):
        raise WikidataPropertyCatalogError(
            "property label DB has an unbound SQLite sidecar"
        )


def _sqlite_schema(
    connection: sqlite3.Connection,
    table_name: str,
) -> tuple[tuple[str, str, int, int], ...]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return tuple(
        (
            str(row[1]),
            str(row[2]).upper(),
            int(row[3]),
            int(row[5]),
        )
        for row in rows
    )


def _canonical_decimal(value: Any, *, label: str) -> int:
    if (
        type(value) is not str
        or re.fullmatch(r"(?:0|[1-9]\d{0,19})", value) is None
    ):
        raise WikidataPropertyCatalogError(f"{label} is not canonical decimal")
    return int(value)


def _read_sqlite_pairs(
    connection: sqlite3.Connection,
    table_name: str,
) -> tuple[tuple[int, str], ...]:
    rows = connection.execute(
        f"SELECT k, v FROM {table_name} ORDER BY k, v COLLATE BINARY"
    ).fetchall()
    result: list[tuple[int, str]] = []
    for index, row in enumerate(rows):
        if (
            len(row) != 2
            or type(row[0]) is not int
            or not 0 < row[0] <= 10**12
            or type(row[1]) is not str
        ):
            raise WikidataPropertyCatalogError(
                f"{table_name} row {index} has invalid SQLite types"
            )
        result.append((row[0], row[1]))
    return tuple(result)


def _validate_dump_binding(
    dump_path: Path,
    dump_identity: _FileIdentity,
    meta: Mapping[str, str],
) -> None:
    if (
        meta["dump_path"] != str(dump_path.resolve())
        or _canonical_decimal(
            meta["dump_size_bytes"],
            label="meta.dump_size_bytes",
        )
        != dump_identity.size
        or _canonical_decimal(
            meta["dump_mtime_ns"],
            label="meta.dump_mtime_ns",
        )
        != dump_identity.modified_ns
        or meta["scope"] != "complete"
        or meta["property_catalog_profile"]
        != "wikidata_property_catalog_v1"
    ):
        raise WikidataPropertyCatalogError(
            "property label DB is not bound to the complete supplied dump"
        )


def load_wikidata_property_catalog_from_label_db(
    label_db: str | Path,
    dump: str | Path,
) -> WikidataPropertyCatalogSnapshot:
    """Load the bound ``pl/pa/pt/pr`` view without modifying SQLite or a graph.

    Evidence binds a deterministic canonical view of the four property tables
    plus the database/dump identity metadata.  Property rows without an
    English label are excluded and recorded in the sealed snapshot.  Missing
    revisions remain ``None`` and are represented by the snapshot binding
    digest; they are never inferred.  This adapter does not preserve raw RDF
    line offsets and does not authenticate the dump publisher, so all
    authority claims remain false.
    """

    database_path = Path(label_db).resolve()
    dump_path = Path(dump).resolve()
    database_before = _capture_identity(database_path)
    dump_before = _capture_identity(dump_path)
    _assert_no_sqlite_sidecars(database_path)

    try:
        connection = sqlite3.connect(
            _sqlite_uri(database_path),
            uri=True,
            timeout=0,
        )
    except sqlite3.Error as exc:
        raise WikidataPropertyCatalogError(
            "property label DB cannot be opened read-only"
        ) from exc

    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        if connection.execute("PRAGMA query_only").fetchone() != (1,):
            raise WikidataPropertyCatalogError(
                "property label DB did not enter query-only mode"
            )
        connection.execute("BEGIN")
        data_version_before = connection.execute(
            "PRAGMA data_version"
        ).fetchone()
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if tables != set(_SQLITE_TABLE_SCHEMAS):
            raise WikidataPropertyCatalogError(
                "property label DB table set mismatch"
            )
        schema_binding: dict[str, list[list[Any]]] = {}
        for table_name, expected_schema in _SQLITE_TABLE_SCHEMAS.items():
            observed_schema = _sqlite_schema(connection, table_name)
            if observed_schema != expected_schema:
                raise WikidataPropertyCatalogError(
                    f"property label DB schema mismatch: {table_name}"
                )
            schema_binding[table_name] = [
                list(column) for column in observed_schema
            ]

        raw_meta = connection.execute(
            "SELECT k, v FROM meta ORDER BY k COLLATE BINARY"
        ).fetchall()
        if any(
            len(row) != 2
            or type(row[0]) is not str
            or type(row[1]) is not str
            for row in raw_meta
        ):
            raise WikidataPropertyCatalogError(
                "property label DB metadata types invalid"
            )
        meta = dict(raw_meta)
        if len(meta) != len(raw_meta) or frozenset(meta) != _SQLITE_META_FIELDS:
            raise WikidataPropertyCatalogError(
                "property label DB metadata fields mismatch"
            )
        _validate_dump_binding(dump_path, dump_before, meta)

        label_rows = _read_sqlite_pairs(connection, "pl")
        alias_rows = _read_sqlite_pairs(connection, "pa")
        type_rows = _read_sqlite_pairs(connection, "pt")
        revision_rows = _read_sqlite_pairs(connection, "pr")
        expected_counts = {
            "property_label_count": len(label_rows),
            "property_alias_count": len(alias_rows),
            "property_type_count": len(type_rows),
            "property_revision_count": len(revision_rows),
        }
        if any(
            _canonical_decimal(meta[key], label=f"meta.{key}") != value
            for key, value in expected_counts.items()
        ):
            raise WikidataPropertyCatalogError(
                "property label DB metadata counts do not align"
            )

        data_version_after = connection.execute(
            "PRAGMA data_version"
        ).fetchone()
        if data_version_before != data_version_after:
            raise WikidataPropertyCatalogError(
                "property label DB changed during snapshot query"
            )
        connection.execute("ROLLBACK")
    except WikidataPropertyCatalogError:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    except sqlite3.Error as exc:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise WikidataPropertyCatalogError(
            "property label DB query failed closed"
        ) from exc
    finally:
        connection.close()

    database_after = _capture_identity(database_path)
    dump_after = _capture_identity(dump_path)
    _assert_no_sqlite_sidecars(database_path)
    if database_before != database_after or dump_before != dump_after:
        raise WikidataPropertyCatalogError(
            "property label DB or dump changed during catalog load"
        )

    raw_labels = dict(label_rows)
    datatypes = dict(type_rows)
    revisions = dict(revision_rows)
    surface_normalization_rows: list[dict[str, str]] = []
    labels: dict[int, str] = {}
    for pid, raw_label in sorted(raw_labels.items()):
        normalized_label = _canonicalize_sqlite_surface(raw_label)
        if normalized_label is None:
            raise WikidataPropertyCatalogError(
                f"property label DB has unusable English label: P{pid}"
            )
        labels[pid] = normalized_label
        if normalized_label != raw_label:
            surface_normalization_rows.append(
                {
                    "field": "label",
                    "id": f"P{pid}",
                    "normalized": normalized_label,
                    "source": raw_label,
                }
            )
    label_keys = set(labels)
    datatype_keys = set(datatypes)
    revision_keys = set(revisions)
    excluded_unlabeled_keys = tuple(sorted(datatype_keys - label_keys))
    if (
        len(labels) != len(label_rows)
        or len(datatypes) != len(type_rows)
        or len(revisions) != len(revision_rows)
        or not label_keys.issubset(datatype_keys)
        or not revision_keys.issubset(datatype_keys)
        or any(pid not in label_keys for pid, _ in alias_rows)
    ):
        raise WikidataPropertyCatalogError(
            "property label DB has duplicate, orphan, or incomplete PIDs"
        )
    raw_aliases_by_pid: dict[int, list[str]] = {
        pid: [] for pid in sorted(label_keys)
    }
    for pid, alias in alias_rows:
        raw_aliases_by_pid[pid].append(alias)
    aliases_by_pid: dict[int, list[str]] = {}
    excluded_alias_rows: list[dict[str, str]] = []
    for pid in sorted(label_keys):
        seen_surfaces = {_surface_key(labels[pid])}
        canonical_aliases: list[str] = []
        for raw_alias in sorted(
            raw_aliases_by_pid[pid],
            key=lambda value: (_surface_key(value), value),
        ):
            alias = _canonicalize_sqlite_surface(raw_alias)
            if alias is None:
                excluded_alias_rows.append(
                    {
                        "id": f"P{pid}",
                        "reason": "unusable_source_alias",
                        "value": raw_alias,
                    }
                )
                continue
            if alias != raw_alias:
                surface_normalization_rows.append(
                    {
                        "field": "alias",
                        "id": f"P{pid}",
                        "normalized": alias,
                        "source": raw_alias,
                    }
                )
            surface_key = _surface_key(alias)
            if surface_key in seen_surfaces:
                excluded_alias_rows.append(
                    {
                        "id": f"P{pid}",
                        "reason": (
                            "normalized_duplicate_of_label_or_alias"
                        ),
                        "value": alias,
                    }
                )
                continue
            seen_surfaces.add(surface_key)
            canonical_aliases.append(alias)
        aliases_by_pid[pid] = canonical_aliases

    records: list[tuple[dict[str, Any], bytes]] = []
    for pid in sorted(label_keys):
        revision = (
            _canonical_decimal(
                revisions[pid],
                label=f"pr.P{pid}",
            )
            if pid in revisions
            else None
        )
        aliases = sorted(
            aliases_by_pid[pid],
            key=lambda value: (_surface_key(value), value),
        )
        record: dict[str, Any] = {
            "aliases": {
                "en": [
                    {"language": "en", "value": alias}
                    for alias in aliases
                ]
            },
            "datatype": datatypes[pid],
            "id": f"P{pid}",
            "labels": {
                "en": {"language": "en", "value": labels[pid]}
            },
            "lastrevid": revision,
            "type": "property",
        }
        line = canonical_json(record).encode("utf-8")
        records.append((record, line))
    if not 1 <= len(records) <= MAX_PROPERTY_ROWS:
        raise WikidataPropertyCatalogError(
            "property label DB row count is out of bounds"
        )
    source_rows = tuple(records)
    canonical_view = b"\n".join(line for _, line in source_rows) + b"\n"
    view_digest = _sha256(canonical_view)
    source_name = (
        f"{database_path.name}#pl-pa-pt-pr.canonical.jsonl"
    )
    claims = {key: False for key in sorted(_CLAIM_FIELDS)}
    excluded_unlabeled_rows = [
        {
            "datatype": datatypes[pid],
            "id": f"P{pid}",
            "reason": "missing_english_label",
            "source_revision": (
                _canonical_decimal(
                    revisions[pid],
                    label=f"pr.P{pid}",
                )
                if pid in revisions
                else None
            ),
        }
        for pid in excluded_unlabeled_keys
    ]
    excluded_unlabeled_property_ids = tuple(
        row["id"] for row in excluded_unlabeled_rows
    )
    revision_unavailable_count = sum(
        record["lastrevid"] is None
        for record, _ in source_rows
    )
    binding_document = {
        "schema_version": SCHEMA_VERSION,
        "adapter": "sqlite_label_db_pl_pa_pt_pr_v2",
        "catalog_id": "wikidata-property-catalog-label-db-v2",
        "database": {
            "resolved_path": str(database_path),
            "size_bytes": database_before.size,
            "mtime_ns": database_before.modified_ns,
            "schema": schema_binding,
            "meta": dict(sorted(meta.items())),
        },
        "dump": {
            "resolved_path": str(dump_path),
            "size_bytes": dump_before.size,
            "mtime_ns": dump_before.modified_ns,
        },
        "source_artifact": {
            "kind": "sqlite_canonical_property_view",
            "name": source_name,
            "bytes": len(canonical_view),
            "sha256": view_digest,
        },
        "property_count": len(source_rows),
        "revision_evidence": {
            "available_count": len(source_rows)
            - revision_unavailable_count,
            "unavailable_count": revision_unavailable_count,
            "unavailable_representation": (
                "null_plus_dump_bound_snapshot_digest"
            ),
        },
        "exclusions": {
            "missing_english_label_count": len(
                excluded_unlabeled_rows
            ),
            "missing_english_label_rows": excluded_unlabeled_rows,
            "alias_count": len(excluded_alias_rows),
            "alias_rows": excluded_alias_rows,
        },
        "surface_normalization": {
            "count": len(surface_normalization_rows),
            "rows": surface_normalization_rows,
            "rule": "NFKC_then_unicode_whitespace_collapse",
        },
        "provenance_policy": _SQLITE_SNAPSHOT_POLICY,
        "claims": claims,
    }
    binding_checksum = canonical_digest(binding_document)
    return _assemble_catalog(
        catalog_id="wikidata-property-catalog-label-db-v2",
        manifest_checksum_sha256=binding_checksum,
        bound_bytes=len(canonical_view),
        source_rows=source_rows,
        source_artifact_name=source_name,
        source_artifact_kind="sqlite_canonical_property_view",
        source_artifact_sha256=view_digest,
        license_name="CC0-1.0",
        policy=_SQLITE_SNAPSHOT_POLICY,
        claims=claims,
        excluded_unlabeled_property_ids=(
            excluded_unlabeled_property_ids
        ),
    )
