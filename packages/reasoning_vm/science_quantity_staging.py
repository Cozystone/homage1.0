"""Strict, read-only staging for the scalar science development lane.

This is deliberately separate from the atomic-number stage.  A quantity stage
binds species-equivalent facts and one audited rational formula, but it carries
no benchmark question, choices, or answer.  The loader validates the complete
generation before exposing an immutable snapshot; the overlay records exactly
which staged rows reached a proof.

The format is development evidence only.  A self-consistent checksum proves
byte integrity, not that an external source is authentic.
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

from packages.cognitive_core.canonical import canonical_digest, canonical_json
from packages.reasoning_vm.scalar_quantity import (
    CONCENTRATION,
    DIMENSIONLESS,
    VOLUME,
    evaluate_dimension_ast,
)


SCIENCE_QUANTITY_STAGE_SCHEMA = "atanor.science-quantity-stage.v1"
MANIFEST_NAME = "manifest.json"
SPECIES_NAME = "species.jsonl"
FORMULAS_NAME = "formulas.jsonl"
EVIDENCE_NAME = "evidence.jsonl"
MAX_BOUND_FILE_BYTES = 4 * 1024 * 1024
MAX_LINE_BYTES = 16 * 1024
MAX_SPECIES_ROWS = 256
MAX_FORMULA_ROWS = 16
MAX_PROOF_LEAVES = 256

NEUTRALIZATION_FORMULA_ID = (
    "complete_neutralization_equivalent_balance_v1"
)
NEUTRALIZATION_EXPRESSION: list[Any] = [
    "op",
    "/",
    [
        "op",
        "*",
        [
            "op",
            "*",
            ["var", "known_concentration"],
            ["var", "known_volume_l"],
        ],
        ["var", "known_equivalents"],
    ],
    [
        "op",
        "*",
        ["var", "target_concentration"],
        ["var", "target_equivalents"],
    ],
]

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_STAGE_ID = re.compile(r"science-quantity-stage-[a-z0-9-]+-v[1-9]\d*\Z")
_ROW_ID = re.compile(r"quantity-species-row-(\d{3,})\Z")
_EVIDENCE_ID = re.compile(r"quantity-evidence-(\d{3,})\Z")
_CANONICAL_ID = re.compile(r"chem:[a-z][a-z0-9_]{1,79}\Z")
_ALIAS = re.compile(r"[A-Za-z][A-Za-z0-9()]{0,39}\Z")
_SOURCE_RECORD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._/@+-]{2,199}\Z")
_SOURCE_REVISION = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._/@+-]{0,199}\Z")
_LICENSE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{1,79}\Z")
_VALIDATION_KEY = os.urandom(32)

_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "stage_id",
        "classification",
        "completion_state",
        "evaluation_only",
        "promotion_eligible",
        "species_count",
        "formula_count",
        "relation_profile",
        "species_file",
        "formulas_file",
        "evidence_file",
        "provenance_policy",
        "claims",
        "manifest_checksum_sha256",
    }
)
_FILE_FIELDS = frozenset({"path", "bytes", "sha256"})
_POLICY_FIELDS = frozenset(
    {
        "one_to_one_claim_evidence",
        "source_statement_digest_required",
        "source_revision_required",
        "license_required",
        "quarantined_rows_allowed",
        "external_authentication_required",
    }
)
_CLAIM_FIELDS = frozenset(
    {
        "e4_development_only",
        "e5_eligible",
        "benchmark_capability_claimed",
        "independent_evaluator_claimed",
        "external_authenticity_established",
    }
)
_SPECIES_FIELDS = frozenset(
    {
        "row_id",
        "canonical_id",
        "alias",
        "role",
        "equivalents_per_mole",
        "evidence_id",
        "quarantined",
    }
)
_FORMULA_FIELDS = frozenset(
    {
        "rule_id",
        "family",
        "expression",
        "input_dimensions",
        "result_dimension",
        "output_unit",
        "evidence_id",
        "quarantined",
    }
)
_EVIDENCE_FIELDS = frozenset(
    {
        "evidence_id",
        "claim_kind",
        "claim_digest_sha256",
        "source_url",
        "source_record_id",
        "source_revision",
        "license",
        "source_statement",
        "source_statement_sha256",
        "externally_authenticated",
    }
)


class ScienceQuantityStageError(RuntimeError):
    """Raised when a scalar stage cannot be trusted as a complete snapshot."""


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


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ScienceQuantityStageError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise ScienceQuantityStageError(f"non-finite JSON number: {token}")


def _strict_object(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_nonfinite,
        )
    except ScienceQuantityStageError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ScienceQuantityStageError(
            f"{label} is not strict readable JSON: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise ScienceQuantityStageError(f"{label} root must be an object")
    return value


def _read_stable(path: Path) -> bytes:
    if _is_link_or_reparse(path) or not path.is_file():
        raise ScienceQuantityStageError(
            f"bound stage file is not regular: {path.name}"
        )
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if before.st_size > MAX_BOUND_FILE_BYTES:
                raise ScienceQuantityStageError(
                    f"bound stage file too large: {path.name}"
                )
            payload = handle.read()
            after = os.fstat(handle.fileno())
    except ScienceQuantityStageError:
        raise
    except OSError as exc:
        raise ScienceQuantityStageError(
            f"bound stage file unreadable: {path.name}"
        ) from exc
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise ScienceQuantityStageError(
            f"bound stage file changed while reading: {path.name}"
        )
    return payload


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest_checksum(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_checksum_sha256", None)
    return _sha256(canonical_json(unsigned).encode("utf-8"))


def _require_exact_fields(
    value: Any,
    fields: frozenset[str],
    *,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != fields:
        raise ScienceQuantityStageError(f"{label} fields mismatch")
    return value


def _validate_file_binding(
    value: Any,
    *,
    path: str,
    payload: bytes,
    label: str,
) -> None:
    record = _require_exact_fields(value, _FILE_FIELDS, label=label)
    if record["path"] != path:
        raise ScienceQuantityStageError(f"{label}.path mismatch")
    if type(record["bytes"]) is not int or record["bytes"] != len(payload):
        raise ScienceQuantityStageError(f"{label}.bytes mismatch")
    digest = record["sha256"]
    if (
        not isinstance(digest, str)
        or _SHA256.fullmatch(digest) is None
        or digest != _sha256(payload)
    ):
        raise ScienceQuantityStageError(f"{label}.sha256 mismatch")


def _parse_jsonl(
    payload: bytes,
    *,
    label: str,
    maximum: int,
) -> list[dict[str, Any]]:
    if not payload or not payload.endswith(b"\n"):
        raise ScienceQuantityStageError(
            f"{label} must be non-empty and newline-terminated"
        )
    lines = payload.splitlines()
    if not 1 <= len(lines) <= maximum:
        raise ScienceQuantityStageError(f"{label} row count out of bounds")
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if not line or len(line) > MAX_LINE_BYTES:
            raise ScienceQuantityStageError(
                f"{label}[{index}] line size invalid"
            )
        row = _strict_object(line, label=f"{label}[{index}]")
        if canonical_json(row).encode("utf-8") != line:
            raise ScienceQuantityStageError(
                f"{label}[{index}] is not canonical JSON"
            )
        rows.append(row)
    return rows


def _freeze_tree(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_freeze_tree(item) for item in value)
    if isinstance(value, dict):
        return MappingProxyType(
            {
                str(key): _freeze_tree(item)
                for key, item in sorted(value.items())
            }
        )
    return value


def _thaw_tree(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_thaw_tree(item) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _thaw_tree(item)
            for key, item in sorted(value.items())
        }
    return value


@dataclass(frozen=True)
class QuantityEvidenceRef:
    evidence_id: str
    claim_kind: str
    claim_digest_sha256: str
    source_url: str
    source_record_id: str
    source_revision: str
    license: str
    source_statement_sha256: str
    externally_authenticated: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StagedSpecies:
    row_id: str
    canonical_id: str
    alias: str
    role: str
    equivalents_per_mole: int
    evidence: QuantityEvidenceRef

    @property
    def proof_fact(self) -> tuple[str, str, str]:
        return (
            self.canonical_id,
            f"{self.role}_equivalents_per_mole",
            str(self.equivalents_per_mole),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "canonical_id": self.canonical_id,
            "alias": self.alias,
            "role": self.role,
            "equivalents_per_mole": self.equivalents_per_mole,
            "evidence": self.evidence.to_dict(),
        }


@dataclass(frozen=True)
class StagedFormula:
    rule_id: str
    family: str
    expression: tuple[Any, ...]
    input_dimensions: Mapping[str, str]
    result_dimension: str
    output_unit: str
    evidence: QuantityEvidenceRef

    @property
    def expression_digest_sha256(self) -> str:
        return canonical_digest(_thaw_tree(self.expression))

    @property
    def proof_fact(self) -> tuple[str, str, str]:
        return (
            self.rule_id,
            "formula_expression_sha256",
            self.expression_digest_sha256,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "family": self.family,
            "expression": _thaw_tree(self.expression),
            "input_dimensions": _thaw_tree(self.input_dimensions),
            "result_dimension": self.result_dimension,
            "output_unit": self.output_unit,
            "evidence": self.evidence.to_dict(),
        }


def _snapshot_tag(
    *,
    stage_id: str,
    stage_digest_sha256: str,
    manifest_checksum_sha256: str,
    bound_bytes: int,
    species: tuple[StagedSpecies, ...],
    formulas: tuple[StagedFormula, ...],
) -> str:
    payload = {
        "stage_id": stage_id,
        "stage_digest_sha256": stage_digest_sha256,
        "manifest_checksum_sha256": manifest_checksum_sha256,
        "bound_bytes": bound_bytes,
        "species": [row.to_dict() for row in species],
        "formulas": [row.to_dict() for row in formulas],
    }
    return hmac.new(
        _VALIDATION_KEY,
        canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@dataclass(frozen=True)
class ScienceQuantityStageSnapshot:
    """Detached immutable view of one fully validated quantity stage."""

    stage_id: str
    stage_digest_sha256: str
    manifest_checksum_sha256: str
    bound_bytes: int
    species: tuple[StagedSpecies, ...]
    formulas: tuple[StagedFormula, ...]
    _species_by_alias: Mapping[str, StagedSpecies]
    _formula_by_id: Mapping[str, StagedFormula]
    _evidence_by_fact: Mapping[tuple[str, str, str], QuantityEvidenceRef]
    _validation_seal: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        self.assert_validated()

    def assert_validated(self) -> None:
        expected = _snapshot_tag(
            stage_id=self.stage_id,
            stage_digest_sha256=self.stage_digest_sha256,
            manifest_checksum_sha256=self.manifest_checksum_sha256,
            bound_bytes=self.bound_bytes,
            species=self.species,
            formulas=self.formulas,
        )
        if (
            type(self._validation_seal) is not str
            or not hmac.compare_digest(expected, self._validation_seal)
        ):
            raise ScienceQuantityStageError(
                "quantity stage validation seal does not bind content"
            )
        expected_species = {row.alias: row for row in self.species}
        expected_formulas = {row.rule_id: row for row in self.formulas}
        expected_evidence = {
            row.proof_fact: row.evidence for row in self.species
        }
        expected_evidence.update(
            {row.proof_fact: row.evidence for row in self.formulas}
        )
        if (
            dict(self._species_by_alias) != expected_species
            or dict(self._formula_by_id) != expected_formulas
            or dict(self._evidence_by_fact) != expected_evidence
        ):
            raise ScienceQuantityStageError(
                "quantity stage indexes do not bind snapshot rows"
            )

    def species_for_alias(self, alias: str) -> StagedSpecies | None:
        if type(alias) is not str:
            return None
        return self._species_by_alias.get(alias)

    def formula_for(self, rule_id: str) -> StagedFormula | None:
        if type(rule_id) is not str:
            return None
        return self._formula_by_id.get(rule_id)

    def evidence_for(
        self,
        fact: tuple[str, str, str],
    ) -> QuantityEvidenceRef | None:
        return self._evidence_by_fact.get(fact)


def _validate_evidence_rows(
    rows: list[dict[str, Any]],
) -> dict[str, QuantityEvidenceRef]:
    evidence: dict[str, QuantityEvidenceRef] = {}
    for index, row in enumerate(rows):
        _require_exact_fields(
            row,
            _EVIDENCE_FIELDS,
            label=f"evidence[{index}]",
        )
        evidence_id = row["evidence_id"]
        match = _EVIDENCE_ID.fullmatch(str(evidence_id))
        if match is None or int(match.group(1)) != index + 1:
            raise ScienceQuantityStageError(
                f"evidence[{index}].evidence_id invalid"
            )
        if evidence_id in evidence:
            raise ScienceQuantityStageError("duplicate evidence id")
        if row["claim_kind"] not in {
            "species_equivalents",
            "formula_rule",
        }:
            raise ScienceQuantityStageError(
                f"evidence[{index}].claim_kind invalid"
            )
        claim_digest = row["claim_digest_sha256"]
        if (
            type(claim_digest) is not str
            or _SHA256.fullmatch(claim_digest) is None
        ):
            raise ScienceQuantityStageError(
                f"evidence[{index}].claim_digest_sha256 invalid"
            )
        source_url = row["source_url"]
        if (
            type(source_url) is not str
            or not source_url.startswith("https://")
            or len(source_url) > 2048
        ):
            raise ScienceQuantityStageError(
                f"evidence[{index}].source_url invalid"
            )
        if (
            type(row["source_record_id"]) is not str
            or _SOURCE_RECORD_ID.fullmatch(row["source_record_id"]) is None
        ):
            raise ScienceQuantityStageError(
                f"evidence[{index}].source_record_id invalid"
            )
        if (
            type(row["source_revision"]) is not str
            or _SOURCE_REVISION.fullmatch(row["source_revision"]) is None
        ):
            raise ScienceQuantityStageError(
                f"evidence[{index}].source_revision invalid"
            )
        if (
            type(row["license"]) is not str
            or _LICENSE.fullmatch(row["license"]) is None
        ):
            raise ScienceQuantityStageError(
                f"evidence[{index}].license invalid"
            )
        statement = row["source_statement"]
        statement_digest = row["source_statement_sha256"]
        if (
            type(statement) is not str
            or not statement
            or statement != statement.strip()
            or len(statement.encode("utf-8")) > 2048
            or type(statement_digest) is not str
            or _SHA256.fullmatch(statement_digest) is None
            or statement_digest
            != _sha256(statement.encode("utf-8"))
        ):
            raise ScienceQuantityStageError(
                f"evidence[{index}] source statement binding invalid"
            )
        if row["externally_authenticated"] is not False:
            raise ScienceQuantityStageError(
                "development stage cannot assert external authentication"
            )
        evidence[evidence_id] = QuantityEvidenceRef(
            evidence_id=evidence_id,
            claim_kind=row["claim_kind"],
            claim_digest_sha256=claim_digest,
            source_url=source_url,
            source_record_id=row["source_record_id"],
            source_revision=row["source_revision"],
            license=row["license"],
            source_statement_sha256=statement_digest,
            externally_authenticated=False,
        )
    return evidence


def load_science_quantity_stage(
    root: str | Path,
) -> ScienceQuantityStageSnapshot:
    """Load an all-or-nothing scalar stage generation."""

    stage_root = Path(root)
    if _is_link_or_reparse(stage_root) or not stage_root.is_dir():
        raise ScienceQuantityStageError(
            "quantity stage root must be a regular directory"
        )
    expected_files = {
        MANIFEST_NAME,
        SPECIES_NAME,
        FORMULAS_NAME,
        EVIDENCE_NAME,
    }
    try:
        present = {entry.name for entry in stage_root.iterdir()}
    except OSError as exc:
        raise ScienceQuantityStageError(
            "quantity stage directory is unreadable"
        ) from exc
    if present != expected_files:
        raise ScienceQuantityStageError("quantity stage file set mismatch")

    manifest_bytes = _read_stable(stage_root / MANIFEST_NAME)
    species_bytes = _read_stable(stage_root / SPECIES_NAME)
    formulas_bytes = _read_stable(stage_root / FORMULAS_NAME)
    evidence_bytes = _read_stable(stage_root / EVIDENCE_NAME)
    manifest = _strict_object(
        manifest_bytes,
        label="quantity stage manifest",
    )
    if (
        manifest_bytes
        != canonical_json(manifest).encode("utf-8") + b"\n"
    ):
        raise ScienceQuantityStageError(
            "quantity stage manifest is not canonical JSON"
        )
    _require_exact_fields(
        manifest,
        _ROOT_FIELDS,
        label="quantity stage manifest",
    )
    if manifest["schema_version"] != SCIENCE_QUANTITY_STAGE_SCHEMA:
        raise ScienceQuantityStageError("quantity stage schema mismatch")
    if _STAGE_ID.fullmatch(str(manifest["stage_id"])) is None:
        raise ScienceQuantityStageError("quantity stage id invalid")
    if (
        manifest["classification"]
        != "frozen_scalar_development_probe_not_e5"
        or manifest["completion_state"] != "complete"
        or manifest["evaluation_only"] is not True
        or manifest["promotion_eligible"] is not False
    ):
        raise ScienceQuantityStageError(
            "quantity stage authority or completion state invalid"
        )
    if manifest["relation_profile"] != [
        "species_role",
        "equivalents_per_mole",
        "formula_rule",
    ]:
        raise ScienceQuantityStageError(
            "quantity stage relation profile invalid"
        )
    policy = _require_exact_fields(
        manifest["provenance_policy"],
        _POLICY_FIELDS,
        label="provenance_policy",
    )
    expected_policy = {
        "one_to_one_claim_evidence": True,
        "source_statement_digest_required": True,
        "source_revision_required": True,
        "license_required": True,
        "quarantined_rows_allowed": False,
        "external_authentication_required": False,
    }
    if (
        any(type(policy[key]) is not bool for key in expected_policy)
        or policy != expected_policy
    ):
        raise ScienceQuantityStageError(
            "quantity stage provenance policy invalid"
        )
    claims = _require_exact_fields(
        manifest["claims"],
        _CLAIM_FIELDS,
        label="claims",
    )
    expected_claims = {
        "e4_development_only": True,
        "e5_eligible": False,
        "benchmark_capability_claimed": False,
        "independent_evaluator_claimed": False,
        "external_authenticity_established": False,
    }
    if (
        any(type(claims[key]) is not bool for key in expected_claims)
        or claims != expected_claims
    ):
        raise ScienceQuantityStageError("quantity stage claims invalid")
    checksum = manifest["manifest_checksum_sha256"]
    if (
        type(checksum) is not str
        or _SHA256.fullmatch(checksum) is None
        or checksum != _manifest_checksum(manifest)
    ):
        raise ScienceQuantityStageError(
            "quantity stage manifest checksum mismatch"
        )
    _validate_file_binding(
        manifest["species_file"],
        path=SPECIES_NAME,
        payload=species_bytes,
        label="species_file",
    )
    _validate_file_binding(
        manifest["formulas_file"],
        path=FORMULAS_NAME,
        payload=formulas_bytes,
        label="formulas_file",
    )
    _validate_file_binding(
        manifest["evidence_file"],
        path=EVIDENCE_NAME,
        payload=evidence_bytes,
        label="evidence_file",
    )

    species_rows = _parse_jsonl(
        species_bytes,
        label="species",
        maximum=MAX_SPECIES_ROWS,
    )
    formula_rows = _parse_jsonl(
        formulas_bytes,
        label="formulas",
        maximum=MAX_FORMULA_ROWS,
    )
    evidence_rows = _parse_jsonl(
        evidence_bytes,
        label="evidence",
        maximum=MAX_SPECIES_ROWS + MAX_FORMULA_ROWS,
    )
    if (
        type(manifest["species_count"]) is not int
        or manifest["species_count"] != len(species_rows)
        or type(manifest["formula_count"]) is not int
        or manifest["formula_count"] != len(formula_rows)
        or len(evidence_rows) != len(species_rows) + len(formula_rows)
    ):
        raise ScienceQuantityStageError(
            "quantity stage row counts do not align"
        )
    evidence = _validate_evidence_rows(evidence_rows)

    staged_species: list[StagedSpecies] = []
    aliases: set[str] = set()
    canonical_roles: dict[str, tuple[str, int]] = {}
    used_evidence: set[str] = set()
    for index, row in enumerate(species_rows):
        _require_exact_fields(
            row,
            _SPECIES_FIELDS,
            label=f"species[{index}]",
        )
        row_match = _ROW_ID.fullmatch(str(row["row_id"]))
        if row_match is None or int(row_match.group(1)) != index + 1:
            raise ScienceQuantityStageError(
                f"species[{index}].row_id invalid"
            )
        canonical_id = row["canonical_id"]
        alias = row["alias"]
        role = row["role"]
        equivalents = row["equivalents_per_mole"]
        evidence_id = row["evidence_id"]
        if (
            type(canonical_id) is not str
            or _CANONICAL_ID.fullmatch(canonical_id) is None
        ):
            raise ScienceQuantityStageError(
                f"species[{index}].canonical_id invalid"
            )
        if (
            type(alias) is not str
            or _ALIAS.fullmatch(alias) is None
            or alias in aliases
        ):
            raise ScienceQuantityStageError(
                f"species[{index}].alias invalid or duplicate"
            )
        if role not in {"acid", "base"}:
            raise ScienceQuantityStageError(
                f"species[{index}].role invalid"
            )
        if type(equivalents) is not int or not 1 <= equivalents <= 8:
            raise ScienceQuantityStageError(
                f"species[{index}].equivalents invalid"
            )
        if row["quarantined"] is not False:
            raise ScienceQuantityStageError(
                f"species[{index}] is quarantined"
            )
        ref = evidence.get(str(evidence_id))
        claim_digest = canonical_digest(
            {
                "kind": "species_equivalents",
                "canonical_id": canonical_id,
                "alias": alias,
                "role": role,
                "equivalents_per_mole": equivalents,
            }
        )
        if (
            ref is None
            or ref.claim_kind != "species_equivalents"
            or ref.claim_digest_sha256 != claim_digest
            or evidence_id in used_evidence
        ):
            raise ScienceQuantityStageError(
                f"species[{index}] evidence binding invalid"
            )
        if canonical_id in canonical_roles:
            raise ScienceQuantityStageError(
                "quantity stage v1 permits one alias per canonical species"
            )
        canonical_roles[canonical_id] = (role, equivalents)
        aliases.add(alias)
        used_evidence.add(evidence_id)
        staged_species.append(
            StagedSpecies(
                row_id=row["row_id"],
                canonical_id=canonical_id,
                alias=alias,
                role=role,
                equivalents_per_mole=equivalents,
                evidence=ref,
            )
        )

    staged_formulas: list[StagedFormula] = []
    formula_ids: set[str] = set()
    expected_dimensions = {
        "known_concentration": "amount_per_volume",
        "known_volume_l": "volume",
        "known_equivalents": "dimensionless",
        "target_concentration": "amount_per_volume",
        "target_equivalents": "dimensionless",
    }
    for index, row in enumerate(formula_rows):
        _require_exact_fields(
            row,
            _FORMULA_FIELDS,
            label=f"formulas[{index}]",
        )
        rule_id = row["rule_id"]
        evidence_id = row["evidence_id"]
        if (
            rule_id != NEUTRALIZATION_FORMULA_ID
            or rule_id in formula_ids
            or row["family"] != "acid_base_complete_neutralization"
            or row["expression"] != NEUTRALIZATION_EXPRESSION
            or row["input_dimensions"] != expected_dimensions
            or row["result_dimension"] != "volume"
            or row["output_unit"] != "L"
            or row["quarantined"] is not False
        ):
            raise ScienceQuantityStageError(
                f"formulas[{index}] contract invalid"
            )
        dimension = evaluate_dimension_ast(
            row["expression"],
            {
                "known_concentration": CONCENTRATION,
                "known_volume_l": VOLUME,
                "known_equivalents": DIMENSIONLESS,
                "target_concentration": CONCENTRATION,
                "target_equivalents": DIMENSIONLESS,
            },
            max_nodes=15,
            max_steps=128,
        )
        if dimension != VOLUME:
            raise ScienceQuantityStageError(
                f"formulas[{index}] dimension proof invalid"
            )
        ref = evidence.get(str(evidence_id))
        claim_digest = canonical_digest(
            {
                "kind": "formula_rule",
                "rule_id": rule_id,
                "family": row["family"],
                "expression": row["expression"],
                "input_dimensions": row["input_dimensions"],
                "result_dimension": row["result_dimension"],
                "output_unit": row["output_unit"],
            }
        )
        if (
            ref is None
            or ref.claim_kind != "formula_rule"
            or ref.claim_digest_sha256 != claim_digest
            or evidence_id in used_evidence
        ):
            raise ScienceQuantityStageError(
                f"formulas[{index}] evidence binding invalid"
            )
        formula_ids.add(rule_id)
        used_evidence.add(evidence_id)
        staged_formulas.append(
            StagedFormula(
                rule_id=rule_id,
                family=row["family"],
                expression=_freeze_tree(row["expression"]),
                input_dimensions=MappingProxyType(
                    dict(sorted(row["input_dimensions"].items()))
                ),
                result_dimension=row["result_dimension"],
                output_unit=row["output_unit"],
                evidence=ref,
            )
        )
    if formula_ids != {NEUTRALIZATION_FORMULA_ID}:
        raise ScienceQuantityStageError(
            "quantity stage requires exactly the declared formula"
        )
    if used_evidence != set(evidence):
        raise ScienceQuantityStageError(
            "quantity stage contains orphan evidence"
        )

    species_tuple = tuple(staged_species)
    formulas_tuple = tuple(staged_formulas)
    species_index = MappingProxyType(
        {row.alias: row for row in species_tuple}
    )
    formula_index = MappingProxyType(
        {row.rule_id: row for row in formulas_tuple}
    )
    proof_facts = [
        row.proof_fact for row in (*species_tuple, *formulas_tuple)
    ]
    if len(proof_facts) != len(set(proof_facts)):
        raise ScienceQuantityStageError(
            "quantity stage proof identities are not unique"
        )
    evidence_index: dict[
        tuple[str, str, str],
        QuantityEvidenceRef,
    ] = {row.proof_fact: row.evidence for row in species_tuple}
    evidence_index.update(
        {row.proof_fact: row.evidence for row in formulas_tuple}
    )
    stage_digest = canonical_digest(
        {
            "schema_version": SCIENCE_QUANTITY_STAGE_SCHEMA,
            "stage_id": manifest["stage_id"],
            "manifest_checksum_sha256": checksum,
            "species_sha256": _sha256(species_bytes),
            "formulas_sha256": _sha256(formulas_bytes),
            "evidence_sha256": _sha256(evidence_bytes),
            "species_count": len(species_tuple),
            "formula_count": len(formulas_tuple),
        }
    )
    bound_bytes = (
        len(manifest_bytes)
        + len(species_bytes)
        + len(formulas_bytes)
        + len(evidence_bytes)
    )
    seal = _snapshot_tag(
        stage_id=manifest["stage_id"],
        stage_digest_sha256=stage_digest,
        manifest_checksum_sha256=checksum,
        bound_bytes=bound_bytes,
        species=species_tuple,
        formulas=formulas_tuple,
    )
    return ScienceQuantityStageSnapshot(
        stage_id=manifest["stage_id"],
        stage_digest_sha256=stage_digest,
        manifest_checksum_sha256=checksum,
        bound_bytes=bound_bytes,
        species=species_tuple,
        formulas=formulas_tuple,
        _species_by_alias=species_index,
        _formula_by_id=formula_index,
        _evidence_by_fact=MappingProxyType(evidence_index),
        _validation_seal=seal,
    )


class QuantityStageOverlay:
    """Structurally isolated OFF/ON view with exact proof-row attribution."""

    def __init__(
        self,
        snapshot: ScienceQuantityStageSnapshot | None,
        *,
        enabled: bool = False,
    ) -> None:
        if type(enabled) is not bool:
            raise TypeError("enabled must be a boolean")
        if enabled:
            if not isinstance(snapshot, ScienceQuantityStageSnapshot):
                raise TypeError(
                    "enabled quantity overlay requires a validated snapshot"
                )
            snapshot.assert_validated()
        elif snapshot is not None:
            raise TypeError(
                "disabled quantity overlay must not retain a snapshot"
            )
        self.snapshot = snapshot
        self.enabled = enabled
        self.species_lookup_count = 0
        self.formula_lookup_count = 0
        self.stage_hit_count = 0
        self._exposed: set[tuple[str, str, str]] = set()

    def _expose(self, fact: tuple[str, str, str]) -> None:
        if fact not in self._exposed:
            self._exposed.add(fact)
            self.stage_hit_count += 1

    def resolve_species(self, alias: str) -> StagedSpecies | None:
        self.species_lookup_count += 1
        if not self.enabled:
            return None
        if self.snapshot is None:
            raise ScienceQuantityStageError(
                "enabled quantity overlay lost its snapshot"
            )
        self.snapshot.assert_validated()
        row = self.snapshot.species_for_alias(alias)
        if row is not None:
            self._expose(row.proof_fact)
        return row

    def formula(self, rule_id: str) -> StagedFormula | None:
        self.formula_lookup_count += 1
        if not self.enabled:
            return None
        if self.snapshot is None:
            raise ScienceQuantityStageError(
                "enabled quantity overlay lost its snapshot"
            )
        self.snapshot.assert_validated()
        row = self.snapshot.formula_for(rule_id)
        if row is not None:
            self._expose(row.proof_fact)
        return row

    def bind_proof(self, proof: Any) -> dict[str, Any]:
        empty = {
            "grounded_leaf_count": 0,
            "grounded_stage_leaf_count": 0,
            "evidence": [],
            "proof_digest_sha256": None,
            "provenance_digest_sha256": None,
        }
        if proof is None or not callable(getattr(proof, "leaves", None)):
            return empty
        try:
            raw_leaves = proof.leaves()
        except Exception as exc:
            raise ScienceQuantityStageError(
                f"quantity proof leaves unreadable: {type(exc).__name__}"
            ) from exc
        if (
            not isinstance(raw_leaves, (list, tuple))
            or not 1 <= len(raw_leaves) <= MAX_PROOF_LEAVES
        ):
            raise ScienceQuantityStageError(
                "quantity proof leaves are not a bounded sequence"
            )
        if self.snapshot is None:
            return {
                **empty,
                "grounded_leaf_count": len(raw_leaves),
                "proof_digest_sha256": canonical_digest(proof.to_dict()),
            }
        self.snapshot.assert_validated()
        evidence_rows: list[dict[str, Any]] = []
        seen_facts: set[tuple[str, str, str]] = set()
        for index, raw in enumerate(raw_leaves):
            if (
                not isinstance(raw, (tuple, list))
                or len(raw) != 3
                or any(type(item) is not str for item in raw)
            ):
                raise ScienceQuantityStageError(
                    f"quantity proof leaf {index} is not a string triple"
                )
            fact = (raw[0], raw[1], raw[2])
            if fact in seen_facts:
                raise ScienceQuantityStageError(
                    "quantity proof contains a duplicate leaf"
                )
            seen_facts.add(fact)
            ref = (
                self.snapshot.evidence_for(fact)
                if fact in self._exposed
                else None
            )
            if ref is not None:
                evidence_rows.append(ref.to_dict())
        evidence_rows.sort(key=lambda row: row["evidence_id"])
        return {
            "grounded_leaf_count": len(raw_leaves),
            "grounded_stage_leaf_count": len(evidence_rows),
            "evidence": evidence_rows,
            "proof_digest_sha256": canonical_digest(proof.to_dict()),
            "provenance_digest_sha256": (
                canonical_digest(evidence_rows) if evidence_rows else None
            ),
        }

    def telemetry(self) -> dict[str, Any]:
        snapshot = self.snapshot
        return {
            "enabled": self.enabled,
            "profile": "scalar_quantity_resolve",
            "lookup_attempted": (
                self.species_lookup_count + self.formula_lookup_count > 0
            ),
            "lookup_count": (
                self.species_lookup_count + self.formula_lookup_count
            ),
            "species_lookup_count": self.species_lookup_count,
            "formula_lookup_count": self.formula_lookup_count,
            "staged_hit_count": self.stage_hit_count,
            "stage_digest_sha256": (
                snapshot.stage_digest_sha256 if snapshot is not None else None
            ),
            "stage_snapshot_bound_bytes": (
                snapshot.bound_bytes if snapshot is not None else 0
            ),
            "stage_bytes_read": 0,
        }
