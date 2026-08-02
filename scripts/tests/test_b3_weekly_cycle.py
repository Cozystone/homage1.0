# -*- coding: utf-8 -*-
"""B3 gate logic — the 4-week monotone + seal criteria must be enforced exactly (criteria v1)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import b3_weekly_cycle as b3  # noqa: E402


def _wk(week, metric, seal=True):
    return {"iso_week": week, "metric": metric, "seal_ok": seal}


def test_four_monotone_weeks_with_seal_pass():
    led = [_wk("2026-W29", 0.80), _wk("2026-W30", 0.82), _wk("2026-W31", 0.82), _wk("2026-W32", 0.85)]
    g = b3.check_gate(led)
    assert g["PASS"] is True
    assert g["weeks_recorded"] == 4 and g["monotone_nondecreasing"] and g["all_seals_intact"]


def test_a_dip_breaks_monotone():
    led = [_wk("2026-W29", 0.80), _wk("2026-W30", 0.85), _wk("2026-W31", 0.83), _wk("2026-W32", 0.88)]
    assert b3.check_gate(led)["PASS"] is False           # W31 fell below W30


def test_broken_seal_fails_even_if_rising():
    led = [_wk("2026-W29", 0.80), _wk("2026-W30", 0.82), _wk("2026-W31", 0.84, seal=False),
           _wk("2026-W32", 0.86)]
    g = b3.check_gate(led)
    assert g["PASS"] is False and g["all_seals_intact"] is False   # wireheading precondition


def test_three_weeks_not_enough():
    led = [_wk("2026-W29", 0.80), _wk("2026-W30", 0.82), _wk("2026-W31", 0.84)]
    assert b3.check_gate(led)["PASS"] is False and b3.check_gate(led)["weeks_recorded"] == 3


def test_nan_weeks_are_dropped_not_counted():
    led = [{"iso_week": "2026-W28", "metric": float("nan"), "seal_ok": True},
           _wk("2026-W29", 0.80), _wk("2026-W30", 0.82), _wk("2026-W31", 0.84), _wk("2026-W32", 0.86)]
    g = b3.check_gate(led)                                # the pending-baseline NaN week must not count
    assert g["weeks_recorded"] == 4 and g["PASS"] is True


def test_unknown_lane_refused():
    assert "refused" in b3._apply_lane("make_it_smarter_somehow")
    assert "registered" in b3._apply_lane("lexical_field_growth")
