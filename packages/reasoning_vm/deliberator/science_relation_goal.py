"""Fail-closed NL-to-goal compiler for one positive ``located_in`` profile.

This module is a candidate-side mechanism, deliberately parallel to the
existing atomic, scalar, and relational-object compilers.  It neither answers a
question nor claims benchmark capability.  Its only successful output is a
typed proof obligation:

``(named subject, located_in, one normalized choice entity)``

The answer choices are treated uniformly as object candidates.  No choice is
looked up, ranked, or compared with an answer while compiling.

This is a timeboxed third sibling-lane diagnostic.  It must not grow by adding
more hand-written predicate or surface templates; its declared successor is a
general extractor that binds relation slots to properties already present in
the graph.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
from itertools import islice
import re
import unicodedata
from typing import Any, Literal

from packages.cognitive_core.canonical import canonical_digest


SCIENCE_RELATION_GOAL_SCHEMA = (
    "atanor.deliberator.science_relation_goal.v1"
)
SCIENCE_RELATION_GOAL_FAMILY = "typed_relation_select_located_in"
SCIENCE_RELATION_STAGE_SCHEMA = "atanor.science-relation-stage.v1"
COMPILER_RULE = "typed_relation_select_located_in_v1"
DIAGNOSTIC_SCOPE = "timeboxed_third_sibling_lane_only"
GENERAL_EXTRACTOR_SUCCESSOR = "general_graph_relation_goal_extractor"

MAX_STEM_CHARS = 512
MAX_SUBJECT_CHARS = 96
MIN_CHOICES = 2
MAX_CHOICES = 10
MAX_CHOICE_KEY_CHARS = 16
MAX_CHOICE_TEXT_CHARS = 192

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ANSWER_TYPES = frozenset(
    {
        "city",
        "continent",
        "country",
        "county",
        "district",
        "nation",
        "province",
        "region",
        "state",
        "territory",
    }
)
_ENTITY_TOKEN = r"[A-Za-z0-9À-ÖØ-öø-ÿ][A-Za-z0-9À-ÖØ-öø-ÿ.'’&-]*"
_SUBJECT = rf"(?P<subject>{_ENTITY_TOKEN}(?: {_ENTITY_TOKEN}){{0,8}})"
_ANSWER_TYPE = r"(?P<answer_type>[A-Za-z][A-Za-z-]{1,31})"
_RELATION = r"(?P<relation_surface>located|situated)"
_AUXILIARY = r"is"

_SURFACES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "which_type_subject_relation_in",
        re.compile(
            rf"^Which {_ANSWER_TYPE} {_AUXILIARY} {_SUBJECT} "
            rf"{_RELATION} in\?$",
            re.IGNORECASE,
        ),
    ),
    (
        "in_which_type_subject_relation",
        re.compile(
            rf"^In which {_ANSWER_TYPE} {_AUXILIARY} {_SUBJECT} "
            rf"{_RELATION}\?$",
            re.IGNORECASE,
        ),
    ),
    (
        "subject_relation_in_which_type",
        re.compile(
            rf"^{_SUBJECT} {_AUXILIARY} {_RELATION} in which "
            rf"{_ANSWER_TYPE}\?$",
            re.IGNORECASE,
        ),
    ),
    (
        "select_type_subject_relation",
        re.compile(
            rf"^Select the {_ANSWER_TYPE} in which {_SUBJECT} "
            rf"{_AUXILIARY} {_RELATION}\.$",
            re.IGNORECASE,
        ),
    ),
)
_SURFACE_IDS = frozenset(surface_id for surface_id, _pattern in _SURFACES)

_UNSUPPORTED_SEMANTICS = re.compile(
    r"\b(?:"
    r"all|associated|because|best|border|cause|caused|causes|causing|"
    r"closest|contains|correct|doesn't|don't|except|false|farthest|"
    r"greater|incorrect|isn't|larger|least|less|more|most|near|"
    r"neither|never|none|not|responsible|result|results|required|"
    r"smaller|than|unlikely|wasn't|weren't|without|worst|why"
    r")\b",
    re.IGNORECASE,
)
_PRONOUN_OR_PLACEHOLDER = frozenset(
    {
        "he",
        "her",
        "him",
        "it",
        "me",
        "one",
        "place",
        "she",
        "someone",
        "something",
        "that",
        "them",
        "there",
        "they",
        "this",
        "those",
        "us",
        "we",
        "where",
        "you",
    }
)
_CHOICE_ENTITY_CHARS = re.compile(
    r"[A-Za-z0-9À-ÖØ-öø-ÿ .,'’&()-]+\Z"
)

RelationCompilationStatus = Literal["compiled", "abstain", "invalid"]


def _canonical_schema_payload() -> dict[str, Any]:
    return {"schema_version": SCIENCE_RELATION_GOAL_SCHEMA}


SCIENCE_RELATION_GOAL_SCHEMA_DIGEST_SHA256 = canonical_digest(
    _canonical_schema_payload()
)


def _canonical_family_payload() -> dict[str, Any]:
    return {
        "schema_version": SCIENCE_RELATION_GOAL_SCHEMA,
        "goal_family": SCIENCE_RELATION_GOAL_FAMILY,
    }


SCIENCE_RELATION_GOAL_FAMILY_DIGEST_SHA256 = canonical_digest(
    _canonical_family_payload()
)


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCIENCE_RELATION_GOAL_SCHEMA,
        "schema_digest_sha256": (
            SCIENCE_RELATION_GOAL_SCHEMA_DIGEST_SHA256
        ),
        "goal_family": SCIENCE_RELATION_GOAL_FAMILY,
        "family_digest_sha256": (
            SCIENCE_RELATION_GOAL_FAMILY_DIGEST_SHA256
        ),
        "scope": {
            "role": DIAGNOSTIC_SCOPE,
            "manual_surface_or_predicate_expansion_allowed": False,
            "successor": GENERAL_EXTRACTOR_SUCCESSOR,
            "capability_claim": False,
        },
        "compiler_rule": COMPILER_RULE,
        "surface_reducer": "exactly_one_declared_surface_v1",
        "surfaces": [
            {
                "surface_id": surface_id,
                "pattern": pattern.pattern,
                "flags": pattern.flags,
            }
            for surface_id, pattern in _SURFACES
        ],
        "answer_types": sorted(_ANSWER_TYPES),
        "goal_literals": {
            "predicate": "located_in",
            "polarity": "positive",
            "object_source": "normalized_choice_entity",
            "selection_cardinality": "exactly_one_provable_choice",
        },
        "choice_contract": {
            "minimum": MIN_CHOICES,
            "maximum": MAX_CHOICES,
            "normalization": "unicode_nfkc_then_ascii_space_collapse_v1",
            "answer_aware": False,
        },
        "stage_evidence": {
            "stage_schema": SCIENCE_RELATION_STAGE_SCHEMA,
            "evidence_kind": "typed_positive_relation_fact",
            "predicate": "located_in",
            "subject_source": "goal_subject",
            "object_source": "normalized_choice_entity",
            "object_answer_type_source": "goal_answer_type",
            "original_property_id_required": True,
            "object_type_evidence_required": True,
            "exact_row_provenance": True,
            "source_revision_required": True,
            "license_required": True,
            "quarantined_allowed": False,
        },
        "envelope": {
            "max_stem_chars": MAX_STEM_CHARS,
            "max_subject_chars": MAX_SUBJECT_CHARS,
            "max_choice_key_chars": MAX_CHOICE_KEY_CHARS,
            "max_choice_text_chars": MAX_CHOICE_TEXT_CHARS,
            "leading_or_trailing_whitespace_allowed": False,
            "non_ascii_stem_whitespace_allowed": False,
            "nul_allowed": False,
        },
    }


SCIENCE_RELATION_GOAL_CONTRACT_DIGEST_SHA256 = canonical_digest(
    _contract_payload()
)


def _is_sha256(value: Any) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _text_descriptor(value: Any) -> dict[str, Any]:
    if type(value) is not str:
        return {"python_type": type(value).__name__}
    encoded = value.encode("utf-8", "surrogatepass")
    return {
        "python_type": "str",
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _input_digest(stem: Any, choice_descriptor: Mapping[str, Any]) -> str:
    return canonical_digest(
        {
            "schema_version": SCIENCE_RELATION_GOAL_SCHEMA,
            "contract_digest_sha256": (
                SCIENCE_RELATION_GOAL_CONTRACT_DIGEST_SHA256
            ),
            "stem": _text_descriptor(stem),
            "choices": dict(choice_descriptor),
        }
    )


def _has_non_ascii_space(value: str) -> bool:
    return any(character.isspace() and character != " " for character in value)


def _validate_stem(stem: Any) -> str | None:
    if type(stem) is not str:
        return "stem_not_string"
    if (
        not stem
        or stem != stem.strip()
        or len(stem) > MAX_STEM_CHARS
        or "\x00" in stem
        or _has_non_ascii_space(stem)
        or "  " in stem
    ):
        return "stem_out_of_bounds"
    return None


def _normalize_entity(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _without_leading_article(value: str) -> str:
    return re.sub(r"^(?:a|an|the) ", "", value, flags=re.IGNORECASE)


def _subject_is_named(value: str) -> bool:
    candidate = _without_leading_article(_normalize_entity(value))
    if (
        not candidate
        or len(candidate) > MAX_SUBJECT_CHARS
        or candidate.casefold() in _PRONOUN_OR_PLACEHOLDER
        or not any(character.isalpha() for character in candidate)
    ):
        return False
    first = candidate[0]
    return first.isupper() or first.isdigit()


def _choice_entity_is_valid(value: str) -> bool:
    return bool(
        value
        and len(value) <= MAX_CHOICE_TEXT_CHARS
        and _CHOICE_ENTITY_CHARS.fullmatch(value) is not None
        and any(character.isalpha() for character in value)
        and len(value.split(" ")) <= 12
        and value[0].isalnum()
        and value[-1].isalnum()
    )


@dataclass(frozen=True, slots=True)
class SubjectSpanBinding:
    """Hash binding from the normalized subject to its exact stem span."""

    slot: str
    start: int
    end: int
    text_bytes: int
    text_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.slot) is not str
            or self.slot != "subject"
            or type(self.start) is not int
            or type(self.end) is not int
            or not 0 <= self.start < self.end <= MAX_STEM_CHARS
            or type(self.text_bytes) is not int
            or self.text_bytes <= 0
            or not _is_sha256(self.text_sha256)
        ):
            raise ValueError("relation subject span binding is invalid")

    def to_dict(self) -> dict[str, Any]:
        _validate_subject_span(self)
        return {
            "slot": self.slot,
            "start": self.start,
            "end": self.end,
            "text_bytes": self.text_bytes,
            "text_sha256": self.text_sha256,
        }


def _validate_subject_span(value: Any) -> None:
    if type(value) is not SubjectSpanBinding:
        raise ValueError("relation subject span type is invalid")
    SubjectSpanBinding.__post_init__(value)


@dataclass(frozen=True, slots=True)
class NormalizedRelationChoice:
    """One detached object candidate; it carries no correctness signal."""

    key: str
    original_text: str
    normalized_entity: str

    def __post_init__(self) -> None:
        if (
            type(self.key) is not str
            or not self.key
            or self.key != self.key.strip()
            or len(self.key) > MAX_CHOICE_KEY_CHARS
            or "\x00" in self.key
            or any(character.isspace() for character in self.key)
            or type(self.original_text) is not str
            or not self.original_text
            or self.original_text != self.original_text.strip()
            or len(self.original_text) > MAX_CHOICE_TEXT_CHARS
            or "\x00" in self.original_text
            or _has_non_ascii_space(self.original_text)
            or type(self.normalized_entity) is not str
            or self.normalized_entity != _normalize_entity(self.original_text)
            or not _choice_entity_is_valid(self.normalized_entity)
        ):
            raise ValueError("normalized relation choice is invalid")

    def to_dict(self) -> dict[str, Any]:
        _validate_choice(self)
        return {
            "key": self.key,
            "original_text": self.original_text,
            "normalized_entity": self.normalized_entity,
        }


def _validate_choice(value: Any) -> None:
    if type(value) is not NormalizedRelationChoice:
        raise ValueError("normalized relation choice type is invalid")
    NormalizedRelationChoice.__post_init__(value)


@dataclass(frozen=True, slots=True)
class RelationStageEvidenceRequirement:
    """Exact evidence boundary required by a future relation stage."""

    stage_schema: str
    evidence_kind: str
    predicate: str
    subject_source: str
    object_source: str
    object_answer_type: str
    object_answer_type_source: str
    polarity: str
    original_property_id_required: bool
    object_type_evidence_required: bool
    exact_row_provenance: bool
    source_revision_required: bool
    license_required: bool
    quarantined_allowed: bool

    def __post_init__(self) -> None:
        if (
            type(self.stage_schema) is not str
            or self.stage_schema != SCIENCE_RELATION_STAGE_SCHEMA
            or type(self.evidence_kind) is not str
            or self.evidence_kind != "typed_positive_relation_fact"
            or type(self.predicate) is not str
            or self.predicate != "located_in"
            or type(self.subject_source) is not str
            or self.subject_source != "goal_subject"
            or type(self.object_source) is not str
            or self.object_source != "normalized_choice_entity"
            or type(self.object_answer_type) is not str
            or self.object_answer_type not in _ANSWER_TYPES
            or type(self.object_answer_type_source) is not str
            or self.object_answer_type_source != "goal_answer_type"
            or type(self.polarity) is not str
            or self.polarity != "positive"
            or self.original_property_id_required is not True
            or self.object_type_evidence_required is not True
            or self.exact_row_provenance is not True
            or self.source_revision_required is not True
            or self.license_required is not True
            or self.quarantined_allowed is not False
        ):
            raise ValueError("relation stage evidence requirement is invalid")

    def to_dict(self) -> dict[str, Any]:
        _validate_evidence(self)
        return {
            "stage_schema": self.stage_schema,
            "evidence_kind": self.evidence_kind,
            "predicate": self.predicate,
            "subject_source": self.subject_source,
            "object_source": self.object_source,
            "object_answer_type": self.object_answer_type,
            "object_answer_type_source": self.object_answer_type_source,
            "polarity": self.polarity,
            "original_property_id_required": (
                self.original_property_id_required
            ),
            "object_type_evidence_required": (
                self.object_type_evidence_required
            ),
            "exact_row_provenance": self.exact_row_provenance,
            "source_revision_required": self.source_revision_required,
            "license_required": self.license_required,
            "quarantined_allowed": self.quarantined_allowed,
        }


def _validate_evidence(value: Any) -> None:
    if type(value) is not RelationStageEvidenceRequirement:
        raise ValueError("relation evidence type is invalid")
    RelationStageEvidenceRequirement.__post_init__(value)


@dataclass(frozen=True, slots=True)
class TypedRelationSelectGoal:
    """A positive relation whose object must be selected by exact proof."""

    subject: str
    subject_span: SubjectSpanBinding
    answer_type: str
    predicate: str
    polarity: str
    object_source: str
    selection_cardinality: str
    surface_id: str
    compiler_rule: str

    def __post_init__(self) -> None:
        if (
            type(self.subject) is not str
            or not self.subject
            or self.subject != _normalize_entity(self.subject)
            or not _subject_is_named(self.subject)
            or type(self.answer_type) is not str
            or self.answer_type not in _ANSWER_TYPES
            or type(self.predicate) is not str
            or self.predicate != "located_in"
            or type(self.polarity) is not str
            or self.polarity != "positive"
            or type(self.object_source) is not str
            or self.object_source != "normalized_choice_entity"
            or type(self.selection_cardinality) is not str
            or self.selection_cardinality
            != "exactly_one_provable_choice"
            or type(self.surface_id) is not str
            or self.surface_id not in _SURFACE_IDS
            or type(self.compiler_rule) is not str
            or self.compiler_rule != COMPILER_RULE
        ):
            raise ValueError("typed relation-select goal is invalid")
        _validate_subject_span(self.subject_span)

    def to_dict(self) -> dict[str, Any]:
        _validate_goal(self)
        return {
            "subject": self.subject,
            "subject_span": self.subject_span.to_dict(),
            "answer_type": self.answer_type,
            "predicate": self.predicate,
            "polarity": self.polarity,
            "object_source": self.object_source,
            "selection_cardinality": self.selection_cardinality,
            "surface_id": self.surface_id,
            "compiler_rule": self.compiler_rule,
        }


def _validate_goal(value: Any) -> None:
    if type(value) is not TypedRelationSelectGoal:
        raise ValueError("typed relation-select goal type is invalid")
    TypedRelationSelectGoal.__post_init__(value)


def _goal_payload(
    *,
    input_digest_sha256: str,
    surface_family: str,
    goal: TypedRelationSelectGoal,
    required_evidence: tuple[RelationStageEvidenceRequirement, ...],
    choice_items: tuple[NormalizedRelationChoice, ...],
) -> dict[str, Any]:
    return {
        "schema_version": SCIENCE_RELATION_GOAL_SCHEMA,
        "schema_digest_sha256": (
            SCIENCE_RELATION_GOAL_SCHEMA_DIGEST_SHA256
        ),
        "goal_family": SCIENCE_RELATION_GOAL_FAMILY,
        "family_digest_sha256": (
            SCIENCE_RELATION_GOAL_FAMILY_DIGEST_SHA256
        ),
        "contract_digest_sha256": (
            SCIENCE_RELATION_GOAL_CONTRACT_DIGEST_SHA256
        ),
        "input_digest_sha256": input_digest_sha256,
        "surface_family": surface_family,
        "goal": goal.to_dict(),
        "required_evidence": [
            requirement.to_dict() for requirement in required_evidence
        ],
        "choice_items": [choice.to_dict() for choice in choice_items],
    }


_INVALID_REASONS = frozenset(
    {
        "stem_not_string",
        "stem_out_of_bounds",
        "choices_not_mapping",
        "choices_unreadable",
        "choice_count_out_of_bounds",
        "invalid_choice_key",
        "duplicate_choice_key",
        "invalid_choice_text",
        "invalid_choice_entity",
        "duplicate_normalized_choices",
    }
)
_ABSTAIN_REASONS = frozenset(
    {
        "unsupported_semantics",
        "unsupported_surface_family",
        "multiple_surface_matches",
        "unsupported_answer_type",
        "subject_not_named_entity",
        "subject_out_of_bounds",
        "surface_adapter_error",
    }
)


@dataclass(frozen=True, slots=True)
class RelationGoalCompilation:
    """Immutable compiler receipt; non-compiled receipts carry no goal plan."""

    schema_version: str
    schema_digest_sha256: str
    goal_family: str
    family_digest_sha256: str
    contract_digest_sha256: str
    input_valid: bool
    status: RelationCompilationStatus
    surface_family: str | None
    goals: tuple[TypedRelationSelectGoal, ...]
    required_evidence: tuple[RelationStageEvidenceRequirement, ...]
    reason: str
    input_digest_sha256: str
    goal_digest_sha256: str | None
    compiler_rule: str | None
    choice_items: tuple[NormalizedRelationChoice, ...]

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not str
            or self.schema_version != SCIENCE_RELATION_GOAL_SCHEMA
            or type(self.schema_digest_sha256) is not str
            or self.schema_digest_sha256
            != SCIENCE_RELATION_GOAL_SCHEMA_DIGEST_SHA256
            or type(self.goal_family) is not str
            or self.goal_family != SCIENCE_RELATION_GOAL_FAMILY
            or type(self.family_digest_sha256) is not str
            or self.family_digest_sha256
            != SCIENCE_RELATION_GOAL_FAMILY_DIGEST_SHA256
            or type(self.contract_digest_sha256) is not str
            or self.contract_digest_sha256
            != SCIENCE_RELATION_GOAL_CONTRACT_DIGEST_SHA256
            or type(self.input_valid) is not bool
            or type(self.status) is not str
            or self.status not in {"compiled", "abstain", "invalid"}
            or type(self.reason) is not str
            or not self.reason
            or not _is_sha256(self.input_digest_sha256)
        ):
            raise ValueError("relation compiler receipt envelope is invalid")

        if self.status == "compiled":
            if (
                self.input_valid is not True
                or type(self.surface_family) is not str
                or self.surface_family != SCIENCE_RELATION_GOAL_FAMILY
                or type(self.goals) is not tuple
                or len(self.goals) != 1
                or type(self.required_evidence) is not tuple
                or len(self.required_evidence) != 1
                or self.reason != "typed_relation_select_goal_emitted"
                or not _is_sha256(self.goal_digest_sha256)
                or type(self.compiler_rule) is not str
                or self.compiler_rule != COMPILER_RULE
                or type(self.choice_items) is not tuple
                or not MIN_CHOICES
                <= len(self.choice_items)
                <= MAX_CHOICES
            ):
                raise ValueError("compiled relation receipt is incomplete")
            goal = self.goals[0]
            _validate_goal(goal)
            evidence = self.required_evidence[0]
            _validate_evidence(evidence)
            if evidence.object_answer_type != goal.answer_type:
                raise ValueError(
                    "relation evidence does not bind the goal answer type"
                )
            for choice in self.choice_items:
                _validate_choice(choice)
            if (
                tuple(sorted(self.choice_items, key=lambda row: row.key))
                != self.choice_items
                or len({row.key for row in self.choice_items})
                != len(self.choice_items)
                or len(
                    {
                        row.normalized_entity.casefold()
                        for row in self.choice_items
                    }
                )
                != len(self.choice_items)
            ):
                raise ValueError("compiled relation choices are inconsistent")
            expected_goal_digest = canonical_digest(
                _goal_payload(
                    input_digest_sha256=self.input_digest_sha256,
                    surface_family=self.surface_family,
                    goal=goal,
                    required_evidence=self.required_evidence,
                    choice_items=self.choice_items,
                )
            )
            if self.goal_digest_sha256 != expected_goal_digest:
                raise ValueError("relation goal digest does not bind the plan")
        else:
            if (
                self.surface_family is not None
                or type(self.goals) is not tuple
                or self.goals
                or type(self.required_evidence) is not tuple
                or self.required_evidence
                or self.goal_digest_sha256 is not None
                or self.compiler_rule is not None
                or type(self.choice_items) is not tuple
                or self.choice_items
            ):
                raise ValueError("non-compiled relation receipt carries a plan")
            if self.status == "invalid":
                if (
                    self.input_valid is not False
                    or self.reason not in _INVALID_REASONS
                ):
                    raise ValueError("invalid relation receipt is inconsistent")
            elif (
                self.input_valid is not True
                or self.reason not in _ABSTAIN_REASONS
            ):
                raise ValueError("relation abstention is inconsistent")

    @property
    def compiled(self) -> bool:
        return self.status == "compiled"

    @property
    def goal(self) -> TypedRelationSelectGoal | None:
        return self.goals[0] if self.goals else None

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            "schema_version": self.schema_version,
            "schema_digest_sha256": self.schema_digest_sha256,
            "goal_family": self.goal_family,
            "family_digest_sha256": self.family_digest_sha256,
            "contract_digest_sha256": self.contract_digest_sha256,
            "input_valid": self.input_valid,
            "status": self.status,
            "compiled": self.compiled,
            "surface_family": self.surface_family,
            "goals": [goal.to_dict() for goal in self.goals],
            "required_evidence": [
                requirement.to_dict()
                for requirement in self.required_evidence
            ],
            "reason": self.reason,
            "input_digest_sha256": self.input_digest_sha256,
            "goal_digest_sha256": self.goal_digest_sha256,
            "compiler_rule": self.compiler_rule,
            "choice_items": [
                choice.to_dict() for choice in self.choice_items
            ],
        }


def _snapshot_choices(
    choices: Any,
) -> tuple[
    tuple[NormalizedRelationChoice, ...] | None,
    dict[str, Any],
    str | None,
]:
    """Consume a possibly hostile Mapping through one bounded ``items`` read."""

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

    pairs: list[tuple[Any, Any]] = []
    descriptor_rows: list[dict[str, Any]] = []
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

    seen_keys: set[str] = set()
    seen_entities: set[str] = set()
    normalized_rows: list[NormalizedRelationChoice] = []
    for key, value in pairs:
        if (
            type(key) is not str
            or not key
            or key != key.strip()
            or len(key) > MAX_CHOICE_KEY_CHARS
            or "\x00" in key
            or any(character.isspace() for character in key)
        ):
            return None, descriptor, "invalid_choice_key"
        if key in seen_keys:
            return None, descriptor, "duplicate_choice_key"
        seen_keys.add(key)
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or len(value) > MAX_CHOICE_TEXT_CHARS
            or "\x00" in value
            or _has_non_ascii_space(value)
        ):
            return None, descriptor, "invalid_choice_text"
        normalized_entity = _normalize_entity(value)
        if not _choice_entity_is_valid(normalized_entity):
            return None, descriptor, "invalid_choice_entity"
        identity = normalized_entity.casefold()
        if identity in seen_entities:
            return None, descriptor, "duplicate_normalized_choices"
        seen_entities.add(identity)
        normalized_rows.append(
            NormalizedRelationChoice(
                key=key,
                original_text=value,
                normalized_entity=normalized_entity,
            )
        )
    return (
        tuple(sorted(normalized_rows, key=lambda row: row.key)),
        descriptor,
        None,
    )


def _surface_matches(
    stem: str,
) -> tuple[tuple[str, re.Match[str]], ...]:
    return tuple(
        (surface_id, match)
        for surface_id, pattern in _SURFACES
        if (match := pattern.fullmatch(stem)) is not None
    )


def looks_like_typed_relation_select(stem: Any) -> bool:
    """Return a stem-only routing hint for the exact positive profile."""

    if _validate_stem(stem) is not None:
        return False
    assert type(stem) is str
    if _UNSUPPORTED_SEMANTICS.search(stem) is not None:
        return False
    try:
        matches = _surface_matches(stem)
    except Exception:
        return False
    if len(matches) != 1:
        return False
    _surface_id, match = matches[0]
    answer_type = match.group("answer_type").casefold()
    subject = match.group("subject")
    return answer_type in _ANSWER_TYPES and _subject_is_named(subject)


def _empty_compilation(
    *,
    input_valid: bool,
    status: Literal["abstain", "invalid"],
    reason: str,
    input_digest_sha256: str,
) -> RelationGoalCompilation:
    return RelationGoalCompilation(
        schema_version=SCIENCE_RELATION_GOAL_SCHEMA,
        schema_digest_sha256=(
            SCIENCE_RELATION_GOAL_SCHEMA_DIGEST_SHA256
        ),
        goal_family=SCIENCE_RELATION_GOAL_FAMILY,
        family_digest_sha256=(
            SCIENCE_RELATION_GOAL_FAMILY_DIGEST_SHA256
        ),
        contract_digest_sha256=(
            SCIENCE_RELATION_GOAL_CONTRACT_DIGEST_SHA256
        ),
        input_valid=input_valid,
        status=status,
        surface_family=None,
        goals=(),
        required_evidence=(),
        reason=reason,
        input_digest_sha256=input_digest_sha256,
        goal_digest_sha256=None,
        compiler_rule=None,
        choice_items=(),
    )


def _subject_span(stem: str, match: re.Match[str]) -> SubjectSpanBinding:
    start, end = match.span("subject")
    text = stem[start:end]
    encoded = text.encode("utf-8")
    return SubjectSpanBinding(
        slot="subject",
        start=start,
        end=end,
        text_bytes=len(encoded),
        text_sha256=hashlib.sha256(encoded).hexdigest(),
    )


def compile_typed_relation_select(
    stem: Any,
    choices: Any,
) -> RelationGoalCompilation:
    """Compile one explicit positive named-subject relation-select question."""

    choice_items, choice_descriptor, choice_reason = _snapshot_choices(choices)
    input_digest_sha256 = _input_digest(stem, choice_descriptor)
    stem_reason = _validate_stem(stem)
    invalid_reason = stem_reason or choice_reason
    if invalid_reason is not None or choice_items is None:
        return _empty_compilation(
            input_valid=False,
            status="invalid",
            reason=invalid_reason or "choices_unreadable",
            input_digest_sha256=input_digest_sha256,
        )

    assert type(stem) is str
    if _UNSUPPORTED_SEMANTICS.search(stem) is not None:
        return _empty_compilation(
            input_valid=True,
            status="abstain",
            reason="unsupported_semantics",
            input_digest_sha256=input_digest_sha256,
        )
    try:
        matches = _surface_matches(stem)
    except Exception:
        return _empty_compilation(
            input_valid=True,
            status="abstain",
            reason="surface_adapter_error",
            input_digest_sha256=input_digest_sha256,
        )
    if not matches:
        return _empty_compilation(
            input_valid=True,
            status="abstain",
            reason="unsupported_surface_family",
            input_digest_sha256=input_digest_sha256,
        )
    if len(matches) != 1:
        return _empty_compilation(
            input_valid=True,
            status="abstain",
            reason="multiple_surface_matches",
            input_digest_sha256=input_digest_sha256,
        )

    surface_id, match = matches[0]
    answer_type = match.group("answer_type").casefold()
    if answer_type not in _ANSWER_TYPES:
        return _empty_compilation(
            input_valid=True,
            status="abstain",
            reason="unsupported_answer_type",
            input_digest_sha256=input_digest_sha256,
        )
    raw_subject = match.group("subject")
    if not _subject_is_named(raw_subject):
        return _empty_compilation(
            input_valid=True,
            status="abstain",
            reason="subject_not_named_entity",
            input_digest_sha256=input_digest_sha256,
        )
    subject = _normalize_entity(raw_subject)
    if not subject or len(subject) > MAX_SUBJECT_CHARS:
        return _empty_compilation(
            input_valid=True,
            status="abstain",
            reason="subject_out_of_bounds",
            input_digest_sha256=input_digest_sha256,
        )

    goal = TypedRelationSelectGoal(
        subject=subject,
        subject_span=_subject_span(stem, match),
        answer_type=answer_type,
        predicate="located_in",
        polarity="positive",
        object_source="normalized_choice_entity",
        selection_cardinality="exactly_one_provable_choice",
        surface_id=surface_id,
        compiler_rule=COMPILER_RULE,
    )
    required_evidence = (
        RelationStageEvidenceRequirement(
            stage_schema=SCIENCE_RELATION_STAGE_SCHEMA,
            evidence_kind="typed_positive_relation_fact",
            predicate="located_in",
            subject_source="goal_subject",
            object_source="normalized_choice_entity",
            object_answer_type=answer_type,
            object_answer_type_source="goal_answer_type",
            polarity="positive",
            original_property_id_required=True,
            object_type_evidence_required=True,
            exact_row_provenance=True,
            source_revision_required=True,
            license_required=True,
            quarantined_allowed=False,
        ),
    )
    goal_digest_sha256 = canonical_digest(
        _goal_payload(
            input_digest_sha256=input_digest_sha256,
            surface_family=SCIENCE_RELATION_GOAL_FAMILY,
            goal=goal,
            required_evidence=required_evidence,
            choice_items=choice_items,
        )
    )
    return RelationGoalCompilation(
        schema_version=SCIENCE_RELATION_GOAL_SCHEMA,
        schema_digest_sha256=(
            SCIENCE_RELATION_GOAL_SCHEMA_DIGEST_SHA256
        ),
        goal_family=SCIENCE_RELATION_GOAL_FAMILY,
        family_digest_sha256=(
            SCIENCE_RELATION_GOAL_FAMILY_DIGEST_SHA256
        ),
        contract_digest_sha256=(
            SCIENCE_RELATION_GOAL_CONTRACT_DIGEST_SHA256
        ),
        input_valid=True,
        status="compiled",
        surface_family=SCIENCE_RELATION_GOAL_FAMILY,
        goals=(goal,),
        required_evidence=required_evidence,
        reason="typed_relation_select_goal_emitted",
        input_digest_sha256=input_digest_sha256,
        goal_digest_sha256=goal_digest_sha256,
        compiler_rule=COMPILER_RULE,
        choice_items=choice_items,
    )


def compile_typed_relation_select_question(
    stem: Any,
    choices: Any,
) -> RelationGoalCompilation:
    """Named alias matching the other science compiler entry-point style."""

    return compile_typed_relation_select(stem, choices)


def verify_compilation_subject_span(
    compilation: Any,
    stem: Any,
) -> bool:
    """Replay the source span without trusting a potentially forged receipt."""

    try:
        if (
            type(compilation) is not RelationGoalCompilation
            or type(stem) is not str
            or not compilation.compiled
            or compilation.goal is None
        ):
            return False
        compilation.__post_init__()
        goal = compilation.goal
        span = goal.subject_span
        raw_subject = stem[span.start : span.end]
        encoded = raw_subject.encode("utf-8")
        return bool(
            span.end <= len(stem)
            and len(encoded) == span.text_bytes
            and hashlib.sha256(encoded).hexdigest() == span.text_sha256
            and _normalize_entity(raw_subject) == goal.subject
        )
    except Exception:
        return False
