# -*- coding: utf-8 -*-
"""F-next: verify-gated induction generalizes to UNCATALOGUED families; the learned-search frontier
stays honestly open; and composite-basis execution fails safe (the None-propagation bug fix)."""
from __future__ import annotations

import pytest

from packages.reasoning_vm import induction_flywheel as FW
from packages.reasoning_vm.open_generalization import _library, run_generalization
from packages.reasoning_vm.procedure_induction import Program


@pytest.fixture(autouse=True)
def _tmp_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(FW, "_LEDGER", tmp_path / "ledger.jsonl")   # keep the real ledger clean


def test_induction_generalizes_beyond_hand_catalog():
    """The real F-next result: procedures NO ONE cataloged (triangular via loop-index, sq_b via
    the second input, bpow via mul-on-mul) are induced correctly and pass the equivalence probe."""
    rep = run_generalization()
    assert rep["all_novel_families_induced"] is True
    assert len(rep["rows"]) == 3
    for r in rep["rows"]:
        assert r["induced_correct"] is True, f"{r['family']} failed: {r}"
        assert r["program"] and "return acc" in r["program"]


def test_novel_programs_use_the_right_dsl_feature():
    """triangular must use the loop INDEX; bpow must compose the induced mul — i.e. the engine
    reached for DSL machinery the hand catalog never exercised, not a memorised skeleton."""
    rows = {r["family"]: r["program"] for r in run_generalization()["rows"]}
    assert "acc, i)" in rows["triangular"]          # arg='i' — the loop index
    assert "mul(acc" in rows["bpow"]                # exponentiation built on induced multiplication


def test_learned_search_extrapolates_to_unseen_families():
    """The F-next result: the featurized PMI guide EXTRAPOLATES its learned search to families it
    never saw — it must HELP (fewer candidates than brute) on at least 2 of the 3 uncatalogued
    families (measured 3/3: triangular 20→2, sq_b 22→20, bpow 90→65). A robust threshold ≥2
    tolerates dream randomness while proving genuine extrapolation, not interpolation."""
    rep = run_generalization()
    assert isinstance(rep["guide_helps_on"], list)
    for r in rep["rows"]:
        assert r["guide_effect"] in ("helps", "neutral", "worse")
    assert len(rep["guide_helps_on"]) >= 2, f"expected extrapolation on >=2 families, got {rep['guide_helps_on']}"
    assert "extrapolat" in rep["verdict"].lower()


def test_composite_basis_runs_fail_safe_not_crash():
    """Regression: a program composing a grown (arity-2) basis fn can push an inner run past the
    loop budget → the inner returns None; Program.run must PROPAGATE None, not crash on
    `None > 10**12`. Before the fix this raised TypeError and broke dreaming over a rich library."""
    basis = _library()                              # includes induced mul (composite, arity 2)
    prog = Program("1", "a", "mul", "b")            # b^a shape; large intermediates blow the budget
    assert prog.run(9, 9, basis) is None            # fails safe: None, no exception
    assert prog.run(2, 3, basis) == 3 ** 2          # still correct where it stays in-budget (b^a=9)
