from __future__ import annotations

from collections.abc import Iterator, Mapping
from fractions import Fraction

import pytest

from packages.reasoning_vm.deliberator.science_quantity_goal import (
    FORMULA_ID,
    SCIENCE_QUANTITY_GOAL_SCHEMA,
    compile_neutralization_question,
    looks_like_complete_neutralization,
    verify_compilation_source_spans,
)


HCL_NAOH_STEM = (
    "What volume of 0.200 M NaOH is required to completely neutralize "
    "25.0 mL of 0.100 M HCl?"
)
HCL_NAOH_CHOICES = {
    "A": "6.25 mL",
    "B": "12.5 mL",
    "C": "25.0 mL",
    "D": "50.0 mL",
}


def test_independent_paraphrase_compiles_to_one_exact_typed_goal():
    receipt = compile_neutralization_question(
        HCL_NAOH_STEM,
        HCL_NAOH_CHOICES,
    )

    assert receipt.schema_version == SCIENCE_QUANTITY_GOAL_SCHEMA
    assert receipt.input_valid is True
    assert receipt.compiled is True
    assert receipt.goal is not None
    assert receipt.goal.known_species == "HCl"
    assert receipt.goal.target_species == "NaOH"
    assert receipt.goal.known_concentration_mol_per_liter == Fraction(1, 10)
    assert receipt.goal.target_concentration_mol_per_liter == Fraction(1, 5)
    assert receipt.goal.known_volume_liters == Fraction(1, 40)
    assert receipt.goal.known_role_required == "acid"
    assert receipt.goal.target_role_required == "base"
    assert receipt.goal.unknown_quantity == "base_volume"
    assert receipt.goal.result_dimension == "volume"
    assert receipt.goal.result_unit == "L"
    assert receipt.goal.formula_id == FORMULA_ID
    assert len(receipt.required_evidence) == 3
    assert {
        item.subject_role for item in receipt.required_evidence
    } == {"known_species", "target_species", "formula"}
    assert all(
        item.exact_row_provenance
        and item.source_revision_required
        and item.license_required
        and not item.quarantined_allowed
        for item in receipt.required_evidence
    )
    assert len(receipt.input_fingerprint) == 64
    assert len(receipt.goal_digest_sha256 or "") == 64
    assert len(receipt.goal.source_spans) == 5
    assert verify_compilation_source_spans(receipt, HCL_NAOH_STEM) is True
    assert verify_compilation_source_spans(
        receipt,
        HCL_NAOH_STEM.replace("25.0 mL", "50.0 mL"),
    ) is False


def test_mol_per_liter_and_liters_are_normalized_without_float():
    stem = (
        "How many liters of 0.500 mol/L Ca(OH)2 are needed to fully "
        "neutralize 0.125 L of 0.250 mol/L H2SO4?"
    )
    choices = {
        "A": "0.015625 L",
        "B": "0.03125 L",
        "C": "0.0625 L",
        "D": "0.125 L",
    }
    receipt = compile_neutralization_question(stem, choices)

    assert receipt.compiled is True
    assert receipt.goal is not None
    assert receipt.goal.known_species == "H2SO4"
    assert receipt.goal.target_species == "Ca(OH)2"
    assert receipt.goal.known_volume_liters == Fraction(1, 8)
    assert [item.value_liters for item in receipt.choice_items] == [
        Fraction(1, 64),
        Fraction(1, 32),
        Fraction(1, 16),
        Fraction(1, 8),
    ]
    assert all(type(item.value_liters) is Fraction for item in receipt.choice_items)
    assert receipt.to_dict()["choice_items"][1]["value_liters"] == "1/32"


def test_neutralize_completely_surface_and_router_predicate_are_supported():
    stem = (
        "How many milliliters of 0.400 M KOH does it take to neutralize "
        "completely 20 mL of 0.200 M HCl?"
    )
    choices = {
        "A": "5 mL",
        "B": "10 mL",
        "C": "20 mL",
        "D": "40 mL",
    }

    assert looks_like_complete_neutralization(stem) is True
    assert compile_neutralization_question(stem, choices).compiled is True
    assert looks_like_complete_neutralization(
        "What is the pH after completely neutralizing the acid?"
    ) is False
    assert looks_like_complete_neutralization(None) is False


def test_mapping_is_consumed_by_one_bounded_items_read():
    class OneReadChoices(Mapping[str, str]):
        def __init__(self, rows: list[tuple[str, str]]) -> None:
            self._rows = rows
            self.items_reads = 0

        def __getitem__(self, key: str) -> str:
            raise AssertionError("snapshot must not re-index the mapping")

        def __iter__(self) -> Iterator[str]:
            raise AssertionError("snapshot must use the one items read")

        def __len__(self) -> int:
            return len(self._rows)

        def items(self) -> Iterator[tuple[str, str]]:
            self.items_reads += 1
            if self.items_reads != 1:
                raise AssertionError("mapping was read more than once")
            return iter(self._rows)

    choices = OneReadChoices(list(HCL_NAOH_CHOICES.items()))
    receipt = compile_neutralization_question(HCL_NAOH_STEM, choices)

    assert receipt.compiled is True
    assert choices.items_reads == 1


