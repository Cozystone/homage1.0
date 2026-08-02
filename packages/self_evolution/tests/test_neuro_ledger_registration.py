# -*- coding: utf-8 -*-
"""The orchestrator registers in the neuro ledger as a ~0-param control organ (not a fact source).

Owner fear (2026-07-22): neuro growth tipping into an LLM. The self-evolution orchestrator adds ZERO
learned parameters — it is control logic over scorecards. This pins that the neuro budget machinery
measures it at exactly 0 params and that it is not a fact source.
"""
from __future__ import annotations

from packages.neuro_ledger.ledger import measure_params
from packages.self_evolution import ledger_contribution as lc


def test_orchestrator_organ_is_zero_params_and_not_a_fact_source():
    o = lc.organ()
    assert o.fact_source is False
    m = measure_params(o)
    assert m["params"] == 0, m
    # the card is a real on-disk artifact (present) measured at 0, not a fallback guess
    assert m["present"] is True


def test_budget_check_reports_ok():
    chk = lc.budget_check()
    assert chk["params"] == 0
    assert chk["fact_source"] is False
    assert chk["ok"] is True


def test_ledger_card_carries_no_weight_arrays():
    """The persisted card must not contain float weight arrays (that is what keeps params == 0)."""
    import json
    p = lc.write_card()
    data = json.loads(p.read_text(encoding="utf-8"))
    for weight_key in ("weights", "bias", "mean", "std", "W", "b", "coef", "intercept"):
        assert weight_key not in data, weight_key
    assert data["learned_params"] == 0
    assert data["fact_source"] is False
