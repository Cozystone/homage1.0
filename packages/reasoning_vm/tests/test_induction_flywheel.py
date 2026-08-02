# -*- coding: utf-8 -*-
"""Verification flywheel: dreamed search guidance (measured speedup) + prediction-error self-repair."""
import pytest

from packages.reasoning_vm import induction_flywheel as FW
from packages.reasoning_vm.induction_flywheel import (SearchGuide, check_and_repair,
                                                      grow_basis, guided_induce, seed_basis)


@pytest.fixture(autouse=True)
def _tmp_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(FW, "_LEDGER", tmp_path / "ledger.jsonl")


def _mul_examples():
    return [((a, b), a * b) for a, b in [(2, 3), (4, 5), (1, 7), (0, 9), (6, 6), (3, 8), (9, 2), (5, 5)]]


def test_dreamed_guide_reduces_search():
    add, _ = guided_induce("add", [((a, b), a + b) for a, b in
                                   [(2, 3), (10, 7), (1, 1), (0, 5), (6, 6), (4, 9), (8, 2), (3, 0)]])
    basis = grow_basis(seed_basis(), add)
    guide = SearchGuide()
    assert guide.dream(basis, rounds=600) > 100        # sleep learned from self-generated pairs
    _, brute = guided_induce("mul", _mul_examples(), basis, guide=None)
    _, guided = guided_induce("mul", _mul_examples(), basis, guide=guide)
    assert guided < brute                              # measured speedup, not a claim
    # generalization: an UNSEEN task family (a^2, second arg ignored)
    sq = [((a, b), a * a) for a, b in [(2, 0), (3, 1), (4, 2), (5, 5), (6, 3), (7, 7), (1, 4), (8, 0)]]
    _, b2 = guided_induce("square", sq, basis, guide=None)
    _, g2 = guided_induce("square", sq, basis, guide=guide)
    assert g2 <= b2


def test_prediction_error_triggers_structural_repair():
    """The owner's flywheel: a rule that fit a biased world is contradicted by reality, and the
    STRUCTURE (program) is rewritten through the same verify gate — not just a stat update."""
    trap = [((a, 1), a + 1) for a in [2, 7, 4, 9, 3, 6, 1, 8]]   # b=1 everywhere → ambiguous world
    hyp, _ = guided_induce("mystery", trap, seed_basis())
    assert hyp.fn(5, 3) != 8                                     # believes a wrong generalization
    fixed, repaired, updated = check_and_repair(
        hyp, trap, truth_fn=lambda a, b: a + b, probes=[(5, 3), (2, 2)], basis=seed_basis())
    assert repaired and fixed.fn(5, 3) == 8 and fixed.fn(9, 4) == 13
    assert len(updated) == len(trap) + 1                         # counterexample joined the examples
    rows = FW._LEDGER.read_text(encoding="utf-8").splitlines()
    kinds = [__import__("json").loads(r)["kind"] for r in rows]
    assert "prediction_error" in kinds and "tombstone" in kinds  # auditable error + retirement


def test_no_error_no_modification():
    ex = [((a, b), a + b) for a, b in [(2, 3), (10, 7), (1, 1), (0, 5), (6, 6), (4, 9), (8, 2), (3, 0)]]
    ind, _ = guided_induce("add", ex, seed_basis())
    same, repaired, _ = check_and_repair(ind, ex, truth_fn=lambda a, b: a + b,
                                         probes=[(5, 3), (7, 7)], basis=seed_basis())
    assert not repaired and same.program.source() == ind.program.source()


