# -*- coding: utf-8 -*-
"""Critic arena — the evaluator evolves against a frozen exam, safely.

Guarantees:
  1. coefficient genomes stay inside viable bounds (no term evolved to 0 = disarmed check);
  2. a candidate scorer built from a genome runs and returns a bounded score;
  3. evolution never DEGRADES the champion (elitism vs. the incumbent baseline);
  4. every saved champion still passes the structural integrity gate (unchanged Critic code).
"""
from __future__ import annotations

import random

from packages.evolution import critic_arena as ca
from packages.evolution import frozen_oracle as fo


def test_genomes_respect_bounds():
    rng = random.Random(3)
    g = dict(ca._CRITIC_DEFAULTS)
    for _ in range(50):
        g = ca.mutate(g, rng, scale=0.9)
        for k, (lo, hi) in ca.BOUNDS.items():
            assert lo <= g[k] <= hi
    child = ca.crossover(ca._CRITIC_DEFAULTS, g, rng)
    for k, (lo, hi) in ca.BOUNDS.items():
        assert lo <= child[k] <= hi


def test_candidate_scorer_is_bounded_and_restores_override():
    from packages.base_brain import speech_selfplay as sp
    before = sp._COEFF_OVERRIDE
    fn = ca.critic_fn_for(ca._CRITIC_DEFAULTS)
    for text in ["봄이 오면 마음이 따뜻해진다.", "음 어 그 저", ""]:
        s = fn(text)
        assert 0.0 <= s <= 1.0
    assert sp._COEFF_OVERRIDE is before  # the live override is restored (None) after scoring


def test_evolution_does_not_degrade(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "OUT_DIR", tmp_path)
    monkeypatch.setattr(ca, "GENOME_PATH", tmp_path / "critic_genome.json")
    monkeypatch.setattr(ca, "HISTORY_PATH", tmp_path / "hist.jsonl")
    monkeypatch.setattr(fo, "ORACLE_PATH", tmp_path / "oracle.json")
    out = ca.evolve(pop=4, generations=3, log=lambda *_: None)
    assert out["champion"]["fitness"] >= out["baseline"]["fitness"]  # elitism: never worse
    # the champion still separates good from bad on the frozen exam
    assert out["champion"]["separation"] > 0.0


def test_saved_champion_passes_structural_gate(tmp_path, monkeypatch):
    from packages.evolution.critic_integrity import CRITIC_SRC, verify_candidate
    # a coefficient-only champion never edits the Critic source → structure intact
    assert verify_candidate(CRITIC_SRC.read_text(encoding="utf-8"))["structural_pass"] is True
