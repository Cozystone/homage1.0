"""General dependency-role to staged-predicate goal compilation.

This module is deliberately proposal-only.  It consumes an already extracted
``RelationRoleReceipt`` and an already resolved ``GenericPredicateContext``;
it does not open a graph, choose a final answer, or write any state.

Predicate selection is graph-conditioned and enumeration-free.  Every
predicate name already present in the supplied context is normalized into a
token sequence.  A predicate is selected only when exactly one such sequence
occurs inside the dependency-isolated relation role or its forward-query
object role, using either exact surface tokens or parser-provided lemmas.

Internal predicate names remain in ``atanor.internal_graph``.  A source QID or
PID attached to an individual staged fact is provenance only and never becomes
the identity of the selected predicate.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Literal
import unicodedata

from packages.cognitive_core.canonical import FrozenMap, canonical_digest
from packages.reasoning_vm.deliberator.generic_predicate_socket import (
    GenericPredicateContext,
    GenericPredicateFact,
    InternalPredicateRef,
    PREDICATE_NAMESPACE,
)
from packages.reasoning_vm.deliberator.relation_role_extractor import (
    RelationRole,
    RelationRoleReceipt,
)


SCHEMA_VERSION = "atanor.deliberator.generic-predicate-compilation.v1"
GOAL_SCHEMA_VERSION = "atanor.deliberator.generic-predicate-goal.v1"
FACT_BUNDLE_SCHEMA_VERSION = (
    "atanor.deliberator.generic-predicate-fact-bundle.v1"
)
COMPILER_RULE = "dependency_roles_to_internal_predicate_v1"

MAX_STEM_CHARS = 2048
MAX_CHOICES = 10
MIN_CHOICES = 2
MAX_CHOICE_KEY_CHARS = 32
MAX_CHOICE_TEXT_CHARS = 8192
MAX_REASON_CHARS = 192

CompilationStatus = Literal["compiled", "abstain", "invalid"]
LinkageSource = Literal[
    "relation_raw",
    "relation_lemma",
    "wh_object_raw",
    "wh_object_lemma",
]

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REASON = re.compile(r"[a-z][a-z0-9_]{0,191}\Z")
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
_COMPILED_EVIDENCE = FrozenMap(
    {
        "exact_context_digest_required": True,
        "exact_internal_predicate_required": True,
        "exact_role_receipt_required": True,
        "exact_stage_fact_required": True,
        "forward_query_required": True,
        "predicate_namespace": PREDICATE_NAMESPACE,
        "verification_membrane_required": True,
        "wikidata_pid_required": False,
    }
)


def _is_sha256(value: Any) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _normalize_surface(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


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
    """Build one dependency-filtered semantic role, never a loose substring."""

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


def _choices_digest(
    choice_items: tuple[tuple[str, str], ...],
) -> str:
    return canonical_digest([[key, value] for key, value in choice_items])


def _input_digest(stem: str, choices_digest_sha256: str) -> str:
    return canonical_digest(
        {
            "stem": stem,
            "choices_digest_sha256": choices_digest_sha256,
        }
    )


def _invalid_choices_digest(value: Any) -> str:
    return canonical_digest(
        {
            "invalid_choice_items_type": (
                f"{type(value).__module__}.{type(value).__qualname__}"
            )
        }
    )


def _invalid_stem_value(value: Any) -> str:
    return f"<python:{type(value).__module__}.{type(value).__qualname__}>"


@dataclass(frozen=True, slots=True)
class GenericPredicateChoice:
    """One immutable MCQ choice derived from an existing one-shot snapshot."""

    key: str
    original_text: str
    normalized_value: str
    value_digest_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.key) is not str
            or not self.key
            or self.key != self.key.strip()
            or len(self.key) > MAX_CHOICE_KEY_CHARS
            or any(character.isspace() for character in self.key)
            or _CONTROL.search(self.key) is not None
            or type(self.original_text) is not str
            or not self.original_text
            or self.original_text != self.original_text.strip()
            or len(self.original_text) > MAX_CHOICE_TEXT_CHARS
            or type(self.normalized_value) is not str
            or not self.normalized_value
            or self.normalized_value != _normalize_surface(self.original_text)
            or not _is_sha256(self.value_digest_sha256)
            or self.value_digest_sha256
            != _text_digest(self.normalized_value)
        ):
            raise ValueError("generic predicate choice is invalid")

    def to_dict(self) -> dict[str, str]:
        self.__post_init__()
        return {
            "key": self.key,
            "original_text": self.original_text,
            "normalized_value": self.normalized_value,
            "value_digest_sha256": self.value_digest_sha256,
        }


@dataclass(frozen=True, slots=True)
class PredicateTokenLinkage:
    """Exact token evidence connecting one role to one internal predicate."""

    source: LinkageSource
    predicate_tokens: tuple[str, ...]
    evidence_tokens: tuple[str, ...]
    match_start: int
    match_end: int

    def __post_init__(self) -> None:
        if (
            self.source
            not in (
                "relation_raw",
                "relation_lemma",
                "wh_object_raw",
                "wh_object_lemma",
            )
            or type(self.predicate_tokens) is not tuple
            or not self.predicate_tokens
            or type(self.evidence_tokens) is not tuple
            or not self.evidence_tokens
            or any(
                type(token) is not str
                or not token
                or _tokens(token) != (token,)
                for token in (*self.predicate_tokens, *self.evidence_tokens)
            )
            or type(self.match_start) is not int
            or type(self.match_end) is not int
            or not 0 <= self.match_start < self.match_end
            <= len(self.evidence_tokens)
            or self.match_end - self.match_start
            != len(self.predicate_tokens)
            or self.evidence_tokens[self.match_start : self.match_end]
            != self.predicate_tokens
        ):
            raise ValueError("generic predicate token linkage is invalid")

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            "source": self.source,
            "predicate_tokens": list(self.predicate_tokens),
            "evidence_tokens": list(self.evidence_tokens),
            "match_start": self.match_start,
            "match_end": self.match_end,
        }


def generic_predicate_fact_bundle_digest(
    subject: str,
    predicate: InternalPredicateRef,
    facts: tuple[GenericPredicateFact, ...],
) -> str:
    """Digest one exact staged fact bundle for later proof replay."""

    if (
        type(subject) is not str
        or not subject
        or type(predicate) is not InternalPredicateRef
        or type(facts) is not tuple
        or not facts
        or any(type(fact) is not GenericPredicateFact for fact in facts)
    ):
        raise ValueError("generic predicate fact bundle is invalid")
    predicate.__post_init__()
    for fact in facts:
        fact.__post_init__()
        if (
            fact.subject not in (subject, subject.lower())
            or fact.predicate != predicate
        ):
            raise ValueError("generic predicate fact bundle is not exact")
    return canonical_digest(
        {
            "schema_version": FACT_BUNDLE_SCHEMA_VERSION,
            "subject": subject,
            "predicate": predicate.to_dict(),
            "facts": [fact.to_dict() for fact in facts],
        }
    )


@dataclass(frozen=True, slots=True)
class GenericPredicateGoal:
    """One exact internal-predicate query with its complete staged fact bundle."""

    schema_version: str
    subject: str
    predicate: InternalPredicateRef
    linkage: PredicateTokenLinkage
    role_receipt_digest_sha256: str
    context_digest_sha256: str
    facts: tuple[GenericPredicateFact, ...]
    fact_bundle_digest_sha256: str

    def __post_init__(self) -> None:
        if (
            self.schema_version != GOAL_SCHEMA_VERSION
            or type(self.subject) is not str
            or not self.subject
            or self.subject != self.subject.strip()
            or len(self.subject) > MAX_STEM_CHARS
            or unicodedata.normalize("NFKC", self.subject) != self.subject
            or type(self.predicate) is not InternalPredicateRef
            or type(self.linkage) is not PredicateTokenLinkage
            or not _is_sha256(self.role_receipt_digest_sha256)
            or not _is_sha256(self.context_digest_sha256)
            or type(self.facts) is not tuple
            or not self.facts
            or not _is_sha256(self.fact_bundle_digest_sha256)
        ):
            raise ValueError("generic predicate goal is invalid")
        self.predicate.__post_init__()
        self.linkage.__post_init__()
        if (
            self.predicate.namespace != PREDICATE_NAMESPACE
            or self.predicate.wikidata_property_id is not None
            or self.linkage.predicate_tokens != _tokens(self.predicate.name)
            or self.fact_bundle_digest_sha256
            != generic_predicate_fact_bundle_digest(
                self.subject,
                self.predicate,
                self.facts,
            )
        ):
            raise ValueError("generic predicate goal evidence does not derive")

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {
            "schema_version": self.schema_version,
            "subject": self.subject,
            "predicate": self.predicate.to_dict(),
            "linkage": self.linkage.to_dict(),
            "role_receipt_digest_sha256": (
                self.role_receipt_digest_sha256
            ),
            "context_digest_sha256": self.context_digest_sha256,
            "facts": [fact.to_dict() for fact in self.facts],
            "fact_bundle_digest_sha256": (
                self.fact_bundle_digest_sha256
            ),
        }


@dataclass(frozen=True, slots=True)
class GenericPredicateCompilation:
    """Immutable proposal receipt; it has no answer authority."""

    schema_version: str
    status: CompilationStatus
    reason: str
    compiler_rule: str
    input_digest_sha256: str
    choices_digest_sha256: str
    role_receipt_digest_sha256: str | None
    context_digest_sha256: str | None
    goal: GenericPredicateGoal | None
    choices: tuple[GenericPredicateChoice, ...]
    required_evidence: FrozenMap
    claims: FrozenMap

    def __post_init__(self) -> None:
        if (
            self.schema_version != SCHEMA_VERSION
            or self.status not in ("compiled", "abstain", "invalid")
            or type(self.reason) is not str
            or len(self.reason) > MAX_REASON_CHARS
            or _REASON.fullmatch(self.reason) is None
            or self.compiler_rule != COMPILER_RULE
            or not _is_sha256(self.input_digest_sha256)
            or not _is_sha256(self.choices_digest_sha256)
            or (
                self.role_receipt_digest_sha256 is not None
                and not _is_sha256(self.role_receipt_digest_sha256)
            )
            or (
                self.context_digest_sha256 is not None
                and not _is_sha256(self.context_digest_sha256)
            )
            or type(self.choices) is not tuple
            or len(self.choices) > MAX_CHOICES
            or any(
                type(choice) is not GenericPredicateChoice
                for choice in self.choices
            )
            or type(self.required_evidence) is not FrozenMap
            or type(self.claims) is not FrozenMap
            or self.claims != _CLAIMS
            or any(value is not False for value in self.claims.values())
        ):
            raise ValueError("generic predicate compilation is invalid")
        for choice in self.choices:
            choice.__post_init__()
        if self.choices and self.choices_digest_sha256 != _choices_digest(
            tuple(
                (choice.key, choice.original_text)
                for choice in self.choices
            )
        ):
            raise ValueError(
                "generic predicate compilation choices digest does not derive"
            )
        if (
            len({choice.key for choice in self.choices})
            != len(self.choices)
            or len(
                {
                    choice.normalized_value.casefold()
                    for choice in self.choices
                }
            )
            != len(self.choices)
        ):
            raise ValueError("generic predicate compilation choices collide")
        if self.status == "compiled":
            if (
                self.reason != "compiled_internal_predicate_goal"
                or type(self.goal) is not GenericPredicateGoal
                or not MIN_CHOICES <= len(self.choices) <= MAX_CHOICES
                or self.role_receipt_digest_sha256
                != self.goal.role_receipt_digest_sha256
                or self.context_digest_sha256
                != self.goal.context_digest_sha256
                or self.required_evidence != _COMPILED_EVIDENCE
            ):
                raise ValueError(
                    "compiled generic predicate receipt is incomplete"
                )
            self.goal.__post_init__()
        elif (
            self.goal is not None
            or len(self.required_evidence)
            or (
                self.status == "abstain"
                and self.reason
                not in {
                    "forward_query_not_established",
                    "predicate_context_not_ready",
                    "predicate_context_subject_mismatch",
                    "predicate_surface_ambiguous",
                    "predicate_surface_not_grounded",
                    "role_receipt_not_safe",
                    "selected_fact_bundle_empty",
                }
            )
            or (
                self.status == "invalid"
                and self.reason
                not in {
                    "choice_count_out_of_bounds",
                    "choice_item_invalid",
                    "choice_items_invalid",
                    "choice_items_not_tuple",
                    "choice_out_of_bounds",
                    "duplicate_choice",
                    "predicate_context_invalid",
                    "role_receipt_input_mismatch",
                    "role_receipt_invalid",
                    "stem_out_of_bounds",
                }
            )
        ):
            raise ValueError(
                "noncompiled generic predicate receipt carries a goal"
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
            "choices_digest_sha256": self.choices_digest_sha256,
            "role_receipt_digest_sha256": (
                self.role_receipt_digest_sha256
            ),
            "context_digest_sha256": self.context_digest_sha256,
            "goal": None if self.goal is None else self.goal.to_dict(),
            "choices": [choice.to_dict() for choice in self.choices],
            "required_evidence": self.required_evidence.to_dict(),
            "claims": self.claims.to_dict(),
        }


def _normalize_choices(
    choice_items: Any,
) -> tuple[
    tuple[GenericPredicateChoice, ...] | None,
    str,
    str,
]:
    if type(choice_items) is not tuple:
        return None, _invalid_choices_digest(choice_items), "choice_items_not_tuple"
    try:
        raw_digest = _choices_digest(choice_items)
    except Exception:
        return None, _invalid_choices_digest(choice_items), "choice_items_invalid"
    if not MIN_CHOICES <= len(choice_items) <= MAX_CHOICES:
        return None, raw_digest, "choice_count_out_of_bounds"
    choices: list[GenericPredicateChoice] = []
    seen_keys: set[str] = set()
    seen_values: set[str] = set()
    for pair in choice_items:
        if type(pair) is not tuple or len(pair) != 2:
            return None, raw_digest, "choice_item_invalid"
        key, value = pair
        if (
            type(key) is not str
            or not key
            or key != key.strip()
            or len(key) > MAX_CHOICE_KEY_CHARS
            or any(character.isspace() for character in key)
            or _CONTROL.search(key) is not None
            or type(value) is not str
            or not value
            or value != value.strip()
            or len(value) > MAX_CHOICE_TEXT_CHARS
            or _CONTROL.search(value) is not None
        ):
            return None, raw_digest, "choice_out_of_bounds"
        normalized = _normalize_surface(value)
        normalized_key = normalized.casefold()
        if key in seen_keys or normalized_key in seen_values:
            return None, raw_digest, "duplicate_choice"
        seen_keys.add(key)
        seen_values.add(normalized_key)
        choices.append(
            GenericPredicateChoice(
                key=key,
                original_text=value,
                normalized_value=normalized,
                value_digest_sha256=_text_digest(normalized),
            )
        )
    return tuple(choices), raw_digest, ""


def _build_compilation(
    *,
    status: CompilationStatus,
    reason: str,
    input_digest_sha256: str,
    choices_digest_sha256: str,
    role_receipt_digest_sha256: str | None,
    context_digest_sha256: str | None,
    choices: tuple[GenericPredicateChoice, ...],
    goal: GenericPredicateGoal | None = None,
) -> GenericPredicateCompilation:
    return GenericPredicateCompilation(
        schema_version=SCHEMA_VERSION,
        status=status,
        reason=reason,
        compiler_rule=COMPILER_RULE,
        input_digest_sha256=input_digest_sha256,
        choices_digest_sha256=choices_digest_sha256,
        role_receipt_digest_sha256=role_receipt_digest_sha256,
        context_digest_sha256=context_digest_sha256,
        goal=goal,
        choices=choices,
        required_evidence=(
            _COMPILED_EVIDENCE if status == "compiled" else FrozenMap()
        ),
        claims=_CLAIMS,
    )


def _role_evidence(
    receipt: RelationRoleReceipt,
) -> tuple[tuple[LinkageSource, tuple[str, ...]], ...]:
    assert receipt.relation is not None
    assert receipt.object is not None
    assert receipt.subject is not None
    subject_uses_relation_preposition = any(
        dependency in {"nmod", "obl", "pobj"}
        for dependency in receipt.subject.dependencies
    )
    return (
        (
            "relation_raw",
            _content_role_tokens(
                receipt.relation,
                lemmas=False,
                trim_subject_preposition=(
                    subject_uses_relation_preposition
                ),
            ),
        ),
        (
            "relation_lemma",
            _content_role_tokens(
                receipt.relation,
                lemmas=True,
                trim_subject_preposition=(
                    subject_uses_relation_preposition
                ),
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


def _select_predicate(
    receipt: RelationRoleReceipt,
    context: GenericPredicateContext,
) -> tuple[
    InternalPredicateRef | None,
    PredicateTokenLinkage | None,
    str,
]:
    evidence = _role_evidence(receipt)
    matches: list[
        tuple[InternalPredicateRef, PredicateTokenLinkage]
    ] = []
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
    if not matches:
        return None, None, "predicate_surface_not_grounded"
    if len(matches) != 1:
        return None, None, "predicate_surface_ambiguous"
    predicate, linkage = matches[0]
    return predicate, linkage, ""


def compile_generic_predicate_goal(
    stem: Any,
    choice_items: Any,
    *,
    role_receipt: Any,
    context: Any,
) -> GenericPredicateCompilation:
    """Compile one exact forward query, or abstain without guessing.

    ``choice_items`` must already be the immutable tuple produced by the
    route-first science input boundary.  Mappings are rejected without being
    enumerated, preserving the single-read contract of that upstream boundary.
    """

    choices, choices_digest, choice_reason = _normalize_choices(choice_items)
    stem_for_digest = stem if type(stem) is str else _invalid_stem_value(stem)
    input_digest = _input_digest(stem_for_digest, choices_digest)
    if (
        type(stem) is not str
        or not stem
        or stem != stem.strip()
        or len(stem) > MAX_STEM_CHARS
        or unicodedata.normalize("NFKC", stem) != stem
        or _CONTROL.search(stem) is not None
    ):
        return _build_compilation(
            status="invalid",
            reason="stem_out_of_bounds",
            input_digest_sha256=input_digest,
            choices_digest_sha256=choices_digest,
            role_receipt_digest_sha256=None,
            context_digest_sha256=None,
            choices=(),
        )
    if choices is None:
        return _build_compilation(
            status="invalid",
            reason=choice_reason,
            input_digest_sha256=input_digest,
            choices_digest_sha256=choices_digest,
            role_receipt_digest_sha256=None,
            context_digest_sha256=None,
            choices=(),
        )

    if type(role_receipt) is not RelationRoleReceipt:
        return _build_compilation(
            status="invalid",
            reason="role_receipt_invalid",
            input_digest_sha256=input_digest,
            choices_digest_sha256=choices_digest,
            role_receipt_digest_sha256=None,
            context_digest_sha256=None,
            choices=choices,
        )
    try:
        role_receipt.__post_init__()
    except Exception:
        return _build_compilation(
            status="invalid",
            reason="role_receipt_invalid",
            input_digest_sha256=input_digest,
            choices_digest_sha256=choices_digest,
            role_receipt_digest_sha256=None,
            context_digest_sha256=None,
            choices=choices,
        )
    role_digest = role_receipt.receipt_digest_sha256
    if role_receipt.input_digest_sha256 != _text_digest(stem):
        return _build_compilation(
            status="invalid",
            reason="role_receipt_input_mismatch",
            input_digest_sha256=input_digest,
            choices_digest_sha256=choices_digest,
            role_receipt_digest_sha256=role_digest,
            context_digest_sha256=None,
            choices=choices,
        )
    if not role_receipt.safe:
        return _build_compilation(
            status="abstain",
            reason="role_receipt_not_safe",
            input_digest_sha256=input_digest,
            choices_digest_sha256=choices_digest,
            role_receipt_digest_sha256=role_digest,
            context_digest_sha256=None,
            choices=choices,
        )
    if (
        role_receipt.direction != "forward"
        or role_receipt.polarity != "positive"
        or role_receipt.subject is None
        or role_receipt.relation is None
        or role_receipt.object is None
        or not any(
            cue.kind == "query_object"
            for cue in role_receipt.direction_evidence
        )
    ):
        return _build_compilation(
            status="abstain",
            reason="forward_query_not_established",
            input_digest_sha256=input_digest,
            choices_digest_sha256=choices_digest,
            role_receipt_digest_sha256=role_digest,
            context_digest_sha256=None,
            choices=choices,
        )

    if type(context) is not GenericPredicateContext:
        return _build_compilation(
            status="invalid",
            reason="predicate_context_invalid",
            input_digest_sha256=input_digest,
            choices_digest_sha256=choices_digest,
            role_receipt_digest_sha256=role_digest,
            context_digest_sha256=None,
            choices=choices,
        )
    try:
        context.assert_validated()
    except Exception:
        return _build_compilation(
            status="invalid",
            reason="predicate_context_invalid",
            input_digest_sha256=input_digest,
            choices_digest_sha256=choices_digest,
            role_receipt_digest_sha256=role_digest,
            context_digest_sha256=None,
            choices=choices,
        )
    context_digest = context.context_digest_sha256
    subject = role_receipt.subject.text
    if context.subject != subject:
        return _build_compilation(
            status="abstain",
            reason="predicate_context_subject_mismatch",
            input_digest_sha256=input_digest,
            choices_digest_sha256=choices_digest,
            role_receipt_digest_sha256=role_digest,
            context_digest_sha256=context_digest,
            choices=choices,
        )
    if context.status != "ready" or not context.complete:
        return _build_compilation(
            status="abstain",
            reason="predicate_context_not_ready",
            input_digest_sha256=input_digest,
            choices_digest_sha256=choices_digest,
            role_receipt_digest_sha256=role_digest,
            context_digest_sha256=context_digest,
            choices=choices,
        )

    predicate, linkage, predicate_reason = _select_predicate(
        role_receipt,
        context,
    )
    if predicate is None or linkage is None:
        return _build_compilation(
            status="abstain",
            reason=predicate_reason,
            input_digest_sha256=input_digest,
            choices_digest_sha256=choices_digest,
            role_receipt_digest_sha256=role_digest,
            context_digest_sha256=context_digest,
            choices=choices,
        )
    facts = context.facts_for_subject(context.subject, predicate)
    if not facts:
        return _build_compilation(
            status="abstain",
            reason="selected_fact_bundle_empty",
            input_digest_sha256=input_digest,
            choices_digest_sha256=choices_digest,
            role_receipt_digest_sha256=role_digest,
            context_digest_sha256=context_digest,
            choices=choices,
        )
    fact_bundle_digest = generic_predicate_fact_bundle_digest(
        subject,
        predicate,
        facts,
    )
    goal = GenericPredicateGoal(
        schema_version=GOAL_SCHEMA_VERSION,
        subject=subject,
        predicate=predicate,
        linkage=linkage,
        role_receipt_digest_sha256=role_digest,
        context_digest_sha256=context_digest,
        facts=facts,
        fact_bundle_digest_sha256=fact_bundle_digest,
    )
    return _build_compilation(
        status="compiled",
        reason="compiled_internal_predicate_goal",
        input_digest_sha256=input_digest,
        choices_digest_sha256=choices_digest,
        role_receipt_digest_sha256=role_digest,
        context_digest_sha256=context_digest,
        choices=choices,
        goal=goal,
    )


def verify_generic_predicate_compilation(
    stem: Any,
    compilation: Any,
    *,
    role_receipt: Any,
    context: Any,
) -> bool:
    """Replay a proposal from the exact parser and graph evidence."""

    if (
        type(stem) is not str
        or type(compilation) is not GenericPredicateCompilation
        or type(role_receipt) is not RelationRoleReceipt
        or type(context) is not GenericPredicateContext
    ):
        return False
    try:
        compilation.__post_init__()
        replay = compile_generic_predicate_goal(
            stem,
            tuple(
                (choice.key, choice.original_text)
                for choice in compilation.choices
            ),
            role_receipt=role_receipt,
            context=context,
        )
        return replay.to_dict() == compilation.to_dict()
    except (TypeError, ValueError):
        return False


__all__ = [
    "COMPILER_RULE",
    "FACT_BUNDLE_SCHEMA_VERSION",
    "GOAL_SCHEMA_VERSION",
    "GenericPredicateChoice",
    "GenericPredicateCompilation",
    "GenericPredicateGoal",
    "PredicateTokenLinkage",
    "SCHEMA_VERSION",
    "compile_generic_predicate_goal",
    "generic_predicate_fact_bundle_digest",
    "verify_generic_predicate_compilation",
]
