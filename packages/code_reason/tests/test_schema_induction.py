# -*- coding: utf-8 -*-
"""Tests for L3 schema induction — the layer that INVENTS algorithm laws from verified solutions.

The properties pinned here are the doctrine made testable: anti-unification finds a hole exactly where
solutions differ (invention); a schema is promoted ONLY when it re-solves sources AND generalizes to a
held-out instance through the EXISTING isolated verifier (survival = verification); a schema that
compresses but cannot generalize is REJECTED (no rubber-stamp for MDL); the simplest hand family is
reinvented after it is ablated (the central honesty experiment); and the no-fabrication floor
(fail==0) holds on a fresh held-out benchmark. With no induced store the whole layer is inert, so the
base engine is unchanged."""
from __future__ import annotations

from dataclasses import replace

import pytest

import packages.code_reason.code_author as ca
import packages.code_reason.schema_induction as si
from packages.code_reason.authorship_harness import Task, _run_candidate
from packages.code_reason.benchmarks.mastery_v1 import all_tasks

_BY = {t.name: t for t in all_tasks()}


def _isolate(monkeypatch, tmp_path):
    """Point the library and induced store at temp paths so nothing touches committed state and the
    induced layer starts empty (default-inert)."""
    monkeypatch.setattr(ca, "LIBRARY", tmp_path / "lib.jsonl")
    monkeypatch.setattr(si, "INDUCED_STORE", tmp_path / "induced.jsonl")


def _tmpl(name: str) -> str:
    """The verified body of a mastery task, normalized to ``_a{i}`` form (an induction-material item)."""
    t = _BY[name]
    a = ca.author(t)
    assert a.verified and a.body, name
    return ca._normalize(a.body, ca._params(t.signature))


# ============================================================================ NORMALIZE

def test_normalize_alpha_renames_locals_to_positional_slots():
    body = "counts = {}\nfor k in xs:\n    counts[k] = counts.get(k, 0) + 1\nreturn counts"
    src = si._normalized_src(body)
    assert "counts" not in src and "_v0" in src        # bound locals -> positional slots
    assert "xs" in src                                 # a load-only (param-like) name is untouched


# ============================================================================ ANTI-UNIFY (invention)

def test_anti_unification_of_three_solutions_yields_a_hole_where_they_differ():
    """Three aggregate solutions differ only in the aggregation function -> the skeleton keeps the
    shared ``return _(_a0)`` shape and puts a single hole exactly at the function position."""
    sols = ["return sum(_a0)", "return max(_a0)", "return min(_a0)"]
    schema = si.anti_unify(sols, arity=1)
    assert schema is not None
    assert schema.n_holes == 1
    assert schema.skeleton_src == "return __HOLE0__(_a0)"
    assert set(schema.holes[0]) == {"sum", "max", "min"}       # the hole is precisely the divergence


def test_anti_unification_declines_when_two_algorithms_only_share_loop_scaffolding(monkeypatch, tmp_path):
    """coin_change (DP-1D) and subset_sum are DIFFERENT algorithms that share only (Assign, For, Return)
    scaffolding: their init, iterable, loop body AND answer all diverge. v2 CAN form statement holes, so
    a naive merge yields a hollow 'generic loop' (a statement hole plus three expression holes). The
    statement-hole COHERENCE guard rejects it — a genuine statement-level law has the statement hole as
    its one dominant locus, not one of four independent divergences — so the engine still declines
    rather than emit a law that merely memorizes two algorithms behind a loop skeleton."""
    _isolate(monkeypatch, tmp_path)
    schema = si.anti_unify([_tmpl("coin_change"), _tmpl("subset_sum")], arity=2)
    assert schema is None


# ============================================================================ VERIFY GATE (survival)

