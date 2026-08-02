"""Dependency-backed relation-role analysis without fact generation.

The extractor in this module only emits an immutable syntactic/semantic
receipt.  It does not select a knowledge-base property, create a fact, or
choose an answer.  A parser backend is an explicit seam so unit tests can use
a deterministic dependency graph without surface-text templates.

``SpacyRelationRoleExtractor`` is deliberately local-only.  It lazily calls
``spacy.load`` after exact distribution-version checks; it never invokes a
downloader or a network API.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from importlib import import_module
from importlib import metadata as importlib_metadata
import math
from threading import Lock
from typing import Any, Literal, Protocol
import unicodedata

from packages.cognitive_core.canonical import canonical_digest


SCHEMA_VERSION = "atanor.deliberator.relation-role-receipt.v1"
MAX_TEXT_CHARS = 2048
MAX_TOKENS = 512

SPACY_DISTRIBUTION = "spacy"
SPACY_VERSION = "3.8.14"
SPACY_MODEL_DISTRIBUTION = "en-core-web-sm"
SPACY_MODEL_NAME = "en_core_web_sm"
SPACY_MODEL_VERSION = "3.8.0"
# Release provenance only.  Runtime loading never fetches this URL.
SPACY_MODEL_WHEEL_URL = (
    "https://github.com/explosion/spacy-models/releases/download/"
    "en_core_web_sm-3.8.0/"
    "en_core_web_sm-3.8.0-py3-none-any.whl"
)
SPACY_MODEL_WHEEL_SHA256 = (
    "1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85"
)

RoleName = Literal["subject", "relation", "object"]
ExtractionStatus = Literal["extracted", "hazard", "abstain", "invalid"]
RelationDirection = Literal["forward", "inverse", "declarative"]
Polarity = Literal["positive", "negative"]
HazardKind = Literal[
    "comparison",
    "coordination",
    "modality",
    "negation",
    "temporal",
]

_ROLE_NAMES = frozenset(("subject", "relation", "object"))
_STATUSES = frozenset(("extracted", "hazard", "abstain", "invalid"))
_DIRECTIONS = frozenset(("forward", "inverse", "declarative"))
_POLARITIES = frozenset(("positive", "negative"))
_HAZARD_KINDS = frozenset(
    ("comparison", "coordination", "modality", "negation", "temporal")
)
_FAILURE_REASONS = frozenset(
    (
        "dependency_backend_error",
        "dependency_backend_unavailable",
        "dependency_backend_version_mismatch",
        "dependency_model_unavailable",
        "dependency_model_version_mismatch",
    )
)
_WH_TAGS = frozenset(("WDT", "WP", "WP$", "WRB"))
_SUBJECT_LABELS = frozenset(
    (
        "csubj",
        "csubj:pass",
        "csubjpass",
        "nsubj",
        "nsubj:pass",
        "nsubjpass",
    )
)
_PASSIVE_SUBJECT_LABELS = frozenset(
    ("csubj:pass", "csubjpass", "nsubj:pass", "nsubjpass")
)
_DIRECT_OBJECT_LABELS = frozenset(
    ("attr", "dative", "dobj", "iobj", "obj", "oprd")
)
_PREPOSITION_LABELS = frozenset(("agent", "case", "prep"))
_PREPOSITION_OBJECT_LABELS = frozenset(("obl", "pcomp", "pobj"))
_ARGUMENT_DESCENDANT_LABELS = frozenset(
    (
        "amod",
        "cc",
        "clf",
        "compound",
        "conj",
        "det",
        "fixed",
        "flat",
        "flat:name",
        "goeswith",
        "name",
        "nmod:poss",
        "nummod",
        "poss",
        "predet",
        "quantmod",
    )
)
_NOMINAL_RELATION_DESCENDANT_LABELS = frozenset(
    ("amod", "compound", "fixed", "flat", "flat:name", "nummod", "quantmod")
)
_RELATION_CHILD_LABELS = frozenset(
    (
        "aux",
        "aux:pass",
        "auxpass",
        "cop",
        "neg",
        "prt",
    )
)
_COMPARATIVE_TAGS = frozenset(("JJR", "JJS", "RBR", "RBS"))
_CONTENT_CLAUSE_LABELS = frozenset(
    ("acomp", "acl", "ccomp", "relcl", "xcomp")
)
_HEX = frozenset("0123456789abcdef")


def _valid_confidence(value: Any) -> bool:
    return value is None or (
        type(value) in (float, int)
        and type(value) is not bool
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    )


def _valid_identifier(value: Any, *, maximum: int = 128) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= maximum
        and value == value.strip()
        and not any(character.isspace() for character in value)
    )


def _is_digest(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _input_digest(value: Any) -> str:
    if type(value) is str:
        payload = value
    else:
        payload = f"<python:{type(value).__module__}.{type(value).__qualname__}>"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TextSpan:
    """A half-open character span in the exact input text."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if (
            type(self.start) is not int
            or type(self.end) is not int
            or not 0 <= self.start < self.end <= MAX_TEXT_CHARS
        ):
            raise ValueError("text span is invalid")

    def to_dict(self) -> dict[str, int]:
        self.__post_init__()
        return {"start": self.start, "end": self.end}


@dataclass(frozen=True, slots=True)
class ParserProvenance:
    backend_name: str
    backend_version: str
    model_name: str
    model_version: str
    model_artifact_sha256: str

    def __post_init__(self) -> None:
        if not all(
            _valid_identifier(value)
            for value in (
                self.backend_name,
                self.backend_version,
                self.model_name,
                self.model_version,
            )
        ) or not _is_digest(self.model_artifact_sha256):
            raise ValueError("parser provenance is invalid")

    def to_dict(self) -> dict[str, str]:
        self.__post_init__()
        return {
            "backend_name": self.backend_name,
            "backend_version": self.backend_version,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_artifact_sha256": self.model_artifact_sha256,
        }


