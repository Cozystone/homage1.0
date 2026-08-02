# -*- coding: utf-8 -*-
"""Growth tests for the code-master flywheel: the new skeleton families synthesize, 2-stage
composition reaches tasks no single family reaches, a solved shape is recalled from the library for
an isomorphic (differently-named) task, and the mastery benchmark's own integrity self-test catches
a task shipped with a wrong reference. Every property still rests on the no-fabrication floor:
nothing is returned that the isolated verifier did not certify."""
from __future__ import annotations

import packages.code_reason.code_author as ca
from packages.code_reason.authorship_harness import Task
from packages.code_reason.code_author import (author, _fam_aggregate, _fam_list_comp, _run_fast)


def _lib(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "LIBRARY", tmp_path / "library.jsonl")


# ------------------------------------------------------------------- (1) new families synthesize

def test_new_expression_families_synthesize(tmp_path, monkeypatch):
    """String / list-comprehension / numeric families each author a verified body — capability the
    old 6-skeleton engine did not have (palindrome, element-wise map, absolute value)."""
    _lib(tmp_path, monkeypatch)
    cases = [
        Task("pal", "def pal(s):", "Return True if s is a palindrome.",
             "assert pal('racecar') is True\nassert pal('abc') is False\nassert pal('') is True"),
        Task("sq", "def sq(xs):", "Return the squares of the elements of xs.",
             "assert sq([1, 2, 3]) == [1, 4, 9]\nassert sq([-2]) == [4]\nassert sq([]) == []"),
        Task("av", "def av(n):", "Return the absolute value of n.",
             "assert av(-5) == 5\nassert av(3) == 3\nassert av(0) == 0"),
    ]
    for t in cases:
        a = author(t)
        assert a.verified and a.source == "skeleton" and a.body is not None, t.name


def test_block_family_synthesizes_a_counter(tmp_path, monkeypatch):
    """A generic fold-into-a-count-dict BLOCK structure authors a frequency map — a multi-statement
    body no expression family can produce."""
    _lib(tmp_path, monkeypatch)
    t = Task("freq", "def freq(s):", "Return a dict of character counts for s.",
             "assert freq('aab') == {'a': 2, 'b': 1}\nassert freq('') == {}\nassert freq('zzz') == {'z': 3}")
    a = author(t)
    assert a.verified and a.source == "skeleton"
    assert "for" in a.body and "counts" in a.body            # it is the block structure, not an expr


# ------------------------------------------------------------------- (2) composition

def _sorted_squares_task(name="ss", param="xs"):
    return Task(name, f"def {name}({param}):", f"Return the sorted squares of {param}.",
                f"assert {name}([3, -1, 2]) == [1, 4, 9]\n"
                f"assert {name}([-3, -1, -2]) == [1, 4, 9]\n"
                f"assert {name}([]) == []")


def test_composition_solves_what_no_single_family_reaches(tmp_path, monkeypatch):
    """sorted-of-the-squares: the list-comprehension family alone yields UNSORTED squares and the
    aggregate family alone yields the sorted ORIGINAL — neither passes. The 2-stage pipeline
    (map -> aggregate) does, and is labeled a composition."""
    _lib(tmp_path, monkeypatch)
    t = _sorted_squares_task()
    # neither family, on its own, produces a passing body:
    assert not any(_run_fast(t, f"return {e}") for e in _fam_list_comp(["xs"], t.docstring))
    assert not any(_run_fast(t, f"return {e}") for e in _fam_aggregate(["xs"], t.docstring))
    a = author(t)
    assert a.verified and a.source == "composition"
    assert a.body is not None and "_t" in a.body             # a two-stage pipeline body


# ------------------------------------------------------------------- (3) library recall compounds

