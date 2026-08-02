"""The sharded on-disk term dictionary removes the RAM vocabulary wall: ids must be stable,
reversible, coordination-free across shards, and survive a full reopen — because a store
that forgets its ids corrupts every column that references them."""
from __future__ import annotations

import tempfile
from pathlib import Path

from packages.graph_scale.sharded_term_dict import ShardedTermDict
from packages.graph_scale.triple_store import TripleStore


def test_ids_stable_and_reversible():
    d = ShardedTermDict(Path(tempfile.mkdtemp()) / "dict", n_shards=4)
    a, b = d.intern("서울"), d.intern("도쿄")
    assert a != b
    assert d.intern("서울") == a                    # stable
    assert d.term(a) == "서울" and d.term(b) == "도쿄"  # reversible
    assert d.lookup("서울") == a and d.lookup("없는말") is None


def test_ids_survive_reopen():
    root = Path(tempfile.mkdtemp()) / "dict"
    d = ShardedTermDict(root, n_shards=4)
    ids = {t: d.intern(t) for t in ("가", "나", "다", "라", "마")}
    d.close()
    d2 = ShardedTermDict(root, n_shards=4)
    for t, i in ids.items():
        assert d2.intern(t) == i                   # same id after reopen (no re-mint)
        assert d2.term(i) == t
    assert len(d2) == 5


def test_no_global_id_collisions_across_shards():
    d = ShardedTermDict(Path(tempfile.mkdtemp()) / "dict", n_shards=8)
    ids = [d.intern(f"term_{i}") for i in range(2000)]
    assert len(set(ids)) == 2000                   # bijective allocation


def test_triple_store_with_sharded_backend():
    root = Path(tempfile.mkdtemp()) / "kg"
    ts = TripleStore(root, dict_backend="sharded")
    ts.bulk_ingest([("일본", "capital", "도쿄도"), ("캐나다", "capital", "오타와")])
    assert ts.facts_about("일본") == [("일본", "capital", "도쿄도")]
    # reopen WITHOUT passing the backend: meta.json remembers it
    ts2 = TripleStore(root)
    assert ts2.dict_backend == "sharded"
    assert ts2.facts_about("캐나다") == [("캐나다", "capital", "오타와")]