@dataclass(frozen=True, slots=True)
class DependencyToken:
    """One normalized token from a single-sentence dependency tree."""

    index: int
    text: str
    start: int
    end: int
    head_index: int | None
    dependency: str
    part_of_speech: str
    tag: str
    lemma: str
    morphology: tuple[str, ...] = ()
    entity_type: str = ""
    confidence: float | None = None

    @property
    def span(self) -> TextSpan:
        return TextSpan(self.start, self.end)

    def __post_init__(self) -> None:
        if (
            type(self.index) is not int
            or self.index < 0
            or type(self.text) is not str
            or not self.text
            or type(self.start) is not int
            or type(self.end) is not int
            or not 0 <= self.start < self.end <= MAX_TEXT_CHARS
            or (
                self.head_index is not None
                and (type(self.head_index) is not int or self.head_index < 0)
            )
            or not _valid_identifier(self.dependency, maximum=64)
            or not _valid_identifier(self.part_of_speech, maximum=32)
            or not _valid_identifier(self.tag, maximum=32)
            or type(self.lemma) is not str
            or not self.lemma
            or len(self.lemma) > 256
            or type(self.morphology) is not tuple
            or any(
                not _valid_identifier(feature, maximum=96)
                for feature in self.morphology
            )
            or tuple(sorted(set(self.morphology))) != self.morphology
            or type(self.entity_type) is not str
            or len(self.entity_type) > 32
            or (
                self.entity_type
                and not _valid_identifier(self.entity_type, maximum=32)
            )
            or not _valid_confidence(self.confidence)
        ):
            raise ValueError("dependency token is invalid")

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            "index": self.index,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "head_index": self.head_index,
            "dependency": self.dependency,
            "part_of_speech": self.part_of_speech,
            "tag": self.tag,
            "lemma": self.lemma,
            "morphology": list(self.morphology),
            "entity_type": self.entity_type,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class DependencyParse:
    """A validated, single-sentence dependency tree."""

    text: str
    tokens: tuple[DependencyToken, ...]
    provenance: ParserProvenance
    confidence: float | None = None

    def __post_init__(self) -> None:
        if (
            type(self.text) is not str
            or not self.text
            or len(self.text) > MAX_TEXT_CHARS
            or type(self.tokens) is not tuple
            or not 1 <= len(self.tokens) <= MAX_TOKENS
            or type(self.provenance) is not ParserProvenance
            or not _valid_confidence(self.confidence)
        ):
            raise ValueError("dependency parse is invalid")
        if tuple(token.index for token in self.tokens) != tuple(
            range(len(self.tokens))
        ):
            raise ValueError("dependency token indices are not contiguous")
        previous_end = -1
        for token in self.tokens:
            if (
                type(token) is not DependencyToken
                or token.end > len(self.text)
                or self.text[token.start : token.end] != token.text
                or token.start < previous_end
                or (
                    token.head_index is not None
                    and token.head_index >= len(self.tokens)
                )
                or token.head_index == token.index
            ):
                raise ValueError("dependency token is not bound to input")
            previous_end = token.end
        roots = tuple(
            token
            for token in self.tokens
            if token.dependency.casefold() == "root"
        )
        if (
            len(roots) != 1
            or roots[0].head_index is not None
            or any(
                token.head_index is None and token is not roots[0]
                for token in self.tokens
            )
        ):
            raise ValueError("dependency parse must have exactly one root")
        root_index = roots[0].index
        for token in self.tokens:
            visited: set[int] = set()
            cursor = token.index
            while cursor != root_index:
                if cursor in visited:
                    raise ValueError("dependency parse contains a cycle")
                visited.add(cursor)
                head = self.tokens[cursor].head_index
                if head is None:
                    raise ValueError("dependency token is disconnected")
                cursor = head

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            "text": self.text,
            "tokens": [token.to_dict() for token in self.tokens],
            "provenance": self.provenance.to_dict(),
            "confidence": self.confidence,
        }


class DependencyParserBackend(Protocol):
    """Local parser seam consumed by :class:`RelationRoleExtractor`."""

    def parse(self, text: str, /) -> DependencyParse:
        """Return one validated dependency tree for ``text``."""


