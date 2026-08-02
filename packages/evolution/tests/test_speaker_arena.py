# -*- coding: utf-8 -*-
"""Speaker arena — locks the safety and selection invariants of the evolution loop.

The load-bearing guarantees:
 1. genes stay inside their viable bounds under any mutation/crossover;
 2. the arena's generated lines contain ONLY corpus-attested tokens (evolution varies HOW
 the voice speaks, never lets it mint words — the fact layer is out of reach);
 3. antibodies are conjunctive (a bigram healthy speech also uses is never banned) and
 actually block the continuation in generate_fluent (removal-only immune memory);
 4. the champion genome round-trips through persistence ( ).
"""
from __future__ import annotations

import random

import pytest

from packages.cgsr.cgsr.holographic_lm import HolographicLM, tokens
from packages.evolution import speaker_arena as arena

_CORPUS = [
    "봄이 오면 마음이 따뜻해진다",
    "바다는 잔잔하게 빛난다",
    "함께 걷는 길은 포근하다",
    "별빛이 고요하게 내린다",
    "생각이 자라면 말도 함께 자란다",
    "마음이 고요하면 생각이 맑아진다",
]
_HOLDOUT = ["마음이 넓어지는 하루였다", "함께 있으면 바다도 가깝다"]


def test_mutation_and_crossover_respect_bounds():
    rng = random.Random(3)
    g = dict(arena.DEFAULT_GENOME)
    for _ in range(60):
        g = arena.mutate(g, rng, scale=0.9)  # violent mutation on purpose
        for name, (lo, hi) in arena.BOUNDS.items():
            assert lo <= g[name] <= hi
        assert isinstance(g["window"], int) and isinstance(g["top_k"], int)
    child = arena.crossover(arena.DEFAULT_GENOME, g, rng)
    for name, (lo, hi) in arena.BOUNDS.items():
        assert lo <= child[name] <= hi


def test_evaluation_speaks_only_attested_tokens():
    seeds = arena.draw_seeds(_HOLDOUT, _CORPUS, random.Random(5), k=4)
    assert seeds, "holdout and corpus share vocabulary — seeds must exist"
    res = arena.evaluate_genome(dict(arena.DEFAULT_GENOME), _CORPUS, seeds, [])
    vocab = set()
    for line in _CORPUS:
        vocab.update(tokens(line))
    assert 0.0 <= res["fitness"] <= 1.0
    for line in res["lines"]:
        for tok in tokens(line["text"]):
            assert tok in vocab  # the gate: no minted words, ever


def test_antibody_harvest_is_conjunctive():
    results = [{"lines": [
        {"text": "나쁜 파편 조각", "total": 0.1},          # failing line
        {"text": "함께 걷는 길은 포근하다", "total": 0.9},  # passing line
        {"text": "나쁜 파편 함께 걷는", "total": 0.2},
    ]}]
    pairs = set(arena.harvest_antibodies(results))
    assert ("나쁜", "파편") in pairs           # unique to failures → antibody
    assert ("함께", "걷는") not in pairs        # healthy tissue → protected


def test_antibody_blocks_continuation_in_generation():
    lm = HolographicLM(dim=256, window=3, decay=0.7, seed=7)
    lm.fit(["가 나 다 라 마 바다"])
    free = lm.generate_fluent("가", max_len=5, coherence=0.0, rep_penalty=0.0)
    assert free[:3] == ["가", "나", "다"]  # the only path
    blocked = lm.generate_fluent("가", max_len=5, coherence=0.0, rep_penalty=0.0,
                                 antibody={("나", "다")})
    assert "다" not in blocked  # the banned continuation is honestly refused, not replaced


def test_champion_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(arena, "OUT_DIR", tmp_path)
    monkeypatch.setattr(arena, "GENOME_PATH", tmp_path / "speaker_genome.json")
    res = {"genome": dict(arena.DEFAULT_GENOME), "fitness": 0.71, "mean_quality": 0.7}
    arena.save_champion(res, generation=2)
    loaded = arena.load_champion(tmp_path / "speaker_genome.json")
    assert loaded and loaded["genome"] == arena.DEFAULT_GENOME and loaded["fitness"] == 0.71


def test_serial_evolve_improves_or_holds(tmp_path, monkeypatch):
    monkeypatch.setattr(arena, "OUT_DIR", tmp_path)
    monkeypatch.setattr(arena, "GENOME_PATH", tmp_path / "speaker_genome.json")
    monkeypatch.setattr(arena, "ANTIBODY_PATH", tmp_path / "antibodies.jsonl")
    monkeypatch.setattr(arena, "HISTORY_PATH", tmp_path / "history.jsonl")
    out = arena.evolve(_CORPUS, _HOLDOUT, pop=3, generations=2, workers=1,
                       log=lambda *_: None)
    hist = out["history"]
    assert len(hist) == 2
    # elitism: the champion's fitness is monotonically non-decreasing across generations
    assert hist[1]["champion_fitness"] >= hist[0]["champion_fitness"]
    assert (tmp_path / "speaker_genome.json").exists()
