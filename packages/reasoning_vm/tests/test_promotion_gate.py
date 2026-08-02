# -*- coding: utf-8 -*-
"""M-track DSL admission gate: every decision path proven, anchored to the historical i1 receipt.

History being encoded here (2026-07-14): hand-adding the `i1` expressiveness regressed guided
search on `square` 17 -> 31 and was reverted BY HAND. The gate must make that judgment automatic:
admit expressiveness only when the battery stays green, search cost holds, and something new
unlocks. These tests prove each path with REAL candidates (no mocks)."""
from packages.reasoning_vm.promotion_gate import DslCandidate, evaluate

FACT = [((1, 0), 1), ((2, 0), 2), ((3, 0), 6), ((4, 0), 24),
        ((5, 0), 120), ((6, 0), 720), ((3, 2), 6), ((4, 1), 24)]


def _fact_step():
    return DslCandidate("fact_step", lambda acc, i: acc * (i + 1), 2, {"factorial": FACT})


def test_historical_receipt_reproduced():
    """The battery reconstruction is faithful: square costs exactly 17 brute candidates —
    the same number measured on 2026-07-14 before/after the i1 incident."""
    v = evaluate(_fact_step())
    assert v.receipts["brute_base"]["square"] == 17


def test_i1_payload_admitted_safely():
    """The SAFE form of i1's expressiveness: the same unlock (factorial) enters as an appended
    primitive — brute order is preserved (square 17 -> 17, vs the historical arg-grammar 17 -> 31),
    battery green, so the gate ADMITS. Expressiveness itself was never the enemy; ungoverned
    grammar surgery was."""
    v = evaluate(_fact_step())
    assert v.admitted, v.reason
    assert "factorial" in v.receipts["unlocked"]
    assert v.receipts["brute_cand"] == v.receipts["brute_base"]      # append cannot reorder brute
    assert v.basis is not None and "fact_step" in v.basis


def test_duplicate_crowding_rejected_as_search_regression():
    """The i1 DISEASE, caught automatically: a duplicate primitive (S-clone) adds search surface,
    splits the guide's PMI mass with the real S, and regresses median guided cost past tolerance —
    the gate rejects it as search_regression with the numbers attached. This is the exact failure
    class that had to be reverted by hand on 2026-07-14."""
    v = evaluate(DslCandidate("S2", lambda x: x + 1, 1, {"factorial": FACT}))
    assert not v.admitted
    assert v.reason.startswith("search_regression"), v.reason


def test_name_collision_rejected():
    v = evaluate(DslCandidate("S", lambda x: x + 1, 1, {}))
    assert not v.admitted
    assert v.reason.startswith("name_collision")


def test_no_unlock_rejected():
    """A primitive that neither breaks nor regresses anything but also unlocks nothing is still
    rejected — expressiveness must buy something, or the haystack grew for nothing."""
    v = evaluate(DslCandidate("cheat", lambda acc, x: acc + x if x <= 8 else acc, 2, {}))
    assert not v.admitted
    assert v.reason.startswith(("no_unlock", "search_regression"))   # either guard may fire first


def test_threshold_actually_gates():
    """The regression check is a live threshold, not decoration: with tolerance below the measured
    delta the SAME admitted candidate flips to rejected."""
    v = evaluate(_fact_step(), tolerance=-0.01)
    assert not v.admitted
    assert v.reason.startswith("search_regression")


def test_reject_returns_no_basis():
    """Structural auto-revert: a rejected candidate leaves nothing behind — no grown basis."""
    v = evaluate(DslCandidate("S2", lambda x: x + 1, 1, {}))
    assert not v.admitted and v.basis is None
