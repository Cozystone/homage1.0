# -*- coding: utf-8 -*-
"""RESTEER-layer tests: the action set is a CLOSED whitelist, every action is bounded, escalation is
never silent, abstention is honest, decisions are journalled with evidence, and the kill-switch refuses
to act."""
from __future__ import annotations

import json

import pytest

from packages.metacog.policies import (
    Finding, resolve, journal_decision, decisions_path, WHITELIST,
    ESCALATE_REPEAT, BACKOFF_CAP_MS, MAX_RETRIES, REALLOCATE_MIN_SCALE, DEFERRABLE_DAEMONS,
)

assert MAX_RETRIES < ESCALATE_REPEAT                          # the ladder must leave a rung for abstain


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ATANOR_METACOG_DIR", str(tmp_path))
    monkeypatch.setenv("ATANOR_MEC", "1")


# ---------- the action set is closed ----------

def test_every_resolution_is_in_the_whitelist():
    cases = [
        Finding("slow_span", "s", 10.0, {"sigma": 10.0}),
        Finding("overload", "process", 0.9, {"rss_pressure": 0.9}),
        Finding("commitment_thrash", "workspace", 20.0, {"commitment_debt": 20}),
        Finding("high_failure", "s", 0.7, {"failure_rate": 0.7}),
        Finding("failure_concentration", "search", 0.6, {"jump_probability": 0.6}),
    ]
    for f in cases:
        res = resolve(f, {}, {"current": "A", "alternatives": ["A", "B"]})
        assert res.policy in WHITELIST


def test_unknown_finding_kind_is_steady_not_an_invented_action():
    res = resolve(Finding("mystery_kind", "x", 5.0), {}, {"current": "A", "alternatives": ["A", "B"]})
    assert res.policy == "steady"


def test_no_finding_is_steady():
    assert resolve(None).policy == "steady"


# ---------- each action is bounded ----------

def test_switch_only_chooses_from_offered_alternatives():
    res = resolve(Finding("slow_span", "s", 10.0, {"sigma": 10.0}), {},
                  {"current": "A", "alternatives": ["A", "B", "C"]})
    assert res.policy == "switch_strategy"
    assert res.directive["to"] in {"B", "C"} and res.directive["to"] != "A"


def test_switch_without_alternative_does_not_fabricate_one():
    res = resolve(Finding("slow_span", "s", 10.0, {"sigma": 10.0}), {},
                  {"current": "A", "alternatives": ["A"]})
    assert res.policy != "switch_strategy"                    # falls through to retry/abstain, never invents a lane


def test_reallocate_scale_is_clamped():
    res = resolve(Finding("overload", "process", 0.99, {"rss_pressure": 0.99}), {"rss_pressure": 0.99}, {})
    assert res.policy in ("reallocate", "escalate_to_operator")
    if res.policy == "reallocate":
        assert REALLOCATE_MIN_SCALE <= res.directive["search_cap_scale"] <= 1.0
        assert set(res.directive["defer_daemons"]) == set(DEFERRABLE_DAEMONS)


def test_retry_backoff_is_capped():
    # no alternative lane -> a slow span becomes a retry; the backoff never exceeds the cap
    res = resolve(Finding("slow_span", "s", 10.0, {"sigma": 10.0}, repeat=1), {}, {"current": "A", "alternatives": ["A"]})
    assert res.policy == "retry_with_backoff"
    assert res.directive["backoff_ms"] <= BACKOFF_CAP_MS
    assert res.directive["attempt"] <= MAX_RETRIES


# ---------- escalation is never silent; abstention is honest ----------

def test_escalation_fires_on_persistence_and_is_never_silent():
    res = resolve(Finding("slow_span", "s", 10.0, {"sigma": 10.0}, repeat=ESCALATE_REPEAT), {},
                  {"current": "A", "alternatives": ["A", "B"]})
    assert res.policy == "escalate_to_operator"
    assert res.directive["silent"] is False and res.directive["operator"] is True


def test_abort_and_abstain_is_honest_last_resort():
    # retries exhausted (repeat == MAX_RETRIES) but not yet escalation-persistent, and no alternative lane
    res = resolve(Finding("high_failure", "s", 0.9, {"failure_rate": 0.9}, repeat=MAX_RETRIES), {},
                  {"current": "A", "alternatives": ["A"]})
    assert res.policy == "abort_and_abstain"
    assert res.directive["honest"] is True


def test_retry_precedes_abstain_precedes_escalate_on_the_no_alternative_ladder():
    """Each rung of the no-alternative ladder is reachable in order (regression guard for the gap where
    retry shadowed abstain)."""
    def rung(repeat):
        return resolve(Finding("high_failure", "s", 0.9, {"failure_rate": 0.9}, repeat=repeat), {},
                       {"current": "A", "alternatives": ["A"]}).policy
    assert rung(0) == "retry_with_backoff"
    assert rung(MAX_RETRIES) == "abort_and_abstain"
    assert rung(ESCALATE_REPEAT) == "escalate_to_operator"


# ---------- decisions are journalled with evidence; steady + kill-switch are not ----------

def test_decision_is_journalled_with_evidence():
    f = Finding("slow_span", "solve", 12.0, {"sigma": 12.0, "baseline_mean": 3.0, "ms": 40.0})
    res = resolve(f, {"recent_failure_rate": 0.1}, {"current": "A", "alternatives": ["A", "B"]})
    journal_decision(res, f, {"recent_failure_rate": 0.1})
    rows = [json.loads(x) for x in decisions_path().read_text(encoding="utf-8").splitlines()]
    assert rows and rows[-1]["policy"] == "switch_strategy"
    assert rows[-1]["evidence"]["sigma"] == 12.0             # evidence travels with the decision
    assert rows[-1]["bounded"] is True and "snapshot" in rows[-1]


def test_steady_is_not_journalled():
    journal_decision(resolve(None), None, {})
    assert not decisions_path().exists()                     # the ledger records interventions, not silence


def test_kill_switch_refuses_to_act(monkeypatch):
    monkeypatch.setenv("ATANOR_MEC", "0")
    res = resolve(Finding("slow_span", "s", 99.0, {"sigma": 99.0}), {}, {"current": "A", "alternatives": ["A", "B"]})
    assert res.policy == "steady"
    journal_decision(res, None, {})
    assert not decisions_path().exists()