def test_choice_order_does_not_change_input_or_goal_identity():
    first = compile_neutralization_question(
        HCL_NAOH_STEM,
        {
            "D": "50.0 mL",
            "B": "12.5 mL",
            "A": "6.25 mL",
            "C": "25.0 mL",
        },
    )
    second = compile_neutralization_question(
        HCL_NAOH_STEM,
        HCL_NAOH_CHOICES,
    )

    assert first.to_dict() == second.to_dict()
    assert first.input_fingerprint == second.input_fingerprint
    assert first.goal_digest_sha256 == second.goal_digest_sha256
    with pytest.raises(TypeError):
        first.constraints[0]["kind"] = "forged"


@pytest.mark.parametrize(
    ("choices", "reason"),
    [
        (
            {
                "A": "12.5 mL",
                "B": "12.500 mL",
                "C": "25 mL",
                "D": "50 mL",
            },
            "duplicate_normalized_choices",
        ),
        (
            {
                "A": "10 mL",
                "B": "0.020 L",
                "C": "30 mL",
                "D": "40 mL",
            },
            "mixed_choice_volume_units",
        ),
        (
            {
                "A": "10 mL",
                "B": "20 grams",
                "C": "30 mL",
                "D": "40 mL",
            },
            "choice_not_exact_volume",
        ),
        (
            {
                "A": "0 mL",
                "B": "20 mL",
                "C": "30 mL",
                "D": "40 mL",
            },
            "choice_volume_out_of_bounds",
        ),
        (
            {
                "A": "10 mL",
                "B": "20 mL",
                "C": "30 mL",
                "D": "100000000 mL",
            },
            "choice_volume_out_of_bounds",
        ),
    ],
)
def test_duplicate_dimension_unit_and_bound_controls_fail_closed(
    choices: dict[str, str],
    reason: str,
):
    receipt = compile_neutralization_question(HCL_NAOH_STEM, choices)

    assert receipt.input_valid is False
    assert receipt.status == "invalid"
    assert receipt.reason == reason
    assert receipt.goal is None
    assert receipt.choice_items == ()


@pytest.mark.parametrize(
    "stem",
    [
        (
            "What volume of 0.200 M NaOH is required to partially neutralize "
            "25.0 mL of 0.100 M HCl?"
        ),
        (
            "What pH results when 0.200 M NaOH is used to completely "
            "neutralize 25.0 mL of 0.100 M HCl?"
        ),
        (
            "What volume of a buffer is needed to completely neutralize "
            "25.0 mL of 0.100 M HCl?"
        ),
        (
            "What volume of 0.200 N NaOH is required to completely neutralize "
            "25.0 mL of 0.100 N HCl?"
        ),
        (
            "What mass of NaOH is required to completely neutralize "
            "25.0 mL of 0.100 M HCl?"
        ),
        (
            "What volume of 0.200 M NaOH is required to neutralize a mixture "
            "containing 25.0 mL of 0.100 M HCl?"
        ),
    ],
)
def test_unsupported_partial_ph_buffer_mixture_normality_and_mass_abstain(
    stem: str,
):
    receipt = compile_neutralization_question(stem, HCL_NAOH_CHOICES)

    assert receipt.input_valid is True
    assert receipt.status == "abstain"
    assert receipt.compiled is False
    assert receipt.goal_digest_sha256 is None


def test_nonpositive_or_excessive_stem_scalars_are_invalid_not_computed():
    zero = compile_neutralization_question(
        (
            "What volume of 0 M NaOH is required to completely neutralize "
            "25.0 mL of 0.100 M HCl?"
        ),
        HCL_NAOH_CHOICES,
    )
    excessive = compile_neutralization_question(
        (
            "What volume of 0.200 M NaOH is required to completely neutralize "
            "1001 L of 0.100 M HCl?"
        ),
        {
            "A": "1 L",
            "B": "2 L",
            "C": "3 L",
            "D": "4 L",
        },
    )

    assert zero.status == "invalid"
    assert zero.reason == "concentration_out_of_bounds"
    assert excessive.status == "invalid"
    assert excessive.reason == "known_volume_out_of_bounds"


def test_malformed_envelope_is_stable_and_fail_closed():
    cases = [
        (None, HCL_NAOH_CHOICES, "stem_not_string"),
        (" " + HCL_NAOH_STEM, HCL_NAOH_CHOICES, "stem_out_of_bounds"),
        (HCL_NAOH_STEM, None, "choices_not_mapping"),
        (HCL_NAOH_STEM, {"A": "10 mL"}, "choice_count_out_of_bounds"),
    ]
    for stem, choices, reason in cases:
        first = compile_neutralization_question(stem, choices)
        second = compile_neutralization_question(stem, choices)
        assert first.status == "invalid"
        assert first.input_valid is False
        assert first.reason == reason
        assert first.input_fingerprint == second.input_fingerprint


def test_unreadable_mapping_fails_closed_without_exception():
    class ExplodingChoices(Mapping[str, str]):
        def __getitem__(self, key: str) -> str:
            raise KeyError(key)

        def __iter__(self) -> Iterator[str]:
            return iter(())

        def __len__(self) -> int:
            return 4

        def items(self):
            raise RuntimeError("mapping changed")

    receipt = compile_neutralization_question(
        HCL_NAOH_STEM,
        ExplodingChoices(),
    )

    assert receipt.status == "invalid"
    assert receipt.reason == "choices_unreadable"
