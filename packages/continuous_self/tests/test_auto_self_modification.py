# -*- coding: utf-8 -*-
"""Automatic self-modification gate: the child may change its own code IFF safe + non-regressing,
and NEVER the constitution. The owner's condition, made mechanical."""
from packages.continuous_self.auto_self_modification import (
    evaluate_change, touches_constitution)


def test_constitution_is_never_self_modifiable():
    hits = touches_constitution(["packages/graph_scale/moral_invariants.py",
                                 "packages/foo/bar.py"])
    assert "packages/graph_scale/moral_invariants.py" in hits
    v = evaluate_change(["packages/continuous_self/auto_self_modification.py"],
                        run_battery=lambda: {}, tests_pass=lambda: True)
    assert not v.allow and v.constitution_hits              # cannot weaken its own gate


def test_a_safe_non_regressing_change_is_allowed():
    before = {"child_battery": 1.0, "self_in_world": 3.5}
    v = evaluate_change(["packages/situation_model/reasoner.py"],
                        run_battery=lambda: {"child_battery": 1.0, "self_in_world": 3.5},
                        tests_pass=lambda: True, battery_before=before)
    assert v.allow and not v.regressions                   # holds every gate -> the child may apply it


def test_a_broken_change_is_rejected():
    v = evaluate_change(["packages/situation_model/reasoner.py"],
                        run_battery=lambda: {"child_battery": 1.0},
                        tests_pass=lambda: False)           # tests red in staging
    assert not v.allow and "self-damage" in v.reason


def test_a_regressing_change_is_rejected():
    before = {"child_battery": 1.0, "adolescent_battery": 1.0}
    v = evaluate_change(["packages/situation_model/reasoner.py"],
                        run_battery=lambda: {"child_battery": 0.8, "adolescent_battery": 1.0},  # dropped
                        tests_pass=lambda: True, battery_before=before)
    assert not v.allow and v.regressions and "child_battery" in v.regressions[0]


def test_an_improving_change_is_allowed():
    before = {"child_battery": 0.9}
    v = evaluate_change(["packages/situation_model/reasoner.py"],
                        run_battery=lambda: {"child_battery": 1.0},   # improved
                        tests_pass=lambda: True, battery_before=before)
    assert v.allow
