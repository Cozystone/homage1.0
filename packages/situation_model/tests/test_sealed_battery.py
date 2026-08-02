# -*- coding: utf-8 -*-
"""The sealed child-gate battery (G3/G4): the engines must clear >=12/20 on generated novel worlds
across unrelated domains, with honest abstention on the unanswerable items."""
from packages.situation_model.sealed_battery import generate, run


def test_generator_covers_all_kinds_with_disjoint_surface():
    items = generate(20)
    kinds = {it.kind for it in items}
    assert {"who", "what", "order", "yesno", "deduce", "abstain"} <= kinds
    # unanswerable items carry no key (must be abstained on)
    assert any(it.key is None for it in items)


def test_child_gate_is_cleared_and_abstention_holds():
    r = run(20)
    assert r["passed"] and r["correct"] >= 12, r
    # the honesty-critical class: designed-unanswerable items must be declined, not answered
    assert r["by_kind"]["abstain"].split("/")[0] == r["by_kind"]["abstain"].split("/")[1]


def test_reproducible_no_rng():
    assert run(20)["correct"] == run(20)["correct"]     # deterministic — a sealed set, re-scorable
