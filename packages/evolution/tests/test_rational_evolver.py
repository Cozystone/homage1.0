# -*- coding: utf-8 -*-
"""Exact rational DSL: safe interpretation, synthesis, and untouched-holdout admission."""
from __future__ import annotations

import json
from fractions import Fraction

from packages.evolution import rational_evolver as revo


def test_parse_value_is_exact_and_rejects_binary_float_or_nonfinite_text():
    assert revo.parse_value("0.1") == Fraction(1, 10)
    assert revo.parse_value("500e-9") == Fraction(1, 2_000_000)
    assert revo.parse_value("6.022e23") == Fraction(602_200_000_000_000_000_000_000)
    assert revo.parse_value("3/4") == Fraction(3, 4)
    for bad in (0.5, True, "nan", "inf", "1e301", "1e1,000", "1,2,3", "not-a-number"):
        assert revo.parse_value(bad) is None
    assert revo.parse_value("1e" + ("9" * 5000)) is None


def test_interpreter_is_exact_fail_closed_and_json_round_trippable():
    tree = ["op", "/", ["var", "wave_speed"], ["var", "wavelength"]]
    env = {"wave_speed": "299792458", "wavelength": "500e-9"}
    want = Fraction(599_584_916_000_000)
    assert revo.evaluate(tree, env) == want
    assert revo.evaluate(json.loads(json.dumps(tree)), env) == want
    assert revo.evaluate(tree, {"wave_speed": "1", "wavelength": "0"}) is None
    assert revo.evaluate(tree, {"wave_speed": "1"}) is None
    assert revo.evaluate(["var", "x"], None) is None
    assert revo.evaluate(["var", "x"], "not-an-env") is None
    assert revo.evaluate(["op", "pow", ["const", 2], ["const", 3]], {}) is None
    assert revo.evaluate(tree, env, max_nodes=2) is None
    cyclic = ["op", "+", ["const", 1], None]
    cyclic[3] = cyclic
    assert revo.evaluate(cyclic, {}) is None


def test_synthesis_finds_frequency_formula_and_passes_explicit_sealed_holdout():
    train = [
        ({"wave_speed": speed, "wavelength": wavelength},
         Fraction(speed) / revo.parse_value(wavelength))
        for speed in (240_000_000, 300_000_000, 360_000_000)
        for wavelength in ("4e-7", "5e-7", "8e-7")
    ]
    holdout = [
        ({"wave_speed": speed, "wavelength": wavelength},
         Fraction(speed) / revo.parse_value(wavelength))
        for speed in (270_000_000, 330_000_000)
        for wavelength in ("6.328e-7", "9e-7")
    ]
    out = revo.synthesize_verified(train, holdout, ["wave_speed", "wavelength"], max_nodes=5)
    assert out["accepted"], out
    assert out["holdout_fitness"] == 1.0
    assert revo.evaluate(out["tree"], {
        "wave_speed": "299792458", "wavelength": "500e-9",
    }) == Fraction(599_584_916_000_000)


def test_synthesis_rejects_noise_at_the_holdout_boundary():
    train = [
        ({"a": "1", "b": "2"}, "7"),
        ({"a": "2", "b": "3"}, "11"),
        ({"a": "3", "b": "5"}, "19"),
        ({"a": "5", "b": "8"}, "31"),
    ]
    holdout = [
        ({"a": "7", "b": "11"}, "2"),
        ({"a": "11", "b": "13"}, "97"),
    ]
    out = revo.synthesize_verified(
        train, holdout, ["a", "b"], max_nodes=5, max_states=2_000,
    )
    assert not out["accepted"]


def test_holdout_validation_checks_every_input_even_when_program_ignores_it():
    train = [
        ({"x": "1", "unused": "11"}, "1"),
        ({"x": "2", "unused": "12"}, "2"),
        ({"x": "3", "unused": "13"}, "3"),
    ]
    holdout = [
        ({"x": "4", "unused": 0.5}, "4"),
        ({"x": "5", "unused": "15"}, "5"),
    ]
    out = revo.synthesize_verified(train, holdout, ["x", "unused"], max_nodes=3)
    assert not out["accepted"]
    assert out["verdict"] == "invalid train or holdout example"


def test_train_holdout_must_be_disjoint_after_exact_canonicalization():
    train = [
        ({"x": "1", "y": "2"}, "3"),
        ({"x": "2", "y": "3"}, "5"),
    ]
    holdout = [
        ({"x": "1.0", "y": "2/1"}, "3.0"),
        ({"x": "4", "y": "5"}, "9"),
    ]
    out = revo.synthesize_verified(train, holdout, ["x", "y"], max_nodes=3)
    assert not out["accepted"]
    assert "overlap" in out["verdict"]


def test_example_digest_is_numeric_canonical_and_order_independent():
    left = [
        ({"x": "1.0", "y": "2/1"}, "3.00"),
        ({"x": "4", "y": "5"}, "9"),
    ]
    right = [
        ({"y": "5.0", "x": "4/1"}, "9/1"),
        ({"y": "2", "x": "1"}, "3"),
    ]
    assert revo.examples_digest(left, ["x", "y"]) == revo.examples_digest(right, ["x", "y"])


def test_state_budget_is_enforced_before_admitting_a_new_candidate():
    out = revo.evolve(
        [({"x": "10"}, "2"), ({"x": "11"}, "2")],
        ["x"],
        max_nodes=1,
        max_states=1,
    )
    assert not out["solved"]
    assert out["states"] == 1
    assert out["verdict"] == "state budget exhausted"


def test_malformed_variable_and_example_shapes_fail_closed():
    examples = [({"x": "1"}, "1"), ({"x": "2"}, "2")]
    for bad_vars in ([1], [["x"]], ["x", "x"]):
        assert not revo.evolve(examples, bad_vars)["solved"]
        assert not revo.synthesize_verified(examples, examples, bad_vars)["accepted"]
    assert not revo.evolve([("not-an-example",)], ["x"])["solved"]


def test_scalar_subclasses_are_rejected_at_the_verifier_boundary():
    class HostileFraction(Fraction):
        @property
        def numerator(self):
            return 1

        @property
        def denominator(self):
            return 1

        def __eq__(self, _other):
            return True

        def __hash__(self):
            return 0

    hostile = HostileFraction(999)
    assert revo.parse_value(hostile) is None
    assert revo.parse_value(type("HostileInt", (int,), {})(999)) is None
    assert revo.parse_value(type("HostileStr", (str,), {})("999")) is None
    train = [({"x": "1"}, hostile), ({"x": "2"}, hostile)]
    holdout = [({"x": "3"}, hostile), ({"x": "4"}, hostile)]
    out = revo.synthesize_verified(train, holdout, ["x"], max_nodes=1)
    assert not out["accepted"]
