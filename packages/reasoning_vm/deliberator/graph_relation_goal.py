"""Graph-conditioned NL-to-goal compilation for arbitrary staged properties.

The predicate vocabulary in this module is empty by design.  A candidate
property must be present both on the resolved subject's staged outgoing edges
and in a validated Wikidata property catalog.  Natural-language matching is
then performed against the source-owned property label and aliases.

This is a proposal mechanism, not an answerer or a capability claim.  It emits
one proof obligation whose object must later be selected by the proof-carrying
stage.  It never receives a gold answer and never chooses a choice.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
import hashlib
import hmac
from itertools import islice
import math
import os
import re
import unicodedata
from types import MappingProxyType
from typing import Any, Literal

from packages.cognitive_core.canonical import canonical_digest
from packages.reasoning_vm.ace.match_features import tokenize
from packages.reasoning_vm.deliberator.wikidata_property_catalog import (
    WikidataProperty,
    WikidataPropertyCatalogSnapshot,
)


SCHEMA_VERSION = "atanor.deliberator.graph-relation-goal.v1"
STAGE_SCHEMA_VERSION = "atanor.graph-relation-context.v1"
COMPILER_RULE = "graph_conditioned_property_binding_v1"

MAX_STEM_CHARS = 2048
MAX_CHOICES = 12
MAX_CHOICE_TEXT_CHARS = 512
MAX_ENTITY_SURFACE_CHARS = 192
MAX_ENTITY_ALIASES = 64
MAX_CONTEXT_ENTITIES = 10_000
MAX_CONTEXT_FACTS = 100_000
MAX_OBJECT_VALUE_CHARS = 2048
MAX_ENTITY_SURFACE_WORDS = 16
MIN_PROPERTY_SCORE = 2.0
MIN_SCORE_MARGIN = 0.25

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_QID = re.compile(r"Q[1-9]\d{0,11}\Z")
_PID = re.compile(r"P[1-9]\d{0,11}\Z")
_STAGE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_WORD = re.compile(r"[A-Za-z0-9]+")
_VALIDATION_KEY = os.urandom(32)
_MAPPING_PROXY_TYPE = type(MappingProxyType({}))

# These are semantic hazard classes, not relation names or surface templates.
_NEGATION = re.compile(
    r"(?:\b(?:except|false|never|no|none|not|without)\b|"
    r"\b[A-Za-z]+n['\u2019]?t\b)",
    re.IGNORECASE,
)
_TEMPORAL = re.compile(
    r"\b(?:after|before|currently|during|formerly|historical|previously|"
    r"since|until|was|were|when|year)\b",
    re.IGNORECASE,
)
_COMPARISON = re.compile(
    r"\b(?:best|closest|farthest|greater|largest|least|less|more|most|"
    r"nearest|same|smallest|than|worst)\b",
    re.IGNORECASE,
)
_SUBJECT_LINK_AUX = re.compile(
    r"\b(?:am|are|can|could|did|do|does|had|has|have|is|may|might|"
    r"should|was|were|will|would)\b",
    re.IGNORECASE,
)
_NOMINAL_BRIDGE = re.compile(
    r"\b(?:for|from|in|of|on|to|with)\b",
    re.IGNORECASE,
)
_INTERROGATIVE = re.compile(
    r"^\s*(?:how|what|when|where|which|who|whom|whose|why|"
    r"am|are|can|could|did|do|does|had|has|have|is|may|might|"
    r"should|was|were|will|would)\b",
    re.IGNORECASE,
)
_INVERSE_ROLE = re.compile(r"\bby\b", re.IGNORECASE)

CompilationStatus = Literal["compiled", "abstain", "invalid"]
ObjectKind = Literal["entity", "literal"]


def _is_sha256(value: Any) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _normalize_surface(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _surface_key(value: str) -> str:
    return _normalize_surface(value).casefold()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class GraphEntity:
    entity_id: str
    label: str
    aliases: tuple[str, ...]
    evidence_digest_sha256: str

    @property
    def surfaces(self) -> tuple[str, ...]:
        return (self.label, *self.aliases)

    def __post_init__(self) -> None:
        surfaces = self.surfaces
        keys = tuple(_surface_key(value) for value in surfaces)
        if (
            type(self.entity_id) is not str
            or _QID.fullmatch(self.entity_id) is None
            or type(self.label) is not str
            or type(self.aliases) is not tuple
            or len(self.aliases) > MAX_ENTITY_ALIASES
            or not surfaces
            or any(
                type(value) is not str
                or not value
                or value != _normalize_surface(value)
                or len(value) > MAX_ENTITY_SURFACE_CHARS
                or not 1
                <= len(_WORD.findall(value))
                <= MAX_ENTITY_SURFACE_WORDS
                for value in surfaces
            )
            or len(set(keys)) != len(keys)
            or not _is_sha256(self.evidence_digest_sha256)
        ):
            raise ValueError("graph entity is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "label": self.label,
            "aliases": list(self.aliases),
            "evidence_digest_sha256": self.evidence_digest_sha256,
        }


@dataclass(frozen=True, slots=True)
class GraphPropertyFact:
    subject_entity_id: str
    property_id: str
    object_kind: ObjectKind
    object_value: str
    evidence_digest_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.subject_entity_id) is not str
            or _QID.fullmatch(self.subject_entity_id) is None
            or type(self.property_id) is not str
            or _PID.fullmatch(self.property_id) is None
            or type(self.object_kind) is not str
            or self.object_kind not in ("entity", "literal")
            or type(self.object_value) is not str
            or not self.object_value
            or self.object_value != _normalize_surface(self.object_value)
            or len(self.object_value) > MAX_OBJECT_VALUE_CHARS
            or (
                self.object_kind == "entity"
                and _QID.fullmatch(self.object_value) is None
            )
            or not _is_sha256(self.evidence_digest_sha256)
        ):
            raise ValueError("graph property fact is invalid")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _context_tag(
    *,
    stage_id: str,
    stage_digest_sha256: str,
    source_digest_sha256: str,
    entities: tuple[GraphEntity, ...],
    facts: tuple[GraphPropertyFact, ...],
) -> str:
    return hmac.new(
        _VALIDATION_KEY,
        canonical_digest(
            {
                "schema_version": STAGE_SCHEMA_VERSION,
                "stage_id": stage_id,
                "stage_digest_sha256": stage_digest_sha256,
                "source_digest_sha256": source_digest_sha256,
                "entities": [row.to_dict() for row in entities],
                "facts": [row.to_dict() for row in facts],
            }
        ).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class GraphRelationContext:
    """Detached, validation-sealed view of a PID-preserving staged graph."""

    stage_id: str
    stage_digest_sha256: str
    source_digest_sha256: str
    entities: tuple[GraphEntity, ...]
    facts: tuple[GraphPropertyFact, ...]
    authority_claims: Mapping[str, bool]
    _entities_by_surface: Mapping[str, tuple[GraphEntity, ...]]
    _properties_by_subject: Mapping[str, tuple[str, ...]]
    _facts_by_subject_property: Mapping[
        tuple[str, str],
        tuple[GraphPropertyFact, ...],
    ]
    _validation_seal: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        self.assert_validated()

    def assert_validated(self) -> None:
        if (
            type(self.stage_id) is not str
            or _STAGE_ID.fullmatch(self.stage_id) is None
            or not _is_sha256(self.stage_digest_sha256)
            or not _is_sha256(self.source_digest_sha256)
            or type(self.entities) is not tuple
            or not 1 <= len(self.entities) <= MAX_CONTEXT_ENTITIES
            or type(self.facts) is not tuple
            or not 1 <= len(self.facts) <= MAX_CONTEXT_FACTS
            or any(type(row) is not GraphEntity for row in self.entities)
            or any(type(row) is not GraphPropertyFact for row in self.facts)
            or type(self._entities_by_surface) is not _MAPPING_PROXY_TYPE
            or type(self._properties_by_subject) is not _MAPPING_PROXY_TYPE
            or type(self._facts_by_subject_property)
            is not _MAPPING_PROXY_TYPE
            or type(self.authority_claims) is not _MAPPING_PROXY_TYPE
        ):
            raise ValueError("graph relation context is not validation bound")
        expected_surfaces: dict[str, list[GraphEntity]] = {}
        for entity in self.entities:
            GraphEntity.__post_init__(entity)
            for surface in entity.surfaces:
                expected_surfaces.setdefault(
                    _surface_key(surface), []
                ).append(entity)
        expected_surface_index = {
            key: tuple(
                sorted(values, key=lambda item: item.entity_id)
            )
            for key, values in sorted(expected_surfaces.items())
        }
        if len({entity.entity_id for entity in self.entities}) != len(
            self.entities
        ):
            raise ValueError("graph relation context is not validation bound")
        grouped: dict[str, set[str]] = {}
        fact_groups: dict[
            tuple[str, str],
            list[GraphPropertyFact],
        ] = {}
        entity_ids = {entity.entity_id for entity in self.entities}
        exact_fact_rows: set[
            tuple[str, str, str, str, str]
        ] = set()
        for fact in self.facts:
            GraphPropertyFact.__post_init__(fact)
            if fact.subject_entity_id not in entity_ids:
                raise ValueError("graph fact subject is not staged")
            exact_key = (
                fact.subject_entity_id,
                fact.property_id,
                fact.object_kind,
                fact.object_value,
                fact.evidence_digest_sha256,
            )
            if exact_key in exact_fact_rows:
                raise ValueError("duplicate exact graph fact")
            exact_fact_rows.add(exact_key)
            grouped.setdefault(fact.subject_entity_id, set()).add(
                fact.property_id
            )
            fact_groups.setdefault(
                (fact.subject_entity_id, fact.property_id),
                [],
            ).append(fact)
        expected_properties = {
            key: tuple(
                sorted(values, key=lambda value: int(value[1:]))
            )
            for key, values in sorted(grouped.items())
        }
        expected_facts = {
            key: tuple(
                sorted(
                    values,
                    key=lambda row: (
                        row.object_kind,
                        row.object_value,
                        row.evidence_digest_sha256,
                    ),
                )
            )
            for key, values in sorted(fact_groups.items())
        }
        expected_tag = _context_tag(
            stage_id=self.stage_id,
            stage_digest_sha256=self.stage_digest_sha256,
            source_digest_sha256=self.source_digest_sha256,
            entities=self.entities,
            facts=self.facts,
        )
        expected_claims = {
            "capability_established": False,
            "e4_established": False,
            "e5_established": False,
            "external_authenticity_established": False,
            "independent_evaluation_established": False,
        }
        if (
            dict(self._entities_by_surface) != expected_surface_index
            or dict(self._properties_by_subject) != expected_properties
            or dict(self._facts_by_subject_property) != expected_facts
            or dict(self.authority_claims) != expected_claims
            or any(
                type(value) is not bool or value is not False
                for value in self.authority_claims.values()
            )
            or type(self._validation_seal) is not str
            or not hmac.compare_digest(
                expected_tag,
                self._validation_seal,
            )
        ):
            raise ValueError("graph relation context is not validation bound")

    def outgoing_property_ids(
        self,
        entity_id: Any,
    ) -> tuple[str, ...]:
        self.assert_validated()
        if type(entity_id) is not str:
            return ()
        return self._properties_by_subject.get(entity_id, ())

    def facts_for_subject_property(
        self,
        subject_entity_id: Any,
        property_id: Any,
    ) -> tuple[GraphPropertyFact, ...]:
        self.assert_validated()
        if (
            type(subject_entity_id) is not str
            or type(property_id) is not str
        ):
            return ()
        return self._facts_by_subject_property.get(
            (subject_entity_id, property_id),
            (),
        )


def build_graph_relation_context(
    *,
    stage_id: str,
    source_digest_sha256: str,
    entities: tuple[GraphEntity, ...],
    facts: tuple[GraphPropertyFact, ...],
) -> GraphRelationContext:
    """Build one immutable context from already staged, evidence-bound rows."""

    if (
        type(stage_id) is not str
        or _STAGE_ID.fullmatch(stage_id) is None
        or not _is_sha256(source_digest_sha256)
        or type(entities) is not tuple
        or type(facts) is not tuple
        or not entities
        or not facts
        or len(entities) > MAX_CONTEXT_ENTITIES
        or len(facts) > MAX_CONTEXT_FACTS
        or any(type(row) is not GraphEntity for row in entities)
        or any(type(row) is not GraphPropertyFact for row in facts)
    ):
        raise ValueError("graph relation context inputs are invalid")
    if len({entity.entity_id for entity in entities}) != len(entities):
        raise ValueError("duplicate graph entity id")
    canonical_entities = tuple(
        sorted(entities, key=lambda item: int(item.entity_id[1:]))
    )
    canonical_facts = tuple(
        sorted(
            facts,
            key=lambda item: (
                int(item.subject_entity_id[1:]),
                int(item.property_id[1:]),
                item.object_kind,
                item.object_value,
                item.evidence_digest_sha256,
            ),
        )
    )
    for entity in canonical_entities:
        GraphEntity.__post_init__(entity)
    for fact in canonical_facts:
        GraphPropertyFact.__post_init__(fact)
    exact_fact_rows = {
        (
            row.subject_entity_id,
            row.property_id,
            row.object_kind,
            row.object_value,
            row.evidence_digest_sha256,
        )
        for row in canonical_facts
    }
    if len(exact_fact_rows) != len(canonical_facts):
        raise ValueError("duplicate exact graph fact")
    stage_digest = canonical_digest(
        {
            "schema_version": STAGE_SCHEMA_VERSION,
            "stage_id": stage_id,
            "source_digest_sha256": source_digest_sha256,
            "entities": [row.to_dict() for row in canonical_entities],
            "facts": [row.to_dict() for row in canonical_facts],
        }
    )
    surface_groups: dict[str, list[GraphEntity]] = {}
    for entity in canonical_entities:
        for surface in entity.surfaces:
            surface_groups.setdefault(_surface_key(surface), []).append(
                entity
            )
    surface_index = MappingProxyType(
        {
            key: tuple(
                sorted(values, key=lambda item: item.entity_id)
            )
            for key, values in sorted(surface_groups.items())
        }
    )
    property_groups: dict[str, set[str]] = {}
    for fact in canonical_facts:
        property_groups.setdefault(
            fact.subject_entity_id,
            set(),
        ).add(fact.property_id)
    property_index = MappingProxyType(
        {
            key: tuple(
                sorted(values, key=lambda value: int(value[1:]))
            )
            for key, values in sorted(property_groups.items())
        }
    )
    fact_groups: dict[
        tuple[str, str],
        list[GraphPropertyFact],
    ] = {}
    for fact in canonical_facts:
        fact_groups.setdefault(
            (fact.subject_entity_id, fact.property_id),
            [],
        ).append(fact)
    fact_index = MappingProxyType(
        {
            key: tuple(
                sorted(
                    values,
                    key=lambda row: (
                        row.object_kind,
                        row.object_value,
                        row.evidence_digest_sha256,
                    ),
                )
            )
            for key, values in sorted(fact_groups.items())
        }
    )
    claims = MappingProxyType(
        {
            "capability_established": False,
            "e4_established": False,
            "e5_established": False,
            "external_authenticity_established": False,
            "independent_evaluation_established": False,
        }
    )
    seal = _context_tag(
        stage_id=stage_id,
        stage_digest_sha256=stage_digest,
        source_digest_sha256=source_digest_sha256,
        entities=canonical_entities,
        facts=canonical_facts,
    )
    return GraphRelationContext(
        stage_id=stage_id,
        stage_digest_sha256=stage_digest,
        source_digest_sha256=source_digest_sha256,
        entities=canonical_entities,
        facts=canonical_facts,
        authority_claims=claims,
        _entities_by_surface=surface_index,
        _properties_by_subject=property_index,
        _facts_by_subject_property=fact_index,
        _validation_seal=seal,
    )


@dataclass(frozen=True, slots=True)
class GraphChoice:
    key: str
    original_text: str
    normalized_value: str
    value_digest_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.key) is not str
            or not self.key
            or self.key != self.key.strip()
            or len(self.key) > 16
            or any(character.isspace() for character in self.key)
            or type(self.original_text) is not str
            or not self.original_text
            or self.original_text != self.original_text.strip()
            or len(self.original_text) > MAX_CHOICE_TEXT_CHARS
            or any(
                unicodedata.category(character) == "Cc"
                for character in self.original_text
            )
            or type(self.normalized_value) is not str
            or self.normalized_value
            != _normalize_surface(self.original_text)
            or not _is_sha256(self.value_digest_sha256)
            or self.value_digest_sha256
            != _text_digest(self.normalized_value)
        ):
            raise ValueError("graph relation choice is invalid")

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GraphRelationGoal:
    subject_entity_id: str
    subject_surface: str
    subject_span_start: int
    subject_span_end: int
    subject_span_sha256: str
    subject_evidence_digest_sha256: str
    property_id: str
    property_label: str
    matched_property_surface: str
    property_datatype: str
    relation_span_start: int
    relation_span_end: int
    relation_span_sha256: str
    linkage_method: str
    linkage_score: float
    linkage_runner_up_score: float
    linkage_margin: float
    expected_object_kind: ObjectKind
    fact_bundle_digest_sha256: str
    selected_fact_count: int
    polarity: str
    object_source: str
    selection_cardinality: str

    def __post_init__(self) -> None:
        if (
            type(self.subject_entity_id) is not str
            or _QID.fullmatch(self.subject_entity_id) is None
            or type(self.subject_surface) is not str
            or not self.subject_surface
            or self.subject_surface
            != _normalize_surface(self.subject_surface)
            or len(self.subject_surface) > MAX_ENTITY_SURFACE_CHARS
            or type(self.subject_span_start) is not int
            or type(self.subject_span_end) is not int
            or not 0
            <= self.subject_span_start
            < self.subject_span_end
            <= MAX_STEM_CHARS
            or not _is_sha256(self.subject_span_sha256)
            or not _is_sha256(self.subject_evidence_digest_sha256)
            or type(self.property_id) is not str
            or _PID.fullmatch(self.property_id) is None
            or type(self.property_label) is not str
            or not self.property_label
            or self.property_label
            != _normalize_surface(self.property_label)
            or len(self.property_label) > 512
            or type(self.matched_property_surface) is not str
            or not self.matched_property_surface
            or self.matched_property_surface
            != _normalize_surface(self.matched_property_surface)
            or len(self.matched_property_surface) > 512
            or type(self.property_datatype) is not str
            or not self.property_datatype
            or self.property_datatype
            != _normalize_surface(self.property_datatype)
            or len(self.property_datatype) > 192
            or type(self.relation_span_start) is not int
            or type(self.relation_span_end) is not int
            or not 0
            <= self.relation_span_start
            < self.relation_span_end
            <= MAX_STEM_CHARS
            or not (
                self.relation_span_end <= self.subject_span_start
                or self.subject_span_end <= self.relation_span_start
            )
            or not _is_sha256(self.relation_span_sha256)
            or type(self.linkage_method) is not str
            or self.linkage_method
            not in {
                "relation_before_subject_aux_gap",
                "relation_before_subject_nominal_bridge",
                "subject_before_relation_aux_gap",
            }
            or type(self.linkage_score) is not float
            or type(self.linkage_runner_up_score) is not float
            or type(self.linkage_margin) is not float
            or not all(
                math.isfinite(value)
                for value in (
                    self.linkage_score,
                    self.linkage_runner_up_score,
                    self.linkage_margin,
                )
            )
            or self.linkage_score < MIN_PROPERTY_SCORE
            or self.linkage_runner_up_score < 0.0
            or self.linkage_margin < MIN_SCORE_MARGIN
            or not math.isclose(
                self.linkage_margin,
                self.linkage_score - self.linkage_runner_up_score,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or type(self.expected_object_kind) is not str
            or self.expected_object_kind not in ("entity", "literal")
            or not _is_sha256(self.fact_bundle_digest_sha256)
            or type(self.selected_fact_count) is not int
            or not 1 <= self.selected_fact_count <= MAX_CONTEXT_FACTS
            or type(self.polarity) is not str
            or self.polarity != "positive"
            or type(self.object_source) is not str
            or self.object_source != "all_normalized_choices"
            or type(self.selection_cardinality) is not str
            or self.selection_cardinality
            != "exactly_one_provable_choice"
        ):
            raise ValueError("graph relation goal is invalid")

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GraphRelationCompilation:
    schema_version: str
    status: CompilationStatus
    reason: str
    compiler_rule: str
    input_digest_sha256: str
    stage_digest_sha256: str
    catalog_digest_sha256: str
    goal: GraphRelationGoal | None
    choices: tuple[GraphChoice, ...]
    required_evidence: Mapping[str, Any]
    claims: Mapping[str, bool]

    def __post_init__(self) -> None:
        expected_claims = {
            "capability_improvement_established": False,
            "e4_established": False,
            "e5_established": False,
            "independent_evaluation_established": False,
        }
        if (
            self.schema_version != SCHEMA_VERSION
            or type(self.status) is not str
            or self.status not in ("compiled", "abstain", "invalid")
            or type(self.reason) is not str
            or not self.reason
            or len(self.reason) > 192
            or self.reason != _normalize_surface(self.reason)
            or self.compiler_rule != COMPILER_RULE
            or not _is_sha256(self.input_digest_sha256)
            or not _is_sha256(self.stage_digest_sha256)
            or not _is_sha256(self.catalog_digest_sha256)
            or type(self.choices) is not tuple
            or len(self.choices) > MAX_CHOICES
            or any(type(choice) is not GraphChoice for choice in self.choices)
            or type(self.required_evidence) is not _MAPPING_PROXY_TYPE
            or type(self.claims) is not _MAPPING_PROXY_TYPE
            or dict(self.claims) != expected_claims
            or any(
                type(value) is not bool or value is not False
                for value in self.claims.values()
            )
        ):
            raise ValueError("graph relation compilation is invalid")
        for choice in self.choices:
            choice.__post_init__()
        if len({choice.key for choice in self.choices}) != len(self.choices):
            raise ValueError("graph relation compilation choices collide")
        if self.status == "compiled":
            if (
                type(self.goal) is not GraphRelationGoal
                or not 2 <= len(self.choices) <= MAX_CHOICES
                or frozenset(self.required_evidence)
                != {
                    "catalog_digest_sha256",
                    "catalog_source_artifact_kind",
                    "catalog_source_artifact_name",
                    "catalog_source_artifact_sha256",
                    "catalog_source_record_sha256",
                    "catalog_source_revision",
                    "exact_property_id_required",
                    "exact_stage_fact_required",
                    "expected_object_kind",
                    "fact_bundle_digest_sha256",
                    "original_property_id",
                    "selected_fact_count",
                    "source_revision_required",
                    "stage_digest_sha256",
                    "subject_entity_id",
                    "subject_evidence_digest_sha256",
                    "verification_membrane_required",
                }
            ):
                raise ValueError(
                    "compiled graph relation receipt is incomplete"
                )
            self.goal.__post_init__()
            evidence = dict(self.required_evidence)
            if (
                evidence["catalog_digest_sha256"]
                != self.catalog_digest_sha256
                or type(evidence["catalog_source_artifact_kind"])
                is not str
                or not evidence["catalog_source_artifact_kind"]
                or len(evidence["catalog_source_artifact_kind"]) > 192
                or type(evidence["catalog_source_artifact_name"]) is not str
                or not evidence["catalog_source_artifact_name"]
                or len(evidence["catalog_source_artifact_name"]) > 512
                or not _is_sha256(
                    evidence["catalog_source_artifact_sha256"]
                )
                or not _is_sha256(
                    evidence["catalog_source_record_sha256"]
                )
                or type(evidence["catalog_source_revision"]) is not int
                or evidence["catalog_source_revision"] <= 0
                or evidence["exact_property_id_required"] is not True
                or evidence["exact_stage_fact_required"] is not True
                or evidence["expected_object_kind"]
                != self.goal.expected_object_kind
                or type(evidence["expected_object_kind"]) is not str
                or evidence["fact_bundle_digest_sha256"]
                != self.goal.fact_bundle_digest_sha256
                or type(evidence["original_property_id"]) is not str
                or evidence["original_property_id"]
                != self.goal.property_id
                or type(evidence["selected_fact_count"]) is not int
                or evidence["selected_fact_count"]
                != self.goal.selected_fact_count
                or evidence["source_revision_required"] is not True
                or evidence["stage_digest_sha256"]
                != self.stage_digest_sha256
                or type(evidence["subject_entity_id"]) is not str
                or evidence["subject_entity_id"]
                != self.goal.subject_entity_id
                or evidence["subject_evidence_digest_sha256"]
                != self.goal.subject_evidence_digest_sha256
                or evidence["verification_membrane_required"] is not True
            ):
                raise ValueError(
                    "compiled graph relation evidence is not bound"
                )
        elif self.goal is not None or dict(self.required_evidence):
            raise ValueError(
                "noncompiled graph relation receipt carries a goal"
            )

    @property
    def compiled(self) -> bool:
        return self.status == "compiled"

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason": self.reason,
            "compiler_rule": self.compiler_rule,
            "input_digest_sha256": self.input_digest_sha256,
            "stage_digest_sha256": self.stage_digest_sha256,
            "catalog_digest_sha256": self.catalog_digest_sha256,
            "goal": None if self.goal is None else self.goal.to_dict(),
            "choices": [choice.to_dict() for choice in self.choices],
            "required_evidence": dict(self.required_evidence),
            "claims": dict(self.claims),
        }


def _snapshot_choices(
    choices: Any,
) -> tuple[tuple[GraphChoice, ...] | None, str]:
    if not isinstance(choices, Mapping):
        return None, "choices_not_mapping"
    try:
        raw_rows = tuple(islice(choices.items(), MAX_CHOICES + 1))
    except Exception:
        return None, "choices_snapshot_failed"
    if not 2 <= len(raw_rows) <= MAX_CHOICES:
        return None, "choice_count_out_of_bounds"
    rows: list[GraphChoice] = []
    seen_keys: set[str] = set()
    seen_values: set[str] = set()
    for raw_row in raw_rows:
        if type(raw_row) not in (tuple, list) or len(raw_row) != 2:
            return None, "choice_item_invalid"
        key, value = raw_row
        if (
            type(key) is not str
            or not key
            or key != key.strip()
            or len(key) > 16
            or any(character.isspace() for character in key)
            or type(value) is not str
            or not value
            or value != value.strip()
            or len(value) > MAX_CHOICE_TEXT_CHARS
        ):
            return None, "choice_out_of_bounds"
        normalized = _normalize_surface(value)
        normalized_key = normalized.casefold()
        if key in seen_keys or normalized_key in seen_values:
            return None, "duplicate_choice"
        seen_keys.add(key)
        seen_values.add(normalized_key)
        rows.append(
            GraphChoice(
                key=key,
                original_text=value,
                normalized_value=normalized,
                value_digest_sha256=_text_digest(normalized),
            )
        )
    rows.sort(key=lambda item: item.key)
    return tuple(rows), ""


def _surface_occurrences(
    stem: str,
    surface: str,
) -> tuple[tuple[int, int], ...]:
    pattern = re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(surface)}(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    return tuple((match.start(), match.end()) for match in pattern.finditer(stem))


def _resolve_subject(
    stem: str,
    context: GraphRelationContext,
) -> tuple[GraphEntity | None, str, int, int, str]:
    matched: dict[str, tuple[GraphEntity, str, int, int]] = {}
    tokens = tuple(_WORD.finditer(stem))
    for first_index, first in enumerate(tokens):
        stop = min(
            len(tokens),
            first_index + MAX_ENTITY_SURFACE_WORDS,
        )
        for last_index in range(first_index, stop):
            last = tokens[last_index]
            start, end = first.start(), last.end()
            surface = stem[start:end]
            candidates = context._entities_by_surface.get(
                _surface_key(surface),
                (),
            )
            for entity in candidates:
                if not context._properties_by_subject.get(entity.entity_id):
                    continue
                current = matched.get(entity.entity_id)
                candidate = (
                    entity,
                    _normalize_surface(surface),
                    start,
                    end,
                )
                if current is None or (
                    end - start,
                    -start,
                ) > (
                    current[3] - current[2],
                    -current[2],
                ):
                    matched[entity.entity_id] = candidate
    if not matched:
        return None, "", 0, 0, "subject_not_grounded"
    if len(matched) != 1:
        return None, "", 0, 0, "subject_ambiguous"
    entity, surface, start, end = next(iter(matched.values()))
    return entity, surface, start, end, ""


@dataclass(frozen=True, slots=True)
class _PropertyLinkage:
    entry: WikidataProperty
    surface: str
    span_start: int
    span_end: int
    method: str
    score: float
    runner_up_score: float
    margin: float


def _structural_linkage_method(
    *,
    stem: str,
    subject_start: int,
    subject_end: int,
    relation_start: int,
    relation_end: int,
) -> str:
    """Require a generic interrogative S-R-O frame around both grounded spans.

    This is deliberately a bounded structural gate, not a claim of complete
    English dependency parsing.  It blocks raw relation-word co-occurrence and
    fails closed outside generic auxiliary/nominal query frames.
    """

    if not (_INTERROGATIVE.search(stem) or stem.endswith("?")):
        return ""
    if relation_end <= subject_start:
        gap = stem[relation_end:subject_start]
        if _INVERSE_ROLE.search(gap):
            return ""
        if _SUBJECT_LINK_AUX.search(gap):
            return "relation_before_subject_aux_gap"
        if (
            _NOMINAL_BRIDGE.search(gap)
            and _SUBJECT_LINK_AUX.search(stem[:relation_start])
        ):
            return "relation_before_subject_nominal_bridge"
        return ""
    if subject_end <= relation_start:
        gap = stem[subject_end:relation_start]
        if _INVERSE_ROLE.search(gap):
            return ""
        if _SUBJECT_LINK_AUX.search(gap):
            return "subject_before_relation_aux_gap"
    return ""


def _select_property(
    *,
    stem: str,
    subject_start: int,
    subject_end: int,
    property_ids: tuple[str, ...],
    catalog: WikidataPropertyCatalogSnapshot,
) -> tuple[_PropertyLinkage | None, str]:
    scored_by_property: list[
        tuple[float, WikidataProperty, str, int, int, str]
    ] = []
    catalogued = False
    lexical_hit = False
    for property_id in property_ids:
        entry = catalog._by_pid.get(property_id)
        if entry is None:
            continue
        catalogued = True
        candidates: list[tuple[float, str, int, int, str]] = []
        for surface in entry.surfaces:
            for start, end in _surface_occurrences(stem, surface):
                if not (
                    end <= subject_start or subject_end <= start
                ):
                    continue
                lexical_hit = True
                method = _structural_linkage_method(
                    stem=stem,
                    subject_start=subject_start,
                    subject_end=subject_end,
                    relation_start=start,
                    relation_end=end,
                )
                if not method:
                    continue
                token_count = len(tokenize(surface))
                score = 2.0 + min(token_count, 100) / 1000.0
                candidates.append(
                    (score, surface, start, end, method)
                )
        if not candidates:
            continue
        candidates.sort(
            key=lambda item: (
                -item[0],
                item[2],
                item[3],
                item[1],
                item[4],
            )
        )
        if (
            len(candidates) > 1
            and candidates[0][0] == candidates[1][0]
            and (
                candidates[0][2],
                candidates[0][3],
            )
            != (
                candidates[1][2],
                candidates[1][3],
            )
        ):
            return None, "property_surface_ambiguous"
        score, surface, start, end, method = candidates[0]
        scored_by_property.append(
            (score, entry, surface, start, end, method)
        )
    if not catalogued:
        return None, "no_catalogued_outgoing_property"
    if not scored_by_property:
        return (
            None,
            (
                "property_role_not_grounded"
                if lexical_hit
                else "property_surface_not_grounded"
            ),
        )
    scored_by_property.sort(
        key=lambda item: (
            -item[0],
            int(item[1].property_id[1:]),
            item[2],
            item[3],
        )
    )
    (
        best_score,
        best_entry,
        best_surface,
        best_start,
        best_end,
        best_method,
    ) = scored_by_property[0]
    if best_score < MIN_PROPERTY_SCORE:
        return None, "property_surface_not_grounded"
    runner_up_score = (
        scored_by_property[1][0]
        if len(scored_by_property) > 1
        else 0.0
    )
    margin = best_score - runner_up_score
    if margin < MIN_SCORE_MARGIN:
        return None, "property_surface_ambiguous"
    return (
        _PropertyLinkage(
            entry=best_entry,
            surface=best_surface,
            span_start=best_start,
            span_end=best_end,
            method=best_method,
            score=float(best_score),
            runner_up_score=float(runner_up_score),
            margin=float(margin),
        ),
        "",
    )


def _expected_object_kind(datatype: str) -> ObjectKind:
    normalized = datatype.casefold()
    if normalized in {
        "wikibase-item",
        "http://wikiba.se/ontology#wikibaseitem",
    }:
        return "entity"
    return "literal"


def _fact_bundle_digest(
    facts: tuple[GraphPropertyFact, ...],
) -> str:
    return canonical_digest(
        {
            "schema_version": STAGE_SCHEMA_VERSION,
            "fact_bundle": [row.to_dict() for row in facts],
        }
    )


def _empty(
    *,
    status: CompilationStatus,
    reason: str,
    input_digest_sha256: str,
    context: GraphRelationContext,
    catalog: WikidataPropertyCatalogSnapshot,
    choices: tuple[GraphChoice, ...] = (),
) -> GraphRelationCompilation:
    return GraphRelationCompilation(
        schema_version=SCHEMA_VERSION,
        status=status,
        reason=reason,
        compiler_rule=COMPILER_RULE,
        input_digest_sha256=input_digest_sha256,
        stage_digest_sha256=context.stage_digest_sha256,
        catalog_digest_sha256=catalog.catalog_digest_sha256,
        goal=None,
        choices=choices,
        required_evidence=MappingProxyType({}),
        claims=MappingProxyType(
            {
                "capability_improvement_established": False,
                "e4_established": False,
                "e5_established": False,
                "independent_evaluation_established": False,
            }
        ),
    )


def compile_graph_relation_goal(
    stem: Any,
    choices: Any,
    *,
    context: GraphRelationContext,
    catalog: WikidataPropertyCatalogSnapshot,
) -> GraphRelationCompilation:
    """Compile one source-driven property goal, or abstain without guessing."""

    if type(context) is not GraphRelationContext:
        raise TypeError("exact GraphRelationContext required")
    if type(catalog) is not WikidataPropertyCatalogSnapshot:
        raise TypeError("exact WikidataPropertyCatalogSnapshot required")
    context.assert_validated()
    catalog.assert_validated()
    descriptor = {
        "stem": (
            stem
            if type(stem) is str
            else {"python_type": type(stem).__name__}
        ),
        "choices_type": type(choices).__name__,
        "stage_digest_sha256": context.stage_digest_sha256,
        "catalog_digest_sha256": catalog.catalog_digest_sha256,
    }
    input_digest = canonical_digest(descriptor)
    if (
        type(stem) is not str
        or not stem
        or stem != stem.strip()
        or len(stem) > MAX_STEM_CHARS
        or unicodedata.normalize("NFKC", stem) != stem
        or any(
            unicodedata.category(character) == "Cc"
            for character in stem
        )
    ):
        return _empty(
            status="invalid",
            reason="stem_out_of_bounds",
            input_digest_sha256=input_digest,
            context=context,
            catalog=catalog,
        )
    choice_rows, choice_reason = _snapshot_choices(choices)
    if choice_rows is None:
        return _empty(
            status="invalid",
            reason=choice_reason,
            input_digest_sha256=input_digest,
            context=context,
            catalog=catalog,
        )
    input_digest = canonical_digest(
        {
            "schema_version": SCHEMA_VERSION,
            "compiler_rule": COMPILER_RULE,
            "stem": stem,
            "choices": [row.to_dict() for row in choice_rows],
            "stage_digest_sha256": context.stage_digest_sha256,
            "catalog_digest_sha256": catalog.catalog_digest_sha256,
        }
    )
    subject, subject_surface, start, end, subject_reason = (
        _resolve_subject(stem, context)
    )
    if subject is None:
        return _empty(
            status="abstain",
            reason=subject_reason,
            input_digest_sha256=input_digest,
            context=context,
            catalog=catalog,
            choices=choice_rows,
        )
    relation_text = stem[:start] + " " + stem[end:]
    for pattern, reason in (
        (_NEGATION, "negation_not_supported"),
        (_TEMPORAL, "temporal_semantics_not_supported"),
        (_COMPARISON, "comparison_not_supported"),
    ):
        if pattern.search(relation_text):
            return _empty(
                status="abstain",
                reason=reason,
                input_digest_sha256=input_digest,
                context=context,
                catalog=catalog,
                choices=choice_rows,
            )
    linkage, property_reason = _select_property(
        stem=stem,
        subject_start=start,
        subject_end=end,
        property_ids=context._properties_by_subject.get(
            subject.entity_id,
            (),
        ),
        catalog=catalog,
    )
    if linkage is None:
        return _empty(
            status="abstain",
            reason=property_reason,
            input_digest_sha256=input_digest,
            context=context,
            catalog=catalog,
            choices=choice_rows,
        )
    entry = linkage.entry
    fact_bundle = context._facts_by_subject_property.get(
        (subject.entity_id, entry.property_id),
        (),
    )
    if not fact_bundle:
        return _empty(
            status="abstain",
            reason="selected_fact_bundle_missing",
            input_digest_sha256=input_digest,
            context=context,
            catalog=catalog,
            choices=choice_rows,
        )
    expected_object_kind = _expected_object_kind(entry.datatype)
    if any(
        row.object_kind != expected_object_kind
        for row in fact_bundle
    ):
        return _empty(
            status="abstain",
            reason="property_datatype_fact_kind_mismatch",
            input_digest_sha256=input_digest,
            context=context,
            catalog=catalog,
            choices=choice_rows,
        )
    fact_bundle_digest = _fact_bundle_digest(fact_bundle)
    span_text = stem[start:end]
    relation_span_text = stem[
        linkage.span_start:linkage.span_end
    ]
    goal = GraphRelationGoal(
        subject_entity_id=subject.entity_id,
        subject_surface=subject_surface,
        subject_span_start=start,
        subject_span_end=end,
        subject_span_sha256=_text_digest(span_text),
        subject_evidence_digest_sha256=(
            subject.evidence_digest_sha256
        ),
        property_id=entry.property_id,
        property_label=entry.label,
        matched_property_surface=linkage.surface,
        property_datatype=entry.datatype,
        relation_span_start=linkage.span_start,
        relation_span_end=linkage.span_end,
        relation_span_sha256=_text_digest(relation_span_text),
        linkage_method=linkage.method,
        linkage_score=linkage.score,
        linkage_runner_up_score=linkage.runner_up_score,
        linkage_margin=linkage.margin,
        expected_object_kind=expected_object_kind,
        fact_bundle_digest_sha256=fact_bundle_digest,
        selected_fact_count=len(fact_bundle),
        polarity="positive",
        object_source="all_normalized_choices",
        selection_cardinality="exactly_one_provable_choice",
    )
    required_evidence = MappingProxyType(
        {
            "catalog_digest_sha256": catalog.catalog_digest_sha256,
            "catalog_source_artifact_kind": (
                entry.evidence.source_artifact_kind
            ),
            "catalog_source_artifact_name": (
                entry.evidence.source_file_name
            ),
            "catalog_source_artifact_sha256": (
                entry.evidence.source_file_sha256
            ),
            "catalog_source_record_sha256": (
                entry.evidence.source_record_sha256
            ),
            "catalog_source_revision": (
                entry.evidence.source_revision
            ),
            "exact_property_id_required": True,
            "exact_stage_fact_required": True,
            "expected_object_kind": expected_object_kind,
            "fact_bundle_digest_sha256": fact_bundle_digest,
            "original_property_id": entry.property_id,
            "selected_fact_count": len(fact_bundle),
            "source_revision_required": True,
            "stage_digest_sha256": context.stage_digest_sha256,
            "subject_entity_id": subject.entity_id,
            "subject_evidence_digest_sha256": (
                subject.evidence_digest_sha256
            ),
            "verification_membrane_required": True,
        }
    )
    return GraphRelationCompilation(
        schema_version=SCHEMA_VERSION,
        status="compiled",
        reason="compiled_graph_conditioned_property",
        compiler_rule=COMPILER_RULE,
        input_digest_sha256=input_digest,
        stage_digest_sha256=context.stage_digest_sha256,
        catalog_digest_sha256=catalog.catalog_digest_sha256,
        goal=goal,
        choices=choice_rows,
        required_evidence=required_evidence,
        claims=MappingProxyType(
            {
                "capability_improvement_established": False,
                "e4_established": False,
                "e5_established": False,
                "independent_evaluation_established": False,
            }
        ),
    )
