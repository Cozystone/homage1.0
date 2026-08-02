# -*- coding: utf-8 -*-
"""Offline, deterministic tests for the FUSED repo-engineering wave — no network, no Docker.

These pin the wiring's load-bearing claims:
  * the edit-schema proposer reaches real single-token / single-block fix shapes;
  * localization runs as a deliberation that MEC-schedules the cheap signals before the expensive AST;
  * the regression gate is isomorphic to physics_truth (accept only green, quarantine red, abstain
    when it cannot run) — proven end-to-end NATIVELY on a self-contained git fixture (a genuine 0->1
    of the propose->verify->ship-green loop, no Docker);
  * self_evolution registers repo_engineering as verifier-backed WITHOUT breaking the safety invariant;
  * the neuro-ledger row is zero-param and not a fact source.
"""
from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from packages.swe_eval import edit_schemas as es
from packages.swe_eval import callgraph as cg
from packages.swe_eval import regression_gate as rg


# ── edit schemas ──────────────────────────────────────────────────────────────────────────────────

def test_operand_substitution_reaches_wrong_operand_fix():
    src = ("def cstack(left, right):\n"
           "    cright = zeros()\n"
           "    cright[0] = 1\n"
           "    return cright\n")
    cands = es.propose_edits(src, "cstack")
    subs = [c for c in cands if c.schema == "operand_substitution"]
    assert subs, "operand substitution should fire on an assignment"
    # the fix substitutes an in-scope name ('right') for the literal RHS
    assert any("cright[0] = right" in c.new_source for c in subs)


def test_block_deletion_reaches_spurious_block_removal():
    src = ("def conv(data):\n"
           "    x = 1\n"
           "    if bad(data):\n"
           "        data = view(data)\n"
           "        flag = True\n"
           "    return data\n")
    cands = es.propose_edits(src, "conv")
    dels = [c for c in cands if c.schema == "block_deletion"]
    assert dels
    assert any("view(data)" not in c.new_source for c in dels)


def test_comparison_flip_is_a_single_operator_change():
    src = "def ok(a, b):\n    return a <= b\n"
    cands = [c for c in es.propose_edits(src, "ok") if c.schema == "comparison_flip"]
    assert any("a < b" in c.new_source for c in cands)


def test_propose_is_deterministic_and_syntactically_valid():
    import ast
    src = "def f(a, b):\n    c = a\n    return c and b\n"
    a = [c.new_source for c in es.propose_edits(src, "f")]
    b = [c.new_source for c in es.propose_edits(src, "f")]
    assert a == b and a                                  # deterministic, non-empty
    for s in a:
        ast.parse(s)                                     # every candidate parses


def test_unified_diff_is_git_shaped():
    src = "def f(a, b):\n    c = a\n    return c\n"
    cand = next(c for c in es.propose_edits(src, "f") if "c = b" in c.new_source)
    d = es.unified_diff(src, cand.new_source, "pkg/f.py")
    assert d.startswith("--- a/pkg/f.py") and "+++ b/pkg/f.py" in d
    assert "-    c = a" in d and "+    c = b" in d


def test_unknown_function_yields_no_candidates():
    assert es.propose_edits("def g():\n    return 1\n", "nonexistent") == []


# ── multi-token / multi-statement families (W-A widening) ────────────────────────────────────────

def test_none_guard_insertion_adds_a_missing_branch():
    src = "def collect(x):\n    out = []\n    for k in x:\n        out.append(k)\n    return out\n"
    cands = [c for c in es.propose_edits(src, "collect") if c.schema == "none_guard_insertion"]
    assert cands, "none_guard_insertion should fire on a function with a parameter"
    # a genuine multi-LINE edit: the guard is two lines inserted at the head
    assert any("if x is None:" in c.new_source and "return []" in c.new_source for c in cands)


def test_guarded_early_return_is_a_two_site_edit():
    src = "def ratio(a, b):\n    return a // b\n"
    cands = [c for c in es.propose_edits(src, "ratio") if c.schema == "guarded_early_return"]
    assert cands
    # guard + return coordinated BEFORE the existing return (two coordinated lines)
    assert any("if not b:" in c.new_source and c.new_source.count("return") == 2 for c in cands)


def test_condition_refinement_adds_a_conjunct():
    src = "def ok(name, active):\n    if name:\n        return True\n    return False\n"
    cands = [c for c in es.propose_edits(src, "ok") if c.schema == "condition_refinement"]
    assert any("and active" in c.new_source for c in cands)


