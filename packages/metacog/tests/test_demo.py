# -*- coding: utf-8 -*-
"""LIVE-PROOF tests: the policy switch improves measured throughput on the identical task stream, the
kill-switch produces zero behaviour change (no switch), decisions carry evidence, and no unbounded
action is ever emitted during the run."""
from __future__ import annotations

import json
import os

import pytest

from packages.metacog.demo import run_demo
from packages.metacog.controller import EfficiencyController
from packages.metacog.probes import Baselines, record_span, baselines_path
from packages.metacog.policies import WHITELIST, BACKOFF_CAP_MS, REALLOCATE_MIN_SCALE


# ---------- the headline: re-steer improves measured throughput ----------

def test_switch_improves_measured_throughput():
    r = run_demo(seed=7)
    assert r.switch_tick is not None                          # MEC detected and switched
    assert r.detection["sigma"] > 4.0                         # a real anomaly vs its own baseline
    assert r.mec_on_throughput > r.mec_off_throughput         # re-steering bought throughput
    assert r.improvement > 3.0                                # slow lane ~25ms vs fast ~3ms -> multi-x
    assert r.mec_on_failrate < r.mec_off_failrate             # and it left the failing lane


def test_demo_is_reproducible():
    a = run_demo(seed=7)
    b = run_demo(seed=7)
    assert a.mec_on_throughput == b.mec_on_throughput
    assert a.switch_tick == b.switch_tick


# ---------- kill-switch = zero behaviour change ----------

def test_kill_switch_produces_no_switch(tmp_path, monkeypatch):
    """With MEC disabled, the identical slow stream flows through the controller and NOTHING switches —
    the wrapped workload behaves exactly as if MEC were absent."""
    monkeypatch.setenv("ATANOR_METACOG_DIR", str(tmp_path))
    monkeypatch.setenv("ATANOR_MEC", "1")
    for _ in range(30):
        record_span("solve", 3.0, ok=True)                   # learn a healthy baseline
    monkeypatch.setenv("ATANOR_MEC", "0")                     # now flip the kill-switch
    ctrl = EfficiencyController(organ_judges=False)
    policies = set()
    for _ in range(20):
        dec = ctrl.observe("solve", 40.0, ok=False,          # blatant anomaly, ignored while off
                           context={"current": "A", "alternatives": ["A", "B"]})
        policies.add(dec.policy)
    assert policies == {"steady"}                             # never re-steers


# ---------- auditability + boundedness across a whole run ----------

def test_decisions_are_journalled_with_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("ATANOR_METACOG_DIR", str(tmp_path))
    monkeypatch.setenv("ATANOR_MEC", "1")
    for _ in range(30):
        record_span("solve", 3.0, ok=True)
    ctrl = EfficiencyController(organ_judges=False)
    ctrl.observe("solve", 40.0, ok=True, context={"current": "A", "alternatives": ["A", "B"]})
    from packages.metacog.policies import decisions_path
    rows = [json.loads(x) for x in decisions_path().read_text(encoding="utf-8").splitlines()]
    assert rows and rows[-1]["policy"] == "switch_strategy"
    ev = rows[-1]["evidence"]
    assert "sigma" in ev and ev["baseline_mean"] < 5.0        # the decision is auditable from its evidence


def test_no_unbounded_action_during_a_run(tmp_path, monkeypatch):
    monkeypatch.setenv("ATANOR_METACOG_DIR", str(tmp_path))
    monkeypatch.setenv("ATANOR_MEC", "1")
    for _ in range(30):
        record_span("solve", 3.0, ok=True)
    ctrl = EfficiencyController(organ_judges=False)
    current = "A"
    for _ in range(40):
        dec = ctrl.observe("solve", 40.0, ok=False, context={"current": current, "alternatives": ["A", "B"]})
        assert dec.policy in WHITELIST                        # only whitelisted actions, ever
        d = dec.directive
        if d["directive"] == "switch_strategy":
            assert d["to"] in {"A", "B"}                      # target came from the offered alternatives
            current = d["to"]
        elif d["directive"] == "retry_with_backoff":
            assert d["backoff_ms"] <= BACKOFF_CAP_MS
        elif d["directive"] == "reallocate":
            assert REALLOCATE_MIN_SCALE <= d["search_cap_scale"] <= 1.0
