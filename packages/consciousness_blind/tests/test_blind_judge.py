# -*- coding: utf-8 -*-
"""Tests for the external-blind consciousness-indicator judge (C-E v1).

They assert the blind protocol is HONEST and HARDER than the self-audit:
  * STRUCTURAL author/judge separation — no module in the package imports consciousness_audit
    (not its probes, not its indicators, not its battery);
  * every frozen/degenerate stub is CAUGHT as falsely-present (never scored present) — the pass the
    self-audit lacked;
  * a held-out positive on a REAL organ scores present;
  * the aggregate blind score is computed and partitions the 14 indicators;
  * integrity — every 'present' cites a real organ .py path that exists AND a specific held-out
    stimulus (no rubber-stamp);
  * the report carries the undecidability header and never makes a bare consciousness claim.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from packages.consciousness_blind import stubs
from packages.consciousness_blind.assessors import ASSESSORS
from packages.consciousness_blind.result import (INDICATORS, combine, UNDECIDABILITY_HEADER,
                                                 PRESENT, PARTIAL, ABSENT, CAUGHT)
from packages.consciousness_blind import judge as J
from packages.consciousness_blind.report import render_report

PKG_DIR = Path(J.__file__).resolve().parent
_VALID = {PRESENT, PARTIAL, ABSENT, CAUGHT}


# ---------------------------------------------------------------- STRUCTURAL author/judge separation
def _imported_modules(py: Path) -> set[str]:
    tree = ast.parse(py.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def test_judge_does_not_import_consciousness_audit_probes():
    """The core separation property: the judge (and every module in the package) must NOT import the
    self-battery's probe logic — verdicts are re-derived from organs, not inherited."""
    offenders: list[str] = []
    for py in sorted(PKG_DIR.rglob("*.py")):
        for mod in _imported_modules(py):
            if mod == "packages.consciousness_audit.probes" or \
               mod.startswith("packages.consciousness_audit"):
                offenders.append(f"{py.name} imports {mod}")
    assert not offenders, f"author/judge separation violated: {offenders}"


def test_judge_module_specifically_excludes_the_probes_module():
    """Explicit, narrow assertion named by the spec: judge.py does not import consciousness_audit.probes."""
    mods = _imported_modules(PKG_DIR / "judge.py")
    assert "packages.consciousness_audit.probes" not in mods
    assert not any(m.startswith("packages.consciousness_audit") for m in mods)


# ---------------------------------------------------------------- adversarial: stubs are CAUGHT
@pytest.mark.parametrize("indicator_id", [iid for iid, _t, _s in INDICATORS])
def test_frozen_stub_is_caught_as_falsely_present(indicator_id):
    """A stubbed / frozen organ must be CAUGHT (falsely-present), never scored present — for EVERY
    indicator. This is exactly the pass the self-audit could not run."""
    overrides = stubs.frozen_overrides(indicator_id)
    assert overrides, f"no falsification stub defined for {indicator_id}"
    res = J.assess_one(indicator_id, overrides=overrides)
    assert res.verdict != PRESENT, f"{indicator_id}: a stub was scored present (judge fooled)"
    assert res.verdict == CAUGHT, (f"{indicator_id}: stub verdict was {res.verdict}, expected "
                                   f"FALSELY-present-caught")
    assert res.control_rejected is False, f"{indicator_id}: control should have failed on the stub"


def test_adversarial_pass_catches_all_and_fools_none():
    v = J.run_blind(save=False)
    adv = v["adversarial"]
    assert adv["of"] == 14
    assert adv["caught"] == 14, f"expected all 14 falsifications caught, got {adv['caught']}"
    assert adv["fooled"] == [], f"a stub fooled the judge: {adv['fooled']}"
    # every adversarial row is specifically a falsely-present catch
    assert all(row["adversarial_verdict"] == CAUGHT for row in adv["details"])


# ---------------------------------------------------------------- held-out positive on real organs
def test_held_out_positive_on_real_organs_scores_present():
    """The held-out positive probes on the REAL organs score present for genuinely-present indicators
    (at least a strong majority), and every 'present' actually passed its strict positive."""
    v = J.run_blind(save=False)
    presents = [r for r in v["results"] if r["verdict"] == PRESENT]
    assert len(presents) >= 8, f"expected many present-under-blind, got {len(presents)}"
    for r in presents:
        assert r["positive_pass"] is True, f"{r['id']} present but strict positive did not pass"
        assert r["control_rejected"] is True, f"{r['id']} present but control not rejected"


def test_specific_strong_indicators_are_present_under_blind():
    """A few indicators with unambiguous, adversarially-tested mechanisms must survive the blind bar:
    the hash-chain tamper test (GWT-3), the decorrelation test (AE-2), the single-winner bottleneck
    (GWT-2), and the prediction-error gate (PP-1)."""
    v = J.run_blind(save=False)
    by_id = {r["id"]: r for r in v["results"]}
    for iid in ("GWT-2", "GWT-3", "PP-1", "AE-2"):
        assert by_id[iid]["verdict"] == PRESENT, f"{iid} should be present-under-blind"


def test_a_real_organ_is_not_falsely_present():
    """No REAL-organ verdict should be FALSELY-present-caught — a real organ's control must reject the
    falsification (only stubs get caught)."""
    v = J.run_blind(save=False)
    caught_real = [r["id"] for r in v["results"] if r["verdict"] == CAUGHT]
    assert caught_real == [], f"a real organ was flagged falsely-present: {caught_real}"


