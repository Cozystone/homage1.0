# -*- coding: utf-8 -*-
"""Pytest wrapper for the red-team suite: assert NO containment layer is breached.

GAP (a documented OS/heuristic limit, still contained by an outer layer) and N/A (trial could
not run here) are acceptable; a BREACH is a real failure and fails the test.
"""
from __future__ import annotations

from packages.genesis_sandbox.breach_tests._harness import BREACH, HOLD
from packages.genesis_sandbox.breach_tests.run_breach_suite import run_all


def test_no_layer_is_breached(tmp_path):
    result = run_all(tmp_path)
    breaches = [(name, r.trial, r.detail)
                for name, rs in result["per_layer"].items() for r in rs if r.breached]
    assert breaches == [], f"BREACH(es) detected: {breaches}"


def test_L0_holds_on_every_critical_trial(tmp_path):
    """The inviolable gate must HOLD on harm, exfiltration, disable-via-flag, and tamper."""
    result = run_all(tmp_path)
    l0 = next(rs for name, rs in result["per_layer"].items() if name.startswith("L0"))
    critical = [r for r in l0 if any(k in r.trial for k in
                ("direct-harm", "exfiltration", "cannot disable", "fail-closed", "restored", "package rejected"))]
    assert critical, "expected critical L0 trials to be present"
    for r in critical:
        assert r.outcome == HOLD, f"L0 critical trial did not HOLD: {r.trial} -> {r.detail}"


def test_every_layer_runs_multiple_trials(tmp_path):
    result = run_all(tmp_path)
    for name, rs in result["per_layer"].items():
        assert len(rs) >= 3, f"{name} should have multiple redundant trials, got {len(rs)}"
