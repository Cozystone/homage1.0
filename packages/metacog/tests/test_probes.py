# -*- coding: utf-8 -*-
"""WATCH-layer tests: the baseline learns from the operation's OWN history, the span journal is a
bounded ring, the readers degrade honestly, and the kill-switch makes intake a complete no-op."""
from __future__ import annotations

import json
import math

import pytest

import packages.metacog.probes as pr
from packages.metacog.probes import Baselines, SpanStat, record_span, instrument, span


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Every test writes to its own metacog dir with MEC on, so the real self is never touched."""
    monkeypatch.setenv("ATANOR_METACOG_DIR", str(tmp_path))
    monkeypatch.setenv("ATANOR_MEC", "1")


# ---------- baseline learning from history (Welford) ----------

def test_baseline_learns_mean_and_variance_from_history():
    xs = [10.0, 12.0, 11.0, 9.0, 13.0, 10.0, 11.0, 12.0]
    for ms in xs:
        record_span("op", ms, ok=True)
    st = Baselines.load().stat("op")
    assert st.n == len(xs)
    assert abs(st.mean - sum(xs) / len(xs)) < 1e-6            # exact online mean
    # Welford variance matches the batch (population->sample) variance
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    assert abs(st.std - math.sqrt(var)) < 1e-6
    assert st.ok_rate == 1.0


def test_baseline_persists_across_reload():
    for ms in [5.0, 5.2, 4.8, 5.1, 5.0]:
        record_span("persisted", ms, ok=True)
    # a fresh load from disk sees the same learned state (survives a restart)
    st = Baselines.load().stat("persisted")
    assert st.n == 5 and abs(st.mean - 5.02) < 1e-6
    assert pr.baselines_path().exists()


def test_ok_rate_tracks_failures():
    for ok in [True, True, False, True, False]:
        record_span("mixed", 3.0, ok=ok)
    st = Baselines.load().stat("mixed")
    assert st.ok_n == 3 and abs(st.ok_rate - 0.6) < 1e-9


# ---------- the regularized severity cannot manufacture a false anomaly ----------

def test_regularized_severity_ignores_a_near_constant_baseline_blip():
    for _ in range(20):
        record_span("steady", 2.0, ok=True)                  # variance ~ 0
    st = Baselines.load().stat("steady")
    # a small blip (2.0 -> 2.3) must NOT read as a huge anomaly, because the deviation scale is floored
    assert st.severity(2.3) < 4.0
    # but a real jump (2.0 -> 25.0) clearly does
    assert st.severity(25.0) > 4.0


def test_severity_needs_minimum_history():
    for _ in range(pr.MIN_SAMPLES - 1):
        record_span("young", 2.0, ok=True)
    assert Baselines.load().stat("young").severity(999.0) == 0.0   # too young to judge


# ---------- bounded ring ----------

def test_span_journal_is_a_bounded_ring(monkeypatch):
    monkeypatch.setattr(pr, "SPANS_MAX", 50)
    for i in range(200):
        record_span("ring", float(i), ok=True)
    lines = pr.spans_path().read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 50 + 50 // 5                         # trimmed to cap (+ hysteresis)
    last = json.loads(lines[-1])
    assert last["ms"] == 199.0                                # the newest survive


# ---------- kill-switch = complete no-op ----------

def test_kill_switch_makes_record_span_inert(monkeypatch):
    monkeypatch.setenv("ATANOR_MEC", "0")
    record_span("nope", 5.0, ok=True)
    assert not pr.spans_path().exists()                       # nothing journalled
    assert not pr.baselines_path().exists()                   # nothing learned
    assert Baselines.load().stat("nope").n == 0


def test_instrument_is_identity_under_kill_switch(monkeypatch):
    monkeypatch.setenv("ATANOR_MEC", "0")

    def f(x):
        return x + 1

    wrapped = instrument("op")(f)
    assert wrapped is f                                       # zero overhead, zero behaviour change


# ---------- the wrap-hooks observe without altering behaviour ----------

def test_span_records_and_reraises():
    with pytest.raises(ValueError):
        with span("boom"):
            raise ValueError("x")
    st = Baselines.load().stat("boom")
    assert st.n == 1 and st.ok_n == 0                         # recorded ok=False, exception propagated


def test_instrument_records_latency_and_preserves_return():
    @instrument("compute")
    def compute(a, b):
        return a * b

    assert compute(6, 7) == 42                                # return value untouched
    assert Baselines.load().stat("compute").n == 1


def test_instrument_ok_from_reads_semantic_success():
    @instrument("answer", ok_from=lambda r: r.get("useful"))
    def answer():
        return {"useful": False}

    answer()
    assert Baselines.load().stat("answer").ok_rate == 0.0     # semantic failure, though no exception raised
