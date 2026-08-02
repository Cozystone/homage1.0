# -*- coding: utf-8 -*-
"""T1 quantitative kernel — exactness, units, scientific notation, proof, dimensional safety."""
from fractions import Fraction

from packages.reasoning_vm.quantity import (
    evaluate,
    format_number_exact,
    format_quantity_exact,
    op,
    parse_quantity,
)


def _v(expr):
    r = evaluate(expr)
    assert r is not None, expr
    return float(r.quantity.value), r.quantity.unit


def test_physics_wavelength_to_frequency():
    v, u = _v("299792458 m/s / 500e-9 m")     # c / λ
    assert abs(v - 5.99585e14) <= 5.99585e14 * 1e-4
    assert u == "1/s"                          # compound-unit cancellation m/s ÷ m


def test_chemistry_molarity_keeps_convention():
    v, u = _v("2.5 mol / 0.5 L")
    assert v == 5.0 and u == "mol/L"           # not converted to mol/m³


def test_molar_mass_unit():
    v, u = _v("100 g / 4 mol")
    assert v == 25.0 and u == "g/mol"


def test_unit_conversion_on_add():
    v, u = _v("3.0 km + 250 m")
    assert v == 3250.0 and u == "m"


def test_scientific_notation():
    v, _ = _v("6.022e23 * 2")
    assert abs(v - 1.2044e24) <= 1.2044e24 * 1e-9


def test_exact_no_float_drift():
    r = op(parse_quantity("0.1"), "+", parse_quantity("0.2"))
    assert r.quantity.value == Fraction(3, 10)   # exact, not 0.30000000000000004


def test_exact_storage_format_round_trips_decimals_and_fractions_with_units():
    assert format_number_exact(Fraction(1, 8)) == "0.125"
    assert format_number_exact(Fraction(1, 3)) == "1/3"
    q = parse_quantity("1/3 mol/L")
    assert q is not None
    assert format_quantity_exact(q) == "1/3 mol/L"
    assert parse_quantity(format_quantity_exact(q)) == q
    assert parse_quantity("1/0 m") is None
    assert parse_quantity("1/0 mol/L") is None


def test_dimensional_mismatch_refused():
    assert op(parse_quantity("3 m"), "+", parse_quantity("2 s")) is None


def test_certificate_is_auditable():
    cert = evaluate("299792458 m/s / 500e-9 m").certificate()
    assert cert["unit"] == "1/s" and len(cert["derivation"]) >= 2
    assert cert["guarantees" if "guarantees" in cert else "basis"]


def test_certificate_and_steps_keep_exact_replayable_numbers():
    result = evaluate("1 / 3")
    assert result is not None
    cert = result.certificate()
    assert cert["value"] == "1/3"
    assert parse_quantity(cert["value"]).value == Fraction(1, 3)
    assert "1/3" in cert["derivation"][-1]
    assert evaluate("1/3 m") is None


def test_large_exact_value_does_not_overflow_proof_formatting():
    result = evaluate("1e309 * 1")
    assert result is not None
    assert result.quantity.value == 10**309
    assert result.certificate()["value"] == str(10**309)
    assert evaluate("1e5000 * 1") is None
    assert format_number_exact(Fraction(1, 2**20_000)) is None


def test_legacy_bare_add_subtract_and_multiply_remain_supported():
    assert _v("3+2")[0] == 5
    assert _v("7-2")[0] == 5
    assert _v("6*7")[0] == 42
    assert _v("6/2")[0] == 3
    assert _v("100g/4mol") == (25, "g/mol")
    assert _v("100g/4") == (25, "g")
