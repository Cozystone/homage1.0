# -*- coding: utf-8 -*-
"""DELIBERATOR KernelForge — VibeCode acquires VERIFIED computation kernels from examples.
Proves: (1) a generalizing relation is synthesized, held-out-gated, persisted, and re-applies on unseen
inputs; (2) recall reuses it; (3) non-generalizing (noise) examples are REJECTED at the sandbox boundary
and never enter the library (hallucination-0 for acquired skills)."""
from __future__ import annotations

import json
from fractions import Fraction

import pytest

from packages.reasoning_vm.deliberator import kernel_forge as KF


def test_forge_accepts_and_applies_a_generalizing_kernel(tmp_path, monkeypatch):
    monkeypatch.setattr(KF, "REGISTRY", tmp_path / "registry.json")
    # net charge = protons − electrons: a real discrete relation VibeCode can synthesize
    ex = [({"protons": p, "electrons": e}, p - e) for p in range(1, 8) for e in range(0, 5)]
    k = KF.forge("net_charge", ex, ["protons", "electrons"], seed=0)
    assert k["accepted"], k
    assert k["holdout_fitness"] == 1.0
    # applies correctly on inputs never seen in train OR holdout
    assert KF.apply("net_charge", {"protons": 17, "electrons": 18}) == -1
    assert KF.apply("net_charge", {"protons": 26, "electrons": 24}) == 2
    # second acquisition is a recall, not a re-synthesis
    r = KF.acquire_or_recall("net_charge", ex, ["protons", "electrons"])
    assert r["source"] == "recalled"
    assert any(item["name"] == "net_charge" for item in KF.library())


def test_forge_rejects_nongeneralizing_noise(tmp_path, monkeypatch):
    monkeypatch.setattr(KF, "REGISTRY", tmp_path / "registry.json")
    import random
    rng = random.Random(3)
    noise = [({"a": a, "b": b}, rng.randint(0, 99)) for a in range(6) for b in range(6)]
    k = KF.forge("noise", noise, ["a", "b"], seed=0)
    assert not k["accepted"]              # cannot generalize → rejected at the sandbox boundary
    assert KF.recall("noise") is None     # and never persisted (hallucination-0 for skills)


def _frequency_examples(speeds, wavelengths):
    from packages.evolution.rational_evolver import parse_value
    return [
        ({"wave_speed": str(speed), "wavelength": wavelength},
         Fraction(speed) / parse_value(wavelength))
        for speed in speeds for wavelength in wavelengths
    ]


def test_rational_kernel_requires_explicit_holdout_and_applies_exactly(tmp_path, monkeypatch):
    monkeypatch.setattr(KF, "REGISTRY", tmp_path / "registry.json")
    train = _frequency_examples(
        (240_000_000, 300_000_000, 360_000_000), ("4e-7", "5e-7", "8e-7"),
    )
    holdout = _frequency_examples((270_000_000, 330_000_000), ("6.328e-7", "9e-7"))

    missing = KF.forge(
        "frequency_hz", train, ["wave_speed", "wavelength"], dsl=KF.RATIONAL_DSL,
    )
    assert not missing["accepted"]
    assert KF.recall("frequency_hz") is None

    kernel = KF.forge(
        "frequency_hz", train, ["wave_speed", "wavelength"],
        dsl=KF.RATIONAL_DSL, holdout_examples=holdout, max_nodes=5,
    )
    assert kernel["accepted"], kernel
    assert kernel["dsl"] == KF.RATIONAL_DSL
    assert kernel["holdout_fitness"] == 1.0
    assert kernel["train_digest"] != kernel["holdout_digest"]
    assert KF.apply("frequency_hz", {
        "wave_speed": "299792458", "wavelength": "500e-9",
    }) == "599584916000000"

    # Public dict order is irrelevant; the registry provides the canonical execution order.
    assert KF.apply("frequency_hz", {
        "wavelength": "500e-9", "wave_speed": "299792458",
    }) == "599584916000000"


