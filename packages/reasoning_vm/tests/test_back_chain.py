# -*- coding: utf-8 -*-
"""DELIBERATOR back-chaining engine — the System-2 spine. Proves multi-step derivation over
facts ∪ Horn rules ∪ verified kernels, each step verified (backward propose → forward confirm), and
작화0: no derivation is ever returned when the facts are absent or the chain is broken."""
from packages.reasoning_vm.deliberator.back_chain import (
    BackChainer, KernelBinding, Rule, Step, unify, unify_triple, verify_proof,
)

# a small multi-hop world (subject-indexed, exactly the store's facts_about API)
_KG = {
    "seoul": [("seoul", "capital_of", "south_korea")],
    "south_korea": [("south_korea", "located_in", "asia")],
    "asia": [("asia", "located_in", "earth")],
    "abe": [("abe", "parent_of", "homer")],
    "homer": [("homer", "parent_of", "bart")],
    "socrates": [("socrates", "is_a", "philosopher")],
    "philosopher": [("philosopher", "is_a", "human")],
}
_INHERIT = {"human": [("human", "has_property", "mortal")]}


def _fa(s):
    return _KG.get(s, [])


def _ip(t):
    return _INHERIT.get(t, [])


# ── unification ────────────────────────────────────────────────────────────────────────────────
def test_unify_binds_and_matches():
    assert unify("?x", "seoul", {}) == {"?x": "seoul"}
    assert unify("seoul", "Seoul", {}) == {}           # loose-normalized equality, no new binding
    assert unify("seoul", "busan", {}) is None
    assert unify_triple(("?a", "located_in", "?b"), ("asia", "located_in", "earth"), {}) == {
        "?a": "asia", "?b": "earth"}


# ── transitive multi-hop derivation ──────────────────────────────────────────────────────────────
def test_transitive_chain_derives_and_verifies():
    bc = BackChainer(_fa, max_depth=6)
    r = bc.can_prove("south_korea", "located_in", "earth")   # 2-hop transitive
    assert r["provable"] and r["hops"] == 2


def test_composition_capital_then_located_in():
    bc = BackChainer(_fa, max_depth=6)
    r = bc.can_prove("seoul", "located_in", "asia")          # capital_of ∘ located_in
    assert r["provable"]
    deep = bc.can_prove("seoul", "located_in", "earth")      # compose + transitive
    assert deep["provable"] and deep["hops"] >= 3


def test_custom_horn_rule_grandparent():
    bc = BackChainer(_fa, max_depth=5)
    bc.rules = bc.rules + [Rule("grandparent_of", ("?x", "grandparent_of", "?z"),
                                [("?x", "parent_of", "?y"), ("?y", "parent_of", "?z")])]
    out = bc.derive("abe", "grandparent_of")
    assert out["answer"] == "bart" and out["fired"] and out["hops"] == 2


def test_type_inheritance_syllogism():
    bc = BackChainer(_fa, inherit_props=_ip, max_depth=6)
    r = bc.can_prove("socrates", "has_property", "mortal")   # is_a* + inherit
    assert r["provable"] and r["hops"] >= 2


# ── computation kernel wiring ────────────────────────────────────────────────────────────────────
def test_kernel_binding_computes_over_derived_inputs(tmp_path, monkeypatch):
    from packages.reasoning_vm.deliberator import kernel_forge as KF
    monkeypatch.setattr(KF, "REGISTRY", tmp_path / "reg.json")
    ex = [({"protons": p, "electrons": e}, p - e) for p in range(1, 9) for e in range(0, 9)]
    assert KF.forge("net_charge", ex, ["protons", "electrons"], seed=0)["accepted"]
    kg = {"ion": [("ion", "protons", "17"), ("ion", "electrons", "18")]}
    bc = BackChainer(lambda s: kg.get(s, []),
                     kernels=[KernelBinding("net_charge", [("protons", "protons"),
                                                           ("electrons", "electrons")], "net_charge")])
    out = bc.derive("ion", "net_charge")
    assert out["answer"] == "-1" and out["fired"]            # derived, not looked up