def test_solved_shape_recalled_for_isomorphic_task(tmp_path, monkeypatch):
    """Solving sorted-squares once stores it param-normalized; an ISOMORPHIC task with a different
    parameter name then solves straight from the LIBRARY (independence compounds), not by re-searching
    the whole composition space."""
    _lib(tmp_path, monkeypatch)
    first = author(_sorted_squares_task("ss1", "xs"))
    assert first.source == "composition" and first.verified

    second = author(_sorted_squares_task("ss2", "values"))   # different name, same shape
    assert second.source == "library" and second.verified
    assert second.tried == 1                                 # recalled on the first try, not re-searched


# ------------------------------------------------------------------- (4) benchmark integrity

def test_benchmark_integrity_catches_a_wrong_reference():
    """The benchmark's own self-test: every shipped task is well-posed (its reference passes
    visible+hidden), and a task authored with a WRONG reference is caught — so the yardstick cannot
    silently certify a broken task."""
    from packages.code_reason.benchmarks.mastery_v1 import check_task_integrity, all_tasks
    assert all(check_task_integrity(t) for t in all_tasks())

    wrong = Task("addx", "def addx(a, b):", "Return the sum of a and b.",
                 "assert addx(2, 3) == 5", reference="return a - b",
                 hidden="assert addx(10, 1) == 11")
    assert check_task_integrity(wrong) is False              # reference fails its own tests -> caught

    right = Task("addy", "def addy(a, b):", "Return the sum of a and b.",
                 "assert addy(2, 3) == 5", reference="return a + b",
                 hidden="assert addy(10, 1) == 11")
    assert check_task_integrity(right) is True


def test_benchmark_run_reports_honest_invariants():
    """A full benchmark run: zero over-fit ships (fail==0, the no-fabrication floor), trivial fully
    solved, and every solved task is mined into the library. With algorithm schemas the hard rung is
    no longer fully abstained — but it is still never fabricated (fail==0)."""
    from packages.code_reason.benchmarks.mastery_v1 import run_benchmark
    res = run_benchmark()                                    # isolated temp library; no side effects
    assert res["totals"]["fail"] == 0                        # the one number that must never move
    assert res["rungs"]["trivial"]["pass"] == 10
    assert res["rungs"]["easy"]["pass"] == 10
    assert res["rungs"]["medium"]["pass"] == 10
    assert res["rungs"]["hard"]["pass"] == 10                # general law families reach the whole rung
    assert res["totals"]["pass"] == 40 and res["totals"]["abstain"] == 0
    assert 0 < res["library_growth"] <= res["totals"]["pass"]


# =================================================================== algorithm schemas (System-2 substrate)

def _bench(name):
    from packages.code_reason.benchmarks.mastery_v1 import all_tasks
    return next(t for t in all_tasks() if t.name == name)


def _passes_hidden(task, body):
    from dataclasses import replace
    from packages.code_reason.authorship_harness import _run_candidate
    full = task.test + ("\n" + task.hidden if task.hidden else "")
    return _run_candidate(replace(task, test=full), body).passed


def test_schema_dp2d_solves_edit_distance(tmp_path, monkeypatch):
    """The DP-2D two-sequence schema reaches Levenshtein edit distance — a hard-rung task the
    skeleton+composition engine abstained on — and the shipped body is correct on held-out inputs."""
    _lib(tmp_path, monkeypatch)
    ed = _bench("edit_distance")
    a = author(ed)
    assert a.verified and a.source == "schema:dp2d"
    assert _passes_hidden(ed, a.body)                        # correct beyond the visible examples


def test_schema_topo_solves_topological_sort(tmp_path, monkeypatch):
    """The TOPO (Kahn) schema reaches a deterministic topological order."""
    _lib(tmp_path, monkeypatch)
    ts = _bench("topo_sort")
    a = author(ts)
    assert a.verified and a.source == "schema:topo"
    assert _passes_hidden(ts, a.body)


def test_schema_backtrack_solves_n_queens_count(tmp_path, monkeypatch):
    """The BACKTRACK-count schema reaches the n-queens solution count via a constraint-expr hole."""
    _lib(tmp_path, monkeypatch)
    nq = _bench("n_queens_count")
    a = author(nq)
    assert a.verified and a.source == "schema:backtrack"
    assert _passes_hidden(nq, a.body)


