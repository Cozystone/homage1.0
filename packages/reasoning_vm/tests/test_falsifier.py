# -*- coding: utf-8 -*-
"""F4 — the falsifier test: the induction engine must RE-DERIVE the hand kernels, or the whole
'let it build its own algorithms' thesis is falsified. Locks in that re-derivation stays true."""
from __future__ import annotations

from packages.reasoning_vm.falsifier import _ARITH, _equivalent, run_falsifier


def _by_name(results, name):
    return next(r for r in results if r.get("kernel") == name)


def test_all_arithmetic_kernels_rederived():
    """Every hand-built arithmetic kernel is re-derived from examples AND equivalent on 120
    random unseen inputs. This is the engineering verdict: their hand-code is redundant."""
    rep = run_falsifier()
    arith = [r for r in rep["results"] if r["domain"] == "arithmetic"]
    assert len(arith) == 6
    for r in arith:
        assert r["rederived"] is True, f"{r['kernel']} not re-derived: {r}"
        # the induced program is real DSL source, not a stub
        assert "return acc" in r["program"]


def test_compositional_kernels_reuse_induced_primitives():
    """mul/square/pow2 must be induced ON TOP of earlier-induced primitives (library growth),
    not from raw successors — the induced program references add / double by name."""
    rep = run_falsifier()
    assert "add(acc" in _by_name(rep["results"], "mul")["program"]
    assert "add(acc" in _by_name(rep["results"], "square")["program"]
    assert "double(acc" in _by_name(rep["results"], "pow2")["program"]


def test_equivalence_check_actually_bites():
    """The equivalence gate is not vacuous: a deliberately wrong fn fails it, so a True verdict
    means real behavioural equality, not a passed-by-construction check."""
    add_oracle = _ARITH[0][1]
    assert _equivalent(add_oracle, add_oracle, 0, 500) is True
    assert _equivalent(lambda a, b: a + b + 1, add_oracle, 0, 500) is False


def test_verdict_counts_are_honest():
    """The reported counts match the per-kernel results — the summary can't overstate."""
    rep = run_falsifier()
    testable = [r for r in rep["results"] if r.get("rederived") is not None]
    rederived = [r for r in testable if r["rederived"]]
    assert rep["testable"] == len(testable)
    assert rep["rederived"] == len(rederived)
    assert set(rep["rederived_kernels"]) == {r["kernel"] for r in rederived}
    assert "frontier" in rep["honest_note"].lower()