def test_promoted_schema_passes_verifier_on_a_held_out_instance(monkeypatch, tmp_path):
    """The count-dict schema induced from char_frequency + most_frequent is promoted only because it
    also solves a HELD-OUT task (distinct_count, needing the new filler len(counts)) through the
    isolated verifier — generalization, not just source reconstruction."""
    _isolate(monkeypatch, tmp_path)
    schema = si.anti_unify([_tmpl("char_frequency"), _tmpl("most_frequent")], family="count_dict",
                           intents=[_BY["char_frequency"].docstring, _BY["most_frequent"].docstring], arity=1)
    holdout = si._distinct_count_probe()
    rep = si.promote(schema, [_BY["char_frequency"], _BY["most_frequent"]], [holdout])
    assert rep["accepted"] is True
    assert rep["resolved"] >= 2 and rep["generalized"] >= 1
    assert si._solve_via_full(schema, holdout) is True         # verified on the held-out instance


def test_candidate_that_compresses_but_fails_verification_is_rejected(monkeypatch, tmp_path):
    """No rubber-stamp for MDL: the count-dict schema DOES compress (positive gain) and re-solves its
    sources, but against a mismatched held-out (an edit-distance task) it cannot generalize — so it is
    NOT promoted. Compression is necessary, verification is decisive."""
    _isolate(monkeypatch, tmp_path)
    schema = si.anti_unify([_tmpl("char_frequency"), _tmpl("most_frequent")], family="count_dict",
                           intents=[_BY["char_frequency"].docstring, _BY["most_frequent"].docstring], arity=1)
    assert schema.mdl_gain() > 0                                # it genuinely compresses the corpus
    rep = si.promote(schema, [_BY["char_frequency"], _BY["most_frequent"]], [_BY["edit_distance"]])
    assert rep["generalized"] == 0
    assert rep["accepted"] is False                            # compressed, but rejected by the floor


# ============================================================================ I3 — ABLATE AND REINVENT

def test_ablate_and_reinvent_the_simplest_family_passes(monkeypatch, tmp_path):
    """CENTRAL HONESTY EXPERIMENT (simplest family). Remove the hand count-dict law; from the verified
    solutions it once produced, induction reinvents a structurally-equivalent law that re-solves the
    target through the isolated verifier and generalizes to a novel probe."""
    _isolate(monkeypatch, tmp_path)
    r = si.ablate_and_reinvent("count_dict")
    assert r["reinvented"] is True
    assert r["hand_abstains_when_ablated"] is True             # the hand law really was necessary
    assert r["generalized_to_novel_probe"] is True


def test_i3_per_family_reinvention_headline(monkeypatch, tmp_path):
    """The headline measurement, asserted per family. Simple families (count-dict fold, aggregate) and
    the DP-2D stretch reinvent; DP-1D does NOT — its only corpus sibling (subset_sum) diverges at
    statement structure, so there is no >=2-solution family to anti-unify. That honest boundary is
    the deliverable, reported as reinvented==False with the reason, not papered over."""
    _isolate(monkeypatch, tmp_path)
    res = {fam: si.ablate_and_reinvent(fam) for fam in ("count_dict", "aggregate", "dp2d", "dp1d")}
    assert res["count_dict"]["reinvented"] is True
    assert res["aggregate"]["reinvented"] is True
    assert res["dp2d"]["reinvented"] is True                   # the deep DP-2D scaffold, reinvented
    assert res["dp1d"]["reinvented"] is False                  # honest: corpus has no clean sibling
    assert "insufficient" in res["dp1d"]["reason"]


# ============================================================================ I2 — induced solves new

def test_induced_schema_solves_a_task_hand_schemas_miss(monkeypatch, tmp_path):
    """A DP-2D-shaped task whose wording misses the hand dp2d keyword cue: the hand engine abstains,
    but the induced schema (structurally applicable by arity) solves it — verified. Induction's
    contribution is broader applicability, still under the no-fabrication floor."""
    _isolate(monkeypatch, tmp_path)
    si.induce_and_promote(tasks=[_BY["edit_distance"], _BY["longest_common_subsequence"]])
    probe = si._min_edits_probe()

    monkeypatch.setattr(si, "INDUCED_STORE", tmp_path / "no_store.jsonl")     # induction OFF
    assert ca.author(probe).body is None                                     # hand alone abstains
    monkeypatch.setattr(si, "INDUCED_STORE", tmp_path / "induced.jsonl")     # induction ON
    a = ca.author(probe)
    assert a.verified and a.source.startswith("induced:")
    assert _run_candidate(replace(probe, test=probe.test + "\n" + probe.hidden), a.body).passed


