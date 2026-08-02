# -*- coding: utf-8 -*-
"""Split-then-merge corpus sharding: each learner process writes its OWN shard file (single-
writer), reads UNION main+shards, and an offline compactor folds shards into main with a global
dedup. Locks the mechanism that gives GIL-free N-way learning throughput without a write race.
See docs/ATANOR_multiprocess_sharding_design.md."""
import importlib

from packages.autonomy_kernel import narrative_corpus as nc


def _use_tmp(tmp_path, monkeypatch):
    # keep the prod filename so with_name('narrative_corpus.shard*') and the glob agree
    monkeypatch.setattr(nc, "CORPUS", tmp_path / "narrative_corpus.jsonl")



_S = {
    "a": "Water is a very simple substance made of hydrogen and oxygen.",
    "b": "A knowledge graph keeps relations between concepts as nodes and edges.",
    "c": "A virtual machine is a software environment behaving like a real computer.",
    "d": "Morphological analysis splits a sentence into units of meaning.",
}


def test_shard_env_isolates_writes_and_reads_union(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)

    # main writer (no shard env) writes the main file
    monkeypatch.delenv(nc._SHARD_ENV, raising=False)
    assert nc.add_lines([_S["a"]], source="main") == 1
    assert nc._write_path().name == "narrative_corpus.jsonl"

    # shard 0 writes ITS OWN file, never the main
    monkeypatch.setenv(nc._SHARD_ENV, "0")
    assert nc._write_path().name == "narrative_corpus.shard0.jsonl"
    assert nc.add_lines([_S["b"]], source="s0") == 1

    # shard 1 writes its own
    monkeypatch.setenv(nc._SHARD_ENV, "1")
    assert nc.add_lines([_S["c"]], source="s1") == 1

    # three distinct files exist, main untouched by shards
    assert (tmp_path / "narrative_corpus.jsonl").exists()
    assert (tmp_path / "narrative_corpus.shard0.jsonl").exists()
    assert (tmp_path / "narrative_corpus.shard1.jsonl").exists()
    assert nc.CORPUS.read_text(encoding="utf-8").count("\n") == 1   # only the main line

    # reads UNION every file regardless of which shard we're acting as
    tail = set(nc.corpus_tail(50))
    assert {_S["a"], _S["b"], _S["c"]} <= tail
    st = nc.stats()
    assert st["total"] == 3 and set(st["by_source"]) == {"main", "s0", "s1"}


def test_cross_shard_dedup_on_write(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    monkeypatch.setenv(nc._SHARD_ENV, "0")
    assert nc.add_lines([_S["a"]], source="s0") == 1
    # a different shard trying the SAME sentence must NOT duplicate it (union hash check)
    monkeypatch.setenv(nc._SHARD_ENV, "1")
    assert nc.add_lines([_S["a"]], source="s1") == 0
    assert nc.add_lines([_S["d"]], source="s1") == 1
    assert nc.stats()["total"] == 2


def test_compactor_merges_shards_into_main(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    compactor = importlib.import_module("scripts.corpus_compactor")

    monkeypatch.delenv(nc._SHARD_ENV, raising=False)
    nc.add_lines([_S["a"]], source="main")
    monkeypatch.setenv(nc._SHARD_ENV, "0")
    nc.add_lines([_S["b"]], source="s0")
    monkeypatch.setenv(nc._SHARD_ENV, "1")
    nc.add_lines([_S["c"], _S["d"]], source="s1")

    res = compactor.compact()
    assert res["shards"] == 2
    assert res["merged"] == 3           # b, c, d folded into main (a already there)
    assert res["main_after"] == 4

    # shards emptied, main holds everything, union read is stable
    assert compactor._read_lines(tmp_path / "narrative_corpus.shard0.jsonl") == []
    assert compactor._read_lines(tmp_path / "narrative_corpus.shard1.jsonl") == []
    assert nc.CORPUS.read_text(encoding="utf-8").count("\n") == 4
    assert {_S["a"], _S["b"], _S["c"], _S["d"]} <= set(nc.corpus_tail(50))

    # idempotent: a second compaction with no new shard lines merges nothing
    assert compactor.compact()["merged"] == 0


def test_default_behaviour_unchanged_without_shards(tmp_path, monkeypatch):
    """No shard env + no shard files == byte-identical single-file behaviour (the live path)."""
    _use_tmp(tmp_path, monkeypatch)
    monkeypatch.delenv(nc._SHARD_ENV, raising=False)
    nc.add_lines([_S["a"], _S["b"]], source="test")
    assert nc._read_paths() == [nc.CORPUS]
    assert nc.corpus_tail(10) == [_S["a"], _S["b"]]
    assert nc.stats()["total"] == 2
