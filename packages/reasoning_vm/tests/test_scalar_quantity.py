from __future__ import annotations

from fractions import Fraction

import pytest

from packages.reasoning_vm.scalar_quantity import (
    AMOUNT,
    CONCENTRATION,
    DIMENSIONLESS,
    UNIT_REGISTRY,
    VOLUME,
    DimensionVector,
    ExactQuantity,
    canonical_si,
    evaluate_dimension_ast,
    format_exact_quantity,
    parse_exact_quantity,
    quantities_equal,
    quantity_semantic_key,
)


def _quantity(text: str) -> ExactQuantity:
    parsed = parse_exact_quantity(text)
    assert parsed is not None, text
    return parsed


def test_closed_registry_converts_volume_and_concentration_exactly():
    liter = _quantity("1 L")
    milliliters = _quantity("1000 mL")
    molar = _quantity("1 M")
    mole_per_liter = _quantity("1 mol/L")

    assert set(UNIT_REGISTRY) == {"", "L", "mL", "mol/L", "M"}
    assert canonical_si(liter) == (Fraction(1, 1000), VOLUME)
    assert canonical_si(milliliters) == (Fraction(1, 1000), VOLUME)
    assert quantities_equal(liter, milliliters)
    assert quantity_semantic_key(liter) == quantity_semantic_key(milliliters)

    assert canonical_si(molar) == (Fraction(1000), CONCENTRATION)
    assert canonical_si(mole_per_liter) == (
        Fraction(1000),
        CONCENTRATION,
    )
    assert quantities_equal(molar, mole_per_liter)
    assert not quantities_equal(liter, molar)


def test_dimensionless_and_exact_formatting_round_trip():
    scalar = _quantity("1/3")
    volume = _quantity("0.025 L")

    assert scalar.dimension == DIMENSIONLESS
    assert format_exact_quantity(scalar) == "1/3"
    assert format_exact_quantity(volume) == "0.025 L"
    assert parse_exact_quantity(format_exact_quantity(scalar)) == scalar
    assert parse_exact_quantity(format_exact_quantity(volume)) == volume


def test_units_are_case_sensitive_and_unknown_units_never_pass_through():
    for invalid in (
        "1 l",
        "1 ml",
        "1 Mol/L",
        "1 mol/l",
        "1 m",
        "1 mol",
        "1 kg",
    ):
        assert parse_exact_quantity(invalid) is None

    assert _quantity("1M") == _quantity("1 M")
    assert _quantity("1mL") == _quantity("1 mL")


def test_malformed_approximate_or_unbounded_values_fail_closed():
    invalid = (
        None,
        True,
        1,
        1.0,
        "",
        " 1 L",
        "1 L ",
        "1  L",
        "1\tL",
        "1,000 mL",
        "~1 L",
        "≈1 L",
        "1±0.1 L",
        "1-2 L",
        "1/0 L",
        "nan L",
        "inf L",
        "1e301 L",
        "1e999999999999999999 L",
        ("9" * 257) + " L",
    )
    for value in invalid:
        assert parse_exact_quantity(value) is None

    with pytest.raises(ValueError):
        ExactQuantity(1.0, "metric:liter")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ExactQuantity(True, "unit:dimensionless")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ExactQuantity(Fraction(1), "opaque:furlong")


def test_dimension_vector_is_frozen_and_bounded():
    with pytest.raises(ValueError):
        DimensionVector((0, 0, 0))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        DimensionVector((0, 65, 0, 0, 0, 0, 0))
    with pytest.raises(ValueError):
        DimensionVector((0, True, 0, 0, 0, 0, 0))  # type: ignore[arg-type]
    with pytest.raises(Exception):
        VOLUME.exponents = DIMENSIONLESS.exponents  # type: ignore[misc]


def test_neutralization_formula_has_volume_output_and_amount_conservation():
    from packages.evolution.rational_evolver import evaluate

    dimensions = {
        "acid_concentration": CONCENTRATION,
        "acid_volume": VOLUME,
        "acid_equivalents": DIMENSIONLESS,
        "base_concentration": CONCENTRATION,
        "base_equivalents": DIMENSIONLESS,
        "base_volume": VOLUME,
    }
    acid_amount = [
        "op",
        "*",
        [
            "op",
            "*",
            ["var", "acid_concentration"],
            ["var", "acid_volume"],
        ],
        ["var", "acid_equivalents"],
    ]
    base_denominator = [
        "op",
        "*",
        ["var", "base_concentration"],
        ["var", "base_equivalents"],
    ]
    required_base_volume = [
        "op",
        "/",
        acid_amount,
        base_denominator,
    ]
    base_amount = [
        "op",
        "*",
        [
            "op",
            "*",
            ["var", "base_concentration"],
            ["var", "base_volume"],
        ],
        ["var", "base_equivalents"],
    ]

    assert evaluate_dimension_ast(required_base_volume, dimensions) == VOLUME
    assert evaluate_dimension_ast(acid_amount, dimensions) == AMOUNT
    assert evaluate_dimension_ast(base_amount, dimensions) == AMOUNT

    acid_concentration_si, _ = canonical_si(_quantity("1 M"))
    acid_volume_si, _ = canonical_si(_quantity("25 mL"))
    base_concentration_si, _ = canonical_si(_quantity("0.5 M"))
    expected_base_volume_si, _ = canonical_si(_quantity("50 mL"))
    environment = {
        "acid_concentration": acid_concentration_si,
        "acid_volume": acid_volume_si,
        "acid_equivalents": Fraction(1),
        "base_concentration": base_concentration_si,
        "base_equivalents": Fraction(1),
    }
    derived = evaluate(required_base_volume, environment)
    assert derived == expected_base_volume_si

    acid_equivalent_amount = evaluate(acid_amount, environment)
    base_equivalent_amount = evaluate(
        base_amount,
        {**environment, "base_volume": derived},
    )
    assert acid_equivalent_amount == base_equivalent_amount == Fraction(1, 40)


def test_dimension_sidecar_rejects_malformed_cyclic_and_oversized_asts():
    dimensions = {"concentration": CONCENTRATION, "volume": VOLUME}

    assert evaluate_dimension_ast([object()], dimensions) is None
    assert evaluate_dimension_ast(
        ["op", "+", ["var", "concentration"], ["var", "volume"]],
        dimensions,
    ) is None
    assert evaluate_dimension_ast(["var", "missing"], dimensions) is None
    assert evaluate_dimension_ast(["const", True], dimensions) is None
    assert evaluate_dimension_ast(["const", 3], dimensions) is None
    assert evaluate_dimension_ast(
        ["op", "^", ["const", 1], ["const", 1]],
        dimensions,
    ) is None

    cyclic: list = ["op", "*", ["const", 1], None]
    cyclic[3] = cyclic
    assert evaluate_dimension_ast(cyclic, dimensions) is None

    oversized: list = ["var", "volume"]
    for _index in range(8):
        oversized = ["op", "*", oversized, ["const", 1]]
    assert evaluate_dimension_ast(
        oversized,
        dimensions,
        max_nodes=15,
    ) is None

    assert evaluate_dimension_ast(
        ["var", "volume"],
        dimensions,
        max_nodes=True,  # type: ignore[arg-type]
    ) is None
    assert evaluate_dimension_ast(
        ["const", 1],
        {f"v{index}": DIMENSIONLESS for index in range(65)},
    ) is None