# ============================================================================ I4 — mastery_v2 + fail==0

def test_mastery_v2_reaches_via_induction_with_fail_zero(monkeypatch, tmp_path):
    """12 novel held-out tasks, each beyond the hand schemas' cues. With the induced store the engine
    reaches the DP-2D-family variants and honestly abstains on the rest; crucially it ships NO over-fit
    body (fail==0). Every reached task passes its held-out hidden inputs, not just the visible gate."""
    _isolate(monkeypatch, tmp_path)
    si.induce_and_promote(tasks=[_BY["edit_distance"], _BY["longest_common_subsequence"],
                                 _BY["char_frequency"], _BY["most_frequent"],
                                 _BY["total"], _BY["maximum"], _BY["minimum"]])
    monkeypatch.setattr(ca, "LIBRARY", tmp_path / "score_lib.jsonl")         # fresh: every solve is synthesis
    reached = abstained = fail = 0
    for t in si.mastery_v2_tasks():
        a = ca.author(t)
        if not a.verified or not a.body:
            abstained += 1
            continue
        full = t.test + ("\n" + t.hidden if t.hidden else "")
        if _run_candidate(replace(t, test=full), a.body).passed:
            reached += 1
        else:
            fail += 1
    assert fail == 0                                           # the one number that must never move
    assert reached >= 4                                        # induction's measured added reach
    assert abstained >= 6                                      # the rest are honestly beyond reach
    assert reached + abstained + fail == 12


def test_mastery_v2_tasks_are_well_posed():
    """Every v2 task is solvable in principle: its reference passes visible + hidden. A benchmark whose
    tasks were ill-posed could hide a fabrication as a false 'reached' — this guards against that."""
    for t in si.mastery_v2_tasks():
        assert t.reference, t.name
        assert _run_candidate(replace(t, test=t.test + "\n" + t.hidden), t.reference).passed, t.name


# ============================================================================ default-inert + wiring

def test_empty_induced_store_leaves_the_base_engine_unchanged(monkeypatch, tmp_path):
    """With no induced store the induced layer yields nothing and code_author is exactly L1/L2: a hard
    task is still solved by its HAND schema, not an induced one."""
    _isolate(monkeypatch, tmp_path)
    assert list(si.induced_candidates(["a", "b"], "anything")) == []
    a = ca.author(_BY["edit_distance"])
    assert a.verified and a.source == "schema:dp2d"            # unchanged by the (empty) induced layer


def test_induce_and_promote_persists_only_verified_survivors(monkeypatch, tmp_path):
    """The sleep pass writes a store; every entry is a schema that PASSED the verification gate (has
    positive MDL and a recorded skeleton), and induced_candidates can reconstruct and fire it."""
    _isolate(monkeypatch, tmp_path)
    rep = si.induce_and_promote(tasks=[_BY["edit_distance"], _BY["longest_common_subsequence"],
                                       _BY["char_frequency"], _BY["most_frequent"]])
    assert rep["promoted"] >= 1
    specs = si.load_induced()
    assert len(specs) == rep["promoted"]
    assert all(s["mdl_gain"] > 0 and s["skeleton"] for s in specs)


# ==================================================================== v2 FRONTIER 1 — STATEMENT-LEVEL