class DependencyBackendFailure(RuntimeError):
    """A sanitized fail-closed backend condition."""

    def __init__(self, reason: str) -> None:
        if reason not in _FAILURE_REASONS:
            raise ValueError("unsupported dependency backend failure")
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class RelationRole:
    role: RoleName
    text: str
    spans: tuple[TextSpan, ...]
    token_indices: tuple[int, ...]
    head_token_index: int
    lemmas: tuple[str, ...]
    parts_of_speech: tuple[str, ...]
    dependencies: tuple[str, ...]
    confidence: float | None

    @property
    def start(self) -> int:
        return self.spans[0].start

    @property
    def end(self) -> int:
        return self.spans[-1].end

    def __post_init__(self) -> None:
        if (
            self.role not in _ROLE_NAMES
            or type(self.text) is not str
            or not self.text
            or type(self.spans) is not tuple
            or not self.spans
            or any(type(span) is not TextSpan for span in self.spans)
            or any(
                left.end >= right.start
                for left, right in zip(self.spans, self.spans[1:])
            )
            or type(self.token_indices) is not tuple
            or not self.token_indices
            or any(type(index) is not int or index < 0 for index in self.token_indices)
            or tuple(sorted(set(self.token_indices))) != self.token_indices
            or type(self.head_token_index) is not int
            or self.head_token_index not in self.token_indices
            or type(self.lemmas) is not tuple
            or len(self.lemmas) != len(self.token_indices)
            or any(
                type(lemma) is not str or not lemma or len(lemma) > 256
                for lemma in self.lemmas
            )
            or type(self.parts_of_speech) is not tuple
            or len(self.parts_of_speech) != len(self.token_indices)
            or any(
                not _valid_identifier(value, maximum=32)
                for value in self.parts_of_speech
            )
            or type(self.dependencies) is not tuple
            or len(self.dependencies) != len(self.token_indices)
            or any(
                not _valid_identifier(value, maximum=64)
                for value in self.dependencies
            )
            or not _valid_confidence(self.confidence)
        ):
            raise ValueError("relation role is invalid")

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            "role": self.role,
            "text": self.text,
            "spans": [span.to_dict() for span in self.spans],
            "token_indices": list(self.token_indices),
            "head_token_index": self.head_token_index,
            "lemmas": list(self.lemmas),
            "parts_of_speech": list(self.parts_of_speech),
            "dependencies": list(self.dependencies),
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class CueEvidence:
    """Exact parser-token evidence for direction, polarity, or a hazard."""

    kind: str
    text: str
    span: TextSpan
    token_index: int
    dependency: str
    part_of_speech: str
    tag: str

    def __post_init__(self) -> None:
        if (
            not _valid_identifier(self.kind)
            or type(self.text) is not str
            or not self.text
            or type(self.span) is not TextSpan
            or type(self.token_index) is not int
            or self.token_index < 0
            or not _valid_identifier(self.dependency, maximum=64)
            or not _valid_identifier(self.part_of_speech, maximum=32)
            or not _valid_identifier(self.tag, maximum=32)
        ):
            raise ValueError("cue evidence is invalid")

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            "kind": self.kind,
            "text": self.text,
            "span": self.span.to_dict(),
            "token_index": self.token_index,
            "dependency": self.dependency,
            "part_of_speech": self.part_of_speech,
            "tag": self.tag,
        }


@dataclass(frozen=True, slots=True)
class SemanticHazard:
    kind: HazardKind
    evidence: tuple[CueEvidence, ...]

    def __post_init__(self) -> None:
        if (
            self.kind not in _HAZARD_KINDS
            or type(self.evidence) is not tuple
            or not self.evidence
            or any(type(cue) is not CueEvidence for cue in self.evidence)
        ):
            raise ValueError("semantic hazard is invalid")

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            "kind": self.kind,
            "evidence": [cue.to_dict() for cue in self.evidence],
        }


def _receipt_body(
    *,
    schema_version: str,
    status: ExtractionStatus,
    reason: str,
    input_digest_sha256: str,
    provenance: ParserProvenance | None,
    subject: RelationRole | None,
    relation: RelationRole | None,
    object_role: RelationRole | None,
    direction: RelationDirection | None,
    direction_evidence: tuple[CueEvidence, ...],
    polarity: Polarity | None,
    polarity_evidence: tuple[CueEvidence, ...],
    hazards: tuple[SemanticHazard, ...],
    confidence: float | None,
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "status": status,
        "reason": reason,
        "input_digest_sha256": input_digest_sha256,
        "provenance": (
            provenance.to_dict() if provenance is not None else None
        ),
        "subject": subject.to_dict() if subject is not None else None,
        "relation": relation.to_dict() if relation is not None else None,
        "object": (
            object_role.to_dict() if object_role is not None else None
        ),
        "direction": direction,
        "direction_evidence": [
            cue.to_dict() for cue in direction_evidence
        ],
        "polarity": polarity,
        "polarity_evidence": [
            cue.to_dict() for cue in polarity_evidence
        ],
        "hazards": [hazard.to_dict() for hazard in hazards],
        "confidence": confidence,
    }


@dataclass(frozen=True, slots=True)
class RelationRoleReceipt:
    """Immutable extraction result; deliberately contains no facts."""

    schema_version: str
    status: ExtractionStatus
    reason: str
    input_digest_sha256: str
    provenance: ParserProvenance | None
    subject: RelationRole | None
    relation: RelationRole | None
    object: RelationRole | None
    direction: RelationDirection | None
    direction_evidence: tuple[CueEvidence, ...]
    polarity: Polarity | None
    polarity_evidence: tuple[CueEvidence, ...]
    hazards: tuple[SemanticHazard, ...]
    confidence: float | None
    receipt_digest_sha256: str

    @property
    def roles_extracted(self) -> bool:
        return self.status in ("extracted", "hazard")

    @property
    def safe(self) -> bool:
        return self.status == "extracted"

    def __post_init__(self) -> None:
        if (
            self.schema_version != SCHEMA_VERSION
            or self.status not in _STATUSES
            or not _valid_identifier(self.reason, maximum=192)
            or not _is_digest(self.input_digest_sha256)
            or type(self.direction_evidence) is not tuple
            or any(
                type(cue) is not CueEvidence for cue in self.direction_evidence
            )
            or type(self.polarity_evidence) is not tuple
            or any(
                type(cue) is not CueEvidence for cue in self.polarity_evidence
            )
            or type(self.hazards) is not tuple
            or any(
                type(hazard) is not SemanticHazard for hazard in self.hazards
            )
            or not _valid_confidence(self.confidence)
            or not _is_digest(self.receipt_digest_sha256)
        ):
            raise ValueError("relation role receipt is invalid")
        if self.roles_extracted:
            if (
                type(self.provenance) is not ParserProvenance
                or type(self.subject) is not RelationRole
                or self.subject.role != "subject"
                or type(self.relation) is not RelationRole
                or self.relation.role != "relation"
                or type(self.object) is not RelationRole
                or self.object.role != "object"
                or self.direction not in _DIRECTIONS
                or self.polarity not in _POLARITIES
                or (self.status == "extracted" and self.hazards)
                or (self.status == "hazard" and not self.hazards)
            ):
                raise ValueError("extracted role receipt is inconsistent")
        elif (
            self.provenance is not None
            or self.subject is not None
            or self.relation is not None
            or self.object is not None
            or self.direction is not None
            or self.direction_evidence
            or self.polarity is not None
            or self.polarity_evidence
            or self.hazards
            or self.confidence is not None
        ):
            raise ValueError("empty role receipt leaked parser output")
        if self.receipt_digest_sha256 != canonical_digest(
            self._digest_body()
        ):
            raise ValueError("relation role receipt digest mismatch")

    def _digest_body(self) -> dict[str, Any]:
        return _receipt_body(
            schema_version=self.schema_version,
            status=self.status,
            reason=self.reason,
            input_digest_sha256=self.input_digest_sha256,
            provenance=self.provenance,
            subject=self.subject,
            relation=self.relation,
            object_role=self.object,
            direction=self.direction,
            direction_evidence=self.direction_evidence,
            polarity=self.polarity,
            polarity_evidence=self.polarity_evidence,
            hazards=self.hazards,
            confidence=self.confidence,
        )

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            **self._digest_body(),
            "receipt_digest_sha256": self.receipt_digest_sha256,
        }


