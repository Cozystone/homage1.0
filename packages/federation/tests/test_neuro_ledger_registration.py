# -*- coding: utf-8 -*-
"""The federation orchestrator registers in the neuro ledger as a ~0-param control organ.

Owner fear (2026-07-22): the No-LLM brain silently growing into an LLM. Federation adds ZERO learned
parameters — it moves capability STRUCTURE between nodes and judges it with a deterministic interpreter.
This pins that the neuro budget measures it at exactly 0 params and that it is not a fact source.
"""
from __future__ import annotations

import json

from packages.neuro_ledger.ledger import measure_params
from packages.federation import ledger_contribution as lc


def test_orchestrator_organ_is_zero_params_and_not_a_fact_source():
    o = lc.organ()
    assert o.fact_source is False
    m = measure_params(o)
    assert m["params"] == 0, m
    assert m["present"] is True                    # a real on-disk card measured at 0, not a fallback


def test_budget_check_reports_ok():
    chk = lc.budget_check()
    assert chk["params"] == 0
    assert chk["fact_source"] is False
    assert chk["ok"] is True


def test_ledger_card_carries_no_weight_arrays():
    p = lc.write_card()
    data = json.loads(p.read_text(encoding="utf-8"))
    for weight_key in ("weights", "bias", "mean", "std", "W", "b", "coef", "intercept"):
        assert weight_key not in data, weight_key
    assert data["learned_params"] == 0
    assert data["fact_source"] is False


def test_promoted_organ_param_footprint_is_accounted():
    """Schemas/routers carry 0 learned params; a promoted organ-param's weights are counted so an
    adopting node's budget can add them honestly."""
    layer = {
        "location_tracking": {"capability_kind": "schema", "payload": {"rules": []}},
        "linear_sep": {"capability_kind": "organ-param",
                       "payload": {"weights": [0.1, 0.2, 0.3], "bias": 0.0}},
    }
    fp = lc.promoted_param_footprint(layer)
    assert fp["organ_param_total"] == 4            # 3 weights + 1 bias
    assert fp["per_capability"] == [{"capability_id": "linear_sep", "params": 4}]
