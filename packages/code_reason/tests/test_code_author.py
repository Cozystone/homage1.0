# -*- coding: utf-8 -*-
"""Code authorship (the code-master flywheel) — verification-anchored program synthesis. The tests
pin the properties that make it a MASTER and not a guesser: it authors real functions from
structure+verification, it NEVER returns unverified code (abstains instead), and a solved shape is
learned so the next same-shaped task is instant (the growing-independence flywheel)."""
from __future__ import annotations

import packages.code_reason.code_author as ca
from packages.code_reason.authorship_harness import Task, seed_tasks
from packages.code_reason.code_author import author, author_suite


def _lib(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "LIBRARY", tmp_path / "lib.jsonl")


def test_authors_the_seed_suite_independently(tmp_path, monkeypatch):
    _lib(tmp_path, monkeypatch)
    r = author_suite(seed_tasks())
    assert r["authorship_rate"] == 1.0                    # 0.0 stub -> 1.0, real synthesis
    assert r["independent_pass"] == r["authored_pass"]    # no advisor needed for these
    assert r["by_source"].get("skeleton", 0) >= 3


def test_every_returned_body_is_verified(tmp_path, monkeypatch):
    _lib(tmp_path, monkeypatch)
    for t in seed_tasks():
        a = author(t)
        assert a.verified and a.body is not None
        assert a.source in ("skeleton", "library")


def test_unsolvable_task_abstains_never_fabricates(tmp_path, monkeypatch):
    """A task no skeleton/composition/schema reaches must yield NO code, not a wrong guess — the code
    honesty floor. (Edit distance USED to be the example here; algorithm schemas now solve it
    verifiably, so the example moved to a task still beyond every organ — a wrapping Caesar cipher,
    which needs per-character modular ord/chr arithmetic no family or schema expresses.)"""
    _lib(tmp_path, monkeypatch)
    hard = Task("caesar_cipher", "def caesar_cipher(s, k):",
                "Return s with every lowercase letter advanced by k positions in the alphabet, wrapping around.",
                "assert caesar_cipher('abc', 1) == 'bcd'\nassert caesar_cipher('xyz', 3) == 'abc'")
    a = author(hard)
    assert a.body is None and not a.verified              # abstain, no fabricated program


def test_solved_shape_is_learned_for_instant_reuse(tmp_path, monkeypatch):
    _lib(tmp_path, monkeypatch)
    t = Task("add", "def add(a, b):", "Return the sum of a and b.", "assert add(2,3)==5")
    first = author(t)
    assert first.source == "skeleton" and first.verified
    # a same-shaped task now resolves from the LIBRARY on the first try (independence compounds)
    again = Task("plus", "def plus(a, b):", "Return the sum of a and b.", "assert plus(10,5)==15")
    second = author(again)
    assert second.source == "library" and second.verified and second.tried == 1


def test_advisor_draft_is_still_gated(tmp_path, monkeypatch):
    """An advisor may draft what skeletons cannot — but a WRONG draft is rejected by the same gate."""
    _lib(tmp_path, monkeypatch)
    hard = Task("triple", "def triple(x):", "Return x multiplied by three.", "assert triple(4)==12")

    def bad_advisor(task):
        return "return x * 2"                             # wrong on purpose

    a = author(hard, advisor=bad_advisor)
    assert a.body is None and not a.verified              # the gate refused the wrong draft

    def good_advisor(task):
        return "def triple(x):\n    return x * 3"

    b = author(hard, advisor=good_advisor)
    assert b.verified and b.source == "advisor" and b.body.strip() == "return x * 3"
