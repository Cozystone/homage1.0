# -*- coding: utf-8 -*-
"""G3: every test here is a way this gate could otherwise be quietly won.

A transfer test that can be passed by editing the exam, re-cutting the baseline, or reading a
silent failure as a null result is worse than no test, because it produces a number people believe.
"""
from __future__ import annotations

import json

import pytest

import packages.transfer_gate.verdict as MEA
from packages.transfer_gate.manifest import Metric, freeze, hash_surface, load, seal_intact

_VALUES: dict[str, float] = {"score": 0.50, "candidates": 1000.0}


def sealed_eval() -> dict[str, float]:
    """Stands in for B's own evaluation; the tests move `_VALUES`, never this function."""
    return dict(_VALUES)


def _domain(tmp_path, **kw):
    (tmp_path / "b").mkdir(parents=True, exist_ok=True)
    (tmp_path / "b" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "b" / "data.txt").write_text("rows\n", encoding="utf-8")
    return freeze(
        kw.pop("name", "domB"), ["b"],
        "packages.transfer_gate.tests.test_gate:sealed_eval",
        [Metric("score", 0.50, "higher_is_better"),
         Metric("candidates", 1000.0, "lower_is_better", "cost, not quality")],
        root=tmp_path, path=tmp_path / "seal.json", **kw)


@pytest.fixture(autouse=True)
def _restore():
    before = dict(_VALUES)
    yield
    _VALUES.clear()
    _VALUES.update(before)


def test_a_frozen_domain_cannot_be_refrozen(tmp_path):
    """Re-cutting the baseline after seeing the result is the most natural way this test is lost."""
    _domain(tmp_path)
    with pytest.raises(FileExistsError):
        _domain(tmp_path)


def test_naming_three_files_does_not_freeze_only_three(tmp_path):
    """A directory in the surface means the whole directory, or a domain could be frozen by naming
    part of itself and editing the rest."""
    _domain(tmp_path)
    before = hash_surface(["b"], tmp_path)
    (tmp_path / "b" / "sneaky.py").write_text("X = 2\n", encoding="utf-8")
    assert hash_surface(["b"], tmp_path) != before


def test_editing_the_exam_is_invalid_and_never_reads_as_unchanged(tmp_path):
    """A silent failure and a real null result look identical from outside, and only one of them is
    evidence."""
    _domain(tmp_path)
    (tmp_path / "b" / "core.py").write_text("VALUE = 999\n", encoding="utf-8")
    got = MEA.measure("domB", root=tmp_path, path=tmp_path / "seal.json", record=False)
    assert got.verdict == MEA.INVALID and not got.usable
    assert not got.surface_intact and "editing the exam" in got.reason


def test_a_file_restored_byte_for_byte_is_genuinely_untouched(tmp_path):
    """Content, not mtime: re-saving a file with no change is not a violation."""
    _domain(tmp_path)
    src = tmp_path / "b" / "core.py"
    original = src.read_text(encoding="utf-8")
    src.write_text("VALUE = 42\n", encoding="utf-8")
    src.write_text(original, encoding="utf-8")
    got = MEA.measure("domB", root=tmp_path, path=tmp_path / "seal.json", record=False)
    assert got.surface_intact and got.usable


def test_editing_the_manifest_is_caught_separately_from_the_code(tmp_path):
    d = _domain(tmp_path)
    assert seal_intact(d)
    row = json.loads((tmp_path / "seal.json").read_text(encoding="utf-8"))
    row["metrics"][0]["baseline"] = 0.01                    # move the goalposts
    (tmp_path / "seal.json").write_text(json.dumps(row), encoding="utf-8")
    got = MEA.measure("domB", root=tmp_path, path=tmp_path / "seal.json", record=False)
    assert got.verdict == MEA.INVALID and not got.seal_intact


def test_the_direction_of_the_claim_is_fixed_at_freeze_time(tmp_path):
    """`candidates` was declared lower-is-better before any result was seen, so a rise cannot be
    re-read as a win."""
    _domain(tmp_path)
    _VALUES["candidates"] = 5000.0
    got = MEA.measure("domB", root=tmp_path, path=tmp_path / "seal.json", record=False)
    assert got.verdict == MEA.REGRESSED
    assert [m.verdict for m in got.moves if m.name == "candidates"] == ["regressed"]


def test_cost_falling_counts_as_transfer_even_when_quality_is_flat(tmp_path):
    """Consolidation is predicted to make B cheaper before it makes B better. A gate that only
    accepted score improvements would miss its own main effect."""
    _domain(tmp_path)
    _VALUES["candidates"] = 400.0
    got = MEA.measure("domB", root=tmp_path, path=tmp_path / "seal.json", record=False)
    assert got.verdict == MEA.IMPROVED


def test_a_regression_outranks_a_win_and_is_not_averaged_away(tmp_path):
    """Consolidation breaking an untouched domain is the most important thing this gate can find."""
    _domain(tmp_path)
    _VALUES.update(score=0.90, candidates=5000.0)
    got = MEA.measure("domB", root=tmp_path, path=tmp_path / "seal.json", record=False)
    assert got.verdict == MEA.REGRESSED


def test_nothing_moving_is_a_real_reportable_outcome(tmp_path):
    _domain(tmp_path)
    got = MEA.measure("domB", root=tmp_path, path=tmp_path / "seal.json", record=False)
    assert got.verdict == MEA.UNCHANGED and got.usable


def test_dropping_a_pre_registered_metric_is_invalid_not_a_pass(tmp_path):
    """Otherwise the metric that refuses to move can simply stop being reported."""
    _domain(tmp_path)
    _VALUES.pop("candidates")
    got = MEA.measure("domB", root=tmp_path, path=tmp_path / "seal.json", record=False)
    assert got.verdict == MEA.INVALID and "pre-registered metric" in got.reason


def test_an_evaluation_that_will_not_run_is_invalid_not_unchanged(tmp_path):
    _domain(tmp_path, name="broken")
    row = json.loads((tmp_path / "seal.json").read_text(encoding="utf-8"))
    row["eval_entry"] = "packages.transfer_gate.tests.test_gate:no_such_function"
    row["seal"] = ""
    (tmp_path / "seal2.json").write_text(json.dumps(row), encoding="utf-8")
    got = MEA.measure("broken", root=tmp_path, path=tmp_path / "seal2.json", record=False)
    assert got.verdict == MEA.INVALID


def test_a_surface_matching_no_files_refuses_to_freeze(tmp_path):
    with pytest.raises(ValueError):
        freeze("empty", ["nowhere"], "x:y", [Metric("m", 0.0, "higher_is_better")],
               root=tmp_path, path=tmp_path / "e.json")


def test_verdicts_are_kept_so_the_gate_cannot_be_re_rolled(tmp_path, monkeypatch):
    monkeypatch.setattr(MEA, "RESULTS", tmp_path / "results.jsonl")
    _domain(tmp_path)
    MEA.measure("domB", root=tmp_path, path=tmp_path / "seal.json")
    _VALUES["score"] = 0.99
    MEA.measure("domB", root=tmp_path, path=tmp_path / "seal.json")
    rows = MEA.history(path=tmp_path / "results.jsonl")
    assert [r["verdict"] for r in rows] == [MEA.UNCHANGED, MEA.IMPROVED]
