"""Proof-carrying consumer for graph-conditioned relation goals.

The compiler proposes a subject and a source-owned Wikidata property.  This
module independently replays that proposal against the exact graph context and
property catalog, then emits a receipt only when exactly one unranked choice
has an exact staged proof.

This is a verification membrane, not a capability or authority claim.  It
does not accept a gold answer, rank candidates, or write to the staged graph.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata
from types import MappingProxyType
from typing import Any, Literal

from packages.cognitive_core.canonical import canonical_digest
from packages.reasoning_vm.deliberator.graph_relation_goal import (
    COMPILER_RULE as GRAPH_COMPILER_RULE,
    MAX_CHOICE_TEXT_CHARS,
    MAX_CONTEXT_FACTS,
    MAX_OBJECT_VALUE_CHARS,
    MAX_STEM_CHARS,
    SCHEMA_VERSION as GRAPH_GOAL_SCHEMA_VERSION,
    STAGE_SCHEMA_VERSION as GRAPH_CONTEXT_SCHEMA_VERSION,
    GraphChoice,
    GraphEntity,
    GraphPropertyFact,
    GraphRelationCompilation,
    GraphRelationContext,
    GraphRelationGoal,
)
from packages.reasoning_vm.deliberator.wikidata_property_catalog import (
    WikidataProperty,
    WikidataPropertyCatalogError,
    WikidataPropertyCatalogSnapshot,
)


SCHEMA_VERSION = "atanor.deliberator.graph-relation-proof.v1"
PROOF_RULE = "exact_graph_fact_choice_membrane_v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_QID = re.compile(r"Q[1-9]\d{0,11}\Z")
_PID = re.compile(r"P[1-9]\d{0,11}\Z")
_STAGE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_CATALOG_ID = re.compile(
    r"wikidata-property-catalog-[a-z0-9-]+-v[1-9]\d*\Z"
)
_MAPPING_PROXY_TYPE = type(MappingProxyType({}))

_CLAIMS = {
    "autonomous_mining_established": False,
    "capability_improvement_established": False,
    "e4_established": False,
    "e5_established": False,
    "external_authenticity_established": False,
    "independent_evaluation_established": False,
}

_RECEIPT_BODY_FIELDS = (
    "schema_version",
    "proof_rule",
    "compilation_input_digest_sha256",
    "compilation_digest_sha256",
    "stage_id",
    "stage_digest_sha256",
    "stage_source_digest_sha256",
    "catalog_id",
    "catalog_digest_sha256",
    "catalog_manifest_checksum_sha256",
    "catalog_bound_bytes",
    "catalog_source_artifact_kind",
    "catalog_source_artifact_name",
    "catalog_source_artifact_sha256",
    "catalog_source_record_sha256",
    "catalog_source_revision",
    "subject_entity_id",
    "subject_evidence_digest_sha256",
    "property_id",
    "property_datatype",
    "expected_object_kind",
    "fact_bundle_digest_sha256",
    "selected_fact_count",
    "fact_object_kind",
    "fact_object_value",
    "fact_evidence_digest_sha256",
    "choice_key",
    "choice_normalized_value",
    "choice_value_digest_sha256",
    "claims",
)

DecisionStatus = Literal["proved", "abstain"]


class GraphRelationStagingError(RuntimeError):
    """Raised when a compiler, graph, or catalog binding is inconsistent."""


def _is_sha256(value: Any) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _normalize_surface(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _surface_key(value: str) -> str:
    return _normalize_surface(value).casefold()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _claims() -> MappingProxyType:
    return MappingProxyType(dict(_CLAIMS))


def _fact_bundle_digest(
    facts: tuple[GraphPropertyFact, ...],
) -> str:
    return canonical_digest(
        {
            "schema_version": GRAPH_CONTEXT_SCHEMA_VERSION,
            "fact_bundle": [row.to_dict() for row in facts],
        }
    )


def _expected_object_kind(datatype: str) -> str:
    if datatype.casefold() in {
        "wikibase-item",
        "http://wikiba.se/ontology#wikibaseitem",
    }:
        return "entity"
    return "literal"


def _receipt_body_from_values(values: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for field_name in _RECEIPT_BODY_FIELDS:
        value = values[field_name]
        body[field_name] = (
            dict(value) if field_name == "claims" else value
        )
    return body


@dataclass(frozen=True, slots=True)
class GraphRelationProofReceipt:
    """Immutable proof receipt for one exact choice and one exact fact."""

    schema_version: str
    proof_rule: str
    compilation_input_digest_sha256: str
    compilation_digest_sha256: str
    stage_id: str
    stage_digest_sha256: str
    stage_source_digest_sha256: str
    catalog_id: str
    catalog_digest_sha256: str
    catalog_manifest_checksum_sha256: str
    catalog_bound_bytes: int
    catalog_source_artifact_kind: str
    catalog_source_artifact_name: str
    catalog_source_artifact_sha256: str
    catalog_source_record_sha256: str
    catalog_source_revision: int
    subject_entity_id: str
    subject_evidence_digest_sha256: str
    property_id: str
    property_datatype: str
    expected_object_kind: str
    fact_bundle_digest_sha256: str
    selected_fact_count: int
    fact_object_kind: str
    fact_object_value: str
    fact_evidence_digest_sha256: str
    choice_key: str
    choice_normalized_value: str
    choice_value_digest_sha256: str
    claims: MappingProxyType
    proof_digest_sha256: str

    def __post_init__(self) -> None:
        if (
            self.schema_version != SCHEMA_VERSION
            or self.proof_rule != PROOF_RULE
            or not _is_sha256(self.compilation_input_digest_sha256)
            or not _is_sha256(self.compilation_digest_sha256)
            or type(self.stage_id) is not str
            or _STAGE_ID.fullmatch(self.stage_id) is None
            or not _is_sha256(self.stage_digest_sha256)
            or not _is_sha256(self.stage_source_digest_sha256)
            or type(self.catalog_id) is not str
            or _CATALOG_ID.fullmatch(self.catalog_id) is None
            or not _is_sha256(self.catalog_digest_sha256)
            or not _is_sha256(
                self.catalog_manifest_checksum_sha256
            )
            or type(self.catalog_bound_bytes) is not int
            or self.catalog_bound_bytes <= 0
            or type(self.catalog_source_artifact_kind) is not str
            or not self.catalog_source_artifact_kind
            or len(self.catalog_source_artifact_kind) > 128
            or type(self.catalog_source_artifact_name) is not str
            or not self.catalog_source_artifact_name
            or len(self.catalog_source_artifact_name) > 512
            or not _is_sha256(
                self.catalog_source_artifact_sha256
            )
            or not _is_sha256(self.catalog_source_record_sha256)
            or type(self.catalog_source_revision) is not int
            or self.catalog_source_revision <= 0
            or type(self.subject_entity_id) is not str
            or _QID.fullmatch(self.subject_entity_id) is None
            or not _is_sha256(
                self.subject_evidence_digest_sha256
            )
            or type(self.property_id) is not str
            or _PID.fullmatch(self.property_id) is None
            or type(self.property_datatype) is not str
            or not self.property_datatype
            or len(self.property_datatype) > 128
            or self.property_datatype
            != _normalize_surface(self.property_datatype)
            or type(self.expected_object_kind) is not str
            or self.expected_object_kind not in ("entity", "literal")
            or not _is_sha256(self.fact_bundle_digest_sha256)
            or type(self.selected_fact_count) is not int
            or not 1 <= self.selected_fact_count <= MAX_CONTEXT_FACTS
            or type(self.fact_object_kind) is not str
            or self.fact_object_kind not in ("entity", "literal")
            or self.fact_object_kind != self.expected_object_kind
            or type(self.fact_object_value) is not str
            or not self.fact_object_value
            or self.fact_object_value
            != _normalize_surface(self.fact_object_value)
            or len(self.fact_object_value) > MAX_OBJECT_VALUE_CHARS
            or (
                self.fact_object_kind == "entity"
                and _QID.fullmatch(self.fact_object_value) is None
            )
            or not _is_sha256(self.fact_evidence_digest_sha256)
            or type(self.choice_key) is not str
            or not self.choice_key
            or self.choice_key != self.choice_key.strip()
            or len(self.choice_key) > 16
            or any(character.isspace() for character in self.choice_key)
            or type(self.choice_normalized_value) is not str
            or not self.choice_normalized_value
            or self.choice_normalized_value
            != _normalize_surface(self.choice_normalized_value)
            or len(self.choice_normalized_value)
            > MAX_CHOICE_TEXT_CHARS
            or not _is_sha256(self.choice_value_digest_sha256)
            or self.choice_value_digest_sha256
            != _text_digest(self.choice_normalized_value)
            or type(self.claims) is not _MAPPING_PROXY_TYPE
            or dict(self.claims) != _CLAIMS
            or any(
                type(value) is not bool or value is not False
                for value in self.claims.values()
            )
            or not _is_sha256(self.proof_digest_sha256)
            or self.proof_digest_sha256
            != canonical_digest(self.proof_body())
        ):
            raise ValueError("graph relation proof receipt is invalid")

    def proof_body(self) -> dict[str, Any]:
        values = {
            field_name: getattr(self, field_name)
            for field_name in _RECEIPT_BODY_FIELDS
        }
        return _receipt_body_from_values(values)

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            **self.proof_body(),
            "proof_digest_sha256": self.proof_digest_sha256,
        }


@dataclass(frozen=True, slots=True)
class GraphRelationProofDecision:
    """Fail-closed result from the optional proof membrane."""

    schema_version: str
    status: DecisionStatus
    reason: str
    engine_fired: bool
    choice_key: str | None
    receipt: GraphRelationProofReceipt | None
    claims: MappingProxyType

    def __post_init__(self) -> None:
        if (
            self.schema_version != SCHEMA_VERSION
            or type(self.status) is not str
            or self.status not in ("proved", "abstain")
            or type(self.reason) is not str
            or self.reason
            not in {
                "compilation_not_compiled",
                "proof_membrane_disabled",
                "no_provable_choice",
                "proof_cardinality_not_one",
                "exactly_one_provable_choice",
            }
            or type(self.engine_fired) is not bool
            or type(self.claims) is not _MAPPING_PROXY_TYPE
            or dict(self.claims) != _CLAIMS
            or any(
                type(value) is not bool or value is not False
                for value in self.claims.values()
            )
        ):
            raise ValueError("graph relation proof decision is invalid")
        if self.status == "proved":
            if (
                self.reason != "exactly_one_provable_choice"
                or self.engine_fired is not True
                or type(self.choice_key) is not str
                or type(self.receipt) is not GraphRelationProofReceipt
                or self.choice_key != self.receipt.choice_key
            ):
                raise ValueError(
                    "proved graph relation decision is incomplete"
                )
            self.receipt.__post_init__()
        elif (
            self.engine_fired is not False
            or self.choice_key is not None
            or self.receipt is not None
        ):
            raise ValueError(
                "abstaining graph relation decision carries a proof"
            )

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason": self.reason,
            "engine_fired": self.engine_fired,
            "choice_key": self.choice_key,
            "receipt": (
                None if self.receipt is None else self.receipt.to_dict()
            ),
            "claims": dict(self.claims),
        }


@dataclass(frozen=True, slots=True)
class _Replay:
    compilation_digest_sha256: str
    goal: GraphRelationGoal
    subject: GraphEntity
    property: WikidataProperty
    facts: tuple[GraphPropertyFact, ...]


@dataclass(frozen=True, slots=True)
class _Candidate:
    choice: GraphChoice
    fact: GraphPropertyFact


def _preflight(
    stem: Any,
    compilation: Any,
    context: Any,
    catalog: Any,
) -> None:
    if type(stem) is not str:
        raise TypeError("exact str stem required")
    if type(compilation) is not GraphRelationCompilation:
        raise TypeError("exact GraphRelationCompilation required")
    if type(context) is not GraphRelationContext:
        raise TypeError("exact GraphRelationContext required")
    if type(catalog) is not WikidataPropertyCatalogSnapshot:
        raise TypeError(
            "exact WikidataPropertyCatalogSnapshot required"
        )
    if (
        not stem
        or stem != stem.strip()
        or len(stem) > MAX_STEM_CHARS
        or "\x00" in stem
    ):
        raise GraphRelationStagingError("stem is outside proof bounds")
    compilation.__post_init__()
    context.assert_validated()
    catalog.assert_validated()
    if (
        compilation.stage_digest_sha256
        != context.stage_digest_sha256
        or compilation.catalog_digest_sha256
        != catalog.catalog_digest_sha256
    ):
        raise GraphRelationStagingError(
            "compiler stage or catalog digest does not replay"
        )


def _replay_compiled_contract(
    stem: str,
    compilation: GraphRelationCompilation,
    context: GraphRelationContext,
    catalog: WikidataPropertyCatalogSnapshot,
) -> _Replay:
    if not compilation.compiled:
        raise GraphRelationStagingError(
            "a compiled graph relation goal is required"
        )
    goal = compilation.goal
    if type(goal) is not GraphRelationGoal:
        raise GraphRelationStagingError("compiled goal type is invalid")
    goal.__post_init__()

    expected_input_digest = canonical_digest(
        {
            "schema_version": GRAPH_GOAL_SCHEMA_VERSION,
            "compiler_rule": GRAPH_COMPILER_RULE,
            "stem": stem,
            "choices": [
                choice.to_dict() for choice in compilation.choices
            ],
            "stage_digest_sha256": context.stage_digest_sha256,
            "catalog_digest_sha256": catalog.catalog_digest_sha256,
        }
    )
    if compilation.input_digest_sha256 != expected_input_digest:
        raise GraphRelationStagingError(
            "compiler input digest does not replay"
        )

    subject_span = stem[
        goal.subject_span_start:goal.subject_span_end
    ]
    relation_span = stem[
        goal.relation_span_start:goal.relation_span_end
    ]
    if (
        _text_digest(subject_span) != goal.subject_span_sha256
        or _normalize_surface(subject_span) != goal.subject_surface
        or _text_digest(relation_span) != goal.relation_span_sha256
        or _surface_key(relation_span)
        != _surface_key(goal.matched_property_surface)
    ):
        raise GraphRelationStagingError(
            "compiler source spans do not replay"
        )

    subjects = tuple(
        row
        for row in context.entities
        if row.entity_id == goal.subject_entity_id
    )
    if len(subjects) != 1:
        raise GraphRelationStagingError(
            "compiled subject is not uniquely staged"
        )
    subject = subjects[0]
    if (
        subject.evidence_digest_sha256
        != goal.subject_evidence_digest_sha256
        or _surface_key(goal.subject_surface)
        not in {_surface_key(value) for value in subject.surfaces}
    ):
        raise GraphRelationStagingError(
            "compiled subject evidence does not replay"
        )

    property_entry = catalog.property_by_id(goal.property_id)
    if (
        type(property_entry) is not WikidataProperty
        or property_entry.label != goal.property_label
        or property_entry.datatype != goal.property_datatype
        or goal.matched_property_surface
        not in property_entry.surfaces
        or property_entry.evidence.externally_authenticated is not False
    ):
        raise GraphRelationStagingError(
            "compiled property catalog leaf does not replay"
        )
    expected_kind = _expected_object_kind(property_entry.datatype)
    if goal.expected_object_kind != expected_kind:
        raise GraphRelationStagingError(
            "compiled property datatype does not replay"
        )

    facts = tuple(
        sorted(
            (
                row
                for row in context.facts
                if row.subject_entity_id == goal.subject_entity_id
                and row.property_id == goal.property_id
            ),
            key=lambda row: (
                row.object_kind,
                row.object_value,
                row.evidence_digest_sha256,
            ),
        )
    )
    if (
        not facts
        or len(facts) != goal.selected_fact_count
        or any(row.object_kind != expected_kind for row in facts)
        or _fact_bundle_digest(facts)
        != goal.fact_bundle_digest_sha256
    ):
        raise GraphRelationStagingError(
            "compiled fact bundle does not replay"
        )

    evidence = dict(compilation.required_evidence)
    expected_evidence = {
        "catalog_digest_sha256": catalog.catalog_digest_sha256,
        "catalog_source_artifact_kind": (
            property_entry.evidence.source_artifact_kind
        ),
        "catalog_source_artifact_name": (
            property_entry.evidence.source_file_name
        ),
        "catalog_source_artifact_sha256": (
            property_entry.evidence.source_file_sha256
        ),
        "catalog_source_record_sha256": (
            property_entry.evidence.source_record_sha256
        ),
        "catalog_source_revision": (
            property_entry.evidence.source_revision
        ),
        "exact_property_id_required": True,
        "exact_stage_fact_required": True,
        "expected_object_kind": expected_kind,
        "fact_bundle_digest_sha256": _fact_bundle_digest(facts),
        "original_property_id": property_entry.property_id,
        "selected_fact_count": len(facts),
        "source_revision_required": True,
        "stage_digest_sha256": context.stage_digest_sha256,
        "subject_entity_id": subject.entity_id,
        "subject_evidence_digest_sha256": (
            subject.evidence_digest_sha256
        ),
        "verification_membrane_required": True,
    }
    if evidence != expected_evidence:
        raise GraphRelationStagingError(
            "compiler evidence contract does not replay"
        )
    return _Replay(
        compilation_digest_sha256=canonical_digest(
            compilation.to_dict()
        ),
        goal=goal,
        subject=subject,
        property=property_entry,
        facts=facts,
    )


def _entity_surface_index(
    context: GraphRelationContext,
) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, set[str]] = {}
    for entity in context.entities:
        for surface in entity.surfaces:
            grouped.setdefault(_surface_key(surface), set()).add(
                entity.entity_id
            )
    return {
        key: tuple(sorted(entity_ids))
        for key, entity_ids in grouped.items()
    }


def _candidate_prefix(
    replay: _Replay,
    compilation: GraphRelationCompilation,
    context: GraphRelationContext,
) -> tuple[_Candidate, ...]:
    """Return at most two candidates; two is sufficient to reject."""

    entity_surfaces = _entity_surface_index(context)
    candidates: list[_Candidate] = []
    for fact in replay.facts:
        for choice in compilation.choices:
            if fact.object_kind == "literal":
                matched = (
                    choice.normalized_value == fact.object_value
                )
            else:
                entity_ids = entity_surfaces.get(
                    _surface_key(choice.normalized_value),
                    (),
                )
                matched = (
                    len(entity_ids) == 1
                    and entity_ids[0] == fact.object_value
                )
            if matched:
                candidates.append(
                    _Candidate(choice=choice, fact=fact)
                )
                if len(candidates) == 2:
                    return tuple(candidates)
    return tuple(candidates)


def _receipt_values(
    *,
    replay: _Replay,
    candidate: _Candidate,
    compilation: GraphRelationCompilation,
    context: GraphRelationContext,
    catalog: WikidataPropertyCatalogSnapshot,
) -> dict[str, Any]:
    entry = replay.property
    return {
        "schema_version": SCHEMA_VERSION,
        "proof_rule": PROOF_RULE,
        "compilation_input_digest_sha256": (
            compilation.input_digest_sha256
        ),
        "compilation_digest_sha256": (
            replay.compilation_digest_sha256
        ),
        "stage_id": context.stage_id,
        "stage_digest_sha256": context.stage_digest_sha256,
        "stage_source_digest_sha256": (
            context.source_digest_sha256
        ),
        "catalog_id": catalog.catalog_id,
        "catalog_digest_sha256": catalog.catalog_digest_sha256,
        "catalog_manifest_checksum_sha256": (
            catalog.manifest_checksum_sha256
        ),
        "catalog_bound_bytes": catalog.bound_bytes,
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
        "catalog_source_revision": entry.evidence.source_revision,
        "subject_entity_id": replay.subject.entity_id,
        "subject_evidence_digest_sha256": (
            replay.subject.evidence_digest_sha256
        ),
        "property_id": entry.property_id,
        "property_datatype": entry.datatype,
        "expected_object_kind": replay.goal.expected_object_kind,
        "fact_bundle_digest_sha256": (
            replay.goal.fact_bundle_digest_sha256
        ),
        "selected_fact_count": len(replay.facts),
        "fact_object_kind": candidate.fact.object_kind,
        "fact_object_value": candidate.fact.object_value,
        "fact_evidence_digest_sha256": (
            candidate.fact.evidence_digest_sha256
        ),
        "choice_key": candidate.choice.key,
        "choice_normalized_value": (
            candidate.choice.normalized_value
        ),
        "choice_value_digest_sha256": (
            candidate.choice.value_digest_sha256
        ),
        "claims": _claims(),
    }


def _build_receipt(
    *,
    replay: _Replay,
    candidate: _Candidate,
    compilation: GraphRelationCompilation,
    context: GraphRelationContext,
    catalog: WikidataPropertyCatalogSnapshot,
) -> GraphRelationProofReceipt:
    values = _receipt_values(
        replay=replay,
        candidate=candidate,
        compilation=compilation,
        context=context,
        catalog=catalog,
    )
    proof_digest = canonical_digest(
        _receipt_body_from_values(values)
    )
    return GraphRelationProofReceipt(
        **values,
        proof_digest_sha256=proof_digest,
    )


def _abstain(reason: str) -> GraphRelationProofDecision:
    return GraphRelationProofDecision(
        schema_version=SCHEMA_VERSION,
        status="abstain",
        reason=reason,
        engine_fired=False,
        choice_key=None,
        receipt=None,
        claims=_claims(),
    )


def consume_graph_relation_compilation(
    stem: Any,
    compilation: Any,
    *,
    context: Any,
    catalog: Any,
    enabled: Any,
) -> GraphRelationProofDecision:
    """Consume one goal without ranking, guessing, or using a gold answer."""

    if type(enabled) is not bool:
        raise TypeError("exact bool enabled flag required")
    _preflight(stem, compilation, context, catalog)
    if not compilation.compiled:
        return _abstain("compilation_not_compiled")
    replay = _replay_compiled_contract(
        stem,
        compilation,
        context,
        catalog,
    )
    if enabled is False:
        return _abstain("proof_membrane_disabled")
    candidates = _candidate_prefix(replay, compilation, context)
    if not candidates:
        return _abstain("no_provable_choice")
    if len(candidates) != 1:
        return _abstain("proof_cardinality_not_one")
    receipt = _build_receipt(
        replay=replay,
        candidate=candidates[0],
        compilation=compilation,
        context=context,
        catalog=catalog,
    )
    return GraphRelationProofDecision(
        schema_version=SCHEMA_VERSION,
        status="proved",
        reason="exactly_one_provable_choice",
        engine_fired=True,
        choice_key=receipt.choice_key,
        receipt=receipt,
        claims=_claims(),
    )


def _verification_candidate(
    replay: _Replay,
    compilation: GraphRelationCompilation,
    context: GraphRelationContext,
) -> _Candidate | None:
    """Independently replay exact candidate cardinality."""

    surface_targets: dict[str, set[str]] = {}
    for entity in context.entities:
        for surface in entity.surfaces:
            surface_targets.setdefault(
                _surface_key(surface),
                set(),
            ).add(entity.entity_id)

    found: _Candidate | None = None
    found_count = 0
    for fact in replay.facts:
        for choice in compilation.choices:
            if fact.object_kind == "literal":
                matches = (
                    choice.normalized_value == fact.object_value
                )
            else:
                targets = surface_targets.get(
                    _surface_key(choice.normalized_value),
                    set(),
                )
                matches = (
                    len(targets) == 1
                    and fact.object_value in targets
                )
            if not matches:
                continue
            found_count += 1
            if found_count > 1:
                return None
            found = _Candidate(choice=choice, fact=fact)
    return found if found_count == 1 else None


def verify_graph_relation_proof_receipt(
    receipt: Any,
    stem: Any,
    compilation: Any,
    *,
    context: Any,
    catalog: Any,
) -> bool:
    """Independently replay every receipt leaf against source snapshots."""

    if type(receipt) is not GraphRelationProofReceipt:
        raise TypeError(
            "exact GraphRelationProofReceipt receipt required"
        )
    if type(stem) is not str:
        raise TypeError("exact str stem required")
    if type(compilation) is not GraphRelationCompilation:
        raise TypeError("exact GraphRelationCompilation required")
    if type(context) is not GraphRelationContext:
        raise TypeError("exact GraphRelationContext required")
    if type(catalog) is not WikidataPropertyCatalogSnapshot:
        raise TypeError(
            "exact WikidataPropertyCatalogSnapshot required"
        )
    try:
        receipt.__post_init__()
        _preflight(stem, compilation, context, catalog)
        replay = _replay_compiled_contract(
            stem,
            compilation,
            context,
            catalog,
        )
        candidate = _verification_candidate(
            replay,
            compilation,
            context,
        )
        if candidate is None:
            return False
        expected = _build_receipt(
            replay=replay,
            candidate=candidate,
            compilation=compilation,
            context=context,
            catalog=catalog,
        )
        return receipt.to_dict() == expected.to_dict()
    except (
        GraphRelationStagingError,
        TypeError,
        ValueError,
        WikidataPropertyCatalogError,
    ):
        return False