def test_schema_graph_solves_reachability(tmp_path, monkeypatch):
    """The GRAPH-traversal schema (frontier drain) reaches connected-reachability — proving the
    schema organ is real substrate, not a one-off for the three required tasks."""
    _lib(tmp_path, monkeypatch)
    t = Task("reach", "def reach(n, edges):",
             "Return how many vertices are reachable from vertex 0 (undirected).",
             "assert reach(3, [(0, 1), (1, 2)]) == 3\nassert reach(3, [(1, 2)]) == 1\n"
             "assert reach(4, [(0, 1)]) == 2")
    a = author(t)
    assert a.verified and a.source == "schema:graph"


def test_hidden_tests_reject_a_wrong_recurrence():
    """A DP-2D body with the WRONG (LCS-style) recurrence can pass a weak visible check, but the
    held-out hidden test rejects it — so a wrong recurrence can never be silently certified as
    correct. This is the property that keeps schema instantiations honest."""
    from dataclasses import replace
    from packages.code_reason.authorship_harness import _run_candidate
    ed = _bench("edit_distance")
    wrong = ("_m, _n = len(a), len(b)\n"
             "_dp = [[_i + _j for _j in range(_n + 1)] for _i in range(_m + 1)]\n"
             "for _i in range(1, _m + 1):\n"
             "    for _j in range(1, _n + 1):\n"
             "        _dp[_i][_j] = _dp[_i - 1][_j - 1] if a[_i - 1] == b[_j - 1] "
             "else max(_dp[_i - 1][_j], _dp[_i][_j - 1])\n"
             "return _dp[_m][_n]")
    assert _run_candidate(replace(ed, test="assert edit_distance('abc', 'abc') == 0"), wrong).passed
    assert not _run_candidate(replace(ed, test=ed.hidden), wrong).passed


def test_out_of_scope_task_still_abstains(tmp_path, monkeypatch):
    """No skeleton, composition, or principled schema reaches these -> honest abstain, never a
    fabricated body. (LRU/roman moved OUT of this test: they are now conquered by the keyed-store and
    induced value-map laws. The floor is proven on tasks still beyond every family.)"""
    _lib(tmp_path, monkeypatch)
    caesar = Task("caesar_cipher", "def caesar_cipher(s, k):",
                  "Return s with every lowercase letter advanced by k positions in the alphabet, wrapping around.",
                  "assert caesar_cipher('abc', 1) == 'bcd'\nassert caesar_cipher('xyz', 3) == 'abc'")
    assert author(caesar).body is None
    collatz = Task("collatz_steps", "def collatz_steps(n):",
                   "Return the number of Collatz steps to reach 1 from n.",
                   "assert collatz_steps(1) == 0\nassert collatz_steps(6) == 8")
    assert author(collatz).body is None
    made_up = Task("mystery", "def mystery(a, b):", "Return the mysterious frobnication of a and b.",
                   "assert mystery('x', 'y') == 'xy!'\nassert mystery('a', 'b') == 'ab!'")
    assert author(made_up).body is None


# =================================================================== GENERALITY GATE (anti-overfit)
# Each new law family must solve its benchmark task AND at least one DISTINCT novel probe via the SAME
# schema. A family with only one reachable instantiation is a memorized answer and is rejected here.

def _solved_by(task, schema_id):
    a = author(task)
    return a.verified and a.source == schema_id


def test_scanrun_family_generalizes(tmp_path, monkeypatch):
    _lib(tmp_path, monkeypatch)
    assert _solved_by(_bench("run_length_encode"), "schema:scanrun")
    run_lengths = Task("run_lengths", "def run_lengths(s):",
                       "Return the list of consecutive run lengths in s.",
                       "assert run_lengths('aaabb') == [3, 2]\nassert run_lengths('abc') == [1, 1, 1]\n"
                       "assert run_lengths('') == []")
    assert _solved_by(run_lengths, "schema:scanrun")         # different emit/answer holes


