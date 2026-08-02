"""Fail-closed, read-only scientific-knowledge staging for A-track evaluation.

The v1 format is deliberately small and strict: a manifest binds canonical
``facts.jsonl`` and row-aligned ``evidence.jsonl`` bytes.  Loading verifies
completion, provenance identity, functional-predicate consistency, and
quarantine state before a fact can reach the reasoner.  It never writes to the
shipped graph and is not a promotion authority.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
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

from packages.cognitive_core.canonical import canonical_digest, canonical_json


SCIENCE_STAGE_SCHEMA = "atanor.science-stage.v1"
MANIFEST_NAME = "manifest.json"
FACTS_NAME = "facts.jsonl"
EVIDENCE_NAME = "evidence.jsonl"
MAX_STAGE_ROWS = 10_000
MAX_BOUND_FILE_BYTES = 16 * 1024 * 1024
MAX_LINE_BYTES = 16 * 1024
MAX_PROOF_LEAVES = 1_024

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ROW_ID = re.compile(r"science-stage-row-(\d{3,})\Z")
_EVIDENCE_ID = re.compile(r"wd-(q\d+)-p1086-r(\d+)\Z")
_SOURCE_URL = re.compile(
    r"https://www\.wikidata\.org/wiki/Special:EntityData/"
    r"(Q\d+)\.json\?revision=(\d+)\Z"
)
_SOURCE_RECORD = re.compile(r"(Q\d+)\$[0-9a-f-]{20,}\Z", re.IGNORECASE)
_INTEGER = re.compile(r"(?:0|[1-9]\d{0,2})\Z")

_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "stage_id",
        "classification",
        "completion_state",
        "evaluation_only",
        "promotion_eligible",
        "row_count",
        "relation_profile",
        "functional_predicates",
        "object_semantics",
        "facts_file",
        "evidence_file",
        "provenance_policy",
        "source_dataset",
        "claims",
        "manifest_checksum_sha256",
    }
)
_FILE_FIELDS = frozenset({"path", "bytes", "sha256"})
_PROVENANCE_FIELDS = frozenset(
    {
        "row_aligned",
        "source_revision_required",
        "source_record_id_required",
        "license_required",
        "allowed_license",
        "quarantined_rows_allowed",
    }
)
_SOURCE_FIELDS = frozenset(
    {"name", "property", "snapshot_kind", "license"}
)
_CLAIM_FIELDS = frozenset(
    {
        "e4_only",
        "e5_eligible",
        "benchmark_capability_claimed",
        "independent_evaluator_claimed",
    }
)
_FACT_FIELDS = frozenset(
    {
        "row_id",
        "subject",
        "predicate",
        "object",
        "evidence_id",
        "quarantined",
    }
)
_EVIDENCE_FIELDS = frozenset(
    {
        "evidence_id",
        "source_url",
        "source_record_id",
        "source_revision",
        "license",
    }
)

Fact = tuple[str, str, str]
FactsAbout = Callable[[str], list[Fact]]
_VALIDATION_KEY = os.urandom(32)


class ScienceStageError(RuntimeError):
    """Raised when staged science bytes cannot be trusted."""


def _is_link_or_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return bool(reparse_flag and attributes & reparse_flag)
    except OSError:
        # An unreadable or racing path is not a trustworthy regular artifact.
        return True


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ScienceStageError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_nonfinite(token: str) -> None:
    raise ScienceStageError(f"non-finite JSON number: {token}")


def _strict_object(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_nonfinite,
        )
    except ScienceStageError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ScienceStageError(
            f"{label} is not strict readable JSON: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise ScienceStageError(f"{label} root must be an object")
    return value


def _read_stable(path: Path, *, max_bytes: int) -> bytes:
    if _is_link_or_reparse(path) or not path.is_file():
        raise ScienceStageError(f"bound stage file is not a regular file: {path.name}")
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if before.st_size > max_bytes:
                raise ScienceStageError(f"bound stage file too large: {path.name}")
            payload = handle.read()
            after = os.fstat(handle.fileno())
    except ScienceStageError:
        raise
    except OSError as exc:
        raise ScienceStageError(
            f"bound stage file unreadable: {path.name}: {type(exc).__name__}"
        ) from exc
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise ScienceStageError(f"bound stage file changed while reading: {path.name}")
    return payload


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest_checksum(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_checksum_sha256", None)
    return hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()


def _require_exact_fields(
    value: Any,
    fields: frozenset[str],
    *,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != fields:
        raise ScienceStageError(f"{label} fields mismatch")
    return value


def _validate_file_binding(
    value: Any,
    *,
    expected_path: str,
    payload: bytes,
    label: str,
) -> None:
    record = _require_exact_fields(value, _FILE_FIELDS, label=label)
    if record["path"] != expected_path:
        raise ScienceStageError(f"{label}.path mismatch")
    if type(record["bytes"]) is not int or record["bytes"] != len(payload):
        raise ScienceStageError(f"{label}.bytes mismatch")
    digest = record["sha256"]
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        raise ScienceStageError(f"{label}.sha256 invalid")
    if digest != _sha256(payload):
        raise ScienceStageError(f"{label}.sha256 mismatch")


def _parse_canonical_jsonl(payload: bytes, *, label: str) -> list[dict[str, Any]]:
    if not payload or not payload.endswith(b"\n"):
        raise ScienceStageError(f"{label} must be non-empty and newline-terminated")
    lines = payload.splitlines()
    if not lines or len(lines) > MAX_STAGE_ROWS:
        raise ScienceStageError(f"{label} row count out of bounds")
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if not line or len(line) > MAX_LINE_BYTES:
            raise ScienceStageError(f"{label}[{index}] line size invalid")
        row = _strict_object(line, label=f"{label}[{index}]")
        if canonical_json(row).encode("utf-8") != line:
            raise ScienceStageError(f"{label}[{index}] is not canonical JSON")
        rows.append(row)
    return rows


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    source_url: str
    source_record_id: str
    source_revision: str
    license: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StagedFact:
    row_id: str
    triple: Fact
    evidence: EvidenceRef

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "triple": list(self.triple),
            "evidence": self.evidence.to_dict(),
        }


def _snapshot_validation_tag(
    *,
    stage_id: str,
    stage_digest_sha256: str,
    manifest_checksum_sha256: str,
    bound_bytes: int,
    facts: tuple[StagedFact, ...],
) -> str:
    payload = {
        "stage_id": stage_id,
        "stage_digest_sha256": stage_digest_sha256,
        "manifest_checksum_sha256": manifest_checksum_sha256,
        "bound_bytes": bound_bytes,
        "facts": [row.to_dict() for row in facts],
    }
    return hmac.new(
        _VALIDATION_KEY,
        canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@dataclass(frozen=True)
class ScienceStageSnapshot:
    """Deeply detached, immutable view of one validated stage generation."""

    stage_id: str
    stage_digest_sha256: str
    manifest_checksum_sha256: str
    bound_bytes: int
    facts: tuple[StagedFact, ...]
    _by_subject: Mapping[str, tuple[StagedFact, ...]]
    _by_triple: Mapping[Fact, EvidenceRef]
    _validation_seal: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        self.assert_validated()

    def assert_validated(self) -> None:
        expected = _snapshot_validation_tag(
            stage_id=self.stage_id,
            stage_digest_sha256=self.stage_digest_sha256,
            manifest_checksum_sha256=self.manifest_checksum_sha256,
            bound_bytes=self.bound_bytes,
            facts=self.facts,
        )
        if (
            type(self._validation_seal) is not str
            or not hmac.compare_digest(self._validation_seal, expected)
        ):
            raise ScienceStageError(
                "science stage snapshot validation seal does not bind its content"
            )
        expected_subjects: dict[str, tuple[StagedFact, ...]] = {}
        subject_rows: dict[str, list[StagedFact]] = {}
        expected_triples: dict[Fact, EvidenceRef] = {}
        for row in self.facts:
            subject_rows.setdefault(row.triple[0], []).append(row)
            if row.triple in expected_triples:
                raise ScienceStageError("science stage snapshot duplicates a triple")
            expected_triples[row.triple] = row.evidence
        expected_subjects = {
            subject: tuple(sorted(rows, key=lambda item: item.row_id))
            for subject, rows in sorted(subject_rows.items())
        }
        actual_subjects = {
            str(subject): tuple(rows)
            for subject, rows in self._by_subject.items()
        }
        actual_triples = dict(self._by_triple.items())
        if (
            actual_subjects != expected_subjects
            or actual_triples != expected_triples
        ):
            raise ScienceStageError(
                "science stage snapshot indexes do not bind its facts"
            )

    def facts_about(self, subject: str) -> tuple[Fact, ...]:
        key = " ".join(str(subject).split()).casefold()
        return tuple(row.triple for row in self._by_subject.get(key, ()))

    def evidence_for(self, fact: Fact) -> EvidenceRef | None:
        normalized = (
            " ".join(str(fact[0]).split()).casefold(),
            str(fact[1]).strip().casefold(),
            str(fact[2]).strip(),
        )
        return self._by_triple.get(normalized)


def load_science_stage(root: str | Path) -> ScienceStageSnapshot:
    """Load one complete science stage or reject the entire generation."""

    stage_root = Path(root)
    if _is_link_or_reparse(stage_root) or not stage_root.is_dir():
        raise ScienceStageError("science stage root must be a regular directory")
    allowed = {MANIFEST_NAME, FACTS_NAME, EVIDENCE_NAME}
    try:
        present = {item.name for item in stage_root.iterdir()}
    except OSError as exc:
        raise ScienceStageError("science stage directory is unreadable") from exc
    if present != allowed:
        raise ScienceStageError("science stage file set mismatch")

    manifest_bytes = _read_stable(
        stage_root / MANIFEST_NAME,
        max_bytes=MAX_BOUND_FILE_BYTES,
    )
    facts_bytes = _read_stable(
        stage_root / FACTS_NAME,
        max_bytes=MAX_BOUND_FILE_BYTES,
    )
    evidence_bytes = _read_stable(
        stage_root / EVIDENCE_NAME,
        max_bytes=MAX_BOUND_FILE_BYTES,
    )
    manifest = _strict_object(manifest_bytes, label="science stage manifest")
    _require_exact_fields(manifest, _ROOT_FIELDS, label="science stage manifest")

    if manifest["schema_version"] != SCIENCE_STAGE_SCHEMA:
        raise ScienceStageError("science stage schema mismatch")
    if (
        manifest["classification"] != "frozen_development_probe_not_e5"
        or manifest["completion_state"] != "complete"
        or manifest["evaluation_only"] is not True
        or manifest["promotion_eligible"] is not False
    ):
        raise ScienceStageError("science stage authority or completion state invalid")
    if (
        manifest["relation_profile"] != ["atomic_number"]
        or manifest["functional_predicates"] != ["atomic_number"]
    ):
        raise ScienceStageError("science stage relation profile invalid")
    semantics = manifest["object_semantics"]
    if semantics != {
        "atomic_number": {
            "kind": "integer",
            "minimum": 1,
            "maximum": 200,
            "unit": "dimensionless",
        }
    }:
        raise ScienceStageError("science stage object semantics invalid")

    policy = _require_exact_fields(
        manifest["provenance_policy"],
        _PROVENANCE_FIELDS,
        label="provenance_policy",
    )
    if policy != {
        "row_aligned": True,
        "source_revision_required": True,
        "source_record_id_required": True,
        "license_required": True,
        "allowed_license": "CC0-1.0",
        "quarantined_rows_allowed": False,
    }:
        raise ScienceStageError("science stage provenance policy invalid")
    source = _require_exact_fields(
        manifest["source_dataset"],
        _SOURCE_FIELDS,
        label="source_dataset",
    )
    if source != {
        "name": "Wikidata",
        "property": "P1086",
        "snapshot_kind": "per_entity_immutable_revision",
        "license": "CC0-1.0",
    }:
        raise ScienceStageError("science stage source dataset invalid")
    claims = _require_exact_fields(
        manifest["claims"],
        _CLAIM_FIELDS,
        label="claims",
    )
    if claims != {
        "e4_only": True,
        "e5_eligible": False,
        "benchmark_capability_claimed": False,
        "independent_evaluator_claimed": False,
    }:
        raise ScienceStageError("science stage claims invalid")

    checksum = manifest["manifest_checksum_sha256"]
    if (
        not isinstance(checksum, str)
        or _SHA256.fullmatch(checksum) is None
        or checksum != _manifest_checksum(manifest)
    ):
        raise ScienceStageError("science stage manifest checksum mismatch")
    _validate_file_binding(
        manifest["facts_file"],
        expected_path=FACTS_NAME,
        payload=facts_bytes,
        label="facts_file",
    )
    _validate_file_binding(
        manifest["evidence_file"],
        expected_path=EVIDENCE_NAME,
        payload=evidence_bytes,
        label="evidence_file",
    )

    fact_rows = _parse_canonical_jsonl(facts_bytes, label="facts")
    evidence_rows = _parse_canonical_jsonl(evidence_bytes, label="evidence")
    row_count = manifest["row_count"]
    if (
        type(row_count) is not int
        or row_count <= 0
        or row_count != len(fact_rows)
        or row_count != len(evidence_rows)
    ):
        raise ScienceStageError("science stage row alignment mismatch")

    staged: list[StagedFact] = []
    seen_rows: set[str] = set()
    seen_evidence: set[str] = set()
    seen_triples: set[Fact] = set()
    subject_values: dict[tuple[str, str], str] = {}
    atomic_subjects: dict[str, str] = {}
    expected_ordinal = 1
    for index, (fact_row, evidence_row) in enumerate(
        zip(fact_rows, evidence_rows, strict=True)
    ):
        _require_exact_fields(fact_row, _FACT_FIELDS, label=f"facts[{index}]")
        _require_exact_fields(
            evidence_row,
            _EVIDENCE_FIELDS,
            label=f"evidence[{index}]",
        )
        row_id = fact_row["row_id"]
        row_match = _ROW_ID.fullmatch(str(row_id))
        if (
            row_match is None
            or int(row_match.group(1)) != expected_ordinal
            or row_id in seen_rows
        ):
            raise ScienceStageError(f"facts[{index}].row_id invalid")
        expected_ordinal += 1
        seen_rows.add(row_id)

        subject = fact_row["subject"]
        predicate = fact_row["predicate"]
        obj = fact_row["object"]
        evidence_id = fact_row["evidence_id"]
        if (
            type(subject) is not str
            or not subject
            or subject != " ".join(subject.split()).casefold()
            or len(subject) > 80
        ):
            raise ScienceStageError(f"facts[{index}].subject invalid")
        if predicate != "atomic_number":
            raise ScienceStageError(f"facts[{index}].predicate invalid")
        if (
            type(obj) is not str
            or _INTEGER.fullmatch(obj) is None
            or not 1 <= int(obj) <= 200
        ):
            raise ScienceStageError(f"facts[{index}].object invalid")
        if fact_row["quarantined"] is not False:
            raise ScienceStageError(f"facts[{index}] is quarantined")
        if evidence_id != evidence_row["evidence_id"]:
            raise ScienceStageError(f"facts[{index}] evidence is torn")

        ev_match = _EVIDENCE_ID.fullmatch(str(evidence_id))
        url_match = _SOURCE_URL.fullmatch(str(evidence_row["source_url"]))
        record_match = _SOURCE_RECORD.fullmatch(
            str(evidence_row["source_record_id"])
        )
        revision = evidence_row["source_revision"]
        if (
            ev_match is None
            or url_match is None
            or record_match is None
            or type(revision) is not str
            or not revision.isdecimal()
            or evidence_row["license"] != "CC0-1.0"
        ):
            raise ScienceStageError(f"evidence[{index}] provenance invalid")
        qid = ev_match.group(1).upper()
        ev_revision = ev_match.group(2)
        if (
            qid != url_match.group(1)
            or qid != record_match.group(1).upper()
            or ev_revision != url_match.group(2)
            or ev_revision != revision
            or evidence_id in seen_evidence
        ):
            raise ScienceStageError(f"evidence[{index}] provenance identity mismatch")
        seen_evidence.add(evidence_id)

        triple = (subject, predicate, obj)
        if triple in seen_triples:
            raise ScienceStageError(f"facts[{index}] duplicate triple")
        seen_triples.add(triple)
        functional_key = (subject, predicate)
        previous = subject_values.setdefault(functional_key, obj)
        if previous != obj:
            raise ScienceStageError("functional predicate conflict")
        previous_subject = atomic_subjects.setdefault(obj, subject)
        if previous_subject != subject:
            raise ScienceStageError("atomic number maps to multiple subjects")

        evidence = EvidenceRef(
            evidence_id=evidence_id,
            source_url=evidence_row["source_url"],
            source_record_id=evidence_row["source_record_id"],
            source_revision=revision,
            license=evidence_row["license"],
        )
        staged.append(
            StagedFact(row_id=row_id, triple=triple, evidence=evidence)
        )

    by_subject: dict[str, list[StagedFact]] = {}
    by_triple: dict[Fact, EvidenceRef] = {}
    for row in staged:
        by_subject.setdefault(row.triple[0], []).append(row)
        by_triple[row.triple] = row.evidence
    frozen_subjects = MappingProxyType(
        {
            subject: tuple(sorted(rows, key=lambda item: item.row_id))
            for subject, rows in sorted(by_subject.items())
        }
    )
    frozen_triples = MappingProxyType(dict(sorted(by_triple.items())))
    stage_digest = canonical_digest(
        {
            "schema_version": SCIENCE_STAGE_SCHEMA,
            "stage_id": manifest["stage_id"],
            "manifest_checksum_sha256": checksum,
            "facts_sha256": _sha256(facts_bytes),
            "evidence_sha256": _sha256(evidence_bytes),
            "row_count": len(staged),
        }
    )
    frozen_facts = tuple(staged)
    validation_seal = _snapshot_validation_tag(
        stage_id=manifest["stage_id"],
        stage_digest_sha256=stage_digest,
        manifest_checksum_sha256=checksum,
        bound_bytes=len(manifest_bytes) + len(facts_bytes) + len(evidence_bytes),
        facts=frozen_facts,
    )
    return ScienceStageSnapshot(
        stage_id=manifest["stage_id"],
        stage_digest_sha256=stage_digest,
        manifest_checksum_sha256=checksum,
        bound_bytes=len(manifest_bytes) + len(facts_bytes) + len(evidence_bytes),
        facts=frozen_facts,
        _by_subject=frozen_subjects,
        _by_triple=frozen_triples,
        _validation_seal=validation_seal,
    )


class StagedKnowledgeOverlay:
    """Read-only base+stage view with structural OFF/ON isolation."""

    def __init__(
        self,
        base_facts: FactsAbout,
        snapshot: ScienceStageSnapshot | None,
        *,
        enabled: bool = False,
    ) -> None:
        if not callable(base_facts):
            raise TypeError("base_facts must be callable")
        if type(enabled) is not bool:
            raise TypeError("enabled must be a boolean")
        if enabled:
            if not isinstance(snapshot, ScienceStageSnapshot):
                raise TypeError(
                    "enabled overlay requires a validated ScienceStageSnapshot"
                )
            snapshot.assert_validated()
        elif snapshot is not None:
            raise TypeError("disabled overlay must not retain a stage snapshot")
        self._base_facts = base_facts
        self.snapshot = snapshot
        self.enabled = enabled
        self.lookup_count = 0
        self.base_row_count = 0
        self.stage_hit_count = 0
        self._stage_exposed: set[Fact] = set()

    def facts_about(self, subject: str) -> list[Fact]:
        self.lookup_count += 1
        try:
            raw_base = self._base_facts(subject) or []
        except Exception as exc:
            raise ScienceStageError(
                f"base facts lookup failed: {type(exc).__name__}"
            ) from exc
        base: list[Fact] = []
        seen: set[Fact] = set()
        for row in raw_base:
            if (
                not isinstance(row, (tuple, list))
                or len(row) != 3
                or any(type(value) is not str for value in row)
            ):
                raise ScienceStageError("base facts returned an invalid row")
            fact = (row[0], row[1], row[2])
            if fact not in seen:
                base.append(fact)
                seen.add(fact)
            # A fact that later appears in the base cannot remain attributed to
            # the candidate stage.  This also fails conservative when a caller
            # supplies a time-varying base accessor without a state probe.
            self._stage_exposed.discard(fact)
        self.base_row_count += len(base)
        if not self.enabled:
            return base

        if self.snapshot is None:  # Constructor invariant; fail closed if forged.
            raise ScienceStageError("enabled overlay lost its stage snapshot")
        self.snapshot.assert_validated()
        for fact in self.snapshot.facts_about(subject):
            if fact in seen:
                continue
            base.append(fact)
            seen.add(fact)
            if fact not in self._stage_exposed:
                self._stage_exposed.add(fact)
                self.stage_hit_count += 1
        return base

    def evidence_for(self, fact: Fact) -> EvidenceRef | None:
        if self.snapshot is None or fact not in self._stage_exposed:
            return None
        self.snapshot.assert_validated()
        return self.snapshot.evidence_for(fact)

    def bind_proof(self, proof: Any) -> dict[str, Any]:
        if proof is None or not callable(getattr(proof, "leaves", None)):
            return {
                "grounded_leaf_count": 0,
                "grounded_stage_leaf_count": 0,
                "evidence": [],
                "proof_digest_sha256": None,
                "provenance_digest_sha256": None,
            }
        try:
            raw_leaves = proof.leaves()
        except Exception as exc:
            raise ScienceStageError(
                f"proof leaves are unreadable: {type(exc).__name__}"
            ) from exc
        if (
            not isinstance(raw_leaves, (list, tuple))
            or len(raw_leaves) > MAX_PROOF_LEAVES
        ):
            raise ScienceStageError("proof leaves are not a bounded sequence")
        leaves: list[Fact] = []
        for row in raw_leaves:
            if (
                not isinstance(row, (list, tuple))
                or len(row) != 3
                or any(type(value) is not str for value in row)
            ):
                raise ScienceStageError(
                    "proof leaf must be an exact string triple"
                )
            leaves.append((row[0], row[1], row[2]))
        evidence: list[dict[str, Any]] = []
        seen_evidence: set[str] = set()
        for fact in leaves:
            ref = self.evidence_for(fact)
            if ref is None or ref.evidence_id in seen_evidence:
                continue
            seen_evidence.add(ref.evidence_id)
            evidence.append(ref.to_dict())
        evidence.sort(key=lambda row: row["evidence_id"])
        return {
            "grounded_leaf_count": len(leaves),
            "grounded_stage_leaf_count": len(evidence),
            "evidence": evidence,
            "proof_digest_sha256": canonical_digest(proof.to_dict()),
            "provenance_digest_sha256": (
                canonical_digest(evidence) if evidence else None
            ),
        }

    def telemetry(self) -> dict[str, Any]:
        snapshot = self.snapshot
        return {
            "enabled": self.enabled,
            "lookup_attempted": self.lookup_count > 0,
            "lookup_count": self.lookup_count,
            "base_row_count": self.base_row_count,
            "staged_hit_count": self.stage_hit_count,
            "stage_digest_sha256": (
                snapshot.stage_digest_sha256 if snapshot is not None else None
            ),
            "stage_snapshot_bound_bytes": (
                snapshot.bound_bytes if snapshot is not None else 0
            ),
            # The snapshot is validated and loaded before a condition starts;
            # this overlay performs in-memory lookups and therefore reads no
            # additional stage bytes per item.
            "stage_bytes_read": 0,
        }
