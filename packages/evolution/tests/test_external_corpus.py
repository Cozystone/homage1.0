# -*- coding: utf-8 -*-
"""X4.1 — external problem corpus + external target stream (owner 2026-07-23).
Fast (small budgets): corpus provenance/graduation, I/O determinism, the flag-gated external round, and
the default-OFF byte-identical guarantee (self-composed baseline unchanged)."""
from __future__ import annotations

import os
import random

from packages.evolution import external_corpus as ec
from packages.evolution import open_domain as od


def test_corpus_is_external_and_graduated():
    p = ec.provenance()
    assert p["external"] is True and p["self_composed"] is False
    assert p["verifier"] == "io_examples"
    assert p["size"] >= 40                                   # curated 40-80 real functions
    # graduated: every tier 0..3 populated, all three families present
    assert all(p["tiers"][t] > 0 for t in (0, 1, 2, 3))
    assert all(p["families"][f] > 0 for f in ("num", "text", "seq"))
    # compounding families exist (a motif shared by >= 2 tasks)
    assert any(len(v) >= 2 for v in ec.motif_families().values())


def test_sample_io_is_deterministic_and_matches_reference():
    task = next(t for t in ec.TASKS if t.name == "seq_count_even")
    a = ec.sample_io(task, 8, random.Random(3))
    b = ec.sample_io(task, 8, random.Random(3))
    assert a == b                                           # deterministic given the rng seed
    for env, out in a:
        assert out == len([x for x in env["xs"] if x % 2 == 0])   # I/O really is the real function


def test_reference_outputs_are_within_interpreter_bounds():
    rng = random.Random(0)
    for task in ec.TASKS:
        for env, out in ec.sample_io(task, 6, rng):
            assert isinstance(out, (int, str, tuple))
            if isinstance(out, (str, tuple)):
                assert len(out) <= od.MAX_LEN
            if isinstance(out, int):
                assert -od._INT_CLAMP <= out <= od._INT_CLAMP


def test_flag_off_is_byte_identical_baseline(monkeypatch):
    # With the flag OFF, autonomous_round must NOT dispatch to the external stream: the self-composed
    # loop is unchanged (no external state keys created).
    monkeypatch.delenv("ATANOR_EXTERNAL_PROBLEMS", raising=False)
    state = od.new_state()
    rng = random.Random(2)
    rec = od.autonomous_round(state, rng, problems=6, pop=40, base_budget=50)
    assert "external" not in rec                            # self-composed record shape
    assert "ext_solved" not in state


def test_external_round_solves_and_tracks_provenance(monkeypatch):
    # With the flag ON, the curriculum draws external targets and solves the easy ones, recording
    # per-task solve + provenance so the compounding metric can be computed.
    monkeypatch.setenv("ATANOR_EXTERNAL_PROBLEMS", "1")
    state = od.new_state()
    rng = random.Random(7)
    solved_any = False
    for _ in range(3):
        rec = od.autonomous_round(state, rng, problems=6, pop=60, base_budget=90)
        assert rec["external"] is True
        solved_any = solved_any or rec["external_solved_total"] > 0
    assert solved_any                                       # the loop SOLVES external problems
    assert state["ext_solved"]                              # per-task solve rounds recorded
    for name, prov in state["ext_prov"].items():
        assert set(prov) >= {"tier", "used_primitive", "reused_library_block", "round"}


def test_frozen_archive_does_not_grow_library(monkeypatch):
    # The frozen-archive ablation (the compounding causal control): with freeze_lib the library must not
    # accumulate new blocks past the seeds, so any solve is from the fixed axioms alone.
    monkeypatch.setenv("ATANOR_EXTERNAL_PROBLEMS", "1")
    state = od.new_state()
    rng = random.Random(1)
    before = {f: len(state["libraries"][f]) for f in od._FAMILIES}
    for _ in range(3):
        od.external_round(state, rng, problems=6, pop=50, base_budget=70,
                          freeze_lib=True, invent=False, close_loop=False)
    after = {f: len(state["libraries"][f]) for f in od._FAMILIES}
    assert after == before                                  # frozen: no library growth
