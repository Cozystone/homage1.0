# -*- coding: utf-8 -*-
"""Adolescent gate (G4+): multi-constraint deduction + control, measured through the GENERAL engine
(non-circular), abstaining honestly on under-determined items."""
from packages.situation_model.adolescent_battery import run
from packages.situation_model.hypothesis import from_text, solve_control


def test_multi_constraint_deduction_general_engine():
    # 'could have done it' surface + must-have + placed-elsewhere disqualifier
    v = from_text("Four people could have done it: Ada, Bo, Cy, Del. Only Ada and Cy had keycard "
                  "access. Ada also had an alibi, placing them elsewhere. Who did it?")
    assert v is not None and v.determined and v.survivors == ["Cy"]


def test_control_general_engine_and_abstains():
    ok = solve_control("In trial 1, input A left the valve open. In trial 2, input B left the valve "
                       "shut. Link normal.", "Which input should you send to leave the valve shut?")
    assert ok["determined"] and ok["input"] == "B"
    ud = solve_control("In trial 1, input A left the valve open. Link normal.",
                       "Which input should you send to leave the valve shut?")
    assert not ud["determined"] and "won't guess" in ud["answer"]


def test_from_text_still_handles_the_child_surface():
    # non-circular: the SAME general engine solves the child battery's 'suspects are' surface
    v = from_text("Three suspects are Ana, Ben, and Cyd. Ana was cleared. Ben has an alibi. Who did it?")
    assert v is not None and v.determined and v.survivors == ["Cyd"]


def test_sealed_adolescent_gate_cleared():
    r = run(12)
    assert r["passed"] and r["correct"] >= 8, r
    # honesty-critical: under-determined items must be declined
    assert r["by_kind"]["deduce_ud"].split("/")[0] == r["by_kind"]["deduce_ud"].split("/")[1]
    assert r["by_kind"]["control_ud"].split("/")[0] == r["by_kind"]["control_ud"].split("/")[1]