@dataclass(frozen=True, slots=True)
class _RoleHeads:
    subject: int
    relation: int
    object: int
    relation_prepositions: tuple[int, ...]
    relation_nominals: tuple[int, ...]
    query_head: int | None
    wh_indices: tuple[int, ...]


class _ExtractionAbstention(RuntimeError):
    pass


def _children(parse: DependencyParse) -> dict[int, tuple[int, ...]]:
    pending: dict[int, list[int]] = {
        token.index: [] for token in parse.tokens
    }
    for token in parse.tokens:
        if token.head_index is not None:
            pending[token.head_index].append(token.index)
    return {
        index: tuple(sorted(indices))
        for index, indices in pending.items()
    }


def _dependency(token: DependencyToken) -> str:
    return token.dependency.casefold()


def _root_index(parse: DependencyParse) -> int:
    return next(
        token.index
        for token in parse.tokens
        if _dependency(token) == "root"
    )


def _query(
    parse: DependencyParse,
) -> tuple[int | None, tuple[int, ...]]:
    wh_indices = tuple(
        token.index for token in parse.tokens if token.tag in _WH_TAGS
    )
    if not wh_indices:
        return None, ()
    heads: set[int] = set()
    for index in wh_indices:
        token = parse.tokens[index]
        if _dependency(token) in ("det", "predet") and token.head_index is not None:
            heads.add(token.head_index)
        else:
            heads.add(index)
    if len(heads) != 1:
        raise _ExtractionAbstention("query_role_ambiguous")
    return next(iter(heads)), wh_indices


def _content_predicate(
    parse: DependencyParse,
    children: dict[int, tuple[int, ...]],
    root: int,
) -> int:
    root_token = parse.tokens[root]
    if root_token.part_of_speech != "AUX":
        return root
    candidates: set[int] = set()
    for child_index in children[root]:
        child = parse.tokens[child_index]
        if (
            _dependency(child) in _CONTENT_CLAUSE_LABELS
            and child.part_of_speech in ("ADJ", "AUX", "VERB")
        ):
            candidates.add(child_index)
        if _dependency(child) in ("attr", "oprd"):
            for descendant_index in children[child_index]:
                descendant = parse.tokens[descendant_index]
                if (
                    _dependency(descendant) in _CONTENT_CLAUSE_LABELS
                    and descendant.part_of_speech in ("ADJ", "AUX", "VERB")
                ):
                    candidates.add(descendant_index)
    if len(candidates) > 1:
        raise _ExtractionAbstention("predicate_ambiguous")
    return next(iter(candidates), root)


def _single(
    candidates: set[int],
    *,
    missing: str,
    ambiguous: str,
) -> int:
    if not candidates:
        raise _ExtractionAbstention(missing)
    if len(candidates) != 1:
        raise _ExtractionAbstention(ambiguous)
    return next(iter(candidates))


def _preposition_objects(
    parse: DependencyParse,
    children: dict[int, tuple[int, ...]],
    predicate: int,
) -> tuple[dict[int, set[int]], set[int]]:
    objects: dict[int, set[int]] = {}
    stranded: set[int] = set()
    for index in children[predicate]:
        token = parse.tokens[index]
        if _dependency(token) not in _PREPOSITION_LABELS:
            continue
        complements = {
            child_index
            for child_index in children[index]
            if _dependency(parse.tokens[child_index])
            in _PREPOSITION_OBJECT_LABELS
        }
        if complements:
            objects[index] = complements
        else:
            stranded.add(index)
    return objects, stranded


def _inherited_attribute(
    parse: DependencyParse,
    predicate: int,
    root: int,
) -> int | None:
    if predicate == root:
        return None
    token = parse.tokens[predicate]
    if (
        _dependency(token) in ("acl", "relcl")
        and token.head_index is not None
        and _dependency(parse.tokens[token.head_index]) in ("attr", "oprd")
    ):
        return token.head_index
    return None