def test_statement_level_anti_unification_finds_a_statement_hole(monkeypatch, tmp_path):
    """FRONTIER 1: two solutions differing by exactly ONE loop-body statement (a bare product-fold vs
    the same fold under a positivity guard) anti-unify to a single scaffold whose one hole is a whole
    STATEMENT (``__SHOLE`` token), and that schema re-solves both sources PLUS a novel third (product
    of evens) through the isolated verifier — invention at statement granularity, still gated."""
    _isolate(monkeypatch, tmp_path)
    name, ta, tb, tc = si._statement_level_cases()[0]                 # product-fold
    aa, ab = ca.author(ta), ca.author(tb)
    assert aa.verified and ab.verified and "for " in aa.body and "for " in ab.body   # both authored as loops
    t1 = ca._normalize(aa.body, ca._params(ta.signature))
    t2 = ca._normalize(ab.body, ca._params(tb.signature))
    schema = si.anti_unify([t1, t2], family=name, intents=[ta.docstring, tb.docstring], arity=1)
    assert schema is not None and schema.n_holes == 1
    assert si._SHOLE_RE.search(schema.skeleton_src)                  # the hole is a whole statement
    assert si._solve_via(schema, ta, ca._params(ta.signature))      # source A re-solves
    assert si._solve_via(schema, tb, ca._params(tb.signature))      # source B re-solves
    assert si._solve_via(schema, tc, ca._params(tc.signature))      # novel third via the statement grammar


def test_statement_level_probe_all_cases_pass(monkeypatch, tmp_path):
    """I5 headline: every statement-level case (product-fold AND guarded-collect) forms one statement-
    hole schema that solves both sources and a novel third."""
    _isolate(monkeypatch, tmp_path)
    res = si.statement_level_probe()
    assert len(res) >= 2
    assert all(c["passed"] and c["statement_hole"] and c["n_holes"] == 1 for c in res)


def test_statement_level_cases_are_well_posed():
    """Each I5 task is solvable in principle (its reference passes visible + hidden), so a 'solved'
    verdict cannot be hiding a fabrication behind an ill-posed task."""
    for _name, ta, tb, tc in si._statement_level_cases():
        for t in (ta, tb, tc):
            assert t.reference, t.name
            assert _run_candidate(replace(t, test=t.test + "\n" + t.hidden), t.reference).passed, t.name


def test_unsound_statement_generalization_is_rejected_by_verifier(monkeypatch, tmp_path):
    """Soundness floor for statement holes: the product scaffold owns ``seed = 1``, so no statement-
    grammar fill can bend it into a plain SUM (which needs seed 0 — e.g. sum([]) == 0, but this scaffold
    returns 1). Every candidate fill is run through the isolated verifier, all fail, and the engine
    returns None — an honest abstain, never a fabricated body from an unsound statement generalization."""
    _isolate(monkeypatch, tmp_path)
    name, ta, tb, _tc = si._statement_level_cases()[0]
    t1 = ca._normalize(ca.author(ta).body, ca._params(ta.signature))
    t2 = ca._normalize(ca.author(tb).body, ca._params(tb.signature))
    schema = si.anti_unify([t1, t2], family=name, intents=[ta.docstring, tb.docstring], arity=1)
    assert si._SHOLE_RE.search(schema.skeleton_src)
    sum_task = Task("sum_all", "def sum_all(xs):", "Return the sum of all numbers in xs.",
                    "assert sum_all([1, 2, 3]) == 6\nassert sum_all([]) == 0\nassert sum_all([5, 5]) == 10",
                    hidden="assert sum_all([-1, 1]) == 0")
    assert si._solve_via(schema, sum_task, ca._params(sum_task.signature)) is None    # no sound fill -> abstain


# ==================================================================== v2 FRONTIER 2 — WAKE-SLEEP GROWTH

def test_dp1d_reinvented_after_wakesleep_growth(monkeypatch, tmp_path):
    """FRONTIER 2 headline. v1 could not reinvent DP-1D — its corpus held a single sibling (coin_change).
    Wake-sleep GROWS a second genuine DP-1D exemplar (ordered change-counting); the engine then reinvents
    the linear-DP law (the whole table-fill scaffold owned, four expression holes) and re-solves
    coin_change through the isolated verifier after the hand dp1d schema is ablated."""
    _isolate(monkeypatch, tmp_path)
    r = si.dp1d_reinvention_after_growth()
    assert r["reinvented"] is True
    assert r["hand_abstains_when_ablated"] is True                   # the hand law really was necessary
    assert r["n_sources"] == 2 and r["n_holes"] == 4