def test_rational_kernel_derives_exact_science_value_and_replays_proof(tmp_path, monkeypatch):
    from fractions import Fraction
    from packages.evolution.rational_evolver import parse_value
    from packages.reasoning_vm.deliberator import kernel_forge as KF

    monkeypatch.setattr(KF, "REGISTRY", tmp_path / "reg.json")
    train = [
        ({"wave_speed": str(speed), "wavelength": wavelength},
         Fraction(speed) / parse_value(wavelength))
        for speed in (240_000_000, 300_000_000, 360_000_000)
        for wavelength in ("4e-7", "5e-7", "8e-7")
    ]
    holdout = [
        ({"wave_speed": str(speed), "wavelength": wavelength},
         Fraction(speed) / parse_value(wavelength))
        for speed in (270_000_000, 330_000_000)
        for wavelength in ("6.328e-7", "9e-7")
    ]
    assert KF.forge(
        "frequency_hz", train, ["wave_speed", "wavelength"],
        dsl=KF.RATIONAL_DSL, holdout_examples=holdout, max_nodes=5,
    )["accepted"]

    kg = {
        "green_light": [
            ("green_light", "wave_speed_m_per_s", "299792458"),
            ("green_light", "wavelength_m", "500e-9"),
        ],
        "invalid_wave": [
            ("invalid_wave", "wave_speed_m_per_s", "299792458"),
            ("invalid_wave", "wavelength_m", "0"),
        ],
    }
    binding = KernelBinding(
        "frequency_hz",
        [("wave_speed_m_per_s", "wave_speed"), ("wavelength_m", "wavelength")],
        "frequency_hz",
    )
    bc = BackChainer(lambda s: kg.get(s, []), kernels=[binding])
    out = bc.derive("green_light", "frequency_hz")
    assert out["answer"] == "599584916000000"
    assert out["fired"] and verify_proof(
        out["proof"], lambda s: kg.get(s, []), kernel_bindings=[binding],
    )
    # Numeric ground matching is exact and notation-independent.
    assert bc.can_prove("green_light", "frequency_hz", "5.99584916e14")["provable"]
    assert not bc.can_prove("green_light", "frequency_hz", "599584916000001")["provable"]
    assert bc.derive("invalid_wave", "frequency_hz")["answer"] is None

    reordered = BackChainer(
        lambda s: kg.get(s, []),
        kernels=[KernelBinding(
            "frequency_hz",
            [("wavelength_m", "wavelength"), ("wave_speed_m_per_s", "wave_speed")],
            "frequency_hz",
        )],
    )
    assert reordered.derive("green_light", "frequency_hz")["answer"] is None


def test_kernel_ground_goal_never_uses_punctuation_stripping(tmp_path, monkeypatch):
    from packages.reasoning_vm.deliberator import kernel_forge as KF

    monkeypatch.setattr(KF, "REGISTRY", tmp_path / "reg.json")
    train = [({"x": str(x)}, str(2 * x)) for x in (1, 2, 3)]
    holdout = [({"x": str(x)}, str(2 * x)) for x in (4, 6)]
    assert KF.forge(
        "double", train, ["x"], dsl=KF.RATIONAL_DSL,
        holdout_examples=holdout, max_nodes=3,
    )["accepted"]
    kg = {
        "item": [("item", "input", "5")],
        "other": [("other", "unrelated", "5")],
        "numeric_item": [("numeric_item", "input", "10")],
    }
    binding = KernelBinding("double_value", [("input", "x")], "double")
    bc = BackChainer(
        lambda s: kg.get(s, []),
        kernels=[binding],
    )
    assert bc.can_prove("item", "double_value", "10.0")["provable"]
    assert not bc.can_prove("item", "double_value", "1.0")["provable"]
    forged = Step(
        ("item", "double_value", "10"), "kernel", "double",
        [Step(("other", "unrelated", "5"), "fact")],
    )
    assert not verify_proof(
        forged, lambda s: kg.get(s, []), kernel_bindings=[binding],
    )
    numeric_forged = Step(
        ("numeric_item", "double_value", "2"), "kernel", "double",
        [Step(("numeric_item", "input", "1.0"), "fact")],
    )
    assert not verify_proof(
        numeric_forged, lambda s: kg.get(s, []), kernel_bindings=[binding],
    )
    assert not bc.can_prove("numeric_item", "input", "1.0")["provable"]


# ── 작화0: never fabricate ─────────────────────────────────────────────────────────────────────
def test_abstains_when_subject_absent():
    bc = BackChainer(_fa, max_depth=6)
    assert bc.derive("atlantis", "located_in")["answer"] is None
    assert not bc.can_prove("seoul", "located_in", "mars")["provable"]


def test_broken_chain_does_not_derive():
    # narnia -> nowhere, but nowhere has no onward edge: no path to earth, must abstain
    kg = {"narnia": [("narnia", "located_in", "nowhere")]}
    bc = BackChainer(lambda s: kg.get(s, []), max_depth=6)
    assert not bc.can_prove("narnia", "located_in", "earth")["provable"]


def test_verify_proof_rejects_tampered_leaf():
    bc = BackChainer(_fa, max_depth=6)
    res = bc.prove(("south_korea", "located_in", "earth"))
    assert res is not None
    _b, step = res
    assert verify_proof(step, _fa)                            # genuine proof verifies
    # tamper: swap a leaf for a fact the KB does not hold → verification must fail
    bad = Step(("south_korea", "located_in", "earth"), "rule", "transitive[located_in]",
               [Step(("south_korea", "located_in", "atlantis"), "fact"),
                Step(("atlantis", "located_in", "earth"), "fact")])
    assert not verify_proof(bad, _fa)


def test_unverified_kernel_never_fires():
    # a kernel binding whose skill is NOT in the accepted library must not produce an answer
    kg = {"ion": [("ion", "protons", "17"), ("ion", "electrons", "18")]}
    bc = BackChainer(lambda s: kg.get(s, []),
                     kernels=[KernelBinding("net_charge", [("protons", "protons"),
                                                           ("electrons", "electrons")], "no_such_kernel")])
    assert bc.derive("ion", "net_charge")["answer"] is None