def _copular_nominal_heads(
    parse: DependencyParse,
    children: dict[int, tuple[int, ...]],
    *,
    root: int,
    query_head: int | None,
    wh_indices: tuple[int, ...],
) -> _RoleHeads | None:
    """Normalize WH copulas by dependency shape, without lexical templates."""

    if query_head is None or parse.tokens[root].part_of_speech != "AUX":
        return None
    root_children = set(children[root])
    if query_head not in root_children:
        return None
    stranded_prepositions = {
        index
        for index in root_children
        if _dependency(parse.tokens[index]) in _PREPOSITION_LABELS
        and not any(
            _dependency(parse.tokens[child])
            in _PREPOSITION_OBJECT_LABELS
            for child in children[index]
        )
    }
    complements = {
        index
        for index in root_children
        if index != query_head
        and _dependency(parse.tokens[index]) in ("attr", "oprd")
    }
    query_dependency = _dependency(parse.tokens[query_head])
    if (
        stranded_prepositions
        and query_dependency in _SUBJECT_LABELS
        and len(complements) == 1
    ):
        if len(stranded_prepositions) != 1:
            raise _ExtractionAbstention("object_ambiguous")
        return _RoleHeads(
            subject=next(iter(complements)),
            relation=root,
            object=query_head,
            relation_prepositions=tuple(sorted(stranded_prepositions)),
            relation_nominals=(),
            query_head=query_head,
            wh_indices=wh_indices,
        )

    nominal_predicates = {
        index
        for index in root_children
        if index != query_head
        and _dependency(parse.tokens[index]) in _SUBJECT_LABELS
        and parse.tokens[index].part_of_speech in ("NOUN", "PROPN")
    }
    normalized: list[tuple[int, int, tuple[int, ...]]] = []
    for nominal in nominal_predicates:
        owners = {
            index
            for index in children[nominal]
            if _dependency(parse.tokens[index]) in ("nmod:poss", "poss")
        }
        links: set[int] = set()
        for index in children[nominal]:
            if _dependency(parse.tokens[index]) not in _PREPOSITION_LABELS:
                continue
            complements_for_link = {
                child
                for child in children[index]
                if _dependency(parse.tokens[child])
                in _PREPOSITION_OBJECT_LABELS
            }
            if complements_for_link:
                owners.update(complements_for_link)
                links.add(index)
        if len(owners) == 1:
            normalized.append(
                (next(iter(owners)), nominal, tuple(sorted(links)))
            )
    if len(normalized) > 1:
        raise _ExtractionAbstention("subject_ambiguous")
    if normalized:
        subject, nominal, links = normalized[0]
        return _RoleHeads(
            subject=subject,
            relation=root,
            object=query_head,
            relation_prepositions=links,
            relation_nominals=(nominal,),
            query_head=query_head,
            wh_indices=wh_indices,
        )

    if parse.tokens[query_head].part_of_speech in ("NOUN", "PROPN"):
        known_complements = {
            index
            for index in root_children
            if index != query_head
            and _dependency(parse.tokens[index])
            in ("attr", "nsubj", "oprd")
        }
        if len(known_complements) > 1:
            raise _ExtractionAbstention("subject_ambiguous")
        if known_complements:
            wh_object_candidates = {
                index
                for index in wh_indices
                if index == query_head
                or parse.tokens[index].head_index == query_head
            }
            wh_object = _single(
                wh_object_candidates,
                missing="query_role_unresolved",
                ambiguous="query_role_ambiguous",
            )
            return _RoleHeads(
                subject=next(iter(known_complements)),
                relation=root,
                object=wh_object,
                relation_prepositions=(),
                relation_nominals=(query_head,),
                query_head=query_head,
                wh_indices=wh_indices,
            )
    return None


def _select_heads(
    parse: DependencyParse,
    children: dict[int, tuple[int, ...]],
) -> _RoleHeads:
    root = _root_index(parse)
    predicate = _content_predicate(parse, children, root)
    predicate_token = parse.tokens[predicate]
    if predicate_token.part_of_speech not in ("ADJ", "AUX", "NOUN", "PROPN", "VERB"):
        raise _ExtractionAbstention("predicate_missing")
    query_head, wh_indices = _query(parse)
    if predicate == root:
        copular = _copular_nominal_heads(
            parse,
            children,
            root=root,
            query_head=query_head,
            wh_indices=wh_indices,
        )
        if copular is not None:
            return copular
    subject_candidates = {
        index
        for index in children[predicate]
        if _dependency(parse.tokens[index]) in _SUBJECT_LABELS
    }
    passive_subjects = {
        index
        for index in subject_candidates
        if _dependency(parse.tokens[index]) in _PASSIVE_SUBJECT_LABELS
    }
    direct_objects = {
        index
        for index in children[predicate]
        if _dependency(parse.tokens[index]) in _DIRECT_OBJECT_LABELS
    }
    prep_objects, stranded_prepositions = _preposition_objects(
        parse, children, predicate
    )
    agent_prepositions = {
        index
        for index in (*prep_objects.keys(), *stranded_prepositions)
        if _dependency(parse.tokens[index]) == "agent"
    }
    inherited = _inherited_attribute(parse, predicate, root)

    agent_objects: set[int] = set()
    for prep_index in agent_prepositions:
        agent_objects.update(prep_objects.get(prep_index, set()))
    if agent_objects:
        subject = _single(
            agent_objects,
            missing="subject_missing",
            ambiguous="subject_ambiguous",
        )
        themes = passive_subjects or ({inherited} if inherited is not None else set())
        object_head = _single(
            themes,
            missing="object_missing",
            ambiguous="object_ambiguous",
        )
        relation_prepositions = tuple(sorted(agent_prepositions))
    elif agent_prepositions and query_head is not None:
        subject = query_head
        themes = passive_subjects or ({inherited} if inherited is not None else set())
        object_head = _single(
            themes,
            missing="object_missing",
            ambiguous="object_ambiguous",
        )
        relation_prepositions = tuple(sorted(agent_prepositions))
    else:
        ordinary_stranded = stranded_prepositions - agent_prepositions
        if (
            query_head is not None
            and query_head in subject_candidates
            and ordinary_stranded
        ):
            nonquery_subjects = subject_candidates - {query_head}
            if nonquery_subjects:
                subject_candidates = nonquery_subjects
        if not subject_candidates and inherited is not None:
            subject_candidates = {inherited}
        subject = _single(
            subject_candidates,
            missing="subject_missing",
            ambiguous="subject_ambiguous",
        )
        ordinary_prep_objects: dict[int, set[int]] = {
            prep: values
            for prep, values in prep_objects.items()
            if prep not in agent_prepositions
        }
        if direct_objects:
            object_head = _single(
                direct_objects,
                missing="object_missing",
                ambiguous="object_ambiguous",
            )
            relation_prepositions = ()
        elif ordinary_prep_objects:
            all_objects = {
                index
                for values in ordinary_prep_objects.values()
                for index in values
            }
            object_head = _single(
                all_objects,
                missing="object_missing",
                ambiguous="object_ambiguous",
            )
            relation_prepositions = tuple(
                sorted(
                    prep
                    for prep, values in ordinary_prep_objects.items()
                    if object_head in values
                )
            )
        else:
            if query_head is None or not ordinary_stranded:
                raise _ExtractionAbstention("object_missing")
            if len(ordinary_stranded) != 1:
                raise _ExtractionAbstention("object_ambiguous")
            object_head = query_head
            relation_prepositions = tuple(sorted(ordinary_stranded))
    if subject == object_head:
        raise _ExtractionAbstention("role_overlap")
    return _RoleHeads(
        subject=subject,
        relation=predicate,
        object=object_head,
        relation_prepositions=relation_prepositions,
        relation_nominals=(),
        query_head=query_head,
        wh_indices=wh_indices,
    )