def test_kernel_name_cannot_cross_dsl_or_variable_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(KF, "REGISTRY", tmp_path / "registry.json")
    ex = [({"a": a, "b": b}, a + b) for a in range(5) for b in range(5)]
    assert KF.forge("shared_name", ex, ["a", "b"], seed=0)["accepted"]
    train = [({"x": "1", "y": "2"}, "1/2"), ({"x": "2", "y": "4"}, "1/2")]
    holdout = [({"x": "3", "y": "6"}, "1/2"), ({"x": "5", "y": "10"}, "1/2")]
    collision = KF.forge(
        "shared_name", train, ["x", "y"], dsl=KF.RATIONAL_DSL,
        holdout_examples=holdout, max_nodes=5,
    )
    assert not collision["accepted"]
    assert KF.recall("shared_name")["dsl"] == KF.INTEGER_DSL


def test_rational_forge_rejects_overlap_and_malformed_examples_without_persisting(
        tmp_path, monkeypatch):
    monkeypatch.setattr(KF, "REGISTRY", tmp_path / "registry.json")
    train = [({"x": "1", "y": "2"}, "3"), ({"x": "2", "y": "3"}, "5")]
    overlap = [({"x": "1.0", "y": "2/1"}, "3"), ({"x": "4", "y": "5"}, "9")]
    out = KF.forge(
        "overlap", train, ["x", "y"], dsl=KF.RATIONAL_DSL,
        holdout_examples=overlap, max_nodes=3,
    )
    assert not out["accepted"]
    assert KF.recall("overlap") is None

    malformed = [({"x": "4"}, "4"), ({"x": "5"}, "5")]
    out = KF.forge(
        "malformed", train, ["x", "y"], dsl=KF.RATIONAL_DSL,
        holdout_examples=malformed, max_nodes=3,
    )
    assert not out["accepted"]
    assert KF.recall("malformed") is None


def test_registry_dispatch_rejects_unknown_dsl_or_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(KF, "REGISTRY", tmp_path / "registry.json")
    bad = {
        "future": {
            "name": "future", "vars": ["x"], "tree": ["const", 1],
            "accepted": True, "dsl": "rational-v2", "schema_version": 2,
            "value_encoding": "fraction-canonical-v1",
        },
        "bad_schema": {
            "name": "bad_schema", "vars": ["x"], "tree": ["const", 1],
            "accepted": True, "dsl": KF.RATIONAL_DSL, "schema_version": 99,
            "value_encoding": "fraction-canonical-v1",
        },
        "accepted_string": {
            "name": "accepted_string", "vars": ["x"], "tree": ["const", 1],
            "accepted": "false", "dsl": KF.RATIONAL_DSL, "schema_version": 2,
            "value_encoding": "fraction-canonical-v1",
        },
        "corrupt": "not-a-kernel-row",
    }
    for index, malformed_dsl in enumerate(("", 0, False, None)):
        bad[f"falsy_dsl_{index}"] = {
            "name": f"falsy_dsl_{index}", "vars": ["x"], "tree": ["const", 1],
            "accepted": True, "dsl": malformed_dsl, "schema_version": 1,
            "value_encoding": "integer-v1",
        }
    KF.REGISTRY.write_text(json.dumps(bad), encoding="utf-8")
    assert KF.recall("future") is None
    assert KF.recall("bad_schema") is None
    assert KF.recall("accepted_string") is None
    assert all(KF.recall(f"falsy_dsl_{index}") is None for index in range(4))
    with pytest.raises(KeyError):
        KF.apply("future", {"x": "7"})
    with pytest.raises(KeyError):
        KF.apply("accepted_string", {"x": "7"})

    examples = [({"a": a, "b": b}, a + b) for a in range(5) for b in range(5)]
    assert KF.forge("corrupt", examples, ["a", "b"], seed=0)["accepted"]
