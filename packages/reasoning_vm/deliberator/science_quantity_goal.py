"""Typed NL-to-goal compiler for one exact neutralization-volume profile.

This module deliberately recognizes only complete acid/base neutralization
questions with one unknown target volume.  It does not identify acids or bases,
look up stoichiometric equivalents, or solve the question.  Those facts and the
formula must come from a separately validated science stage.

The compiler is deterministic and fail closed:

* all scalars are parsed as :class:`fractions.Fraction`;
* the supplied choice ``Mapping`` is consumed by one bounded ``items()`` read;
* choices are dimension-checked and normalized to exact liters; and
* well-formed questions outside the declared grammar remain valid abstentions.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
import hashlib
from itertools import islice
import re
from typing import Any

from packages.cognitive_core.canonical import FrozenMap, canonical_digest
from packages.evolution.rational_evolver import (
    canonical as canonical_rational,
    parse_value,
)


SCIENCE_QUANTITY_GOAL_SCHEMA = (
    "atanor.deliberator.science_quantity_goal.v1"
)
SCIENCE_QUANTITY_GOAL_FAMILY = "complete_neutralization_base_volume"
SCIENCE_QUANTITY_STAGE_SCHEMA = "atanor.science-quantity-stage.v1"
FORMULA_ID = "complete_neutralization_equivalent_balance_v1"
COMPILER_RULE = "complete_neutralization_base_volume_v1"

MAX_STEM_CHARS = 4096
MIN_CHOICES = 2
MAX_CHOICES = 10
MAX_CHOICE_KEY_CHARS = 16
MAX_CHOICE_TEXT_CHARS = 256
MAX_SPECIES_CHARS = 32
MAX_NUMBER_CHARS = 48
MAX_CONCENTRATION_MOL_PER_LITER = Fraction(100)
MAX_VOLUME_LITERS = Fraction(1000)

_NUMBER = (
    r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d{1,3})?"
)
_SPECIES = (
    r"(?:[A-Z][a-z]?\d*|\((?:[A-Z][a-z]?\d*)+\)\d*)+"
)
_CONCENTRATION_UNIT = r"(?:mol/L|M)"
_VOLUME_UNIT = r"(?:mL|L|milliliters?|millilitres?|liters?|litres?)"
_TARGET_PROMPT = (
    rf"(?:(?:How many (?P<requested_unit>{_VOLUME_UNIT}) of)"
    r"|How much"
    r"|What volume of)"
)
_AUXILIARY = (
    r"(?:does it take|is required|are required|is needed|are needed)"
)
_COMPLETENESS = (
    r"(?:to (?:completely|fully) neutralize"
    r"|to neutralize (?:completely|fully)"
    r"|for (?:the )?complete neutralization of)"
)
_DECLARED_SURFACE = re.compile(
    rf"^{_TARGET_PROMPT} "
    rf"(?P<target_concentration>{_NUMBER})\s*"
    rf"(?P<target_concentration_unit>{_CONCENTRATION_UNIT}) "
    rf"(?P<target_species>{_SPECIES}) "
    rf"{_AUXILIARY} {_COMPLETENESS} "
    rf"(?P<known_volume>{_NUMBER})\s*"
    rf"(?P<known_volume_unit>{_VOLUME_UNIT}) of "
    rf"(?P<known_concentration>{_NUMBER})\s*"
    rf"(?P<known_concentration_unit>{_CONCENTRATION_UNIT}) "
    rf"(?P<known_species>{_SPECIES})\?$"
)
_CHOICE_VOLUME = re.compile(
    rf"^(?P<value>{_NUMBER})\s*(?P<unit>{_VOLUME_UNIT})$"
)
_ROUTER_NEUTRALIZE = re.compile(
    r"\b(?:neutralize|neutralization)\b",
    re.IGNORECASE,
)
_ROUTER_COMPLETE = re.compile(
    r"\b(?:complete(?:ly)?|fully)\b",
    re.IGNORECASE,
)
_ROUTER_VOLUME_QUESTION = re.compile(
    r"^(?:How many|How much|What volume\b)",
    re.IGNORECASE,
)
_UNSUPPORTED_VARIANT = re.compile(
    r"\b(?:partial(?:ly)?|pH|buffer(?:ed|s)?|mixtures?|normality|"
    r"equivalent weight|mass|grams?|kilograms?|excess)\b",
    re.IGNORECASE,
)


def _text_descriptor(value: Any) -> dict[str, Any]:
    if type(value) is not str:
        return {"python_type": type(value).__name__}
    encoded = value.encode("utf-8", "surrogatepass")
    return {
        "python_type": "str",
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _input_fingerprint(
    stem: Any,
    choice_descriptor: Mapping[str, Any],
) -> str:
    return canonical_digest(
        {
            "schema_version": SCIENCE_QUANTITY_GOAL_SCHEMA,
            "stem": _text_descriptor(stem),
            "choices": dict(choice_descriptor),
        }
    )


def _validate_stem(stem: Any) -> str | None:
    if type(stem) is not str:
        return "stem_not_string"
    if (
        not stem
        or stem != stem.strip()
        or len(stem) > MAX_STEM_CHARS
        or "\x00" in stem
    ):
        return "stem_out_of_bounds"
    return None


def _snapshot_choices(
    choices: Any,
) -> tuple[dict[str, str] | None, dict[str, Any], str | None]:
    """Consume a Mapping through one bounded ``items()`` iteration."""

    if not isinstance(choices, Mapping):
        return (
            None,
            {"python_type": type(choices).__name__},
            "choices_not_mapping",
        )
    try:
        items = list(islice(iter(choices.items()), MAX_CHOICES + 1))
    except Exception as exc:
        return (
            None,
            {
                "python_type": type(choices).__name__,
                "read_error": type(exc).__name__,
            },
            "choices_unreadable",
        )

    descriptor_rows: list[dict[str, Any]] = []
    pairs: list[tuple[Any, Any]] = []
    for item in items:
        try:
            key, value = item
        except Exception:
            descriptor_rows.append(
                {"mapping_item": {"python_type": type(item).__name__}}
            )
            descriptor_rows.sort(key=canonical_digest)
            return (
                None,
                {
                    "python_type": type(choices).__name__,
                    "count": len(items),
                    "items": descriptor_rows,
                    "truncated": len(items) > MAX_CHOICES,
                },
                "choices_unreadable",
            )
        pairs.append((key, value))
        descriptor_rows.append(
            {
                "key": _text_descriptor(key),
                "value": _text_descriptor(value),
            }
        )

    descriptor_rows.sort(key=canonical_digest)
    descriptor = {
        "python_type": type(choices).__name__,
        "count": len(items),
        "items": descriptor_rows,
        "truncated": len(items) > MAX_CHOICES,
    }
    if not MIN_CHOICES <= len(items) <= MAX_CHOICES:
        return None, descriptor, "choice_count_out_of_bounds"

    snapshot: dict[str, str] = {}
    for key, value in pairs:
        if (
            type(key) is not str
            or not key
            or key != key.strip()
            or len(key) > MAX_CHOICE_KEY_CHARS
            or "\x00" in key
        ):
            return None, descriptor, "invalid_choice_key"
        if key in snapshot:
            return None, descriptor, "duplicate_choice_key"
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or len(value) > MAX_CHOICE_TEXT_CHARS
            or "\x00" in value
        ):
            return None, descriptor, "invalid_choice_text"
        snapshot[key] = value
    return snapshot, descriptor, None


def _canonical_volume_unit(raw: str) -> tuple[str, Fraction] | None:
    if raw in {"mL", "milliliter", "milliliters", "millilitre", "millilitres"}:
        return "mL", Fraction(1, 1000)
    if raw in {"L", "liter", "liters", "litre", "litres"}:
        return "L", Fraction(1)
    return None


def _bounded_positive(
    raw: str,
    maximum: Fraction,
) -> Fraction | None:
    if type(raw) is not str or not raw or len(raw) > MAX_NUMBER_CHARS:
        return None
    value = parse_value(raw)
    if value is None or value <= 0 or value > maximum:
        return None
    return value


def _volume_in_liters(
    value_raw: str,
    unit_raw: str,
) -> tuple[Fraction, str] | None:
    unit = _canonical_volume_unit(unit_raw)
    value = _bounded_positive(value_raw, MAX_VOLUME_LITERS * 1000)
    if unit is None or value is None:
        return None
    source_unit, multiplier = unit
    liters = value * multiplier
    if liters <= 0 or liters > MAX_VOLUME_LITERS:
        return None
    return liters, source_unit


def looks_like_complete_neutralization(stem: Any) -> bool:
    """Cheap, stem-only router predicate for the declared profile.

    A ``True`` result is only a routing hint.  Full grammar, scalar, unit, and
    choice validation remains the responsibility of
    :func:`compile_neutralization_question`.
    """

    if _validate_stem(stem) is not None:
        return False
    assert isinstance(stem, str)
    if _UNSUPPORTED_VARIANT.search(stem) is not None:
        return False
    return bool(
        _ROUTER_VOLUME_QUESTION.search(stem)
        and _ROUTER_NEUTRALIZE.search(stem)
        and _ROUTER_COMPLETE.search(stem)
    )


@dataclass(frozen=True)
class TextSpanBinding:
    """Hash-bound source span for one entity or prompt quantity."""

    slot: str
    start: int
    end: int
    text_bytes: int
    text_sha256: str

    def __post_init__(self) -> None:
        if self.slot not in {
            "target_concentration",
            "target_species",
            "known_volume",
            "known_concentration",
            "known_species",
        }:
            raise ValueError("quantity source span slot is invalid")
        if (
            type(self.start) is not int
            or type(self.end) is not int
            or not 0 <= self.start < self.end <= MAX_STEM_CHARS
            or type(self.text_bytes) is not int
            or self.text_bytes <= 0
            or type(self.text_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", self.text_sha256) is None
        ):
            raise ValueError("quantity source span binding is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "start": self.start,
            "end": self.end,
            "text_bytes": self.text_bytes,
            "text_sha256": self.text_sha256,
        }


def _span_binding(
    stem: str,
    *,
    slot: str,
    start: int,
    end: int,
) -> TextSpanBinding:
    text = stem[start:end]
    encoded = text.encode("utf-8")
    return TextSpanBinding(
        slot=slot,
        start=start,
        end=end,
        text_bytes=len(encoded),
        text_sha256=hashlib.sha256(encoded).hexdigest(),
    )


@dataclass(frozen=True)
class NormalizedVolumeChoice:
    key: str
    original_text: str
    value_liters: Fraction
    source_unit: str

    def __post_init__(self) -> None:
        if (
            type(self.key) is not str
            or not self.key
            or type(self.original_text) is not str
            or not self.original_text
            or type(self.value_liters) is not Fraction
            or self.value_liters <= 0
            or self.value_liters > MAX_VOLUME_LITERS
            or self.source_unit not in {"mL", "L"}
        ):
            raise ValueError("normalized volume choice is invalid")

    @property
    def canonical_liters(self) -> str:
        return canonical_rational(self.value_liters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "original_text": self.original_text,
            "value_liters": self.canonical_liters,
            "unit": "L",
            "source_unit": self.source_unit,
        }


@dataclass(frozen=True)
class QuantityStageEvidenceRequirement:
    evidence_kind: str
    subject_role: str
    relation_or_formula: str
    stage_schema: str
    exact_row_provenance: bool
    source_revision_required: bool
    license_required: bool
    quarantined_allowed: bool

    def __post_init__(self) -> None:
        if self.evidence_kind not in {"fact", "formula"}:
            raise ValueError("quantity evidence kind is invalid")
        if self.subject_role not in {
            "known_species",
            "target_species",
            "formula",
        }:
            raise ValueError("quantity evidence subject role is invalid")
        if not self.relation_or_formula:
            raise ValueError("quantity evidence relation is required")
        if self.stage_schema != SCIENCE_QUANTITY_STAGE_SCHEMA:
            raise ValueError("quantity evidence stage schema is invalid")
        if (
            self.exact_row_provenance is not True
            or self.source_revision_required is not True
            or self.license_required is not True
            or self.quarantined_allowed is not False
        ):
            raise ValueError("quantity evidence must be provenance strict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_kind": self.evidence_kind,
            "subject_role": self.subject_role,
            "relation_or_formula": self.relation_or_formula,
            "stage_schema": self.stage_schema,
            "exact_row_provenance": self.exact_row_provenance,
            "source_revision_required": self.source_revision_required,
            "license_required": self.license_required,
            "quarantined_allowed": self.quarantined_allowed,
        }


@dataclass(frozen=True)
class TypedNeutralizationVolumeGoal:
    known_species: str
    target_species: str
    known_role_required: str
    target_role_required: str
    known_concentration_mol_per_liter: Fraction
    target_concentration_mol_per_liter: Fraction
    known_volume_liters: Fraction
    source_spans: tuple[TextSpanBinding, ...]
    unknown_quantity: str
    result_dimension: str
    result_unit: str
    formula_id: str
    compiler_rule: str

    def __post_init__(self) -> None:
        for species in (self.known_species, self.target_species):
            if (
                type(species) is not str
                or not species
                or len(species) > MAX_SPECIES_CHARS
                or re.fullmatch(_SPECIES, species) is None
            ):
                raise ValueError("neutralization species is invalid")
        for concentration in (
            self.known_concentration_mol_per_liter,
            self.target_concentration_mol_per_liter,
        ):
            if (
                type(concentration) is not Fraction
                or concentration <= 0
                or concentration > MAX_CONCENTRATION_MOL_PER_LITER
            ):
                raise ValueError("neutralization concentration is invalid")
        if (
            self.known_role_required != "acid"
            or self.target_role_required != "base"
        ):
            raise ValueError(
                "neutralization v1 requires known acid and target base"
            )
        if (
            type(self.known_volume_liters) is not Fraction
            or self.known_volume_liters <= 0
            or self.known_volume_liters > MAX_VOLUME_LITERS
        ):
            raise ValueError("neutralization known volume is invalid")
        if (
            type(self.source_spans) is not tuple
            or len(self.source_spans) != 5
            or {row.slot for row in self.source_spans}
            != {
                "target_concentration",
                "target_species",
                "known_volume",
                "known_concentration",
                "known_species",
            }
        ):
            raise ValueError(
                "neutralization goal requires five source span bindings"
            )
        if self.unknown_quantity != "base_volume":
            raise ValueError("neutralization profile has one base-volume unknown")
        if self.result_dimension != "volume" or self.result_unit != "L":
            raise ValueError("neutralization result must be a volume in liters")
        if self.formula_id != FORMULA_ID or self.compiler_rule != COMPILER_RULE:
            raise ValueError("neutralization formula/compiler contract is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "known_species": self.known_species,
            "target_species": self.target_species,
            "known_role_required": self.known_role_required,
            "target_role_required": self.target_role_required,
            "known_concentration_mol_per_liter": canonical_rational(
                self.known_concentration_mol_per_liter
            ),
            "target_concentration_mol_per_liter": canonical_rational(
                self.target_concentration_mol_per_liter
            ),
            "known_volume_liters": canonical_rational(
                self.known_volume_liters
            ),
            "source_spans": [row.to_dict() for row in self.source_spans],
            "unknown_quantity": self.unknown_quantity,
            "result_dimension": self.result_dimension,
            "result_unit": self.result_unit,
            "formula_id": self.formula_id,
            "compiler_rule": self.compiler_rule,
        }


@dataclass(frozen=True)
class NeutralizationCompilation:
    schema_version: str
    input_valid: bool
    status: str
    surface_family: str | None
    goals: tuple[TypedNeutralizationVolumeGoal, ...]
    constraints: tuple[FrozenMap, ...]
    required_evidence: tuple[QuantityStageEvidenceRequirement, ...]
    reason: str
    input_fingerprint: str
    goal_digest_sha256: str | None
    compiler_rule: str | None
    choice_items: tuple[NormalizedVolumeChoice, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SCIENCE_QUANTITY_GOAL_SCHEMA:
            raise ValueError("unsupported quantity compiler schema")
        if self.status not in {"compiled", "abstain", "invalid"}:
            raise ValueError("invalid quantity compiler status")
        if not re.fullmatch(r"[0-9a-f]{64}", self.input_fingerprint):
            raise ValueError("quantity input fingerprint is invalid")
        if self.status == "compiled":
            if (
                self.input_valid is not True
                or self.surface_family != SCIENCE_QUANTITY_GOAL_FAMILY
                or len(self.goals) != 1
                or not self.constraints
                or len(self.required_evidence) != 3
                or self.goal_digest_sha256 is None
                or self.compiler_rule != COMPILER_RULE
                or not MIN_CHOICES <= len(self.choice_items) <= MAX_CHOICES
            ):
                raise ValueError("compiled quantity receipt is incomplete")
            if any(not isinstance(item, FrozenMap) for item in self.constraints):
                raise ValueError("quantity constraints must be immutable")
            if len({item.key for item in self.choice_items}) != len(
                self.choice_items
            ):
                raise ValueError("quantity receipt has duplicate choice keys")
            if len({item.value_liters for item in self.choice_items}) != len(
                self.choice_items
            ):
                raise ValueError("quantity receipt has duplicate exact choices")
        elif (
            self.surface_family is not None
            or self.goals
            or self.constraints
            or self.required_evidence
            or self.goal_digest_sha256 is not None
            or self.compiler_rule is not None
            or self.choice_items
        ):
            raise ValueError("non-compiled receipt cannot carry a goal plan")
        if self.status == "invalid" and self.input_valid is not False:
            raise ValueError("invalid receipt cannot mark input valid")
        if self.status == "abstain" and self.input_valid is not True:
            raise ValueError("abstention must preserve evaluator eligibility")
        if self.goal_digest_sha256 is not None and re.fullmatch(
            r"[0-9a-f]{64}", self.goal_digest_sha256
        ) is None:
            raise ValueError("quantity goal digest is invalid")

    @property
    def compiled(self) -> bool:
        return self.status == "compiled"

    @property
    def goal(self) -> TypedNeutralizationVolumeGoal | None:
        return self.goals[0] if self.goals else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "input_valid": self.input_valid,
            "status": self.status,
            "compiled": self.compiled,
            "surface_family": self.surface_family,
            "goals": [item.to_dict() for item in self.goals],
            "constraints": [item.to_dict() for item in self.constraints],
            "required_evidence": [
                item.to_dict() for item in self.required_evidence
            ],
            "reason": self.reason,
            "input_fingerprint": self.input_fingerprint,
            "goal_digest_sha256": self.goal_digest_sha256,
            "compiler_rule": self.compiler_rule,
            "choice_items": [
                item.to_dict() for item in self.choice_items
            ],
        }


def verify_compilation_source_spans(
    compilation: NeutralizationCompilation,
    stem: Any,
) -> bool:
    """Replay the declared surface and bind every parsed value to raw NL."""

    if (
        type(compilation) is not NeutralizationCompilation
        or not compilation.compiled
        or type(stem) is not str
        or compilation.goal is None
    ):
        return False
    match = _DECLARED_SURFACE.fullmatch(stem)
    if match is None:
        return False
    expected_spans = (
        _span_binding(
            stem,
            slot="target_concentration",
            start=match.start("target_concentration"),
            end=match.end("target_concentration_unit"),
        ),
        _span_binding(
            stem,
            slot="target_species",
            start=match.start("target_species"),
            end=match.end("target_species"),
        ),
        _span_binding(
            stem,
            slot="known_volume",
            start=match.start("known_volume"),
            end=match.end("known_volume_unit"),
        ),
        _span_binding(
            stem,
            slot="known_concentration",
            start=match.start("known_concentration"),
            end=match.end("known_concentration_unit"),
        ),
        _span_binding(
            stem,
            slot="known_species",
            start=match.start("known_species"),
            end=match.end("known_species"),
        ),
    )
    known_concentration = _bounded_positive(
        match.group("known_concentration"),
        MAX_CONCENTRATION_MOL_PER_LITER,
    )
    target_concentration = _bounded_positive(
        match.group("target_concentration"),
        MAX_CONCENTRATION_MOL_PER_LITER,
    )
    known_volume = _volume_in_liters(
        match.group("known_volume"),
        match.group("known_volume_unit"),
    )
    goal = compilation.goal
    return (
        goal.source_spans == expected_spans
        and goal.known_species == match.group("known_species")
        and goal.target_species == match.group("target_species")
        and goal.known_role_required == "acid"
        and goal.target_role_required == "base"
        and known_concentration
        == goal.known_concentration_mol_per_liter
        and target_concentration
        == goal.target_concentration_mol_per_liter
        and known_volume is not None
        and known_volume[0] == goal.known_volume_liters
    )


def _empty_compilation(
    *,
    input_valid: bool,
    status: str,
    reason: str,
    input_fingerprint: str,
) -> NeutralizationCompilation:
    return NeutralizationCompilation(
        schema_version=SCIENCE_QUANTITY_GOAL_SCHEMA,
        input_valid=input_valid,
        status=status,
        surface_family=None,
        goals=(),
        constraints=(),
        required_evidence=(),
        reason=reason,
        input_fingerprint=input_fingerprint,
        goal_digest_sha256=None,
        compiler_rule=None,
        choice_items=(),
    )


def _normalize_choices(
    choices: Mapping[str, str],
    *,
    requested_unit: str | None,
) -> tuple[tuple[NormalizedVolumeChoice, ...] | None, str | None]:
    normalized: list[NormalizedVolumeChoice] = []
    source_units: set[str] = set()
    exact_values: set[Fraction] = set()
    for key, text in choices.items():
        match = _CHOICE_VOLUME.fullmatch(text)
        if match is None:
            return None, "choice_not_exact_volume"
        volume = _volume_in_liters(match.group("value"), match.group("unit"))
        if volume is None:
            return None, "choice_volume_out_of_bounds"
        value_liters, source_unit = volume
        if value_liters in exact_values:
            return None, "duplicate_normalized_choices"
        exact_values.add(value_liters)
        source_units.add(source_unit)
        normalized.append(
            NormalizedVolumeChoice(
                key=key,
                original_text=text,
                value_liters=value_liters,
                source_unit=source_unit,
            )
        )
    if len(source_units) != 1:
        return None, "mixed_choice_volume_units"
    if requested_unit is not None:
        requested = _canonical_volume_unit(requested_unit)
        if requested is None or requested[0] not in source_units:
            return None, "choice_unit_mismatches_requested_unit"
    normalized.sort(key=lambda item: item.key)
    return tuple(normalized), None


def _evidence_requirements() -> tuple[
    QuantityStageEvidenceRequirement,
    ...,
]:
    strict = {
        "stage_schema": SCIENCE_QUANTITY_STAGE_SCHEMA,
        "exact_row_provenance": True,
        "source_revision_required": True,
        "license_required": True,
        "quarantined_allowed": False,
    }
    return (
        QuantityStageEvidenceRequirement(
            evidence_kind="fact",
            subject_role="known_species",
            relation_or_formula="acid_equivalents_per_mole",
            **strict,
        ),
        QuantityStageEvidenceRequirement(
            evidence_kind="fact",
            subject_role="target_species",
            relation_or_formula="base_equivalents_per_mole",
            **strict,
        ),
        QuantityStageEvidenceRequirement(
            evidence_kind="formula",
            subject_role="formula",
            relation_or_formula=FORMULA_ID,
            **strict,
        ),
    )


def compile_neutralization_question(
    stem: Any,
    choices: Any,
) -> NeutralizationCompilation:
    """Compile the declared exact target-volume profile or fail closed."""

    exact_choices, choice_descriptor, choice_reason = _snapshot_choices(choices)
    fingerprint = _input_fingerprint(stem, choice_descriptor)
    stem_reason = _validate_stem(stem)
    invalid_reason = stem_reason or choice_reason
    if invalid_reason is not None or exact_choices is None:
        return _empty_compilation(
            input_valid=False,
            status="invalid",
            reason=invalid_reason or "choices_unreadable",
            input_fingerprint=fingerprint,
        )

    assert isinstance(stem, str)
    if _UNSUPPORTED_VARIANT.search(stem) is not None:
        return _empty_compilation(
            input_valid=True,
            status="abstain",
            reason="unsupported_neutralization_variant",
            input_fingerprint=fingerprint,
        )
    match = _DECLARED_SURFACE.fullmatch(stem)
    if match is None:
        return _empty_compilation(
            input_valid=True,
            status="abstain",
            reason="unsupported_goal_family",
            input_fingerprint=fingerprint,
        )

    known_concentration = _bounded_positive(
        match.group("known_concentration"),
        MAX_CONCENTRATION_MOL_PER_LITER,
    )
    target_concentration = _bounded_positive(
        match.group("target_concentration"),
        MAX_CONCENTRATION_MOL_PER_LITER,
    )
    known_volume = _volume_in_liters(
        match.group("known_volume"),
        match.group("known_volume_unit"),
    )
    if known_concentration is None or target_concentration is None:
        return _empty_compilation(
            input_valid=False,
            status="invalid",
            reason="concentration_out_of_bounds",
            input_fingerprint=fingerprint,
        )
    if known_volume is None:
        return _empty_compilation(
            input_valid=False,
            status="invalid",
            reason="known_volume_out_of_bounds",
            input_fingerprint=fingerprint,
        )

    normalized_choices, choice_semantic_reason = _normalize_choices(
        exact_choices,
        requested_unit=match.group("requested_unit"),
    )
    if normalized_choices is None:
        return _empty_compilation(
            input_valid=False,
            status="invalid",
            reason=choice_semantic_reason or "invalid_volume_choices",
            input_fingerprint=fingerprint,
        )

    known_volume_liters, _known_source_unit = known_volume
    source_spans = (
        _span_binding(
            stem,
            slot="target_concentration",
            start=match.start("target_concentration"),
            end=match.end("target_concentration_unit"),
        ),
        _span_binding(
            stem,
            slot="target_species",
            start=match.start("target_species"),
            end=match.end("target_species"),
        ),
        _span_binding(
            stem,
            slot="known_volume",
            start=match.start("known_volume"),
            end=match.end("known_volume_unit"),
        ),
        _span_binding(
            stem,
            slot="known_concentration",
            start=match.start("known_concentration"),
            end=match.end("known_concentration_unit"),
        ),
        _span_binding(
            stem,
            slot="known_species",
            start=match.start("known_species"),
            end=match.end("known_species"),
        ),
    )
    goal = TypedNeutralizationVolumeGoal(
        known_species=match.group("known_species"),
        target_species=match.group("target_species"),
        known_role_required="acid",
        target_role_required="base",
        known_concentration_mol_per_liter=known_concentration,
        target_concentration_mol_per_liter=target_concentration,
        known_volume_liters=known_volume_liters,
        source_spans=source_spans,
        unknown_quantity="base_volume",
        result_dimension="volume",
        result_unit="L",
        formula_id=FORMULA_ID,
        compiler_rule=COMPILER_RULE,
    )
    constraints = (
        FrozenMap(
            {
                "kind": "unknown_cardinality",
                "quantity": "base_volume",
                "cardinality": "exactly_one",
            }
        ),
        FrozenMap(
            {
                "kind": "required_entity_roles",
                "known_species": "acid",
                "target_species": "base",
            }
        ),
        FrozenMap(
            {
                "kind": "exact_rational_quantity",
                "dimension": "volume",
                "canonical_unit": "L",
                "binary_float_allowed": False,
            }
        ),
        FrozenMap(
            {
                "kind": "stage_bound_formula",
                "formula_id": FORMULA_ID,
                "required_species_fact_count": 2,
            }
        ),
    )
    required_evidence = _evidence_requirements()
    goal_payload = {
        "schema_version": SCIENCE_QUANTITY_GOAL_SCHEMA,
        "surface_family": SCIENCE_QUANTITY_GOAL_FAMILY,
        "goal": goal.to_dict(),
        "constraints": [item.to_dict() for item in constraints],
        "required_evidence": [
            item.to_dict() for item in required_evidence
        ],
        "choices": [item.to_dict() for item in normalized_choices],
        "input_fingerprint": fingerprint,
    }
    return NeutralizationCompilation(
        schema_version=SCIENCE_QUANTITY_GOAL_SCHEMA,
        input_valid=True,
        status="compiled",
        surface_family=SCIENCE_QUANTITY_GOAL_FAMILY,
        goals=(goal,),
        constraints=constraints,
        required_evidence=required_evidence,
        reason="typed_neutralization_volume_goal_emitted",
        input_fingerprint=fingerprint,
        goal_digest_sha256=canonical_digest(goal_payload),
        compiler_rule=COMPILER_RULE,
        choice_items=normalized_choices,
    )