def _argument_indices(
    parse: DependencyParse,
    children: dict[int, tuple[int, ...]],
    head: int,
) -> tuple[int, ...]:
    included = {head}
    pending = [head]
    while pending:
        parent = pending.pop()
        for index in children[parent]:
            if (
                index not in included
                and _dependency(parse.tokens[index])
                in _ARGUMENT_DESCENDANT_LABELS
            ):
                included.add(index)
                pending.append(index)
    return tuple(sorted(included))


def _relation_indices(
    parse: DependencyParse,
    children: dict[int, tuple[int, ...]],
    heads: _RoleHeads,
) -> tuple[int, ...]:
    root = _root_index(parse)
    included = {
        heads.relation,
        *heads.relation_prepositions,
        *heads.relation_nominals,
    }
    if heads.relation != root and parse.tokens[root].part_of_speech == "AUX":
        included.add(root)
    for parent in (heads.relation, root):
        for index in children[parent]:
            token = parse.tokens[index]
            dependency = _dependency(token)
            if (
                dependency in _RELATION_CHILD_LABELS
                or token.tag in _COMPARATIVE_TAGS
            ):
                included.add(index)
    pending = list(heads.relation_prepositions)
    while pending:
        parent = pending.pop()
        for index in children[parent]:
            if _dependency(parse.tokens[index]) == "fixed":
                included.add(index)
                pending.append(index)
    pending = list(heads.relation_nominals)
    while pending:
        parent = pending.pop()
        for index in children[parent]:
            if (
                index not in included
                and _dependency(parse.tokens[index])
                in _NOMINAL_RELATION_DESCENDANT_LABELS
            ):
                included.add(index)
                pending.append(index)
    return tuple(sorted(included))


def _spans(
    parse: DependencyParse,
    indices: tuple[int, ...],
) -> tuple[TextSpan, ...]:
    spans: list[TextSpan] = []
    start = parse.tokens[indices[0]].start
    end = parse.tokens[indices[0]].end
    previous_index = indices[0]
    for index in indices[1:]:
        token = parse.tokens[index]
        between = parse.text[end : token.start]
        if index == previous_index + 1 and (not between or between.isspace()):
            end = token.end
        else:
            spans.append(TextSpan(start, end))
            start = token.start
            end = token.end
        previous_index = index
    spans.append(TextSpan(start, end))
    return tuple(spans)


def _confidence(
    parse: DependencyParse,
    indices: tuple[int, ...],
) -> float | None:
    values = [
        float(value)
        for value in (
            parse.confidence,
            *(parse.tokens[index].confidence for index in indices),
        )
        if value is not None
    ]
    return min(values) if values else None


def _role(
    parse: DependencyParse,
    *,
    role: RoleName,
    head: int,
    indices: tuple[int, ...],
) -> RelationRole:
    return RelationRole(
        role=role,
        text=" ".join(parse.tokens[index].text for index in indices),
        spans=_spans(parse, indices),
        token_indices=indices,
        head_token_index=head,
        lemmas=tuple(parse.tokens[index].lemma for index in indices),
        parts_of_speech=tuple(
            parse.tokens[index].part_of_speech for index in indices
        ),
        dependencies=tuple(
            parse.tokens[index].dependency for index in indices
        ),
        confidence=_confidence(parse, indices),
    )


def _cue(
    token: DependencyToken,
    kind: str,
) -> CueEvidence:
    return CueEvidence(
        kind=kind,
        text=token.text,
        span=token.span,
        token_index=token.index,
        dependency=token.dependency,
        part_of_speech=token.part_of_speech,
        tag=token.tag,
    )


