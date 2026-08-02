from __future__ import annotations

from collections.abc import Mapping
import pytest

from packages.reasoning_vm.deliberator.science_goal import (
    SCIENCE_GOAL_SCHEMA,
    compile_science_question,
)


CHOICES = {"A": "1", "B": "2", "C": "8", "D": "10"}


def test_declared_atomic_number_surfaces_compile_to_one_typed_goal():
    surfaces = {
        "What is the atomic number of oxygen?": "atomic_number_what_is",
        "Which number is the atomic number of oxygen?": (
            "atomic_number_which_number"
        ),
        "Oxygen has which atomic number?": "atomic_number_has_which",
        "Select the atomic number of oxygen.": "atomic_number_select",
    }
    for question, family in surfaces.items():
        receipt = compile_science_question(question, CHOICES)
        assert receipt.schema_version == SCIENCE_GOAL_SCHEMA
        assert receipt.input_valid is True
        assert receipt.compiled is True
        assert receipt.surface_family == family
        assert receipt.goals[0].subject == "oxygen"
        assert receipt.goals[0].relation == "atomic_number"
        assert receipt.goals[0].object_source == "choice_text"
        assert receipt.quantities[0].number_kind == "integer"
        assert receipt.quantities[0].unit == "dimensionless"
        assert receipt.required_evidence[0].exact_row_provenance is True
        assert receipt.required_evidence[0].quarantined_allowed is False
        assert len(receipt.input_fingerprint) == 64
        assert len(receipt.goal_digest_sha256 or "") == 64


def test_compilation_replays_with_stable_input_and_goal_digests():
    first = compile_science_question(
        "What is the atomic number of oxygen?",
        {"D": "10", "B": "2", "A": "1", "C": "8"},
    )
    second = compile_science_question(
        "What is the atomic number of oxygen?",
        {"A": "1", "B": "2", "C": "8", "D": "10"},
    )
    assert first.to_dict() == second.to_dict()
    digest = first.goal_digest_sha256
    with pytest.raises(TypeError):
        first.constraints[0]["kind"] = "forged"
    assert first.goal_digest_sha256 == digest


def test_well_formed_unsupported_question_stays_in_evaluator_denominator():
    receipt = compile_science_question(
        "What is the boiling point of iron?",
        {"A": "1811 K", "B": "3134 K", "C": "26 K", "D": "56 K"},
    )
    assert receipt.input_valid is True
    assert receipt.compiled is False
    assert receipt.status == "abstain"
    assert receipt.reason == "unsupported_goal_family"
    assert receipt.input_fingerprint
    assert receipt.goal_digest_sha256 is None

    ten_choice = compile_science_question(
        "Which unsupported scientific explanation best fits the observation?",
        {str(index): f"candidate explanation {index}" for index in range(10)},
    )
    assert ten_choice.input_valid is True
    assert ten_choice.status == "abstain"


def test_duplicate_or_nonexact_atomic_choices_fail_closed():
    duplicate = compile_science_question(
        "What is the atomic number of hydrogen?",
        {"A": "1", "B": "1", "C": "2", "D": "8"},
    )
    assert duplicate.input_valid is False
    assert duplicate.status == "invalid"
    assert duplicate.reason == "duplicate_normalized_choices"

    noninteger = compile_science_question(
        "What is the atomic number of hydrogen?",
        {"A": "1", "B": "2.0", "C": "8", "D": "10"},
    )
    assert noninteger.input_valid is False
    assert noninteger.reason == "atomic_number_choice_not_exact_integer"

    mass_number_distractor = compile_science_question(
        "What is the atomic number of hydrogen?",
        {"A": "1", "B": "2", "C": "8", "D": "238"},
    )
    assert mass_number_distractor.compiled is True


def test_global_input_envelope_preserves_case_sensitive_science_notation():
    receipt = compile_science_question(
        (
            "In minks, which parental genotypes could produce silver "
            "offspring?"
        ),
        {
            "A": "Bb BB",
            "B": "BB Bb",
            "C": "Bb Bb",
            "D": "bb bb",
        },
    )
    assert receipt.input_valid is True
    assert receipt.status == "abstain"
    assert receipt.reason == "unsupported_goal_family"


def test_unknown_entity_compiles_but_is_not_resolved_by_the_compiler():
    receipt = compile_science_question(
        "What is the atomic number of unobtainium?",
        {"A": "42", "B": "92", "C": "118", "D": "119"},
    )
    assert receipt.input_valid is True
    assert receipt.compiled is True
    assert receipt.goals[0].subject == "unobtainium"


def test_malformed_inputs_get_stable_invalid_receipts_without_exceptions():
    cases = [
        (None, CHOICES, "stem_not_string"),
        (" What is the atomic number of oxygen?", CHOICES, "stem_out_of_bounds"),
        ("What is the atomic number of oxygen?", None, "choices_not_mapping"),
        (
            "What is the atomic number of oxygen?",
            {"A": "1"},
            "choice_count_out_of_bounds",
        ),
    ]
    for stem, choices, expected_reason in cases:
        first = compile_science_question(stem, choices)
        second = compile_science_question(stem, choices)
        assert first.status == "invalid"
        assert first.input_valid is False
        assert first.reason == expected_reason
        assert first.input_fingerprint == second.input_fingerprint


def test_unreadable_mapping_fails_closed_after_one_bounded_read():
    class ExplodingChoices(Mapping):
        def __getitem__(self, key):
            raise KeyError(key)

        def __iter__(self):
            return iter(())

        def __len__(self):
            return 4

        def items(self):
            raise RuntimeError("mapping changed")

    first = compile_science_question(
        "What is the atomic number of oxygen?",
        ExplodingChoices(),
    )
    second = compile_science_question(
        "What is the atomic number of oxygen?",
        ExplodingChoices(),
    )
    assert first.status == "invalid"
    assert first.reason == "choices_unreadable"
    assert first.input_fingerprint == second.input_fingerprint