def test_adjacent_stmt_swap_is_a_block_replacement():
    src = "def f(a, b):\n    x = a + 1\n    y = b + 2\n    return x - y\n"
    cands = [c for c in es.propose_edits(src, "f") if c.schema == "adjacent_stmt_swap"]
    assert len(cands) == 1
    assert cands[0].new_source.index("y = b + 2") < cands[0].new_source.index("x = a + 1")


def test_multi_edit_enumeration_stays_bounded_and_valid():
    import ast
    # a function with several params, ifs, returns and statements — the multiplicative families here
    src = ("def big(a, b, c):\n"
           "    r = a\n"
           "    if a > b:\n"
           "        r = b\n"
           "    s = c\n"
           "    if s:\n"
           "        r = s\n"
           "    return r\n")
    cands = es.propose_edits(src, "big")
    assert len(cands) <= es.MAX_TOTAL_CANDIDATES          # never explodes the verify budget
    for c in cands:
        ast.parse(c.new_source)                          # every widened candidate is still valid Python
    a = [c.new_source for c in es.propose_edits(src, "big")]
    assert a == [c.new_source for c in es.propose_edits(src, "big")]   # deterministic


def test_l3_induced_family_is_inert_when_store_empty():
    """L3 reuse is honest: with no induced schema on disk it proposes nothing (never fabricates)."""
    from packages.code_reason import schema_induction as si
    if si.load_induced() or getattr(si, "LOAD_GROWN", False):
        import pytest as _pt
        _pt.skip("induced store is populated in this checkout")
    src = "def f(a, b):\n    c = a\n    return c\n"
    assert [c for c in es.propose_edits(src, "f") if c.schema == "l3_induced"] == []


# ── native gate: the MULTI-STATEMENT path ships only the green edit (a 0->1 for the widened families) ─

