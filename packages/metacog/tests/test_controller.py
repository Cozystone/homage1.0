# -*- coding: utf-8 -*-
"""DETECT-layer tests: an anomaly fires when a span departs from its OWN learned baseline, the single
most-urgent bottleneck is chosen, the attention-schema-for-control self-model + report are honest, and
the kill-switch yields a steady no-op with nothing journalled."""
from __future__ import annotations

import pytest

import packages.metacog.probes as pr
from packages.metacog.probes import Baselines, record_span
from packages.metacog.controller import (
    EfficiencyController, judge_span, judge_overload, judge_thrash, _urgency, Z_HOT,
)
from packages.metacog.policies import Finding, decisions_path


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ATANOR_METACOG_DIR", str(tmp_path))
    monkeypatch.setenv("ATANOR_MEC", "1")


def _warm(name: str, ms: float = 3.0, n: int = 30):
    for i in range(n):
        record_span(name, ms + (i % 3) * 0.1, ok=True)       # small realistic jitter


# ---------- anomaly fires on an injected slowdown ----------

def test_slow_span_anomaly_fires_against_own_baseline():
    _warm("solve")
    bl = Baselines.load()
    f = judge_span(bl, "solve", 30.0, ok=True)
    assert f is not None and f.kind == "slow_span"
    assert f.severity > Z_HOT
    assert f.evidence["baseline_mean"] < 5.0 and f.evidence["ms"] == 30.0


def test_no_anomaly_when_span_is_normal():
    _warm("solve")
    assert judge_span(Baselines.load(), "solve", 3.1, ok=True) is None


def test_observe_switches_strategy_on_injected_slowdown():
    _warm("solve")
    ctrl = EfficiencyController(organ_judges=False)
    dec = ctrl.observe("solve", 30.0, ok=True,
                       context={"current": "A", "alternatives": ["A", "B"]})
    assert dec.policy == "switch_strategy"
    assert dec.directive["to"] == "B" and dec.directive["from"] == "A"
    assert dec.efficiency < 0.5                               # the index collapses under the anomaly


# ---------- worst-of selection (one re-steer per tick, like the workspace bottleneck) ----------

def test_worst_finding_is_selected():
    ctrl = EfficiencyController()
    snap = {"recent_failure_rate": 0.0, "recent_samples": 20, "rss_pressure": 0.90,
            "commitment_debt": 40, "coherence": 0.9}
    # overload urgency = 0.90/0.85 ~ 1.06 ; thrash urgency = 40/8 = 5.0 -> thrash must win
    findings = ctrl._organ_findings(snap)
    kinds = {f.kind for f in findings}
    assert "overload" in kinds and "commitment_thrash" in kinds
    worst = max(findings, key=_urgency)
    assert worst.kind == "commitment_thrash"


def test_organ_judges_can_be_disabled():
    ctrl = EfficiencyController(organ_judges=False)
    snap = {"rss_pressure": 0.99, "commitment_debt": 999}
    assert ctrl._organ_findings(snap) == []


# ---------- the attention-schema-for-control self-model + report ----------

def test_schema_is_a_bounded_self_model_that_owns_its_limits():
    _warm("solve")
    sch = EfficiencyController(organ_judges=False).schema()
    assert "solve" in sch["monitoring"]
    assert "efficiency" in sch and 0.0 <= sch["efficiency"] <= 1.0
    assert "not_monitoring" in sch                            # the schema owns its blind spot
    assert "no claim" in sch["epistemic_status"].lower()      # honest about what it is


def test_report_speaks_steady_and_inefficient_states():
    _warm("solve")
    ctrl = EfficiencyController(organ_judges=False)
    steady = ctrl.observe("solve", 3.0, ok=True,
                          context={"current": "A", "alternatives": ["A", "B"]})
    assert "not intervening" in ctrl.report(steady)
    hot = ctrl.observe("solve", 40.0, ok=True,
                       context={"current": "A", "alternatives": ["A", "B"]})
    assert "inefficient" in ctrl.report(hot) and "slow_span" in ctrl.report(hot)


# ---------- kill-switch = steady no-op, nothing journalled ----------

def test_kill_switch_yields_steady_and_no_journal(monkeypatch):
    _warm("solve")                                           # baseline built while on
    monkeypatch.setenv("ATANOR_MEC", "0")
    ctrl = EfficiencyController(organ_judges=False)
    dec = ctrl.observe("solve", 999.0, ok=False,
                       context={"current": "A", "alternatives": ["A", "B"]})
    assert dec.policy == "steady"
    assert not decisions_path().exists()                     # no decision written while disabled
