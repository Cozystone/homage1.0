"""High-precision compiler for one explicit relational-object MCQ family.

This module is deliberately separate from the live MCQ compiler.  It recognizes
only questions shaped like::

    Which country is Athens located in?

and emits the typed proof obligation ``(Athens, located_in, choice_text)``.  The
compiler does not answer the question, does not enter the live answer cascade,
and does not claim general relational-language understanding.  Anything outside
the narrow, audited surface family becomes an inspectable abstention.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any

from packages.base_brain.relational_lookup import REL_SYNONYMS, parse_relational_shape


EXPLICIT_RELATIONAL_OBJECT_SCHEMA = (
    "atanor.deliberator.explicit_relational_object_mcq.v2"
)
COMPILER_RULE = "explicit_located_in_object_choice_v2"
SOURCE_PARSER = "packages.base_brain.relational_lookup:parse_relational_shape"
RELATION_SEMANTICS = (
    "packages.base_brain.relational_lookup:REL_SYNONYMS[located in]"
)
MAX_STEM_CHARS = 256
MAX_SUBJECT_CHARS = 80
MAX_CHOICE_KEY_CHARS = 16
MAX_CHOICE_TEXT_CHARS = 160
MIN_CHOICES = 2
MAX_CHOICES = 8

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
    }
)
_ANSWER_TYPE_PATTERN = "|".join(sorted(_ANSWER_TYPES, key=lambda item: (-len(item), item)))
_SUBJECT_TOKEN = r"[A-Za-z0-9][A-Za-z0-9.'-]*"
_SUBJECT = rf"(?P<subject>{_SUBJECT_TOKEN}(?:\s+{_SUBJECT_TOKEN}){{0,7}})"
_LOCATION_PATTERN = re.compile(
    rf"^Which\s+(?P<answer_type>{_ANSWER_TYPE_PATTERN})\s+"
    rf"(?:is|are|was|were)\s+{_SUBJECT}\s+"
    rf"(?P<relation_surface>located|situated)\s+in\?$",
    re.IGNORECASE,
)
_AMBIGUITY_TOKEN = re.compile(
    r"\b(?:"
    r"associated|because|cause|caused|causes|causing|correct|except|greater|"
    r"incorrect|larger|least|less|most|not|required|responsible|smaller|than|"
    r"unlikely|why"
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
        "you",
    }
)


def _normalized_space(value: str) -> str:
    return " ".join(value.split())


def _subject_is_named(subject: str) -> bool:
    """Require a bounded named-entity-like subject, not a generic lower-case phrase."""

    candidate = re.sub(r"^(?:a|an|the)\s+", "", subject, flags=re.IGNORECASE)
    if not candidate or candidate.casefold() in _PRONOUN_OR_PLACEHOLDER:
        return False
    first = candidate[0]
    return first.isupper() or first.isdigit()


def _without_leading_article(subject: str) -> str:
    return re.sub(r"^(?:a|an|the)\s+", "", subject, flags=re.IGNORECASE)


def _stem_fingerprint(stem: str) -> str:
    return hashlib.sha256(stem.encode("utf-8")).hexdigest()


def _input_fingerprint(stem: str, choices: Mapping[str, str]) -> str:
    payload = {
        "stem": stem,
        "choices": sorted(choices.items(), key=lambda item: item[0]),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_choices(choices: Any) -> tuple[bool, str]:
    if not isinstance(choices, Mapping):
        return False, "choices_not_mapping"
    try:
        count = len(choices)
    except Exception:
        return False, "choices_unreadable"
    if count < MIN_CHOICES or count > MAX_CHOICES:
        return False, "choice_count_out_of_bounds"
    normalized_texts: set[str] = set()
    try:
        items = list(choices.items())
    except Exception:
        return False, "choices_unreadable"
    for key, value in items:
        if type(key) is not str or not key.strip() or len(key) > MAX_CHOICE_KEY_CHARS:
            return False, "invalid_choice_key"
        if (
            type(value) is not str
            or not value.strip()
            or len(value) > MAX_CHOICE_TEXT_CHARS
        ):
            return False, "invalid_choice_text"
        normalized = _normalized_space(value).casefold()
        if normalized in normalized_texts:
            return False, "duplicate_choice_text"
        normalized_texts.add(normalized)
    return True, "choices_valid"


@dataclass(frozen=True)
class TypedRelationalObjectGoal:
    """A ground subject/relation whose object is supplied by each choice text."""

    subject: str
    relation: str
    object_source: str
    answer_type: str
    compiler_rule: str
    confidence: float

    def __post_init__(self) -> None:
        if type(self.subject) is not str or not self.subject.strip():
            raise ValueError("subject must be a non-empty string")
        if len(self.subject) > MAX_SUBJECT_CHARS:
            raise ValueError("subject exceeds compiler bound")
        if self.relation != "located_in":
            raise ValueError("v2 permits only the located_in relation")
        if self.object_source != "choice_text":
            raise ValueError("object must come from choice_text")
        if self.answer_type not in _ANSWER_TYPES:
            raise ValueError("unsupported answer type")
        if self.compiler_rule != COMPILER_RULE:
            raise ValueError("unknown compiler rule")
        if type(self.confidence) is not float or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be a finite float in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RelationalObjectCompilation:
    """Bounded provenance receipt; an abstention never carries a proof goal."""

    schema_version: str
    status: str
    surface_family: str | None
    goal: TypedRelationalObjectGoal | None
    reason: str
    stem_fingerprint: str
    input_fingerprint: str | None
    compiler_rule: str | None
    source_parser: str
    relation_semantics: str

    def __post_init__(self) -> None:
        if self.schema_version != EXPLICIT_RELATIONAL_OBJECT_SCHEMA:
            raise ValueError("unsupported relational-object schema")
        if self.status not in {"compiled", "abstain"}:
            raise ValueError("status must be compiled or abstain")
        if self.status == "compiled" and self.goal is None:
            raise ValueError("compiled receipt requires a goal")
        if self.status == "abstain" and self.goal is not None:
            raise ValueError("abstention receipt cannot carry a goal")
        if self.status == "compiled" and self.input_fingerprint is None:
            raise ValueError("compiled receipt requires an input fingerprint")
        if self.goal is not None and self.compiler_rule != self.goal.compiler_rule:
            raise ValueError("receipt and goal compiler rules must match")

    @property
    def compiled(self) -> bool:
        return self.status == "compiled"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "surface_family": self.surface_family,
            "goal": self.goal.to_dict() if self.goal is not None else None,
            "reason": self.reason,
            "stem_fingerprint": self.stem_fingerprint,
            "input_fingerprint": self.input_fingerprint,
            "compiler_rule": self.compiler_rule,
            "provenance": {
                "source_parser": self.source_parser,
                "relation_semantics": self.relation_semantics,
            },
        }


def _abstain(stem: str, reason: str) -> RelationalObjectCompilation:
    return RelationalObjectCompilation(
        schema_version=EXPLICIT_RELATIONAL_OBJECT_SCHEMA,
        status="abstain",
        surface_family=None,
        goal=None,
        reason=reason,
        stem_fingerprint=_stem_fingerprint(stem),
        input_fingerprint=None,
        compiler_rule=None,
        source_parser=SOURCE_PARSER,
        relation_semantics=RELATION_SEMANTICS,
    )


def compile_explicit_relational_object_mcq(
    stem: Any,
    choices: Any,
) -> RelationalObjectCompilation:
    """Compile the explicit located-in/object-choice family or abstain.

    ``choices`` are validated here because the proof goal explicitly treats each
    choice text as an object candidate.  Duplicate or unbounded candidates make
    that proof obligation ambiguous and therefore cannot compile.
    """

    if type(stem) is not str:
        return _abstain("", "stem_not_string")
    if not stem or len(stem) > MAX_STEM_CHARS or stem != stem.strip():
        return _abstain(stem[:MAX_STEM_CHARS], "stem_out_of_bounds")
    if _AMBIGUITY_TOKEN.search(stem) is not None:
        return _abstain(stem, "ambiguous_or_unsupported_semantics")

    match = _LOCATION_PATTERN.fullmatch(stem)
    if match is None:
        return _abstain(stem, "unsupported_surface_family")

    subject = _normalized_space(match.group("subject"))
    answer_type = match.group("answer_type").casefold()
    if len(subject) > MAX_SUBJECT_CHARS or not _subject_is_named(subject):
        return _abstain(stem, "subject_not_typed_named_entity")

    choices_valid, choice_reason = _validate_choices(choices)
    if not choices_valid:
        return _abstain(stem, choice_reason)

    # Reuse the existing relational surface parser as an independent structural
    # agreement check.  The new compiler stays narrower than that parser.
    parsed = parse_relational_shape(stem)
    parsed_entity = (
        _normalized_space(parsed["entity"])
        if isinstance(parsed, dict) and type(parsed.get("entity")) is str
        else ""
    )
    if (
        not isinstance(parsed, dict)
        or parsed.get("kind") != "verb"
        or not parsed_entity
        or _without_leading_article(parsed_entity).casefold()
        != _without_leading_article(subject).casefold()
        or parsed.get("rel_norm") != answer_type
    ):
        return _abstain(stem, "base_relational_parser_disagreed")
    # Use the existing parser's entity canonicalization (notably its article
    # handling) so the proof lookup uses the same subject semantics.
    subject = parsed_entity

    located_semantics = REL_SYNONYMS.get("located in", frozenset())
    if "located_in" not in located_semantics:
        return _abstain(stem, "base_relation_semantics_unavailable")

    typed_choices = dict(choices)
    return RelationalObjectCompilation(
        schema_version=EXPLICIT_RELATIONAL_OBJECT_SCHEMA,
        status="compiled",
        surface_family="explicit_relational_object_mcq",
        goal=TypedRelationalObjectGoal(
            subject=subject,
            relation="located_in",
            object_source="choice_text",
            answer_type=answer_type,
            compiler_rule=COMPILER_RULE,
            confidence=0.98,
        ),
        reason="typed_subject_relation_object_candidates_emitted",
        stem_fingerprint=_stem_fingerprint(stem),
        input_fingerprint=_input_fingerprint(stem, typed_choices),
        compiler_rule=COMPILER_RULE,
        source_parser=SOURCE_PARSER,
        relation_semantics=RELATION_SEMANTICS,
    )