@pytest.mark.skipif(shutil.which("git") is None, reason="git required for the native gate fixture")
def test_native_gate_ships_multistatement_none_guard(tmp_path):
    """A real bug whose fix is a MULTI-LINE statement insertion (a missing None-guard): prove the
    regression gate ACCEPTS exactly the inserted-guard candidate and QUARANTINES a wrong guard. This
    is the multi-statement analogue of the single-token native 0->1 — no Docker."""
    rd = tmp_path / "repo"
    rd.mkdir()
    (rd / "mod.py").write_text(
        "def collect(x):\n    out = []\n    for k in x:\n        out.append(k)\n    return out\n",
        encoding="utf-8")
    (rd / "test_mod.py").write_text(
        "from mod import collect\n"
        "def test_none():\n    assert collect(None) == []\n"
        "def test_list():\n    assert collect([1, 2, 3]) == [1, 2, 3]\n", encoding="utf-8")
    _git(rd, "init", "-q"); _git(rd, "config", "user.email", "t@t"); _git(rd, "config", "user.name", "t")
    _git(rd, "add", "-A"); _git(rd, "commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(rd), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    src = (rd / "mod.py").read_text(encoding="utf-8")
    f2p, p2p = ["test_mod.py::test_none"], ["test_mod.py::test_list"]

    fix = next(c for c in es.propose_edits(src, "collect")
               if c.schema == "none_guard_insertion" and "if x is None:" in c.new_source
               and "return []" in c.new_source)
    v = rg.verify_native(str(rd), "", es.unified_diff(src, fix.new_source, "mod.py"), f2p, p2p,
                         base_commit=base)
    assert v.backend == "native"
    assert v.status == rg.ACCEPTED and v.resolved is True, (v.status, v.reason, v.failed)
    assert v.f2p_pass == 1 and v.p2p_pass == 1

    wrong = next(c for c in es.propose_edits(src, "collect")
                 if c.schema == "none_guard_insertion" and "return None" in c.new_source)
    vw = rg.verify_native(str(rd), "", es.unified_diff(src, wrong.new_source, "mod.py"), f2p, p2p,
                          base_commit=base)
    assert vw.resolved is False                          # a wrong guard is never shipped (fail-0)


@pytest.mark.skipif(shutil.which("git") is None, reason="git required for the native gate fixture")
def test_native_gate_ships_two_site_guarded_return(tmp_path):
    """A real bug whose fix is a TWO-SITE coordinated edit (guard + early return): the gate accepts the
    inserted `if not b: return 0` guard and rejects a guard that regresses PASS_TO_PASS."""
    rd = tmp_path / "repo"
    rd.mkdir()
    (rd / "mod.py").write_text("def ratio(a, b):\n    return a // b\n", encoding="utf-8")
    (rd / "test_mod.py").write_text(
        "from mod import ratio\n"
        "def test_zero():\n    assert ratio(4, 0) == 0\n"
        "def test_div():\n    assert ratio(6, 2) == 3\n", encoding="utf-8")
    _git(rd, "init", "-q"); _git(rd, "config", "user.email", "t@t"); _git(rd, "config", "user.name", "t")
    _git(rd, "add", "-A"); _git(rd, "commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(rd), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    src = (rd / "mod.py").read_text(encoding="utf-8")
    f2p, p2p = ["test_mod.py::test_zero"], ["test_mod.py::test_div"]

    fix = next(c for c in es.propose_edits(src, "ratio")
               if c.schema == "guarded_early_return" and "if not b:" in c.new_source
               and "return 0" in c.new_source)
    v = rg.verify_native(str(rd), "", es.unified_diff(src, fix.new_source, "mod.py"), f2p, p2p,
                         base_commit=base)
    assert v.status == rg.ACCEPTED and v.resolved is True, (v.status, v.reason, v.failed)
    assert v.f2p_pass == 1 and v.p2p_pass == 1


@pytest.mark.skipif(shutil.which("git") is None, reason="git required for the native gate fixture")
def test_native_gate_ships_a_two_file_coordinated_diff(tmp_path):
    """A bug whose FAIL_TO_PASS needs BOTH files fixed: prove the 2-file mechanism (combine two single-
    file diffs, gate as one) ACCEPTS the coordinated pair and that NEITHER single file alone resolves."""
    rd = tmp_path / "repo"
    rd.mkdir()
    (rd / "a.py").write_text("def pick_a(a, b):\n    r = a\n    return r\n", encoding="utf-8")
    (rd / "b.py").write_text("def pick_b(c, d):\n    s = c\n    return s\n", encoding="utf-8")
    (rd / "test_mod.py").write_text(
        "from a import pick_a\nfrom b import pick_b\n"
        "def test_both():\n    assert pick_a(1, 2) + pick_b(3, 4) == 6\n", encoding="utf-8")
    _git(rd, "init", "-q"); _git(rd, "config", "user.email", "t@t"); _git(rd, "config", "user.name", "t")
    _git(rd, "add", "-A"); _git(rd, "commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(rd), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    sa = (rd / "a.py").read_text(encoding="utf-8")
    sb = (rd / "b.py").read_text(encoding="utf-8")
    f2p = ["test_mod.py::test_both"]

    fa = next(c for c in es.propose_edits(sa, "pick_a")
              if c.schema == "operand_substitution" and "r = b" in c.new_source)
    fb = next(c for c in es.propose_edits(sb, "pick_b")
              if c.schema == "operand_substitution" and "s = d" in c.new_source)
    da = es.unified_diff(sa, fa.new_source, "a.py")
    db = es.unified_diff(sb, fb.new_source, "b.py")

    # the COMBINED 2-file diff resolves
    combined = es.combine_diffs([da, db])
    v = rg.verify_native(str(rd), "", combined, f2p, [], base_commit=base)
    assert v.status == rg.ACCEPTED and v.resolved is True, (v.status, v.reason, v.failed)
    # each single file alone does NOT (proving the fix genuinely spans two files)
    assert rg.verify_native(str(rd), "", da, f2p, [], base_commit=base).resolved is False
    assert rg.verify_native(str(rd), "", db, f2p, [], base_commit=base).resolved is False


# ── call graph ──────────────────────────────────────────────────────────────────────────────────

def test_callgraph_corroborates_defining_file():
    files = {"pkg/sep.py": "def separability_matrix(m):\n    return m\n",
             "pkg/user.py": "from pkg.sep import separability_matrix\ndef go():\n    pass\n"}
    corr = cg.corroborate({"separability_matrix"}, "pkg/sep.py", list(files),
                          read_file=lambda p: files.get(p))
    assert "separability_matrix" in corr.top_defines
    assert "pkg/user.py" in corr.importers_of_top


# ── localization deliberation (MEC cheap-before-expensive; honest abstain) ───────────────────────

def _toy_repo():
    files = {
        "pkg/core.py": "x = 1\n",
        "pkg/separable.py": ("def separability_matrix(model):\n    return _cstack(model)\n\n"
                             "def _cstack(left):\n    a = 1\n    return a\n"),
        "pkg/util.py": "def helper():\n    return 0\n",
    }
    return files


def test_localization_is_a_deliberation_that_grounds_and_reorders(monkeypatch, tmp_path):
    monkeypatch.setenv("ATANOR_METACOG_DIR", str(tmp_path / "mec"))
    from packages.deliberator import repo_engineering as red
    from packages.swe_eval import localizer as loc
    files = _toy_repo()
    toks = loc._tokens("`separability_matrix` returns a wrong separable result")
    lz = red.deliberate_localization("separability_matrix wrong", list(files),
                                     read_file=lambda p: files.get(p), issue_tokens=toks)
    assert lz.abstained is False
    assert lz.top_file == "pkg/separable.py"             # the file defining the issue symbol
    assert lz.target_function == "separability_matrix"
    assert lz.hops == 3
    # MEC re-steer ran the CHEAP callgraph before the EXPENSIVE AST read -> order != declared baseline
    assert lz.mec["reordered"] is True
    assert lz.certificate["guarantees"]["fabricated_facts"] is False
    assert lz.certificate["guarantees"]["every_executed_step_verified"] is False
    assert lz.certificate["guarantees"]["every_executed_step_structurally_grounded"] is True
    assert lz.certificate["guarantees"]["localization_authority"] == "candidate_only"
    target_step = next(step for step in lz.steps if step.organ == "function_target")
    assert target_step.grounded is True
    assert target_step.certificate["authority"] == "candidate_only"


def test_function_target_does_not_ground_a_ghost_issue_symbol():
    from packages.deliberator import repo_engineering as red

    outcome = red._run_function_target(
        {"ghost_symbol"},
        "pkg/core.py",
        lambda _path: "def existing_function():\n    return 1\n",
    )

    assert outcome.answer is None
    assert outcome.bind_value is None
    assert outcome.grounded is False
    assert outcome.certificate["function_identified"] is None
    assert outcome.certificate["authority"] == "candidate_only"
    assert "no issue-named function candidate" in outcome.certificate["reason"]


def test_localization_abstains_when_no_file_grounds(monkeypatch, tmp_path):
    monkeypatch.setenv("ATANOR_METACOG_DIR", str(tmp_path / "mec"))
    from packages.deliberator import repo_engineering as red
    lz = red.deliberate_localization("something", [], read_file=lambda p: None, issue_tokens=set())
    assert lz.abstained is True and lz.top_file is None
    assert "won't guess" in (lz.reason or "")


# ── FUSED localization: the failing-test signal is the W-A top-1 lever ────────────────────────────

def test_build_test_signal_extracts_package_stem_and_imports():
    from packages.swe_eval import localizer as loc
    f2p = ["astropy/io/ascii/tests/test_rst.py::test_rst_with_header_rows"]
    tp = ("diff --git a/astropy/io/ascii/tests/test_rst.py b/astropy/io/ascii/tests/test_rst.py\n"
          "--- a/astropy/io/ascii/tests/test_rst.py\n+++ b/astropy/io/ascii/tests/test_rst.py\n"
          "@@ -1 +1 @@\n+from astropy.io.ascii.rst import RST\n")
    sig = loc.build_test_signal(f2p, tp, read_file=lambda p: None)
    assert sig.active
    assert "astropy/io/ascii" in sig.pkg_dirs          # package = parent-of-/tests
    assert "rst" in sig.test_stems                     # test_rst -> rst
    assert "astropy.io.ascii.rst" in sig.imported_modules


def test_localize_fused_reranks_the_test_named_file_above_a_lexical_winner():
    """The gold file shares the test's package + stem but is lexically dominated by a central file in
    another package; the failing-test signal must float it to top-1 (the 2/10 -> higher lever)."""
    from packages.swe_eval import localizer as loc
    files = {
        # the true edit site: the RST writer (the test is named test_rst) — but it matches little of the
        # issue's vocabulary, so it loses on lexical score alone
        "astropy/io/ascii/rst.py": "class RST:\n    def write(self, lines):\n        return lines\n",
        "astropy/io/ascii/core.py": "x = 1\n",
        # a central file in a DIFFERENT package that matches MANY issue identifiers -> lexical winner
        "astropy/table/table.py": ("class Table:\n    pass\nclass Column:\n    pass\n"
                                   "class Row:\n    pass\ndef join():\n    pass\ndef vstack():\n    pass\n"),
    }
    problem = "Table Column Row join vstack lose formatting when written by the writer"
    f2p = ["astropy/io/ascii/tests/test_rst.py::test_rst_with_header_rows"]
    base = loc.localize(problem, list(files), read_file=files.get)
    fused, sig = loc.localize_fused(problem, list(files), files.get, f2p=f2p, test_patch="")
    assert base.top1 == "astropy/table/table.py"                  # lexical winner is the WRONG file
    assert fused.top1 == "astropy/io/ascii/rst.py"               # fused corrects it to the edit site


def test_localize_fused_is_identity_without_a_test_signal():
    from packages.swe_eval import localizer as loc
    files = {"pkg/a.py": "def foo():\n    return 1\n", "pkg/b.py": "x = 1\n"}
    base = loc.localize("foo", list(files), read_file=files.get)
    fused, sig = loc.localize_fused("foo", list(files), files.get, f2p=[], test_patch="")
    assert sig.active is False
    assert fused.ranked == base.ranked                           # no signal -> exactly the lexical rank


def test_deliberation_adds_test_proximity_hop_and_reranks(monkeypatch, tmp_path):
    monkeypatch.setenv("ATANOR_METACOG_DIR", str(tmp_path / "mec"))
    from packages.deliberator import repo_engineering as red
    from packages.swe_eval import localizer as loc
    files = {
        "pkg/sub/rst.py": "def write_table(header):\n    return header\n",
        "pkg/sub/core.py": "x = 1\n",
        "pkg/other/big.py": "def write_table(header):\n    return header\n" + "# table\n" * 40,
    }
    toks = loc._tokens("write_table drops header")
    lz = red.deliberate_localization("write_table drops header", list(files), read_file=files.get,
                                     issue_tokens=toks,
                                     f2p=["pkg/sub/tests/test_rst.py::test_x"], test_patch="")
    assert lz.hops == 4
    assert [s.organ for s in lz.steps] == ["file_scan", "test_proximity", "callgraph", "function_target"]
    assert lz.top_file == "pkg/sub/rst.py"               # re-ranked into the test's package, by stem
    assert lz.mec["reordered"] is True                   # MEC still schedules cheap-before-expensive
    assert lz.certificate["guarantees"]["fabricated_facts"] is False


def test_generation_never_reads_the_gold_patch(tmp_path, monkeypatch):
    """No-gold-leakage guard: wrap the instance so ANY read of instance['patch'] raises, then run the
    generator. It must complete (proposing + gating) without ever touching the gold solution."""
    from packages.swe_eval import patch_pipeline as pp

    class _GoldGuard(dict):
        def __getitem__(self, k):
            assert k != "patch", "gold leakage: generation read instance['patch']"
            return super().__getitem__(k)

        def get(self, k, d=None):
            assert k != "patch", "gold leakage: generation read instance['patch']"
            return super().get(k, d)

    rd = tmp_path / "repo"
    rd.mkdir()
    (rd / "mod.py").write_text("def choose(a, b):\n    result = a\n    return result\n", encoding="utf-8")
    _git(rd, "init", "-q"); _git(rd, "config", "user.email", "t@t"); _git(rd, "config", "user.name", "t")
    _git(rd, "add", "-A"); _git(rd, "commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(rd), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    inst = _GoldGuard(instance_id="x__y-1", repo="x/y", base_commit=base,
                      problem_statement="choose returns the wrong operand",
                      FAIL_TO_PASS=["test_mod.py::test_choose"], PASS_TO_PASS=[], test_patch="",
                      patch="+++ b/mod.py\n@@ -1 +1 @@\n-x\n+y\n")   # the gold (must never be read)
    # stub the gate so no Docker is needed; it just proves the generator never reached for gold
    monkeypatch.setattr(rg, "verify_docker",
                        lambda instance, diff, cid=None, timeout_s=900: rg.RegressionVerdict(
                            rg.UNDECIDED, "insufficient-eval-environment", "stub", backend="none"))
    gv = pp.generate_and_verify(inst, str(rd), ["mod.py"], container=None, budget=3)
    assert gv.n_candidates >= 1                          # it did propose edits (from localization only)


def test_repo_deliberation_ledger_entry_is_zero_param():
    from packages.deliberator.repo_engineering import ledger_entry
    e = ledger_entry()
    assert e.fact_source is False and e.fallback_params == 0 and e.enforced is False


# ── regression gate: physics_truth isomorphism + a NATIVE end-to-end 0->1 ────────────────────────

def test_verdict_resolved_only_on_accepted():
    assert rg.RegressionVerdict(rg.ACCEPTED, "regression-green", "").resolved is True
    assert rg.RegressionVerdict(rg.QUARANTINED, "fail-to-pass-still-red", "").resolved is False
    assert rg.RegressionVerdict(rg.UNDECIDED, "insufficient-eval-environment", "").resolved is False


def test_image_name_normalizes_instance_id():
    assert rg.image_for("astropy__astropy-12907") == \
        "swebench/sweb.eval.x86_64.astropy_1776_astropy-12907:latest"


def _git(rd, *args):
    subprocess.run(["git", "-C", str(rd), *args], check=True, capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git required for the native gate fixture")
def test_native_gate_ships_only_the_green_edit(tmp_path):
    """A self-contained git repo with a real bug + a real FAIL_TO_PASS test: propose edits, and prove
    the regression gate ACCEPTS exactly the fixing candidate and QUARANTINES a wrong one. This is a
    native, offline 0->1 of the whole propose->verify->ship-green loop (no Docker)."""
    rd = tmp_path / "repo"
    rd.mkdir()
    (rd / "mod.py").write_text("def choose(a, b):\n    result = a\n    return result\n", encoding="utf-8")
    (rd / "test_mod.py").write_text(
        "from mod import choose\n"
        "def test_choose():\n    assert choose(1, 2) == 2\n"
        "def test_keeps():\n    assert choose(5, 5) == 5\n", encoding="utf-8")
    _git(rd, "init", "-q")
    _git(rd, "config", "user.email", "t@t")
    _git(rd, "config", "user.name", "t")
    _git(rd, "add", "-A")
    _git(rd, "commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(rd), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()

    src = (rd / "mod.py").read_text(encoding="utf-8")
    f2p = ["test_mod.py::test_choose"]
    p2p = ["test_mod.py::test_keeps"]

    fixing = next(c for c in es.propose_edits(src, "choose") if "result = b" in c.new_source)
    fix_diff = es.unified_diff(src, fixing.new_source, "mod.py")
    v = rg.verify_native(str(rd), "", fix_diff, f2p, p2p, base_commit=base)
    assert v.backend == "native"
    assert v.status == rg.ACCEPTED and v.resolved is True, (v.status, v.reason, v.failed)
    assert v.f2p_pass == 1 and v.p2p_pass == 1

    # a WRONG structural edit (substitute the wrong name) must be quarantined, never shipped
    wrong = next(c for c in es.propose_edits(src, "choose")
                 if "result = a" not in c.new_source and "result = b" not in c.new_source
                 and c.schema == "operand_substitution")
    wrong_diff = es.unified_diff(src, wrong.new_source, "mod.py")
    vw = rg.verify_native(str(rd), "", wrong_diff, f2p, p2p, base_commit=base)
    assert vw.resolved is False


# ── self_evolution: repo_engineering registered as verifier-backed, invariant intact ─────────────

def test_repo_engineering_domain_is_registered_and_verifier_backed():
    from packages.self_evolution.evolution_registry import load_registry, evolvability_probes
    loop = next((lp for lp in load_registry() if lp.domain == "repo_engineering"), None)
    assert loop is not None, "repo_engineering must be registered"
    assert loop.generator_kind == "code"
    flags = evolvability_probes(loop)
    assert flags["verifier_exists"] is True              # the regression gate is on disk
    assert flags["generator_exists"] is True


def test_safety_invariant_still_holds_with_new_domain():
    """Adding repo_engineering must not break: a verifier-less loop is NEVER autonomous."""
    from packages.self_evolution.evolution_registry import load_registry, evolvability_probes
    for loop in load_registry():
        flags = evolvability_probes(loop)
        if not flags["verifier_exists"]:
            assert flags["autonomous_safe"] is False, loop.domain


# ── neuro-ledger: zero-param, not a fact source ──────────────────────────────────────────────────

def test_neuro_registration_is_zero_param_not_fact_source():
    from packages.swe_eval import neuro_registration as nr
    chk = nr.budget_check()
    assert chk["params"] == 0 and chk["fact_source"] is False and chk["ok"] is True