# ---------------------------------------------------------------- aggregate + delta
def test_aggregate_is_computed_and_partitions_the_indicators():
    v = J.run_blind(save=False)
    assert v["n_indicators"] == 14 == len(v["results"])
    agg = v["aggregate_blind_score"]
    assert agg["of"] == 14
    c = v["counts"]
    assert c[PRESENT] + c[PARTIAL] + c[ABSENT] + c[CAUGHT] == 14
    assert agg["present"] == c[PRESENT]
    # by-theory totals partition the 14 as well
    assert sum(row["total"] for row in v["by_theory"].values()) == 14


def test_honest_delta_vs_self_audit_is_reported():
    """The delta must be present and honest: drops are present->partial with a precise reason each, and
    the blind present count is <= the self-audit's (a harder bar cannot invent new presents here)."""
    v = J.run_blind(save=False)
    d = v["delta_vs_self_audit"]
    assert d["self_audit_present"] >= d["blind_present"], "blind should not exceed the self-audit"
    for drop in d["drops"]:
        assert drop["self_audit"] == PRESENT and drop["blind"] in (PARTIAL, ABSENT, CAUGHT)
        assert drop["reason"].strip(), f"{drop['id']} drop must carry a precise reason"


# ---------------------------------------------------------------- integrity (no rubber-stamp)
def test_every_present_cites_a_real_organ_path_and_a_held_out_stimulus():
    v = J.run_blind(save=False)
    for r in v["results"]:
        assert r["verdict"] in _VALID
        assert r["stimulus"].strip(), f"{r['id']} carries no held-out stimulus"
        if r["verdict"] == PRESENT:
            real = [p for p in r["organ_paths"] if p.endswith(".py") and (J.REPO / p).exists()]
            assert real, f"{r['id']} is present but cites no existing organ .py path: {r['organ_paths']}"
            assert r["integrity_ok"] is True


def test_integrity_gate_downgrades_a_present_without_a_real_path(monkeypatch):
    """A 'present' with no real organ path is not defensible under the blind bar and is downgraded."""
    from packages.consciousness_blind.result import BlindResult

    def fake_assessor():
        return BlindResult(id="RPT-1", theory="RPT", statement="fake", verdict=PRESENT,
                           positive_pass=True, positive_partial=True, control_rejected=True,
                           organ_paths=["packages/ghost/nope.py"], stimulus="held-out X",
                           positive_detail="d", control_detail="d", notes="n")
    monkeypatch.setitem(ASSESSORS, "RPT-1", fake_assessor)
    res = J.assess_one("RPT-1")
    assert res.verdict == PARTIAL
    assert res.integrity_ok is False


def test_a_broken_assessor_is_an_honest_absent_not_a_crash(monkeypatch):
    def boom():
        raise RuntimeError("organ missing")
    monkeypatch.setitem(ASSESSORS, "PP-1", boom)
    res = J.assess_one("PP-1")
    assert res.verdict == ABSENT
    assert "organ missing" in res.notes


# ---------------------------------------------------------------- verdict algebra (unit)
def test_verdict_algebra():
    # control not rejected -> any positive reading is a caught false-positive
    assert combine(True, True, False) == CAUGHT
    assert combine(False, True, False) == CAUGHT
    assert combine(False, False, False) == ABSENT
    # control rejected -> verdict by positive strength
    assert combine(True, True, True) == PRESENT
    assert combine(False, True, True) == PARTIAL
    assert combine(False, False, True) == ABSENT


# ---------------------------------------------------------------- report + undecidability header
def test_report_carries_undecidability_header():
    v = J.run_blind(save=False)
    md = render_report(v)
    assert UNDECIDABILITY_HEADER in md
    assert "undecidable" in md.lower()
    assert "indicator properties" in md.lower()
    assert "not a claim that ATANOR is conscious".lower() in md.lower()


def test_report_never_makes_a_bare_consciousness_claim():
    v = J.run_blind(save=False)
    md = render_report(v).lower()
    for forbidden in ("is phenomenally conscious", "has subjective experience", "proves consciousness"):
        assert forbidden not in md
    # every 'is conscious' must sit inside a negation (the honest header), never bare
    idx = 0
    while (i := md.find("is conscious", idx)) != -1:
        assert "not" in md[max(0, i - 30):i], f"un-negated consciousness claim near ...{md[i-30:i+12]}..."
        idx = i + len("is conscious")


# ---------------------------------------------------------------- persistence
def test_run_blind_saves_verdict_and_report(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "OUT_DIR", tmp_path)
    monkeypatch.setattr(J, "VERDICT_JSON", tmp_path / "verdict.json")
    monkeypatch.setattr(J, "REPORT_MD", tmp_path / "report.md")
    v = J.run_blind(save=True)
    assert (tmp_path / "verdict.json").exists()
    assert (tmp_path / "report.md").exists()
    saved = json.loads((tmp_path / "verdict.json").read_text(encoding="utf-8"))
    assert saved["instrument"] == "consciousness_blind"
    assert "undecidable" in (tmp_path / "report.md").read_text(encoding="utf-8").lower()


# ---------------------------------------------------------------- neuro-ledger registration
def test_neuro_ledger_entry_is_zero_param_and_not_a_fact_source():
    from packages.consciousness_blind.neuro_entry import ledger_entry
    organ = ledger_entry()
    assert organ.id == "consciousness_blind_judge"
    assert organ.fact_source is False          # invariant: an assessor never provides world facts
    assert organ.fallback_params == 0          # honest count: no trained weights
    assert (J.REPO / organ.path).exists()