def test_groupby_family_generalizes(tmp_path, monkeypatch):
    _lib(tmp_path, monkeypatch)
    assert _solved_by(_bench("anagram_groups"), "schema:groupby")
    by_length = Task("group_by_length", "def group_by_length(words):",
                     "Group the words by their length; return the groups sorted.",
                     "assert group_by_length(['a', 'bb', 'cc', 'd']) == [['a', 'd'], ['bb', 'cc']]\n"
                     "assert group_by_length([]) == []\nassert group_by_length(['x']) == [['x']]")
    assert _solved_by(by_length, "schema:groupby")           # different key hole (len vs sorted-letters)


def test_stackscan_family_generalizes(tmp_path, monkeypatch):
    _lib(tmp_path, monkeypatch)
    assert _solved_by(_bench("balanced_brackets"), "schema:stackscan")
    angles = Task("balanced_angles", "def balanced_angles(s):",
                  "Return True if the angle brackets in s are balanced.",
                  "assert balanced_angles('<>') is True\nassert balanced_angles('<<>>') is True\n"
                  "assert balanced_angles('><') is False\nassert balanced_angles('<') is False")
    assert _solved_by(angles, "schema:stackscan")            # different bracket alphabet


def test_valuemap_family_generalizes_to_a_novel_numeral_system(tmp_path, monkeypatch):
    """The induced value-map law is reused for a SYNTHETIC numeral system it has never seen — the
    scan structure is owned, the per-symbol values are re-learned from that task's own examples."""
    _lib(tmp_path, monkeypatch)
    assert _solved_by(_bench("roman_to_int"), "schema:valuemap")
    from dataclasses import replace
    from packages.code_reason.authorship_harness import _run_candidate
    zorb = Task("zorb_to_int", "def zorb_to_int(s):",
                "Return the integer value of a numeral string in the Zorb system.",
                "assert zorb_to_int('A') == 1\nassert zorb_to_int('B') == 5\nassert zorb_to_int('Z') == 10\n"
                "assert zorb_to_int('AAA') == 3\nassert zorb_to_int('AB') == 4")
    a = author(zorb)
    assert a.verified and a.source == "schema:valuemap"
    # the induced-table body generalizes to novel Zorb composites never in the examples:
    assert _run_candidate(replace(zorb, test="assert zorb_to_int('ZAB') == 14\nassert zorb_to_int('AZ') == 9"),
                          a.body).passed


def test_dpstring_family_generalizes(tmp_path, monkeypatch):
    _lib(tmp_path, monkeypatch)
    assert _solved_by(_bench("word_break"), "schema:dpstring")
    count = Task("count_segmentations", "def count_segmentations(s, words):",
                 "Return the number of ways to segment s into dictionary words.",
                 "assert count_segmentations('aaa', ['a', 'aa']) == 3\n"
                 "assert count_segmentations('aa', ['a']) == 1\n"       # 2 vowels but 1 way (discriminates)
                 "assert count_segmentations('bb', ['b']) == 1\n"       # 0 vowels but 1 way
                 "assert count_segmentations('x', ['y']) == 0")
    assert _solved_by(count, "schema:dpstring")              # count-mode vs any-mode hole


def test_reachset_family_generalizes(tmp_path, monkeypatch):
    _lib(tmp_path, monkeypatch)
    assert _solved_by(_bench("subset_sum"), "schema:reachset")
    max_reach = Task("max_reachable", "def max_reachable(nums, target):",
                     "Return the largest subset sum of nums not exceeding target.",
                     "assert max_reachable([2, 3, 5], 9) == 8\nassert max_reachable([1, 2], 5) == 3\n"
                     "assert max_reachable([], 0) == 0")
    assert _solved_by(max_reach, "schema:reachset")          # different answer read


