# -*- coding: utf-8 -*-
"""Adult-gate harness (G5): sealed weekly self-directed growth over REAL wall-clock — unforgeable.
A clock plus an anti-forgery ledger, never a shortcut to being an adult."""
from packages.live_selfhood_cycle.self_directed_growth import (
    refresh_signal, seal_week, sealed_months)


def _stamp(day: int) -> str:
    # day-of-July that rolls into August so >31 stays a valid date
    from datetime import datetime, timedelta
    d = datetime(2026, 7, 1) + timedelta(days=day - 1)
    return d.strftime("%Y-%m-%dT00:00:00.000Z")


def test_two_months_needs_two_months_of_real_clock(tmp_path):
    led = tmp_path / "g.jsonl"
    # eight weekly self-directed improvements spanning ~2 months of real stamps
    for i in range(8):
        seal_week("speech", 0.5 + i * 0.02, 0.5 + (i + 1) * 0.02,
                  now_utc=f"2026-{6 + i // 4:02d}-{1 + (i % 4) * 7:02d}T00:00:00.000Z", ledger=led)
    m = sealed_months(led)
    assert m["self_directed_weeks"] == 8 and m["span_days"] >= 45
    assert m["months"] >= 1.5


def test_same_day_rows_cannot_forge_months(tmp_path):
    led = tmp_path / "g.jsonl"
    for i in range(20):
        seal_week("speech", 0.4, 0.5, now_utc=_stamp(20), ledger=led)   # all same day
    assert sealed_months(led)["months"] == 0.0    # zero wall-clock span -> zero months


def test_human_picked_weeks_do_not_count(tmp_path):
    led = tmp_path / "g.jsonl"
    seal_week("speech", 0.4, 0.6, now_utc=_stamp(1), human_picked=True, ledger=led)
    seal_week("router", 0.4, 0.6, now_utc=_stamp(40), human_picked=True, ledger=led)
    m = sealed_months(led)
    assert m["self_directed_weeks"] == 0 and m["months"] == 0.0   # steered growth is not self-directed


def test_regressing_week_is_not_an_improvement(tmp_path):
    led = tmp_path / "g.jsonl"
    seal_week("speech", 0.6, 0.5, now_utc=_stamp(1), ledger=led)      # got worse
    assert sealed_months(led)["self_directed_weeks"] == 0


def test_signal_is_derived_not_asserted(tmp_path):
    led = tmp_path / "g.jsonl"; out = tmp_path / "sig.json"
    seal_week("speech", 0.4, 0.5, now_utc=_stamp(1), ledger=led)
    seal_week("speech", 0.5, 0.6, now_utc=_stamp(40), ledger=led)
    v = refresh_signal(ledger=led, out=out)
    import json
    assert v == json.loads(out.read_text())["self_directed_months"]
    assert v > 1.0   # ~39 days between the two self-directed weeks