def test_sleep_abstraction_tower_and_persistence(tmp_path, monkeypatch):
    """F1: the 3-level tower — add/double induced from seed, auto-promoted to a PERSISTENT
    library, reloaded from disk, and 2^a (inexpressible from seed alone) induced on top."""
    monkeypatch.setattr(FW, "_LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(FW, "_LIBRARY", tmp_path / "library.json")
    guided_induce("add", [((a, b), a + b) for a, b in
                          [(2, 3), (10, 7), (1, 1), (0, 5), (6, 6), (4, 9), (8, 2), (3, 0)]])
    guided_induce("double", [((a, b), 2 * a) for a, b in
                             [(2, 9), (5, 0), (1, 3), (7, 7), (4, 1), (0, 4), (3, 2), (6, 5)]])
    rep = FW.sleep_abstraction()                       # sleep: auto-promotion, no hand grow_basis
    assert rep["library_size"] == 2
    basis = FW.load_library()                          # rebirth from DISK
    assert "add" in basis and "double" in basis
    pow2_ex = [((a, b), 2 ** a) for a, b in
               [(1, 0), (2, 3), (3, 1), (4, 4), (0, 7), (5, 2), (6, 0), (3, 3)]]
    bare, _ = guided_induce("pow2_bare", pow2_ex, seed_basis())
    assert bare is None                                # honest: inexpressible from seed alone
    pow2, _ = guided_induce("pow2", pow2_ex, basis)
    assert pow2 is not None and all(pow2.fn(a, 0) == 2 ** a for a in range(0, 11))
    FW.sleep_abstraction()
    basis2 = FW.load_library()                         # the tower keeps growing
    assert "pow2" in basis2 and basis2["pow2"][0](7, 0) == 128


def test_tombstoned_programs_are_not_promoted(tmp_path, monkeypatch):
    monkeypatch.setattr(FW, "_LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(FW, "_LIBRARY", tmp_path / "library.json")
    trap = [((a, 1), a + 1) for a in [2, 7, 4, 9, 3, 6, 1, 8]]
    hyp, _ = guided_induce("mystery", trap, seed_basis())
    check_and_repair(hyp, trap, truth_fn=lambda a, b: a + b, probes=[(5, 3)], basis=seed_basis())
    FW.sleep_abstraction()
    lib = FW._load_lib_file()
    # the repaired (correct) version is in the library; the tombstoned wrong one is not
    assert lib.get("mystery", {}).get("init") == "a"   # acc=a; repeat b: S — the CORRECT program


def test_graduation_gate_earns_speech(tmp_path, monkeypatch):
    """F2.5: an induced procedure may SPEAK only after sustained shadow accuracy — and even then
    only when the oracle cross-check agrees at answer time."""
    import packages.reasoning_vm.shadow_flywheel as SF
    monkeypatch.setattr(FW, "_LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(FW, "_LIBRARY", tmp_path / "library.json")
    # build the tower first (as the live persistent library already has): add + double
    guided_induce("add", [((a, b), a + b) for a, b in
                          [(2, 3), (10, 7), (1, 1), (0, 5), (6, 6), (4, 9), (8, 2), (3, 0)]])
    guided_induce("double", [((a, b), 2 * a) for a, b in
                             [(2, 9), (5, 0), (1, 3), (7, 7), (4, 1), (0, 4), (3, 2), (6, 5)]])
    FW.sleep_abstraction()
    SF._LIB_CACHE["basis"] = None
    assert SF.graduated_answer("2의 10승은?") is None            # default-deny: nothing earned yet
    for k in (6, 7, 8, 9, 11):                                   # earn it on real-shaped traffic
        r = SF.shadow_observe(f"2의 {k}승은?")
        assert r and r["correct"]
    assert SF.graduated("pow2")
    ans = SF.graduated_answer("2의 10승은?")
    assert ans and ans["result_value"] == 1024
    assert ans["reasoning_certificate"]["guarantees"]["self_induced"] is True


def test_one_shadow_miss_ungraduates(tmp_path, monkeypatch):
    import json as _json

    import packages.reasoning_vm.shadow_flywheel as SF
    monkeypatch.setattr(FW, "_LEDGER", tmp_path / "ledger.jsonl")
    rows = [{"kind": "shadow_prediction", "name": "pow2", "correct": True}] * 6
    rows.append({"kind": "shadow_prediction", "name": "pow2", "correct": False})
    (tmp_path / "ledger.jsonl").write_text(
        "\n".join(_json.dumps(r) for r in rows), encoding="utf-8")
    assert not SF.graduated("pow2")                              # one miss → re-earn required
