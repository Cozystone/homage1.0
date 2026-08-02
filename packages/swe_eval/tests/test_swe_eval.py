# -*- coding: utf-8 -*-
"""Offline, deterministic tests for the swe_eval harness — no network, no Docker.

These pin the two honest claims the diagnostic rests on: (1) the lexical localizer ranks the file an
issue is about above noise, and (2) a SWE-bench-shaped instance yields ZERO literal examples for
code_author (the shape gap), so abstention there is a real property, not an accident."""
from __future__ import annotations

from packages.swe_eval import localizer as loc
from packages.swe_eval import repo_reader as rr


def test_tokens_pull_salient_identifiers():
    toks = loc._tokens("`separability_matrix` in astropy.modeling.separable is wrong for "
                       "nested CompoundModel")
    assert "separability_matrix" in toks
    assert "separable" in toks          # leaf of the dotted path
    assert "compoundmodel" in toks
    assert "the" not in toks and "for" not in toks


def test_localize_ranks_the_named_file_first():
    files = ["pkg/util/helpers.py", "pkg/modeling/separable.py", "pkg/io/reader.py",
             "pkg/modeling/tests/test_separable.py"]

    def read(p):
        return "def separability_matrix(m):\n    return m\n" if p.endswith("separable.py") else "x = 1\n"

    lz = loc.localize("separability_matrix computes separable wrong", files, read_file=read)
    assert lz.top1 == "pkg/modeling/separable.py"
    # the test file must be excluded from candidates (fixes don't live in the test tree)
    assert all("test_" not in p.rsplit("/", 1)[-1] for p, _ in lz.ranked)


def test_gold_files_parses_unified_diff():
    patch = ("diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py\n"
             "--- a/astropy/modeling/separable.py\n"
             "+++ b/astropy/modeling/separable.py\n@@ -1 +1 @@\n-x\n+y\n")
    assert loc.gold_files(patch) == ["astropy/modeling/separable.py"]


def test_read_functions_lifts_code_situation_over_a_file():
    src = ("def a(x):\n    return x + 1\n\n"
           "class C:\n    def m(self, y):\n        return y\n\n"
           "def b(z):\n    for _ in z:\n        pass\n")
    sits = rr.read_functions(src)
    names = {s.name for s in sits}
    assert {"a", "m", "b"} <= names
    b = next(s for s in sits if s.name == "b")
    assert b.has_loop is True


def test_swe_instance_yields_zero_literal_examples_for_code_author():
    # A SWE-bench-shaped instance: NL issue + pytest node-ids, no `assert f(...)==v`.
    from packages.code_reason import code_author as ca
    from packages.code_reason.authorship_harness import Task
    inst = {"FAIL_TO_PASS": ["astropy/modeling/tests/test_separable.py::test_separable[compound6]"]}
    from packages.swe_eval.pipeline import _as_asserts, _LITERAL_ASSERT
    test = "\n".join(_as_asserts(inst))
    assert _LITERAL_ASSERT.search(test) is None
    task = Task(name="x", signature="def _unknown():", docstring="an issue", test=test)
    assert ca._parse_examples(task) == ()      # nothing code_author can learn from -> abstain
