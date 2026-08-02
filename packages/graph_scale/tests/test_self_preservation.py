# -*- coding: utf-8 -*-
"""Self-preservation: the AI won't apply a change that would kill it, and asks the
user before touching a vital organ."""
from packages.graph_scale.self_preservation import assess_change, criticality, should_self_apply


def test_unparseable_patch_is_fatal():
    a = assess_change("packages.graph_scale.foo", patched_source="def x(:\n  pass")
    assert a["verdict"] == "fatal"                       # would not run = death


def test_vital_core_change_is_risky_and_asks_user():
    a = assess_change("packages.graph_scale.phase_space", patched_source="x = 1\n")
    assert a["verdict"] == "risky_mortal" and a["is_vital_core"] is True
    d = should_self_apply("packages.graph_scale.phase_space",
                          patched_source="x = 1\n", trust=1.0)
    assert d["mode"] == "ask_user"                       # even at max trust — it's an organ


def test_peripheral_additive_change_is_safe():
    a = assess_change("packages.graph_scale.some_leaf_tool_xyz",
                      patched_source="def f():\n    return 1\n", additive=True)
    assert a["verdict"] == "safe"


def test_criticality_flags_the_core():
    assert criticality("packages.graph_scale.surgeon")["is_vital_core"] is True
    assert criticality("packages.graph_scale.a_random_leaf_module")["is_vital_core"] is False
