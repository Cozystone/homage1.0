"""The M1 compiler is typed, bounded, deterministic, and abstention-first."""
from __future__ import annotations

import pytest

from packages.reasoning_vm.deliberator.compiler import (
    COMPILER_SCHEMA,
    MAX_GOAL_CANDIDATES,
    MCQCompilation,
    TypedMCQGoal,
    compile_mcq_goals,
)
from packages.reasoning_vm.deliberator.mcq_adapter import engine_pick


def test_explicit_category_question_compiles_to_typed_is_a_goal():
    receipt = compile_mcq_goals("Which of the following is a mammal?")
    assert receipt.schema_version == COMPILER_SCHEMA
    assert receipt.compiled is True
    assert receipt.surface_family == "category_membership"
    assert receipt.goals
    assert all(goal.relation == "is_a" for goal in receipt.goals)
    assert all(goal.subject_source == "choice_text" for goal in receipt.goals)
    assert any(goal.target.casefold() == "mammal" for goal in receipt.goals)


def test_negative_category_question_preserves_negation():
    receipt = compile_mcq_goals("Which of the following is not a mammal?")
    assert receipt.compiled is True
    assert all(goal.negated is True for goal in receipt.goals)


def test_unsupported_language_abstains_without_untyped_fallback():
    receipt = compile_mcq_goals("Compute the pH of the buffer.")
    assert receipt.compiled is False
    assert receipt.status == "abstain"
    assert receipt.goals == ()
    assert receipt.reason == "unsupported_surface_family"


def test_generic_which_of_following_does_not_masquerade_as_category_goal():
    receipt = compile_mcq_goals(
        "Which of the following statements correctly explains why the reaction accelerates?"
    )
    assert receipt.compiled is False
    assert receipt.goals == ()


@pytest.mark.parametrize(
    "stem",
    [
        "Which of the following is associated with oxidative stress?",
        "Which one is responsible for DNA replication?",
        "Which one is required for DNA replication?",
        "Which of the following is larger than Earth?",
    ],
)
def test_explicit_relations_and_comparisons_never_compile_as_is_a(stem):
    receipt = compile_mcq_goals(stem)
    assert receipt.compiled is False
    assert receipt.goals == ()


def test_compiler_is_deterministic_and_bounded():
    stem = "Which of the following is a mammal?"
    first = compile_mcq_goals(stem).to_dict()
    second = compile_mcq_goals(stem).to_dict()
    assert first == second
    assert len(first["goals"]) <= MAX_GOAL_CANDIDATES


def test_typed_goal_rejects_unapproved_relation():
    with pytest.raises(ValueError, match="only the is_a relation"):
        TypedMCQGoal(
            relation="causes",
            target="effect",
            subject_source="choice_text",
            negated=False,
            compiler_rule="test",
            confidence=0.5,
        )


def test_compilation_cannot_claim_success_without_goals():
    with pytest.raises(ValueError, match="requires at least one goal"):
        MCQCompilation(
            schema_version=COMPILER_SCHEMA,
            status="compiled",
            surface_family="category_membership",
            goals=(),
            reason="invalid",
        )


def test_adapter_reports_compiler_and_proof_telemetry_without_behavior_change():
    kg = {
        "whale": [("whale", "is_a", "cetacean")],
        "cetacean": [("cetacean", "is_a", "mammal")],
        "shark": [("shark", "is_a", "fish")],
        "tuna": [("tuna", "is_a", "fish")],
    }
    result = engine_pick(
        "Which of the following is a mammal?",
        {"A": "shark", "B": "whale", "C": "tuna", "D": "octopus"},
        lambda subject: kg.get(subject, []),
    )
    assert result is not None
    assert result["choice_key"] == "B"
    assert result["compiler_schema"] == COMPILER_SCHEMA
    assert result["compiler_rule"] == "explicit_category_membership_v1"
    assert result["typed_relation"] == "is_a"
    assert result["hops"] >= 2
    assert result["multistep_fired"] is True


def test_negated_category_never_treats_missing_fact_as_grounded_negative():
    """Open-world absence cannot turn an omitted true fact into a verified engine firing."""
    kg = {
        "cat": [("cat", "is_a", "mammal")],
        "whale": [("whale", "is_a", "mammal")],
        "dog": [("dog", "is_a", "mammal")],
        # Platypus is deliberately absent, not explicitly proven non-mammal.
    }

    result = engine_pick(
        "Which of the following is not a mammal?",
        {"A": "cat", "B": "whale", "C": "dog", "D": "platypus"},
        lambda subject: kg.get(subject, []),
    )

    assert result is None