def _hazards(
    parse: DependencyParse,
    selected_indices: set[int],
    relation_indices: set[int],
) -> tuple[
    Polarity,
    tuple[CueEvidence, ...],
    tuple[SemanticHazard, ...],
]:
    negative = tuple(
        _cue(token, "negation")
        for token in parse.tokens
        if _dependency(token) == "neg" or "Polarity=Neg" in token.morphology
    )
    comparison = tuple(
        _cue(token, "comparison")
        for token in parse.tokens
        if token.tag in _COMPARATIVE_TAGS
        or "Degree=Cmp" in token.morphology
        or "Degree=Sup" in token.morphology
    )
    temporal = tuple(
        _cue(token, "past_tense")
        for token in parse.tokens
        if (
            token.index in relation_indices
            and "Tense=Past" in token.morphology
            and (
                "VerbForm=Fin" in token.morphology
                or token.tag == "VBD"
            )
        )
        or token.entity_type in ("DATE", "TIME")
    )
    modality = tuple(
        _cue(token, "modal_auxiliary")
        for token in parse.tokens
        if token.index in relation_indices and token.tag == "MD"
    )
    coordination = tuple(
        _cue(token, "coordination")
        for token in parse.tokens
        if token.index in selected_indices
        and _dependency(token) in ("cc", "conj")
    )
    groups: tuple[tuple[HazardKind, tuple[CueEvidence, ...]], ...] = (
        ("negation", negative),
        ("comparison", comparison),
        ("temporal", temporal),
        ("modality", modality),
        ("coordination", coordination),
    )
    hazards = tuple(
        SemanticHazard(kind=kind, evidence=evidence)
        for kind, evidence in groups
        if evidence
    )
    return ("negative" if negative else "positive"), negative, hazards


def _make_receipt(
    *,
    status: ExtractionStatus,
    reason: str,
    digest: str,
    provenance: ParserProvenance | None,
    subject: RelationRole | None,
    relation: RelationRole | None,
    object_role: RelationRole | None,
    direction: RelationDirection | None,
    direction_evidence: tuple[CueEvidence, ...],
    polarity: Polarity | None,
    polarity_evidence: tuple[CueEvidence, ...],
    hazards: tuple[SemanticHazard, ...],
    confidence: float | None,
) -> RelationRoleReceipt:
    body = _receipt_body(
        schema_version=SCHEMA_VERSION,
        status=status,
        reason=reason,
        input_digest_sha256=digest,
        provenance=provenance,
        subject=subject,
        relation=relation,
        object_role=object_role,
        direction=direction,
        direction_evidence=direction_evidence,
        polarity=polarity,
        polarity_evidence=polarity_evidence,
        hazards=hazards,
        confidence=confidence,
    )
    return RelationRoleReceipt(
        schema_version=SCHEMA_VERSION,
        status=status,
        reason=reason,
        input_digest_sha256=digest,
        provenance=provenance,
        subject=subject,
        relation=relation,
        object=object_role,
        direction=direction,
        direction_evidence=direction_evidence,
        polarity=polarity,
        polarity_evidence=polarity_evidence,
        hazards=hazards,
        confidence=confidence,
        receipt_digest_sha256=canonical_digest(body),
    )


def _empty_receipt(
    *,
    status: Literal["abstain", "invalid"],
    reason: str,
    digest: str,
) -> RelationRoleReceipt:
    return _make_receipt(
        status=status,
        reason=reason,
        digest=digest,
        provenance=None,
        subject=None,
        relation=None,
        object_role=None,
        direction=None,
        direction_evidence=(),
        polarity=None,
        polarity_evidence=(),
        hazards=(),
        confidence=None,
    )


class RelationRoleExtractor:
    """Extract S/R/O roles from a backend-provided dependency graph."""

    def __init__(
        self,
        backend: DependencyParserBackend | None = None,
    ) -> None:
        self._backend = backend

    @property
    def available(self) -> bool:
        return self._backend is not None

    def extract(self, text: Any) -> RelationRoleReceipt:
        digest = _input_digest(text)
        if (
            type(text) is not str
            or not text
            or text != text.strip()
            or len(text) > MAX_TEXT_CHARS
            or unicodedata.normalize("NFKC", text) != text
            or any(
                unicodedata.category(character) == "Cc"
                for character in text
            )
        ):
            return _empty_receipt(
                status="invalid",
                reason="text_out_of_bounds",
                digest=digest,
            )
        if self._backend is None:
            return _empty_receipt(
                status="abstain",
                reason="dependency_backend_unavailable",
                digest=digest,
            )
        try:
            parse = self._backend.parse(text)
        except DependencyBackendFailure as error:
            return _empty_receipt(
                status="abstain",
                reason=error.reason,
                digest=digest,
            )
        except Exception:
            return _empty_receipt(
                status="abstain",
                reason="dependency_backend_error",
                digest=digest,
            )
        if type(parse) is not DependencyParse or parse.text != text:
            return _empty_receipt(
                status="abstain",
                reason="dependency_backend_error",
                digest=digest,
            )
        try:
            children = _children(parse)
            heads = _select_heads(parse, children)
            subject_indices = _argument_indices(
                parse, children, heads.subject
            )
            object_indices = _argument_indices(
                parse, children, heads.object
            )
            relation_indices = _relation_indices(parse, children, heads)
            if (
                set(subject_indices) & set(object_indices)
                or set(subject_indices) & set(relation_indices)
                or set(object_indices) & set(relation_indices)
            ):
                raise _ExtractionAbstention("role_overlap")
            subject = _role(
                parse,
                role="subject",
                head=heads.subject,
                indices=subject_indices,
            )
            relation = _role(
                parse,
                role="relation",
                head=heads.relation,
                indices=relation_indices,
            )
            object_role = _role(
                parse,
                role="object",
                head=heads.object,
                indices=object_indices,
            )
            if heads.query_head is None:
                direction: RelationDirection = "declarative"
                direction_evidence: tuple[CueEvidence, ...] = ()
            elif set(heads.wh_indices) & set(subject_indices):
                direction = "inverse"
                direction_evidence = tuple(
                    _cue(parse.tokens[index], "query_subject")
                    for index in heads.wh_indices
                )
            elif set(heads.wh_indices) & set(object_indices):
                direction = "forward"
                direction_evidence = tuple(
                    _cue(parse.tokens[index], "query_object")
                    for index in heads.wh_indices
                )
            else:
                raise _ExtractionAbstention("query_role_unresolved")
            selected = set(
                (*subject_indices, *relation_indices, *object_indices)
            )
            polarity, polarity_evidence, hazards = _hazards(
                parse, selected, set(relation_indices)
            )
            role_confidences = (
                subject.confidence,
                relation.confidence,
                object_role.confidence,
            )
            known_confidences = tuple(
                value for value in role_confidences if value is not None
            )
            confidence = (
                min(known_confidences) if known_confidences else None
            )
        except _ExtractionAbstention as error:
            return _empty_receipt(
                status="abstain",
                reason=str(error),
                digest=digest,
            )
        status: ExtractionStatus = "hazard" if hazards else "extracted"
        return _make_receipt(
            status=status,
            reason=(
                "semantic_hazard_detected"
                if hazards
                else "roles_extracted"
            ),
            digest=digest,
            provenance=parse.provenance,
            subject=subject,
            relation=relation,
            object_role=object_role,
            direction=direction,
            direction_evidence=direction_evidence,
            polarity=polarity,
            polarity_evidence=polarity_evidence,
            hazards=hazards,
            confidence=confidence,
        )


