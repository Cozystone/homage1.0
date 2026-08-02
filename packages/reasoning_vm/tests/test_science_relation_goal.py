"""Mechanism tests for the parallel typed relation-select compiler.

These tests cover deterministic compilation and fail-closed boundaries only.
They make no capability, benchmark, or evaluation-tier claim.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import replace

import pytest

from packages.reasoning_vm.deliberator import science_relation_goal as relation
from packages.reasoning_vm.deliberator.relational_object_compiler import (
    EXPLICIT_RELATIONAL_OBJECT_SCHEMA,
    compile_explicit_relational_object_mcq,
)
from packages.reasoning_vm.deliberator.science_relation_goal import (
    COMPILER_RULE,
    DIAGNOSTIC_SCOPE,
    GENERAL_EXTRACTOR_SUCCESSOR,
    MAX_CHOICE_TEXT_CHARS,
    MAX_STEM_CHARS,
    SCIENCE_RELATION_GOAL_CONTRACT_DIGEST_SHA256,
    SCIENCE_RELATION_GOAL_FAMILY,
    SCIENCE_RELATION_GOAL_FAMILY_DIGEST_SHA256,
    SCIENCE_RELATION_GOAL_SCHEMA,
    SCIENCE_RELATION_GOAL_SCHEMA_DIGEST_SHA256,
    SCIENCE_RELATION_STAGE_SCHEMA,
    NormalizedRelationChoice,
    RelationStageEvidenceRequirement,
    TypedRelationSelectGoal,
    compile_typed_relation_select,
    compile_typed_relation_select_question,
    looks_like_typed_relation_select,
    verify_compilation_subject_span,
)


CHOICES = {
    "A": "North Reach",
    "B": "South Reach",
    "C": "East Reach",
    "D": "West Reach",
}
PRIMARY_STEM = "Which province is Lake Brindle situated in?"


def test_contract_marks_this_as_a_nonexpanding_diagnostic_sibling_lane():
    payload = relation._contract_payload()

    assert payload["scope"] == {
        "role": DIAGNOSTIC_SCOPE,
        "manual_surface_or_predicate_expansion_allowed": False,
        "successor": GENERAL_EXTRACTOR_SUCCESSOR,
        "capability_claim": False,
    }
    assert len(payload["surfaces"]) == 4
    assert payload["goal_literals"]["predicate"] == "located_in"


@pytest.mark.parametrize(
    ("stem", "surface_id", "subject", "answer_type"),
    [
        (
            "Which province is Lake Brindle situated in?",
            "which_type_subject_relation_in",
            "Lake Brindle",
            "province",
        ),
        (
            "In which country is Port Meridian located?",
            "in_which_type_subject_relation",
            "Port Meridian",
            "country",
        ),
        (
            "Mount Aster is located in which region?",
            "subject_relation_in_which_type",
            "Mount Aster",
            "region",
        ),
        (
            "Select the continent in which Aurora Isle is situated.",
            "select_type_subject_relation",
            "Aurora Isle",
            "continent",
        ),
    ],
)
def test_independent_paraphrases_emit_the_exact_positive_relation_goal(
    stem: str,
    surface_id: str,
    subject: str,
    answer_type: str,
):
    receipt = compile_typed_relation_select(stem, CHOICES)

    assert looks_like_typed_relation_select(stem) is True
    assert receipt.compiled is True
    assert receipt.input_valid is True
    assert receipt.schema_version == SCIENCE_RELATION_GOAL_SCHEMA
    assert receipt.goal_family == SCIENCE_RELATION_GOAL_FAMILY
    assert receipt.surface_family == SCIENCE_RELATION_GOAL_FAMILY
    assert receipt.goal is not None
    assert receipt.goal.subject == subject
    assert receipt.goal.answer_type == answer_type
    assert receipt.goal.predicate == "located_in"
    assert receipt.goal.polarity == "positive"
    assert receipt.goal.object_source == "normalized_choice_entity"
    assert (
        receipt.goal.selection_cardinality
        == "exactly_one_provable_choice"
    )
    assert receipt.goal.surface_id == surface_id
    assert receipt.goal.compiler_rule == COMPILER_RULE
    assert verify_compilation_subject_span(receipt, stem) is True
    assert not hasattr(receipt, "__dict__")
    assert not hasattr(receipt.goal, "__dict__")


def test_schema_family_contract_and_goal_are_all_digest_bound():
    receipt = compile_typed_relation_select(PRIMARY_STEM, CHOICES)

    assert receipt.schema_digest_sha256 == (
        SCIENCE_RELATION_GOAL_SCHEMA_DIGEST_SHA256
    )
    assert receipt.family_digest_sha256 == (
        SCIENCE_RELATION_GOAL_FAMILY_DIGEST_SHA256
    )
    assert receipt.contract_digest_sha256 == (
        SCIENCE_RELATION_GOAL_CONTRACT_DIGEST_SHA256
    )
    assert all(
        len(value) == 64
        for value in (
            receipt.schema_digest_sha256,
            receipt.family_digest_sha256,
            receipt.contract_digest_sha256,
            receipt.input_digest_sha256,
            receipt.goal_digest_sha256 or "",
        )
    )
    with pytest.raises(ValueError, match="does not bind"):
        replace(receipt, goal_digest_sha256="0" * 64)
    with pytest.raises(ValueError, match="envelope"):
        replace(receipt, contract_digest_sha256="1" * 64)


def test_stage_evidence_requirement_is_exact_and_provenance_strict():
    receipt = compile_typed_relation_select(PRIMARY_STEM, CHOICES)

    assert len(receipt.required_evidence) == 1
    requirement = receipt.required_evidence[0]
    assert requirement.to_dict() == {
        "stage_schema": SCIENCE_RELATION_STAGE_SCHEMA,
        "evidence_kind": "typed_positive_relation_fact",
        "predicate": "located_in",
        "subject_source": "goal_subject",
        "object_source": "normalized_choice_entity",
        "object_answer_type": "province",
        "object_answer_type_source": "goal_answer_type",
        "polarity": "positive",
        "original_property_id_required": True,
        "object_type_evidence_required": True,
        "exact_row_provenance": True,
        "source_revision_required": True,
        "license_required": True,
        "quarantined_allowed": False,
    }
    with pytest.raises(ValueError, match="evidence"):
        replace(requirement, exact_row_provenance=1)
    with pytest.raises(ValueError, match="evidence"):
        replace(requirement, stage_schema="forged-stage")


def test_choices_are_normalized_but_never_marked_or_ranked_as_an_answer():
    receipt = compile_typed_relation_select(
        PRIMARY_STEM,
        {
            "A": "New   Albion",
            "B": "Old Coast",
            "C": "West Haven",
            "D": "East March",
        },
    )

    assert receipt.compiled is True
    assert [item.normalized_entity for item in receipt.choice_items] == [
        "New Albion",
        "Old Coast",
        "West Haven",
        "East March",
    ]
    payload = receipt.to_dict()
    assert "answer" not in payload
    assert "selected_choice" not in payload
    assert all(
        set(item) == {"key", "original_text", "normalized_entity"}
        for item in payload["choice_items"]
    )


def test_choice_order_is_digest_invariant_and_counterfactual_subject_is_not():
    first = compile_typed_relation_select(
        PRIMARY_STEM,
        {"D": "West Reach", "B": "South Reach", "A": "North Reach", "C": "East Reach"},
    )
    reordered = compile_typed_relation_select(PRIMARY_STEM, CHOICES)
    counterfactual = compile_typed_relation_select(
        "Which province is Lake Sable situated in?",
        CHOICES,
    )

    assert first.to_dict() == reordered.to_dict()
    assert first.input_digest_sha256 == reordered.input_digest_sha256
    assert first.goal_digest_sha256 == reordered.goal_digest_sha256
    assert counterfactual.compiled is True
    assert counterfactual.goal is not None
    assert counterfactual.goal.subject == "Lake Sable"
    assert counterfactual.input_digest_sha256 != first.input_digest_sha256
    assert counterfactual.goal_digest_sha256 != first.goal_digest_sha256


@pytest.mark.parametrize("subject", ["The Gambia", "The Hague"])
def test_leading_article_is_preserved_when_it_is_part_of_entity_identity(
    subject: str,
):
    stem = f"Which country is {subject} located in?"
    receipt = compile_typed_relation_select(stem, CHOICES)

    assert receipt.compiled is True
    assert receipt.goal is not None
    assert receipt.goal.subject == subject
    assert verify_compilation_subject_span(receipt, stem) is True


def test_mapping_is_read_once_bounded_and_detached_from_later_mutation():
    class OneReadChoices(Mapping[str, str]):
        def __init__(self, rows: list[tuple[str, str]]) -> None:
            self.rows = rows
            self.items_reads = 0

        def __getitem__(self, key: str) -> str:
            raise AssertionError("compiler must not re-index the mapping")

        def __iter__(self) -> Iterator[str]:
            raise AssertionError("compiler must use the bounded items snapshot")

        def __len__(self) -> int:
            raise AssertionError("compiler must not trust Mapping.__len__")

        def items(self) -> Iterator[tuple[str, str]]:
            self.items_reads += 1
            if self.items_reads != 1:
                raise AssertionError("mapping was read more than once")
            return iter(self.rows)

    source = OneReadChoices(list(CHOICES.items()))
    receipt = compile_typed_relation_select(PRIMARY_STEM, source)
    original_payload = receipt.to_dict()
    source.rows[0] = ("A", "Mutated After Compilation")

    assert receipt.compiled is True
    assert source.items_reads == 1
    assert receipt.to_dict() == original_payload
    assert receipt.choice_items[0].normalized_entity == "North Reach"


@pytest.mark.parametrize(
    ("stem", "reason"),
    [
        (None, "stem_not_string"),
        (" " + PRIMARY_STEM, "stem_out_of_bounds"),
        (PRIMARY_STEM + "\x00", "stem_out_of_bounds"),
        (PRIMARY_STEM.replace("Lake Brindle", "Lake\tBrindle"), "stem_out_of_bounds"),
        (PRIMARY_STEM.replace("Lake Brindle", "Lake  Brindle"), "stem_out_of_bounds"),
        ("x" * (MAX_STEM_CHARS + 1), "stem_out_of_bounds"),
    ],
)
def test_non_string_bounds_nul_and_noncanonical_stem_whitespace_are_invalid(
    stem,
    reason: str,
):
    first = compile_typed_relation_select(stem, CHOICES)
    second = compile_typed_relation_select(stem, CHOICES)

    assert first.input_valid is False
    assert first.status == "invalid"
    assert first.reason == reason
    assert first.goals == ()
    assert first.choice_items == ()
    assert first.input_digest_sha256 == second.input_digest_sha256
    assert looks_like_typed_relation_select(stem) is False


@pytest.mark.parametrize(
    ("choices", "reason"),
    [
        (None, "choices_not_mapping"),
        ({"A": "North Reach"}, "choice_count_out_of_bounds"),
        (
            {str(index): f"Place {index}" for index in range(11)},
            "choice_count_out_of_bounds",
        ),
        ({" A": "North Reach", "B": "South Reach"}, "invalid_choice_key"),
        ({"A": " North Reach", "B": "South Reach"}, "invalid_choice_text"),
        ({"A": "North\x00Reach", "B": "South Reach"}, "invalid_choice_text"),
        ({"A": "North\nReach", "B": "South Reach"}, "invalid_choice_text"),
        ({"A": "123", "B": "South Reach"}, "invalid_choice_entity"),
        (
            {"A": "X" * (MAX_CHOICE_TEXT_CHARS + 1), "B": "South Reach"},
            "invalid_choice_text",
        ),
        (
            {"A": "New   Albion", "B": "new albion", "C": "Old Coast"},
            "duplicate_normalized_choices",
        ),
        ({"A": "North Reach", "B": 7}, "invalid_choice_text"),
    ],
)
def test_invalid_or_duplicate_choice_entities_fail_closed(choices, reason: str):
    receipt = compile_typed_relation_select(PRIMARY_STEM, choices)

    assert receipt.input_valid is False
    assert receipt.status == "invalid"
    assert receipt.reason == reason
    assert receipt.goal is None
    assert receipt.goal_digest_sha256 is None


def test_unreadable_and_malformed_mapping_items_never_escape():
    class ExplodingChoices(Mapping[str, str]):
        def __getitem__(self, key: str) -> str:
            raise KeyError(key)

        def __iter__(self) -> Iterator[str]:
            return iter(())

        def __len__(self) -> int:
            return 4

        def items(self):
            raise OSError("unstable mapping")

    class MalformedItems(ExplodingChoices):
        def items(self):
            return iter([("A", "North Reach"), object()])

    exploding = compile_typed_relation_select(PRIMARY_STEM, ExplodingChoices())
    malformed = compile_typed_relation_select(PRIMARY_STEM, MalformedItems())

    assert exploding.status == "invalid"
    assert exploding.reason == "choices_unreadable"
    assert malformed.status == "invalid"
    assert malformed.reason == "choices_unreadable"


@pytest.mark.parametrize(
    "stem",
    [
        "Which country is Lake Brindle not located in?",
        "Which country except North Reach is Lake Brindle located in?",
        "Which country is Lake Brindle located closer to than South Reach?",
        "Why is Lake Brindle located in North Reach?",
        "Which country is Lake Brindle associated with?",
        "Which country is most likely Lake Brindle located in?",
        "Which country is Lake Brindle located in because of rainfall?",
    ],
)
def test_negation_except_comparative_causal_and_ambiguous_tokens_abstain(
    stem: str,
):
    receipt = compile_typed_relation_select(stem, CHOICES)

    assert looks_like_typed_relation_select(stem) is False
    assert receipt.input_valid is True
    assert receipt.status == "abstain"
    assert receipt.reason in {
        "unsupported_semantics",
        "unsupported_surface_family",
    }
    assert receipt.goal is None


@pytest.mark.parametrize(
    ("stem", "reason"),
    [
        (
            "Which molecule is Lake Brindle located in?",
            "unsupported_answer_type",
        ),
        (
            "Which country is a village located in?",
            "subject_not_named_entity",
        ),
        (
            "Which country is It located in?",
            "subject_not_named_entity",
        ),
        (
            "Where is Lake Brindle located?",
            "unsupported_surface_family",
        ),
    ],
)
def test_wrong_answer_types_generic_subjects_and_implicit_types_abstain(
    stem: str,
    reason: str,
):
    receipt = compile_typed_relation_select(stem, CHOICES)

    assert receipt.input_valid is True
    assert receipt.status == "abstain"
    assert receipt.reason == reason
    assert receipt.goal is None
    assert looks_like_typed_relation_select(stem) is False


@pytest.mark.parametrize("auxiliary", ["are", "was", "were"])
def test_plural_or_historical_auxiliaries_abstain_without_temporal_proof(
    auxiliary: str,
):
    stem = f"Which country {auxiliary} Lake Brindle located in?"
    receipt = compile_typed_relation_select(stem, CHOICES)

    assert looks_like_typed_relation_select(stem) is False
    assert receipt.input_valid is True
    assert receipt.status == "abstain"
    assert receipt.reason == "unsupported_surface_family"
    assert receipt.goal is None


def test_multiple_surface_matches_and_adapter_errors_fail_closed(monkeypatch):
    real_matches = relation._surface_matches(PRIMARY_STEM)
    assert len(real_matches) == 1

    monkeypatch.setattr(
        relation,
        "_surface_matches",
        lambda _stem: real_matches + real_matches,
    )
    duplicate = compile_typed_relation_select(PRIMARY_STEM, CHOICES)
    assert duplicate.status == "abstain"
    assert duplicate.reason == "multiple_surface_matches"
    assert duplicate.goal is None
    assert looks_like_typed_relation_select(PRIMARY_STEM) is False

    def explode(_stem):
        raise RuntimeError("adapter failure")

    monkeypatch.setattr(relation, "_surface_matches", explode)
    failed = compile_typed_relation_select(PRIMARY_STEM, CHOICES)
    assert failed.status == "abstain"
    assert failed.reason == "surface_adapter_error"
    assert failed.goal is None
    assert looks_like_typed_relation_select(PRIMARY_STEM) is False


def test_frozen_slot_types_reject_coercion_and_object_level_forgery():
    receipt = compile_typed_relation_select(PRIMARY_STEM, CHOICES)
    assert receipt.goal is not None
    goal = receipt.goal

    with pytest.raises(ValueError, match="goal"):
        replace(goal, answer_type=True)
    with pytest.raises(ValueError, match="goal"):
        replace(goal, predicate=type("StringSubclass", (str,), {})("located_in"))
    with pytest.raises(ValueError, match="choice"):
        replace(receipt.choice_items[0], normalized_entity="forged")
    with pytest.raises(ValueError, match="envelope"):
        replace(receipt, input_valid=1)
    with pytest.raises(ValueError, match="incomplete"):
        replace(
            receipt,
            surface_family=type("StringSubclass", (str,), {})(
                SCIENCE_RELATION_GOAL_FAMILY
            ),
        )

    object.__setattr__(goal, "predicate", "contained_in")
    with pytest.raises(ValueError, match="goal"):
        goal.to_dict()
    with pytest.raises(ValueError, match="goal"):
        receipt.to_dict()
    assert verify_compilation_subject_span(receipt, PRIMARY_STEM) is False


def test_nested_forged_evidence_is_revalidated_by_outer_receipt():
    receipt = compile_typed_relation_select(PRIMARY_STEM, CHOICES)
    forged = receipt.required_evidence[0]
    object.__setattr__(forged, "quarantined_allowed", True)

    with pytest.raises(ValueError, match="evidence"):
        receipt.to_dict()
    with pytest.raises(ValueError, match="evidence"):
        replace(receipt, required_evidence=(forged,))


def test_evidence_answer_type_must_match_the_goal_answer_type():
    receipt = compile_typed_relation_select(PRIMARY_STEM, CHOICES)
    forged = replace(
        receipt.required_evidence[0],
        object_answer_type="country",
    )

    with pytest.raises(ValueError, match="answer type"):
        replace(receipt, required_evidence=(forged,))


def test_alias_entry_point_is_exactly_deterministic():
    direct = compile_typed_relation_select(PRIMARY_STEM, CHOICES)
    named = compile_typed_relation_select_question(PRIMARY_STEM, CHOICES)

    assert direct.to_dict() == named.to_dict()


def test_old_relational_object_compiler_is_importable_and_behavior_is_unchanged():
    old = compile_explicit_relational_object_mcq(
        "Which country is Bellhaven located in?",
        {
            "A": "Northland",
            "B": "Southland",
            "C": "Eastland",
            "D": "Westland",
        },
    )

    assert old.schema_version == EXPLICIT_RELATIONAL_OBJECT_SCHEMA
    assert old.compiled is True
    assert old.goal is not None
    assert old.goal.subject == "Bellhaven"
    assert old.goal.relation == "located_in"
    assert old.goal.object_source == "choice_text"


def test_dataclass_constructors_reject_wrong_literal_and_boolean_types():
    receipt = compile_typed_relation_select(PRIMARY_STEM, CHOICES)
    assert receipt.goal is not None

    with pytest.raises(ValueError, match="goal"):
        TypedRelationSelectGoal(
            subject=receipt.goal.subject,
            subject_span=receipt.goal.subject_span,
            answer_type="chemical",
            predicate="located_in",
            polarity="positive",
            object_source="normalized_choice_entity",
            selection_cardinality="exactly_one_provable_choice",
            surface_id=receipt.goal.surface_id,
            compiler_rule=COMPILER_RULE,
        )
    with pytest.raises(ValueError, match="choice"):
        NormalizedRelationChoice(
            key="A",
            original_text="North Reach",
            normalized_entity=True,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="evidence"):
        RelationStageEvidenceRequirement(
            stage_schema=SCIENCE_RELATION_STAGE_SCHEMA,
            evidence_kind="typed_positive_relation_fact",
            predicate="located_in",
            subject_source="goal_subject",
            object_source="normalized_choice_entity",
            object_answer_type="province",
            object_answer_type_source="goal_answer_type",
            polarity="positive",
            original_property_id_required=True,
            object_type_evidence_required=True,
            exact_row_provenance=True,
            source_revision_required=True,
            license_required=True,
            quarantined_allowed=0,  # type: ignore[arg-type]
        )