def test_dp1d_static_ablation_still_honestly_insufficient(monkeypatch, tmp_path):
    """The unblock is attributable to GROWTH, not a weakened gate: WITHOUT wake-sleep the base ablation
    still hits the v1 boundary (a single verified sibling), reported honestly as insufficient."""
    _isolate(monkeypatch, tmp_path)
    r = si.ablate_and_reinvent("dp1d")
    assert r["reinvented"] is False and "insufficient" in r["reason"]


def test_wakesleep_grows_the_dp1d_law_that_static_induction_misses(monkeypatch, tmp_path):
    """Static induction over the fixed library promotes no DP-1D law (one exemplar); wake-sleep, having
    grown the second exemplar, promotes it. The difference is exactly the corpus growth."""
    _isolate(monkeypatch, tmp_path)
    static = si.induce_and_promote(tasks=[_BY["coin_change"]], persist=False, rounds=1, wake=False)
    grown = si.induce_and_promote(tasks=[_BY["coin_change"]], persist=False, rounds=1, wake=True)
    assert not any("coin_change" in f for f in static["survivors"])          # 1 exemplar -> no law
    assert any("coin_change+count_change_ways" in f for f in grown["survivors"])   # grown 2nd -> reinvented


def test_grown_corpus_is_default_inert_and_flag_gated(monkeypatch, tmp_path):
    """grow_corpus persists the grown laws to a data/code_reason/ file that is DEFAULT-INERT: with
    LOAD_GROWN False the production induced layer never consults it (growing the corpus cannot silently
    change the shipped engine); flipping LOAD_GROWN True makes the grown DP-1D law fire."""
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(si, "GROWN_CORPUS", tmp_path / "grown.jsonl")
    monkeypatch.setattr(si, "LOAD_GROWN", False)
    g = si.grow_corpus(rounds=1, tasks=[_BY["coin_change"]])
    assert (tmp_path / "grown.jsonl").exists()
    assert any("coin_change+count_change_ways" in f for f in g["grown_families"])
    monkeypatch.setattr(si, "INDUCED_STORE", tmp_path / "no_store.jsonl")     # empty induced store
    assert list(si.induced_candidates(["coins", "amount"], "fewest coins to make change")) == []
    monkeypatch.setattr(si, "LOAD_GROWN", True)                              # opt-in
    fired = [fam for fam, _ in si.induced_candidates(["coins", "amount"], "fewest coins to make change")]
    assert any("coin_change" in f for f in fired)


def test_mastery_v2_fail_zero_under_wakesleep_grown_store(monkeypatch, tmp_path):
    """The no-fabrication floor holds under the GROWN engine: after wake-sleep growth, scoring the 12
    held-out tasks ships zero over-fit bodies (fail == 0). The v2 frontiers add reach (measured by I3b
    and I5) without ever moving the one number that must not move."""
    _isolate(monkeypatch, tmp_path)
    si.induce_and_promote(tasks=[_BY["edit_distance"], _BY["longest_common_subsequence"],
                                 _BY["coin_change"]], wake=True, rounds=1)
    monkeypatch.setattr(ca, "LIBRARY", tmp_path / "score.jsonl")             # fresh: every solve is synthesis
    reached = fail = 0
    for t in si.mastery_v2_tasks():
        a = ca.author(t)
        if not (a.verified and a.body):
            continue
        full = t.test + ("\n" + t.hidden if t.hidden else "")
        if _run_candidate(replace(t, test=full), a.body).passed:
            reached += 1
        else:
            fail += 1
    assert fail == 0
    assert reached >= 4
