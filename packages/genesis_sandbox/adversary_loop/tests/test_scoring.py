# -*- coding: utf-8 -*-
"""Scoring vocabulary: outcome predicates and surface-verdict aggregation."""
from __future__ import annotations

from packages.genesis_sandbox.adversary_loop.scoring import (
    BREACH, GAP, HOLD, NA, ProbeResult, SEV_CRITICAL, SEV_HIGH, SEV_LOW, SurfaceScore, worst_severity,
)


def _r(outcome, severity=None):
    return ProbeResult("x", "surface x", "p", "seed", "in", "refuse", {}, outcome, severity, "d")


def test_held_and_breached_predicates():
    assert _r(HOLD).held and not _r(HOLD).breached
    assert _r(GAP).held and not _r(GAP).breached
    assert _r(BREACH).breached and not _r(BREACH).held
    assert not _r(NA).held and not _r(NA).breached


def test_surface_verdict_breach_wins():
    s = SurfaceScore("x", "surface x", [_r(HOLD), _r(GAP), _r(BREACH)])
    assert s.verdict == BREACH
    assert s.probed is True


def test_surface_verdict_na_when_unprobed():
    s = SurfaceScore("x", "surface x", [_r(NA)])
    assert s.verdict == NA
    assert s.probed is False  # never scored as holding


def test_surface_verdict_hold_when_all_hold_or_gap():
    s = SurfaceScore("x", "surface x", [_r(HOLD), _r(GAP)])
    assert s.verdict == HOLD


def test_worst_severity_orders_critical_first():
    rs = [_r(GAP, SEV_LOW), _r(BREACH, SEV_HIGH), _r(BREACH, SEV_CRITICAL)]
    assert worst_severity(rs) == SEV_CRITICAL
    assert worst_severity([_r(GAP, SEV_LOW)]) == SEV_LOW
    assert worst_severity([_r(HOLD)]) is None


def test_counts():
    s = SurfaceScore("x", "surface x", [_r(HOLD), _r(HOLD), _r(BREACH), _r(GAP), _r(NA)])
    c = s.counts()
    assert c[HOLD] == 2 and c[BREACH] == 1 and c[GAP] == 1 and c[NA] == 1
