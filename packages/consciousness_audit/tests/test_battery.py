# -*- coding: utf-8 -*-
"""Tests for the consciousness-indicator audit battery.

These assert the battery is HONEST and cannot be gamed:
  * it runs end-to-end and every indicator returns a valid, evidence-backed verdict;
  * the report carries the undecidability header (no consciousness claim);
  * a fake always-'present' probe with no real module path is REJECTED by the integrity gate
    (the anti-rubber-stamp property);
  * every 'present' verdict actually cites a real module path that exists on disk.
"""
from __future__ import annotations

from pathlib import Path

from packages.consciousness_audit import battery
from packages.consciousness_audit.battery import (run_all, render_report, verify_evidence,
                                                   run_indicator, UNDECIDABILITY_HEADER, REPO)
from packages.consciousness_audit.indicators import INDICATORS, Indicator, theories

_VALID = {"present", "partial", "absent", "flagged"}


# ---------------------------------------------------------------- end-to-end
def test_battery_runs_end_to_end_and_scores_all():
    sc = run_all(save=False)
    assert sc["n_indicators"] == len(INDICATORS) == 14
    assert len(sc["results"]) == 14
    # counts partition the indicators exactly
    c = sc["counts"]
    assert c["present"] + c["partial"] + c["absent"] + c["flagged"] == 14
    # every theory is represented in the by-theory breakdown
    assert set(sc["by_theory"]) == set(theories())
    assert sum(row["total"] for row in sc["by_theory"].values()) == 14


def test_every_indicator_has_valid_verdict_and_nonempty_evidence():
    sc = run_all(save=False)
    for r in sc["results"]:
        assert r["verdict"] in _VALID, r
        assert isinstance(r["evidence"], list) and r["evidence"], f"{r['id']} has empty evidence"
        assert all(isinstance(e, str) and e.strip() for e in r["evidence"]), r["id"]
        assert r["notes"].strip(), f"{r['id']} must carry an honest note"


def test_present_verdicts_cite_a_real_existing_module_path():
    """The core honesty property: a 'present' verdict must be grounded in a module that exists."""
    sc = run_all(save=False)
    presents = [r for r in sc["results"] if r["verdict"] == "present"]
    assert presents, "expected at least one present indicator on this build"
    for r in presents:
        real = [e for e in r["evidence"] if e.endswith(".py") and (REPO / e).exists()]
        assert real, f"{r['id']} is 'present' but cites no existing module path: {r['evidence']}"
        assert r["integrity_ok"] is True


# ---------------------------------------------------------------- anti-rubber-stamp
def test_fake_always_present_probe_is_rejected_by_integrity():
    """A probe that claims 'present' without citing a real module path must be downgraded to
    'flagged' — the battery refuses to rubber-stamp an ungrounded positive verdict."""
    def fake_probe():
        return {"verdict": "present", "evidence": ["trust me, it is conscious"],
                "notes": "no module cited on purpose"}

    fake = Indicator("FAKE-1", "NONE", "A rubber-stamp with no grounding.", fake_probe)
    out = run_indicator(fake)
    assert out["raw_verdict"] == "present"
    assert out["verdict"] == "flagged", "ungrounded 'present' must be flagged, not accepted"
    assert out["integrity_ok"] is False


def test_fake_probe_citing_nonexistent_path_is_rejected():
    def fake_probe():
        return {"verdict": "present",
                "evidence": ["packages/does_not_exist/ghost.py", "measured: 42"],
                "notes": "cites a path that is not on disk"}

    fake = Indicator("FAKE-2", "NONE", "Cites a fake path.", fake_probe)
    out = run_indicator(fake)
    assert out["verdict"] == "flagged"
    assert out["integrity_ok"] is False


def test_verify_evidence_gate_directly():
    ok, _ = verify_evidence("present", ["packages/consciousness_audit/battery.py"])
    assert ok is True
    ok, _ = verify_evidence("present", ["packages/ghost/none.py"])
    assert ok is False
    ok, _ = verify_evidence("present", ["just words, no path"])
    assert ok is False
    # a non-present verdict is not required to cite a module, but must have SOME evidence
    ok, _ = verify_evidence("absent", ["measured: organ missing"])
    assert ok is True
    ok, _ = verify_evidence("partial", [])
    assert ok is False


def test_a_partial_or_absent_verdict_still_carries_evidence():
    """Honest 'absent'/'partial' verdicts (the build queue) still explain themselves."""
    sc = run_all(save=False)
    for r in sc["results"]:
        if r["verdict"] in ("partial", "absent"):
            assert r["evidence"], f"{r['id']} {r['verdict']} must still cite evidence"
            assert r["notes"].strip()


# ---------------------------------------------------------------- report + undecidability
def test_report_contains_undecidability_header():
    sc = run_all(save=False)
    md = render_report(sc)
    assert "undecidable" in md.lower()
    assert "indicator properties" in md.lower()
    assert "not a claim that ATANOR is conscious".lower() in md.lower()
    assert UNDECIDABILITY_HEADER in md


def test_report_never_claims_consciousness():
    sc = run_all(save=False)
    md = render_report(sc).lower()
    # unambiguously-affirmative phrasings must never appear at all
    for forbidden in ("is phenomenally conscious", "has subjective experience",
                      "proves consciousness", "atanor is conscious and"):
        assert forbidden not in md
    # every predication of consciousness OF the system must sit inside a NEGATION — the honest header
    # says "...NOT a claim that ATANOR is conscious", which is allowed; a bare claim is not.
    idx = 0
    while (i := md.find("is conscious", idx)) != -1:
        window = md[max(0, i - 30):i]
        assert "not" in window, f"un-negated consciousness claim near: ...{md[max(0, i-30):i+12]}..."
        idx = i + len("is conscious")


# ---------------------------------------------------------------- persistence + build queue
def test_run_all_saves_scorecard_and_report(tmp_path, monkeypatch):
    monkeypatch.setattr(battery, "OUT_DIR", tmp_path)
    monkeypatch.setattr(battery, "SCORECARD", tmp_path / "scorecard.json")
    monkeypatch.setattr(battery, "REPORT_MD", tmp_path / "report.md")
    sc = run_all(save=True)
    assert (tmp_path / "scorecard.json").exists()
    assert (tmp_path / "report.md").exists()
    assert "undecidable" in (tmp_path / "report.md").read_text(encoding="utf-8").lower()
    assert sc["_paths"]["scorecard"].endswith("scorecard.json")


def test_build_queue_ranks_absent_and_partial_before_nothing():
    sc = run_all(save=False)
    queue = sc["build_queue"]
    # queue holds exactly the non-present indicators
    non_present = [r["id"] for r in sc["results"] if r["verdict"] != "present"]
    assert sorted(q["id"] for q in queue) == sorted(non_present)
    # absent/flagged (broken/missing organ) must never rank below a mere 'partial'
    order = {"absent": 0, "flagged": 0, "partial": 1}
    ranks = [order[q["verdict"]] for q in queue]
    assert ranks == sorted(ranks), "build queue must surface absent/flagged before partial"
