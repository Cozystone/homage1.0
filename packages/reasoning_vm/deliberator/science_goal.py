"""Narrow, typed NL-to-goal compiler for provenance-grounded science questions.

This module is an A-track candidate, not a general science-language claim.  The
v1 contract recognizes four explicitly declared atomic-number MCQ surfaces.  A
well-formed but unsupported science question remains input-valid and abstains.
Benchmark eligibility belongs to the evaluator, never to this compiler, so
compiler coverage cannot shrink its own denominator.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
from itertools import islice
import re
from typing import Any

from packages.cognitive_core.canonical import FrozenMap, canonical_digest


SCIENCE_GOAL_SCHEMA = "atanor.deliberator.science_goal.v1"
SCIENCE_GOAL_FAMILY = "atomic_number_lookup"
MAX_STEM_CHARS = 4096
MIN_CHOICES = 2
MAX_CHOICES = 10
MAX_CHOICE_KEY_CHARS = 16
MAX_CHOICE_TEXT_CHARS = 4096
MAX_SUBJECT_CHARS = 80

_SUBJECT_TOKEN = r"[A-Za-z][A-Za-z0-9.'-]*"
_SUBJECT = rf"(?P<subject>{_SUBJECT_TOKEN}(?:\s+{_SUBJECT_TOKEN}){{0,5}})"
_SURFACES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "atomic_number_what_is",
        "atomic_number_what_is_v1",
        re.compile(
            rf"^What is the atomic number of {_SUBJECT}\?$",
            re.IGNORECASE,
        ),
    ),
    (
        "atomic_number_which_number",
        "atomic_number_which_number_v1",
        re.compile(
            rf"^Which number is the atomic number of {_SUBJECT}\?$",
            re.IGNORECASE,
        ),
    ),
    (
        "atomic_number_has_which",
        "atomic_number_has_which_v1",
        re.compile(
            rf"^{_SUBJECT} has which atomic number\?$",
            re.IGNORECASE,
        ),
    ),
    (
        "atomic_number_select",
        "atomic_number_select_v1",
        re.compile(
            rf"^Select the atomic number of {_SUBJECT}\.$",
            re.IGNORECASE,
        ),
    ),
)
_EXACT_INTEGER = re.compile(r"(?:0|[1-9]\d{0,2})\Z")


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
    """Bind every outcome, including malformed inputs, without invoking repr()."""

    return canonical_digest(
        {
            "schema_version": SCIENCE_GOAL_SCHEMA,
            "stem": _text_descriptor(stem),
            "choices": dict(choice_descriptor),
        }
    )


def _normalized_space(value: str) -> str:
    return " ".join(value.split())


def _snapshot_choices(
    choices: Any,
) -> tuple[dict[str, str] | None, dict[str, Any], str | None]:
    """Read an arbitrary Mapping once, with a hard item cap.

    The returned descriptor and candidate snapshot are derived from the same
    bounded iteration.  A time-varying Mapping therefore cannot make the
    compiler fingerprint one set of choices and execute another.
    """

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
    normalized: set[str] = set()
    snapshot: dict[str, str] = {}
    for key, value in pairs:
        if (
            type(key) is not str
            or not key.strip()
            or key != key.strip()
            or len(key) > MAX_CHOICE_KEY_CHARS
        ):
            return None, descriptor, "invalid_choice_key"
        if key in snapshot:
            return None, descriptor, "duplicate_choice_key"
        if (
            type(value) is not str
            or not value.strip()
            or value != value.strip()
            or len(value) > MAX_CHOICE_TEXT_CHARS
            or "\x00" in value
        ):
            return None, descriptor, "invalid_choice_text"
        # Choice text is not globally case-insensitive: scientific notation
        # such as ``Bb`` versus ``BB`` can change the proposition.  Collapse
        # whitespace only; relation-specific compilers may impose stricter
        # equivalence after they understand the choice semantics.
        identity = _normalized_space(value)
        if identity in normalized:
            return None, descriptor, "duplicate_normalized_choices"
        normalized.add(identity)
        snapshot[key] = value
    return snapshot, descriptor, None


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


def _validate_atomic_number_choices(choices: Mapping[str, str]) -> tuple[bool, str]:
    exact_values: set[int] = set()
    for value in choices.values():
        if _EXACT_INTEGER.fullmatch(value) is None:
            return False, "atomic_number_choice_not_exact_integer"
        number = int(value)
        if number in exact_values:
            return False, "duplicate_normalized_choices"
        exact_values.add(number)
    return True, "exact_integer_choices_valid"


@dataclass(frozen=True)
class TypedScienceGoal:
    """A fixed subject/relation whose exact integer object comes from a choice."""

    subject: str
    relation: str
    object_source: str
    answer_kind: str
    compiler_rule: str

    def __post_init__(self) -> None:
        if (
            type(self.subject) is not str
            or not self.subject
            or len(self.subject) > MAX_SUBJECT_CHARS
        ):
            raise ValueError("science goal subject is invalid")
        if self.relation != "atomic_number":
            raise ValueError("science-goal v1 permits only atomic_number")
        if self.object_source != "choice_text":
            raise ValueError("science-goal v1 object must come from choice_text")
        if self.answer_kind != "exact_integer_mcq":
            raise ValueError("science-goal v1 answer kind is invalid")
        if not self.compiler_rule:
            raise ValueError("science goal requires a compiler rule")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QuantitySlot:
    name: str
    source: str
    number_kind: str
    minimum: int
    maximum: int
    unit: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRequirement:
    relation: str
    stage_schema: str
    exact_row_provenance: bool
    source_revision_required: bool
    license_required: bool
    quarantined_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScienceCompilation:
    """Deterministic compiler receipt; an abstention never carries a goal."""

    schema_version: str
    input_valid: bool
    status: str
    surface_family: str | None
    goals: tuple[TypedScienceGoal, ...]
    constraints: tuple[FrozenMap, ...]
    quantities: tuple[QuantitySlot, ...]
    required_evidence: tuple[EvidenceRequirement, ...]
    reason: str
    input_fingerprint: str
    goal_digest_sha256: str | None
    compiler_rule: str | None
    choice_items: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if self.schema_version != SCIENCE_GOAL_SCHEMA:
            raise ValueError("unsupported science compiler schema")
        if self.status not in {"compiled", "abstain", "invalid"}:
            raise ValueError("invalid science compiler status")
        if self.status == "compiled":
            if not self.input_valid or len(self.goals) != 1:
                raise ValueError("compiled science receipt requires one valid input goal")
            if (
                not self.constraints
                or not self.quantities
                or not self.required_evidence
                or self.goal_digest_sha256 is None
                or self.compiler_rule is None
            ):
                raise ValueError("compiled science receipt is incomplete")
            if any(not isinstance(item, FrozenMap) for item in self.constraints):
                raise ValueError("science goal constraints must be immutable")
            if (
                not MIN_CHOICES <= len(self.choice_items) <= MAX_CHOICES
                or any(
                    type(key) is not str or type(value) is not str
                    for key, value in self.choice_items
                )
                or len({key for key, _value in self.choice_items})
                != len(self.choice_items)
            ):
                raise ValueError("compiled science receipt choices are invalid")
        elif (
            self.goals
            or self.constraints
            or self.quantities
            or self.required_evidence
            or self.goal_digest_sha256 is not None
            or self.compiler_rule is not None
            or self.choice_items
        ):
            raise ValueError("non-compiled receipt cannot carry a goal plan")
        if self.status == "invalid" and self.input_valid:
            raise ValueError("invalid input cannot be marked input-valid")
        if self.status == "abstain" and not self.input_valid:
            raise ValueError("well-formed abstention must stay input-valid")
        if not re.fullmatch(r"[0-9a-f]{64}", self.input_fingerprint):
            raise ValueError("science input fingerprint is invalid")
        if self.goal_digest_sha256 is not None and not re.fullmatch(
            r"[0-9a-f]{64}", self.goal_digest_sha256
        ):
            raise ValueError("science goal digest is invalid")

    @property
    def compiled(self) -> bool:
        return self.status == "compiled"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "input_valid": self.input_valid,
            "status": self.status,
            "compiled": self.compiled,
            "surface_family": self.surface_family,
            "goals": [goal.to_dict() for goal in self.goals],
            "constraints": [item.to_dict() for item in self.constraints],
            "quantities": [item.to_dict() for item in self.quantities],
            "required_evidence": [
                item.to_dict() for item in self.required_evidence
            ],
            "reason": self.reason,
            "input_fingerprint": self.input_fingerprint,
            "goal_digest_sha256": self.goal_digest_sha256,
            "compiler_rule": self.compiler_rule,
        }


def _empty_compilation(
    *,
    input_valid: bool,
    status: str,
    reason: str,
    input_fingerprint: str,
) -> ScienceCompilation:
    return ScienceCompilation(
        schema_version=SCIENCE_GOAL_SCHEMA,
        input_valid=input_valid,
        status=status,
        surface_family=None,
        goals=(),
        constraints=(),
        quantities=(),
        required_evidence=(),
        reason=reason,
        input_fingerprint=input_fingerprint,
        goal_digest_sha256=None,
        compiler_rule=None,
        choice_items=(),
    )


def compile_science_question(stem: Any, choices: Any) -> ScienceCompilation:
    """Compile a declared atomic-number surface or fail closed with telemetry."""

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
    surface_family = None
    compiler_rule = None
    subject = None
    for family, rule, pattern in _SURFACES:
        match = pattern.fullmatch(stem)
        if match is not None:
            surface_family = family
            compiler_rule = rule
            subject = _normalized_space(match.group("subject")).casefold()
            break
    if surface_family is None or compiler_rule is None or subject is None:
        return _empty_compilation(
            input_valid=True,
            status="abstain",
            reason="unsupported_goal_family",
            input_fingerprint=fingerprint,
        )
    if not subject or len(subject) > MAX_SUBJECT_CHARS:
        return _empty_compilation(
            input_valid=True,
            status="abstain",
            reason="subject_out_of_bounds",
            input_fingerprint=fingerprint,
        )

    valid_quantities, quantity_reason = _validate_atomic_number_choices(
        exact_choices
    )
    if not valid_quantities:
        return _empty_compilation(
            input_valid=False,
            status="invalid",
            reason=quantity_reason,
            input_fingerprint=fingerprint,
        )

    goal = TypedScienceGoal(
        subject=subject,
        relation="atomic_number",
        object_source="choice_text",
        answer_kind="exact_integer_mcq",
        compiler_rule=compiler_rule,
    )
    constraints = (
        FrozenMap(
            {
                "kind": "functional_relation",
                "relation": "atomic_number",
                "cardinality": "exactly_one",
            }
        ),
        FrozenMap(
            {
                "kind": "exact_numeric_equality",
                "number_kind": "integer",
                "unit": "dimensionless",
            }
        ),
    )
    quantities = (
        QuantitySlot(
            name="atomic_number",
            source="choice_text",
            number_kind="integer",
            minimum=1,
            maximum=200,
            unit="dimensionless",
        ),
    )
    required_evidence = (
        EvidenceRequirement(
            relation="atomic_number",
            stage_schema="atanor.science-stage.v1",
            exact_row_provenance=True,
            source_revision_required=True,
            license_required=True,
            quarantined_allowed=False,
        ),
    )
    goal_payload = {
        "schema_version": SCIENCE_GOAL_SCHEMA,
        "surface_family": surface_family,
        "goals": [goal.to_dict()],
        "constraints": [item.to_dict() for item in constraints],
        "quantities": [item.to_dict() for item in quantities],
        "required_evidence": [
            item.to_dict() for item in required_evidence
        ],
        "input_fingerprint": fingerprint,
    }
    return ScienceCompilation(
        schema_version=SCIENCE_GOAL_SCHEMA,
        input_valid=True,
        status="compiled",
        surface_family=surface_family,
        goals=(goal,),
        constraints=constraints,
        quantities=quantities,
        required_evidence=required_evidence,
        reason="typed_science_goal_emitted",
        input_fingerprint=fingerprint,
        goal_digest_sha256=canonical_digest(goal_payload),
        compiler_rule=compiler_rule,
        choice_items=tuple(sorted(exact_choices.items())),
    )
