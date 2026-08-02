"""Proof membrane for generic internal-predicate compilations.

The compiler proposes an internal predicate and a complete staged fact bundle.
This module independently replays the compilation, dependency-role receipt,
context, predicate linkage, and fact bundle.  It fires only when the Cartesian
product of exact staged facts and normalized choices contains one proof.

No gold answer, ranking, fallback lookup, network access, or state mutation is
part of this module.  Source QID/PID values, when present on an S1 fact, remain
separate provenance and never become the selected predicate identity.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Literal
import unicodedata

from packages.cognitive_core.canonical import FrozenMap, canonical_digest
from packages.reasoning_vm.deliberator.generic_predicate_goal import (
    GOAL_SCHEMA_VERSION,
    MAX_CHOICE_KEY_CHARS,
    MAX_CHOICE_TEXT_CHARS,
    MAX_STEM_CHARS,
    GenericPredicateChoice,
    GenericPredicateCompilation,
    GenericPredicateGoal,
    PredicateTokenLinkage,
    generic_predicate_fact_bundle_digest,
    verify_generic_predicate_compilation,
)
from packages.reasoning_vm.deliberator.generic_predicate_socket import (
    MAX_FACTS_PER_STAGE,
    MAX_STAGES,
    PREDICATE_NAMESPACE,
    QID_PID_RECORD_FORMAT,
    BoundPredicateStage,
    GenericPredicateContext,
    GenericPredicateFact,
    InternalPredicateRef,
)
from packages.reasoning_vm.deliberator.relation_role_extractor import (
    RelationRole,
    RelationRoleReceipt,
)


SCHEMA_VERSION = "atanor.deliberator.generic-predicate-proof.v1"
PROOF_RULE = "exact_generic_fact_choice_membrane_v1"

DecisionStatus = Literal["proved", "abstain"]
SourceBindingKind = Literal["none", "qid_pid_sidecar"]

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_QID = re.compile(r"Q[1-9]\d{0,19}\Z")
_PID = re.compile(r"P[1-9]\d{0,9}\Z")
_STAGE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_CONTENT_PARTS_OF_SPEECH = frozenset(
    {
        "ADJ",
        "ADP",
        "ADV",
        "NOUN",
        "NUM",
        "PART",
        "PROPN",
        "SYM",
        "VERB",
    }
)
_SUBSTANTIVE_PARTS_OF_SPEECH = frozenset(
    {
        "ADJ",
        "ADV",
        "NOUN",
        "NUM",
        "PROPN",
        "SYM",
        "VERB",
    }
)

_CLAIMS = FrozenMap(
    {
        "answer_authority_established": False,
        "capability_improvement_established": False,
        "e4_established": False,
        "e5_established": False,
        "external_authenticity_established": False,
        "independent_evaluation_established": False,
        "wikidata_pid_binding_established": False,
    }
)
_DECISION_REASONS = frozenset(
    (
        "compilation_not_compiled",
        "exactly_one_provable_choice",
        "no_provable_choice",
        "proof_cardinality_not_one",
        "proof_membrane_disabled",
    )
)


class GenericPredicateStagingError(RuntimeError):
    """A compilation or source binding does not replay exactly."""


def _is_sha256(value: Any) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _normalize_surface(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _surface_key(value: str) -> str:
    # NFKC/whitespace normalization is structural; case remains evidence.
    return _normalize_surface(value)


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _tokens(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.replace("_", " ").replace("-", " ").casefold()
    return tuple(match.group(0) for match in _WORD.finditer(normalized))


def _content_role_tokens(
    role: RelationRole,
    *,
    lemmas: bool,
    trim_subject_preposition: bool,
) -> tuple[str, ...]:
    if lemmas:
        units = role.lemmas
    else:
        units = tuple(role.text.split())
        if len(units) != len(role.parts_of_speech):
            return ()
    selected: list[str] = []
    selected_parts: list[str] = []
    for unit, part_of_speech in zip(units, role.parts_of_speech):
        if part_of_speech not in _CONTENT_PARTS_OF_SPEECH:
            continue
        unit_tokens = _tokens(unit)
        if not unit_tokens:
            continue
        selected.extend(unit_tokens)
        selected_parts.extend((part_of_speech,) * len(unit_tokens))
    if (
        trim_subject_preposition
        and selected_parts
        and selected_parts[-1] == "ADP"
    ):
        selected.pop()
        selected_parts.pop()
    if not any(
        part in _SUBSTANTIVE_PARTS_OF_SPEECH
        for part in selected_parts
    ):
        return ()
    return tuple(selected)


def _choice_items(
    choices: tuple[GenericPredicateChoice, ...],
) -> list[list[str]]:
    return [[choice.key, choice.original_text] for choice in choices]


def _linkage_evidence(
    receipt: RelationRoleReceipt,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if (
        receipt.subject is None
        or receipt.relation is None
        or receipt.object is None
    ):
        raise GenericPredicateStagingError(
            "role receipt has no replayable semantic roles"
        )
    trim_relation_preposition = any(
        dependency in {"nmod", "obl", "pobj"}
        for dependency in receipt.subject.dependencies
    )
    return (
        (
            "relation_raw",
            _content_role_tokens(
                receipt.relation,
                lemmas=False,
                trim_subject_preposition=trim_relation_preposition,
            ),
        ),
        (
            "relation_lemma",
            _content_role_tokens(
                receipt.relation,
                lemmas=True,
                trim_subject_preposition=trim_relation_preposition,
            ),
        ),
        (
            "wh_object_raw",
            _content_role_tokens(
                receipt.object,
                lemmas=False,
                trim_subject_preposition=False,
            ),
        ),
        (
            "wh_object_lemma",
            _content_role_tokens(
                receipt.object,
                lemmas=True,
                trim_subject_preposition=False,
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class _Replay:
    compilation_digest_sha256: str
    goal: GenericPredicateGoal
    facts: tuple[GenericPredicateFact, ...]


@dataclass(frozen=True, slots=True)
class _Candidate:
    choice: GenericPredicateChoice
    fact: GenericPredicateFact
    binding: BoundPredicateStage


def _proof_body(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": values["schema_version"],
        "proof_rule": values["proof_rule"],
        "compilation_input_digest_sha256": (
            values["compilation_input_digest_sha256"]
        ),
        "compilation_choices_digest_sha256": (
            values["compilation_choices_digest_sha256"]
        ),
        "compilation_digest_sha256": values["compilation_digest_sha256"],
        "role_receipt_digest_sha256": (
            values["role_receipt_digest_sha256"]
        ),
        "context_digest_sha256": values["context_digest_sha256"],
        "subject": values["subject"],
        "predicate_name": values["predicate_name"],
        "predicate_namespace": values["predicate_namespace"],
        "predicate_canonical_id": values["predicate_canonical_id"],
        "predicate_wikidata_property_id": (
            values["predicate_wikidata_property_id"]
        ),
        "linkage_source": values["linkage_source"],
        "linkage_predicate_tokens": list(
            values["linkage_predicate_tokens"]
        ),
        "linkage_evidence_tokens": list(
            values["linkage_evidence_tokens"]
        ),
        "linkage_match_start": values["linkage_match_start"],
        "linkage_match_end": values["linkage_match_end"],
        "fact_bundle_digest_sha256": values["fact_bundle_digest_sha256"],
        "selected_fact_count": values["selected_fact_count"],
        "stage_id": values["stage_id"],
        "stage_role": values["stage_role"],
        "stage_digest_sha256": values["stage_digest_sha256"],
        "stage_source_digest_sha256": (
            values["stage_source_digest_sha256"]
        ),
        "stage_artifact_identity_digest_sha256": (
            values["stage_artifact_identity_digest_sha256"]
        ),
        "stage_row_count": values["stage_row_count"],
        "stage_index_generation": values["stage_index_generation"],
        "stage_qid_pid_sidecar_digest_sha256": (
            values["stage_qid_pid_sidecar_digest_sha256"]
        ),
        "stage_qid_pid_sidecar_records": (
            values["stage_qid_pid_sidecar_records"]
        ),
        "stage_qid_pid_sidecar_record_format": (
            values["stage_qid_pid_sidecar_record_format"]
        ),
        "fact_digest_sha256": values["fact_digest_sha256"],
        "fact_row_index": values["fact_row_index"],
        "fact_object_kind": values["fact_object_kind"],
        "fact_object_value": values["fact_object_value"],
        "fact_source_name": values["fact_source_name"],
        "fact_source_url": values["fact_source_url"],
        "fact_source_registry_digest_sha256": (
            values["fact_source_registry_digest_sha256"]
        ),
        "fact_source_record_digest_sha256": (
            values["fact_source_record_digest_sha256"]
        ),
        "source_binding_kind": values["source_binding_kind"],
        "source_subject_entity_id": values["source_subject_entity_id"],
        "source_property_id": values["source_property_id"],
        "source_qid_pid_sidecar_digest_sha256": (
            values["source_qid_pid_sidecar_digest_sha256"]
        ),
        "choice_key": values["choice_key"],
        "choice_normalized_value": values["choice_normalized_value"],
        "choice_value_digest_sha256": (
            values["choice_value_digest_sha256"]
        ),
        "claims": values["claims"].to_dict(),
    }


@dataclass(frozen=True, slots=True)
class GenericPredicateProofReceipt:
    """Immutable proof of one exact fact and one exact choice."""

    schema_version: str
    proof_rule: str
    compilation_input_digest_sha256: str
    compilation_choices_digest_sha256: str
    compilation_digest_sha256: str
    role_receipt_digest_sha256: str
    context_digest_sha256: str
    subject: str
    predicate_name: str
    predicate_namespace: str
    predicate_canonical_id: str
    predicate_wikidata_property_id: None
    linkage_source: str
    linkage_predicate_tokens: tuple[str, ...]
    linkage_evidence_tokens: tuple[str, ...]
    linkage_match_start: int
    linkage_match_end: int
    fact_bundle_digest_sha256: str
    selected_fact_count: int
    stage_id: str
    stage_role: str
    stage_digest_sha256: str
    stage_source_digest_sha256: str
    stage_artifact_identity_digest_sha256: str
    stage_row_count: int
    stage_index_generation: str
    stage_qid_pid_sidecar_digest_sha256: str | None
    stage_qid_pid_sidecar_records: int | None
    stage_qid_pid_sidecar_record_format: str | None
    fact_digest_sha256: str
    fact_row_index: int
    fact_object_kind: str
    fact_object_value: str
    fact_source_name: str
    fact_source_url: str
    fact_source_registry_digest_sha256: str
    fact_source_record_digest_sha256: str
    source_binding_kind: SourceBindingKind
    source_subject_entity_id: str | None
    source_property_id: str | None
    source_qid_pid_sidecar_digest_sha256: str | None
    choice_key: str
    choice_normalized_value: str
    choice_value_digest_sha256: str
    claims: FrozenMap
    proof_digest_sha256: str

    def __post_init__(self) -> None:
        if (
            self.schema_version != SCHEMA_VERSION
            or self.proof_rule != PROOF_RULE
            or not all(
                _is_sha256(value)
                for value in (
                    self.compilation_input_digest_sha256,
                    self.compilation_choices_digest_sha256,
                    self.compilation_digest_sha256,
                    self.role_receipt_digest_sha256,
                    self.context_digest_sha256,
                    self.fact_bundle_digest_sha256,
                    self.stage_digest_sha256,
                    self.stage_source_digest_sha256,
                    self.stage_artifact_identity_digest_sha256,
                    self.fact_digest_sha256,
                    self.fact_source_registry_digest_sha256,
                    self.fact_source_record_digest_sha256,
                    self.choice_value_digest_sha256,
                    self.proof_digest_sha256,
                )
            )
            or type(self.subject) is not str
            or not self.subject
            or self.subject != self.subject.strip()
            or len(self.subject) > MAX_STEM_CHARS
            or type(self.predicate_name) is not str
            or not self.predicate_name
            or self.predicate_namespace != PREDICATE_NAMESPACE
            or self.predicate_canonical_id
            != f"stage:{self.predicate_name}"
            or self.predicate_wikidata_property_id is not None
            or self.linkage_source
            not in (
                "relation_raw",
                "relation_lemma",
                "wh_object_raw",
                "wh_object_lemma",
            )
            or type(self.linkage_predicate_tokens) is not tuple
            or not self.linkage_predicate_tokens
            or type(self.linkage_evidence_tokens) is not tuple
            or not self.linkage_evidence_tokens
            or any(
                type(token) is not str
                or not token
                or _tokens(token) != (token,)
                for token in (
                    *self.linkage_predicate_tokens,
                    *self.linkage_evidence_tokens,
                )
            )
            or type(self.linkage_match_start) is not int
            or type(self.linkage_match_end) is not int
            or not 0
            <= self.linkage_match_start
            < self.linkage_match_end
            <= len(self.linkage_evidence_tokens)
            or self.linkage_evidence_tokens[
                self.linkage_match_start : self.linkage_match_end
            ]
            != self.linkage_predicate_tokens
            or self.linkage_predicate_tokens != _tokens(self.predicate_name)
            or type(self.selected_fact_count) is not int
            or not 1
            <= self.selected_fact_count
            <= MAX_FACTS_PER_STAGE * MAX_STAGES
            or type(self.stage_id) is not str
            or _STAGE_ID.fullmatch(self.stage_id) is None
            or self.stage_role not in ("entity", "literal", "generic")
            or type(self.stage_row_count) is not int
            or self.stage_row_count <= 0
            or type(self.stage_index_generation) is not str
            or not self.stage_index_generation
            or type(self.fact_row_index) is not int
            or not 0 <= self.fact_row_index < self.stage_row_count
            or self.fact_object_kind not in ("entity", "literal", "unknown")
            or self.fact_object_kind
            != {
                "entity": "entity",
                "literal": "literal",
                "generic": "unknown",
            }[self.stage_role]
            or type(self.fact_object_value) is not str
            or not self.fact_object_value
            or len(self.fact_object_value) > MAX_CHOICE_TEXT_CHARS
            or type(self.fact_source_name) is not str
            or not self.fact_source_name
            or type(self.fact_source_url) is not str
            or self.fact_source_registry_digest_sha256
            != self.stage_source_digest_sha256
            or self.source_binding_kind not in ("none", "qid_pid_sidecar")
            or type(self.choice_key) is not str
            or not self.choice_key
            or len(self.choice_key) > MAX_CHOICE_KEY_CHARS
            or self.choice_key != self.choice_key.strip()
            or any(character.isspace() for character in self.choice_key)
            or type(self.choice_normalized_value) is not str
            or not self.choice_normalized_value
            or self.choice_normalized_value
            != _normalize_surface(self.choice_normalized_value)
            or len(self.choice_normalized_value) > MAX_CHOICE_TEXT_CHARS
            or self.choice_value_digest_sha256
            != _text_digest(self.choice_normalized_value)
            or _surface_key(self.choice_normalized_value)
            != _surface_key(self.fact_object_value)
            or type(self.claims) is not FrozenMap
            or self.claims != _CLAIMS
            or any(value is not False for value in self.claims.values())
        ):
            raise ValueError("generic predicate proof receipt is invalid")
        stage_sidecar = (
            self.stage_qid_pid_sidecar_digest_sha256,
            self.stage_qid_pid_sidecar_records,
            self.stage_qid_pid_sidecar_record_format,
        )
        source_binding = (
            self.source_subject_entity_id,
            self.source_property_id,
            self.source_qid_pid_sidecar_digest_sha256,
        )
        if (self.stage_role == "literal") != (
            self.source_binding_kind == "qid_pid_sidecar"
        ):
            raise ValueError(
                "stage role and source provenance kind do not agree"
            )
        if self.source_binding_kind == "none":
            if any(value is not None for value in (*stage_sidecar, *source_binding)):
                raise ValueError(
                    "unbound source provenance carries QID/PID evidence"
                )
        elif (
            self.stage_role != "literal"
            or not _is_sha256(self.stage_qid_pid_sidecar_digest_sha256)
            or type(self.stage_qid_pid_sidecar_records) is not int
            or self.stage_qid_pid_sidecar_records != self.stage_row_count
            or self.stage_qid_pid_sidecar_record_format
            != QID_PID_RECORD_FORMAT
            or type(self.source_subject_entity_id) is not str
            or _QID.fullmatch(self.source_subject_entity_id) is None
            or type(self.source_property_id) is not str
            or _PID.fullmatch(self.source_property_id) is None
            or self.source_qid_pid_sidecar_digest_sha256
            != self.stage_qid_pid_sidecar_digest_sha256
        ):
            raise ValueError("S1 source QID/PID evidence is invalid")
        if self.proof_digest_sha256 != canonical_digest(self.proof_body()):
            raise ValueError("generic predicate proof digest is invalid")

    def proof_body(self) -> dict[str, Any]:
        values = {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
            if field_name != "proof_digest_sha256"
        }
        return _proof_body(values)

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            **self.proof_body(),
            "proof_digest_sha256": self.proof_digest_sha256,
        }


@dataclass(frozen=True, slots=True)
class GenericPredicateProofDecision:
    """Fail-closed decision from the optional proof membrane."""

    schema_version: str
    status: DecisionStatus
    reason: str
    engine_fired: bool
    choice_key: str | None
    receipt: GenericPredicateProofReceipt | None
    claims: FrozenMap

    def __post_init__(self) -> None:
        if (
            self.schema_version != SCHEMA_VERSION
            or self.status not in ("proved", "abstain")
            or self.reason not in _DECISION_REASONS
            or type(self.engine_fired) is not bool
            or type(self.claims) is not FrozenMap
            or self.claims != _CLAIMS
            or any(value is not False for value in self.claims.values())
        ):
            raise ValueError("generic predicate proof decision is invalid")
        if self.status == "proved":
            if (
                self.reason != "exactly_one_provable_choice"
                or self.engine_fired is not True
                or type(self.choice_key) is not str
                or type(self.receipt) is not GenericPredicateProofReceipt
                or self.choice_key != self.receipt.choice_key
            ):
                raise ValueError(
                    "proved generic predicate decision is incomplete"
                )
            self.receipt.__post_init__()
        elif (
            self.engine_fired is not False
            or self.choice_key is not None
            or self.receipt is not None
        ):
            raise ValueError(
                "abstaining generic predicate decision carries a proof"
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
                self.receipt.to_dict() if self.receipt is not None else None
            ),
            "claims": self.claims.to_dict(),
        }


def _preflight(
    stem: Any,
    compilation: Any,
    role_receipt: Any,
    context: Any,
) -> None:
    if type(stem) is not str:
        raise TypeError("exact str stem required")
    if type(compilation) is not GenericPredicateCompilation:
        raise TypeError("exact GenericPredicateCompilation required")
    if type(role_receipt) is not RelationRoleReceipt:
        raise TypeError("exact RelationRoleReceipt required")
    if type(context) is not GenericPredicateContext:
        raise TypeError("exact GenericPredicateContext required")
    if (
        not stem
        or stem != stem.strip()
        or len(stem) > MAX_STEM_CHARS
        or unicodedata.normalize("NFKC", stem) != stem
        or _CONTROL.search(stem) is not None
    ):
        raise GenericPredicateStagingError("stem is outside proof bounds")
    try:
        compilation.__post_init__()
        role_receipt.__post_init__()
        context.assert_validated()
    except (TypeError, ValueError) as error:
        raise GenericPredicateStagingError(
            "compiler, role, or context validation failed"
        ) from error


def _replay_linkage(
    role_receipt: RelationRoleReceipt,
    context: GenericPredicateContext,
    goal: GenericPredicateGoal,
) -> None:
    matches: list[tuple[InternalPredicateRef, PredicateTokenLinkage]] = []
    evidence = _linkage_evidence(role_receipt)
    for predicate in context.predicate_vocabulary:
        predicate_tokens = _tokens(predicate.name)
        if not predicate_tokens:
            continue
        selected: PredicateTokenLinkage | None = None
        for source, evidence_tokens in evidence:
            if not evidence_tokens or evidence_tokens != predicate_tokens:
                continue
            selected = PredicateTokenLinkage(
                source=source,
                predicate_tokens=predicate_tokens,
                evidence_tokens=evidence_tokens,
                match_start=0,
                match_end=len(predicate_tokens),
            )
            break
        if selected is not None:
            matches.append((predicate, selected))
    if (
        len(matches) != 1
        or matches[0][0] != goal.predicate
        or matches[0][1] != goal.linkage
    ):
        raise GenericPredicateStagingError(
            "compiled predicate linkage does not replay"
        )


def _replay_compiled_contract(
    stem: str,
    compilation: GenericPredicateCompilation,
    role_receipt: RelationRoleReceipt,
    context: GenericPredicateContext,
) -> _Replay:
    if not compilation.compiled:
        raise GenericPredicateStagingError(
            "a compiled generic predicate goal is required"
        )
    if not verify_generic_predicate_compilation(
        stem,
        compilation,
        role_receipt=role_receipt,
        context=context,
    ):
        raise GenericPredicateStagingError(
            "compiled proposal does not replay through its compiler"
        )
    goal = compilation.goal
    if type(goal) is not GenericPredicateGoal:
        raise GenericPredicateStagingError("compiled goal type is invalid")
    try:
        goal.__post_init__()
    except (TypeError, ValueError) as error:
        raise GenericPredicateStagingError(
            "compiled goal validation failed"
        ) from error
    expected_choices_digest = canonical_digest(
        _choice_items(compilation.choices)
    )
    expected_input_digest = canonical_digest(
        {
            "stem": stem,
            "choices_digest_sha256": expected_choices_digest,
        }
    )
    if (
        compilation.choices_digest_sha256 != expected_choices_digest
        or compilation.input_digest_sha256 != expected_input_digest
        or role_receipt.input_digest_sha256 != _text_digest(stem)
        or compilation.role_receipt_digest_sha256
        != role_receipt.receipt_digest_sha256
        or goal.role_receipt_digest_sha256
        != role_receipt.receipt_digest_sha256
        or compilation.context_digest_sha256
        != context.context_digest_sha256
        or goal.context_digest_sha256 != context.context_digest_sha256
    ):
        raise GenericPredicateStagingError(
            "compiler input, role, or context digest does not replay"
        )
    if (
        not role_receipt.safe
        or role_receipt.direction != "forward"
        or role_receipt.polarity != "positive"
        or role_receipt.subject is None
        or role_receipt.relation is None
        or role_receipt.object is None
        or not any(
            cue.kind == "query_object"
            for cue in role_receipt.direction_evidence
        )
        or goal.subject != role_receipt.subject.text
        or context.subject != goal.subject
        or context.status != "ready"
        or not context.complete
    ):
        raise GenericPredicateStagingError(
            "compiled semantic role or context does not replay"
        )
    _validate_context_fact_bindings(context)
    if (
        goal.schema_version != GOAL_SCHEMA_VERSION
        or goal.predicate.namespace != PREDICATE_NAMESPACE
        or goal.predicate.wikidata_property_id is not None
        or sum(
            predicate == goal.predicate
            for predicate in context.predicate_vocabulary
        )
        != 1
    ):
        raise GenericPredicateStagingError(
            "compiled internal predicate does not replay"
        )
    _replay_linkage(role_receipt, context, goal)
    facts = context.facts_for_subject(goal.subject, goal.predicate)
    if (
        not facts
        or facts != goal.facts
        or generic_predicate_fact_bundle_digest(
            goal.subject,
            goal.predicate,
            facts,
        )
        != goal.fact_bundle_digest_sha256
    ):
        raise GenericPredicateStagingError(
            "compiled fact bundle does not replay"
        )
    return _Replay(
        compilation_digest_sha256=canonical_digest(
            compilation.to_dict()
        ),
        goal=goal,
        facts=facts,
    )


def _binding_for_fact(
    context: GenericPredicateContext,
    fact: GenericPredicateFact,
) -> BoundPredicateStage:
    bindings = tuple(
        binding
        for binding in context.stage_bindings
        if binding.stage_id == fact.stage_id
    )
    if len(bindings) != 1:
        raise GenericPredicateStagingError(
            "fact stage binding is not unique"
        )
    return bindings[0]


def _validate_context_fact_bindings(
    context: GenericPredicateContext,
) -> None:
    """Replay socket invariants omitted by the detached context schema."""

    expected_object_kind = {
        "entity": "entity",
        "literal": "literal",
        "generic": "unknown",
    }
    seen_rows: set[tuple[str, int]] = set()
    facts_per_stage: dict[str, int] = {}
    for fact in context.facts:
        binding = _binding_for_fact(context, fact)
        row_key = (binding.stage_id, fact.row_index)
        facts_per_stage[binding.stage_id] = (
            facts_per_stage.get(binding.stage_id, 0) + 1
        )
        stage_has_sidecar = (
            binding.qid_pid_sidecar_digest_sha256 is not None
        )
        fact_source_binding = (
            fact.source_subject_entity_id,
            fact.source_property_id,
            fact.source_qid_pid_sidecar_digest_sha256,
        )
        if (
            row_key in seen_rows
            or facts_per_stage[binding.stage_id]
            > context.max_facts_per_stage
            or fact.stage_role != binding.role
            or fact.object_kind != expected_object_kind[binding.role]
            or fact.stage_digest_sha256
            != binding.stage_digest_sha256
            or fact.source_registry_digest_sha256
            != binding.source_digest_sha256
            or not 0 <= fact.row_index < binding.row_count
            or (binding.role == "literal") != stage_has_sidecar
            or (
                binding.role == "literal"
                and (
                    any(value is None for value in fact_source_binding)
                    or fact.source_qid_pid_sidecar_digest_sha256
                    != binding.qid_pid_sidecar_digest_sha256
                )
            )
            or (
                binding.role != "literal"
                and any(
                    value is not None for value in fact_source_binding
                )
            )
        ):
            raise GenericPredicateStagingError(
                "context fact does not replay its exact stage binding"
            )
        seen_rows.add(row_key)


def _matches(
    fact: GenericPredicateFact,
    choice: GenericPredicateChoice,
) -> bool:
    return _surface_key(fact.object_value) == _surface_key(
        choice.normalized_value
    )


def _candidate_prefix(
    replay: _Replay,
    compilation: GenericPredicateCompilation,
    context: GenericPredicateContext,
) -> tuple[_Candidate, ...]:
    candidates: list[_Candidate] = []
    for fact in replay.facts:
        for choice in compilation.choices:
            if not _matches(fact, choice):
                continue
            candidates.append(
                _Candidate(
                    choice=choice,
                    fact=fact,
                    binding=_binding_for_fact(context, fact),
                )
            )
            if len(candidates) == 2:
                return tuple(candidates)
    return tuple(candidates)


def _receipt_values(
    *,
    replay: _Replay,
    candidate: _Candidate,
    compilation: GenericPredicateCompilation,
    role_receipt: RelationRoleReceipt,
    context: GenericPredicateContext,
) -> dict[str, Any]:
    goal = replay.goal
    fact = candidate.fact
    binding = candidate.binding
    source_kind: SourceBindingKind = (
        "qid_pid_sidecar"
        if fact.source_qid_pid_sidecar_digest_sha256 is not None
        else "none"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "proof_rule": PROOF_RULE,
        "compilation_input_digest_sha256": (
            compilation.input_digest_sha256
        ),
        "compilation_choices_digest_sha256": (
            compilation.choices_digest_sha256
        ),
        "compilation_digest_sha256": (
            replay.compilation_digest_sha256
        ),
        "role_receipt_digest_sha256": (
            role_receipt.receipt_digest_sha256
        ),
        "context_digest_sha256": context.context_digest_sha256,
        "subject": goal.subject,
        "predicate_name": goal.predicate.name,
        "predicate_namespace": goal.predicate.namespace,
        "predicate_canonical_id": goal.predicate.canonical_id,
        "predicate_wikidata_property_id": (
            goal.predicate.wikidata_property_id
        ),
        "linkage_source": goal.linkage.source,
        "linkage_predicate_tokens": goal.linkage.predicate_tokens,
        "linkage_evidence_tokens": goal.linkage.evidence_tokens,
        "linkage_match_start": goal.linkage.match_start,
        "linkage_match_end": goal.linkage.match_end,
        "fact_bundle_digest_sha256": (
            goal.fact_bundle_digest_sha256
        ),
        "selected_fact_count": len(replay.facts),
        "stage_id": binding.stage_id,
        "stage_role": binding.role,
        "stage_digest_sha256": binding.stage_digest_sha256,
        "stage_source_digest_sha256": binding.source_digest_sha256,
        "stage_artifact_identity_digest_sha256": (
            binding.artifact_identity_digest_sha256
        ),
        "stage_row_count": binding.row_count,
        "stage_index_generation": binding.index_generation,
        "stage_qid_pid_sidecar_digest_sha256": (
            binding.qid_pid_sidecar_digest_sha256
        ),
        "stage_qid_pid_sidecar_records": (
            binding.qid_pid_sidecar_records
        ),
        "stage_qid_pid_sidecar_record_format": (
            binding.qid_pid_sidecar_record_format
        ),
        "fact_digest_sha256": fact.fact_digest_sha256,
        "fact_row_index": fact.row_index,
        "fact_object_kind": fact.object_kind,
        "fact_object_value": fact.object_value,
        "fact_source_name": fact.source_name,
        "fact_source_url": fact.source_url,
        "fact_source_registry_digest_sha256": (
            fact.source_registry_digest_sha256
        ),
        "fact_source_record_digest_sha256": (
            fact.source_record_digest_sha256
        ),
        "source_binding_kind": source_kind,
        "source_subject_entity_id": fact.source_subject_entity_id,
        "source_property_id": fact.source_property_id,
        "source_qid_pid_sidecar_digest_sha256": (
            fact.source_qid_pid_sidecar_digest_sha256
        ),
        "choice_key": candidate.choice.key,
        "choice_normalized_value": (
            candidate.choice.normalized_value
        ),
        "choice_value_digest_sha256": (
            candidate.choice.value_digest_sha256
        ),
        "claims": _CLAIMS,
    }


def _build_receipt(
    *,
    replay: _Replay,
    candidate: _Candidate,
    compilation: GenericPredicateCompilation,
    role_receipt: RelationRoleReceipt,
    context: GenericPredicateContext,
) -> GenericPredicateProofReceipt:
    values = _receipt_values(
        replay=replay,
        candidate=candidate,
        compilation=compilation,
        role_receipt=role_receipt,
        context=context,
    )
    return GenericPredicateProofReceipt(
        **values,
        proof_digest_sha256=canonical_digest(_proof_body(values)),
    )


def _abstain(reason: str) -> GenericPredicateProofDecision:
    return GenericPredicateProofDecision(
        schema_version=SCHEMA_VERSION,
        status="abstain",
        reason=reason,
        engine_fired=False,
        choice_key=None,
        receipt=None,
        claims=_CLAIMS,
    )


def consume_generic_predicate_compilation(
    stem: Any,
    compilation: Any,
    *,
    role_receipt: Any,
    context: Any,
    enabled: Any,
) -> GenericPredicateProofDecision:
    """Replay one proposal and prove exactly one unranked fact-choice pair."""

    if type(enabled) is not bool:
        raise TypeError("exact bool enabled flag required")
    _preflight(stem, compilation, role_receipt, context)
    if not compilation.compiled:
        return _abstain("compilation_not_compiled")
    replay = _replay_compiled_contract(
        stem,
        compilation,
        role_receipt,
        context,
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
        role_receipt=role_receipt,
        context=context,
    )
    return GenericPredicateProofDecision(
        schema_version=SCHEMA_VERSION,
        status="proved",
        reason="exactly_one_provable_choice",
        engine_fired=True,
        choice_key=receipt.choice_key,
        receipt=receipt,
        claims=_CLAIMS,
    )


def _verification_candidate(
    replay: _Replay,
    compilation: GenericPredicateCompilation,
    context: GenericPredicateContext,
) -> _Candidate | None:
    found: _Candidate | None = None
    count = 0
    for fact in replay.facts:
        for choice in compilation.choices:
            if _surface_key(fact.object_value) != _surface_key(
                choice.normalized_value
            ):
                continue
            count += 1
            if count > 1:
                return None
            found = _Candidate(
                choice=choice,
                fact=fact,
                binding=_binding_for_fact(context, fact),
            )
    return found if count == 1 else None


def verify_generic_predicate_proof_receipt(
    receipt: Any,
    stem: Any,
    compilation: Any,
    *,
    role_receipt: Any,
    context: Any,
) -> bool:
    """Independently replay every proof leaf against immutable inputs."""

    if (
        type(receipt) is not GenericPredicateProofReceipt
        or type(stem) is not str
        or type(compilation) is not GenericPredicateCompilation
        or type(role_receipt) is not RelationRoleReceipt
        or type(context) is not GenericPredicateContext
    ):
        return False
    try:
        receipt.__post_init__()
        _preflight(stem, compilation, role_receipt, context)
        replay = _replay_compiled_contract(
            stem,
            compilation,
            role_receipt,
            context,
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
            role_receipt=role_receipt,
            context=context,
        )
        return receipt.to_dict() == expected.to_dict()
    except (GenericPredicateStagingError, TypeError, ValueError):
        return False


__all__ = [
    "GenericPredicateProofDecision",
    "GenericPredicateProofReceipt",
    "GenericPredicateStagingError",
    "PROOF_RULE",
    "SCHEMA_VERSION",
    "consume_generic_predicate_compilation",
    "verify_generic_predicate_proof_receipt",
]