def test_traversal_family_generalizes(tmp_path, monkeypatch):
    _lib(tmp_path, monkeypatch)
    assert _solved_by(_bench("spiral_order"), "schema:traversal")
    col_major = Task("column_major", "def column_major(matrix):",
                     "Return the elements of a matrix in column-major order.",
                     "assert column_major([[1, 2, 3], [4, 5, 6]]) == [1, 4, 2, 5, 3, 6]\n"
                     "assert column_major([[1]]) == [1]\nassert column_major([]) == []")
    assert _solved_by(col_major, "schema:traversal")         # different order-pattern hole


def test_keyedstore_family_generalizes(tmp_path, monkeypatch):
    _lib(tmp_path, monkeypatch)
    assert _solved_by(_bench("lru_cache_sim"), "schema:keyedstore")
    fifo = Task("fifo_cache_sim", "def fifo_cache_sim(capacity, ops):",
                "Simulate a FIFO cache over ops; return the list of get results (-1 if absent).",
                "assert fifo_cache_sim(2, [('put', 1, 1), ('put', 2, 2), ('get', 1), ('put', 3, 3), "
                "('get', 1), ('get', 2)]) == [1, -1, 2]\n"
                "assert fifo_cache_sim(1, [('put', 1, 5), ('get', 1)]) == [5]")
    assert _solved_by(fifo, "schema:keyedstore")             # FIFO eviction policy vs LRU


# =================================================================== wrong-hole rejection (honesty)

def test_valuemap_abstains_when_table_underdetermined(tmp_path, monkeypatch):
    """If the visible examples do not pin a consistent symbol table (a symbol never shown as a pure
    repeat, or contradictory values), induction fails and the engine ABSTAINS — content is learned
    from data or not at all, never fabricated."""
    _lib(tmp_path, monkeypatch)
    # 'M' appears only inside a composite, never as a pure-repeat example -> cannot be pinned.
    underdetermined = Task("rn", "def rn(s):", "Return the value of a Roman numeral string.",
                           "assert rn('I') == 1\nassert rn('V') == 5\nassert rn('IM') == 999")
    assert author(underdetermined).body is None
    # contradictory examples ('II' claims 3, but 'I' == 1) -> inconsistent -> abstain
    contradictory = Task("rn2", "def rn2(s):", "Return the value of a Roman numeral string.",
                         "assert rn2('I') == 1\nassert rn2('II') == 3")
    assert author(contradictory).body is None


def test_wrong_eviction_policy_is_rejected_by_hidden(tmp_path, monkeypatch):
    """A FIFO task authored with the WRONG (LRU) policy body passes a weak visible check but the
    held-out FIFO behavior rejects it — the policy hole cannot be silently mis-filled."""
    from dataclasses import replace
    from packages.code_reason.authorship_harness import _run_candidate
    fifo = Task("fc", "def fc(capacity, ops):", "Simulate a FIFO cache; return get results.",
                "assert fc(2, [('put', 1, 1), ('get', 1)]) == [1]",
                hidden="assert fc(2, [('put', 1, 1), ('put', 2, 2), ('get', 1), ('put', 3, 3), "
                       "('get', 1), ('get', 2)]) == [1, -1, 2]")
    lru_body = ("_cache = {}\n_order = []\n_out = []\n"
                "for _op in ops:\n    if _op[0] == 'put':\n        _, _k, _val = _op\n"
                "        if _k in _cache:\n            _order.remove(_k)\n"
                "        elif len(_cache) >= capacity:\n            del _cache[_order.pop(0)]\n"
                "        _cache[_k] = _val\n        _order.append(_k)\n"
                "    else:\n        _, _k = _op\n"
                "        if _k in _cache:\n            _order.remove(_k)\n            _order.append(_k)\n"
                "            _out.append(_cache[_k])\n        else:\n            _out.append(-1)\nreturn _out")
    assert _run_candidate(replace(fifo, test="assert fc(2, [('put', 1, 1), ('get', 1)]) == [1]"), lru_body).passed
    assert not _run_candidate(replace(fifo, test=fifo.hidden), lru_body).passed