class _SpacyDependencyBackend:
    """Exact-version, lazy, local-only spaCy parser adapter."""

    def __init__(
        self,
        *,
        version_reader: Callable[[str], str] | None = None,
        module_importer: Callable[[str], Any] | None = None,
    ) -> None:
        self._version_reader = version_reader or importlib_metadata.version
        self._module_importer = module_importer or import_module
        self._nlp: Any | None = None
        self._lock = Lock()
        self._provenance = ParserProvenance(
            backend_name=SPACY_DISTRIBUTION,
            backend_version=SPACY_VERSION,
            model_name=SPACY_MODEL_NAME,
            model_version=SPACY_MODEL_VERSION,
            model_artifact_sha256=SPACY_MODEL_WHEEL_SHA256,
        )

    @property
    def loaded(self) -> bool:
        return self._nlp is not None

    def _distribution_version(
        self,
        distribution: str,
        *,
        missing_reason: str,
    ) -> str:
        try:
            return self._version_reader(distribution)
        except importlib_metadata.PackageNotFoundError as error:
            raise DependencyBackendFailure(missing_reason) from error

    def _load(self) -> Any:
        if self._nlp is not None:
            return self._nlp
        with self._lock:
            if self._nlp is not None:
                return self._nlp
            runtime_version = self._distribution_version(
                SPACY_DISTRIBUTION,
                missing_reason="dependency_backend_unavailable",
            )
            if runtime_version != SPACY_VERSION:
                raise DependencyBackendFailure(
                    "dependency_backend_version_mismatch"
                )
            model_version = self._distribution_version(
                SPACY_MODEL_DISTRIBUTION,
                missing_reason="dependency_model_unavailable",
            )
            if model_version != SPACY_MODEL_VERSION:
                raise DependencyBackendFailure(
                    "dependency_model_version_mismatch"
                )
            try:
                spacy = self._module_importer(SPACY_DISTRIBUTION)
            except (ImportError, ModuleNotFoundError) as error:
                raise DependencyBackendFailure(
                    "dependency_backend_unavailable"
                ) from error
            if getattr(spacy, "__version__", None) != SPACY_VERSION:
                raise DependencyBackendFailure(
                    "dependency_backend_version_mismatch"
                )
            try:
                nlp = spacy.load(SPACY_MODEL_NAME)
            except OSError as error:
                raise DependencyBackendFailure(
                    "dependency_model_unavailable"
                ) from error
            meta = getattr(nlp, "meta", {})
            if (
                meta.get("lang") != "en"
                or meta.get("name") != "core_web_sm"
                or meta.get("version") != SPACY_MODEL_VERSION
            ):
                raise DependencyBackendFailure(
                    "dependency_model_version_mismatch"
                )
            required_pipes = {
                "attribute_ruler",
                "lemmatizer",
                "parser",
                "tagger",
                "tok2vec",
            }
            if not required_pipes.issubset(set(nlp.pipe_names)):
                raise DependencyBackendFailure(
                    "dependency_model_version_mismatch"
                )
            self._nlp = nlp
            return nlp

    def parse(self, text: str, /) -> DependencyParse:
        nlp = self._load()
        doc = nlp(text)
        if (
            len(doc) > MAX_TOKENS
            or not doc.has_annotation("DEP")
            or not doc.has_annotation("POS")
            or len(tuple(doc.sents)) != 1
        ):
            raise DependencyBackendFailure("dependency_backend_error")
        tokens = tuple(
            DependencyToken(
                index=token.i,
                text=token.text,
                start=token.idx,
                end=token.idx + len(token.text),
                head_index=(
                    None if token.head.i == token.i else token.head.i
                ),
                dependency=token.dep_.casefold(),
                part_of_speech=token.pos_,
                tag=token.tag_,
                lemma=token.lemma_,
                morphology=tuple(
                    sorted(str(feature) for feature in token.morph)
                ),
                entity_type=token.ent_type_,
                confidence=None,
            )
            for token in doc
        )
        return DependencyParse(
            text=text,
            tokens=tokens,
            provenance=self._provenance,
            confidence=None,
        )


class SpacyRelationRoleExtractor(RelationRoleExtractor):
    """Pinned spaCy 3.8.14 / en_core_web_sm 3.8.0 local extractor."""

    def __init__(self) -> None:
        backend = _SpacyDependencyBackend()
        self._spacy_backend = backend
        super().__init__(backend)

    @property
    def loaded(self) -> bool:
        return self._spacy_backend.loaded
