# -*- coding: utf-8 -*-
"""Distributed tensor sharding: concept-key routing = exact single-node result,
verified per op, capacity math concrete."""
import numpy as np

from packages.brain_link_pool.distributed_tensor_shard import (
    ShardRouter, partition_columns, plan_capacity, shard_of)


class _Terms:
    def __init__(self, labels):
        self._l = labels
        self._i = {t: i for i, t in enumerate(labels)}
    def term(self, i):
        return self._l[i] if 0 <= i < len(self._l) else ""
    def lookup(self, t):
        return self._i.get(t)


def _graph():
    labels = ["cat", "dog", "mammal", "animal", "seoul", "korea", "city"]
    T = _Terms(labels)
    edges = [("cat", "is_a", "mammal"), ("cat", "is_a", "animal"),
             ("dog", "is_a", "mammal"), ("seoul", "is_a", "city"),
             ("seoul", "located_in", "korea"), ("mammal", "is_a", "animal")]
    s = np.array([T.lookup(a) for a, _, _ in edges])
    p = np.array([T.lookup(b) if T.lookup(b) is not None else -1 for _, b, _ in edges])
    o = np.array([T.lookup(c) for _, _, c in edges])
    return T, s, p, o


def test_partition_keeps_a_subjects_edges_together():
    T, s, p, o = _graph()
    for K in (2, 3, 4):
        shards = partition_columns(s, p, o, T, K)
        # every 'cat' edge lands in the shard that owns 'cat'
        owner = shard_of("cat", K)
        cat_id = T.lookup("cat")
        for sh in shards:
            if sh.shard_id != owner:
                assert (sh.s != cat_id).all()
        assert sum(sh.rows() for sh in shards) == len(s)   # no edge lost/duplicated


def test_router_matches_single_node_degree_and_neighbors():
    T, s, p, o = _graph()
    shards = partition_columns(s, p, o, T, 3)
    r = ShardRouter(shards, T)
    # single-node reference
    cat = T.lookup("cat")
    assert r.degree("cat") == int((s == cat).sum())
    assert r.neighbors("cat") == sorted(int(x) for x in o[s == cat].tolist())
    assert r.stats["verified"] == 2 and r.stats["rejected"] == 0


def test_proof_rejects_a_lying_shard():
    T, s, p, o = _graph()
    shards = partition_columns(s, p, o, T, 2)
    r = ShardRouter(shards, T)
    k = r.owner("cat")
    orig = shards[k].degree_of
    shards[k].degree_of = lambda cid: orig(cid) + 99   # a cheating peer
    assert r.degree("cat") is None                     # proof re-run catches it
    assert r.stats["rejected"] == 1


def test_capacity_plan_trillion_scale():
    plan = plan_capacity(1_000_000_000_000, vram_gb_per_peer=16.0)
    assert plan["gb_total"] == 24000.0                 # ~23-24 TB, the owner's number
    assert plan["peers_required"] == 1500              # 24TB / 16GB


def test_majority_router_storage_offload():
    """Coordinator holds no columns; replica majority = single-node truth,
    and a lying replica is outvoted, not trusted."""
    import numpy as np
    from packages.brain_link_pool.distributed_tensor_shard import (
        MajorityRouter, partition_columns_replicated, partition_columns)

    class _T:
        def __init__(self, n):
            self._names = {f"c{i}": i for i in range(n)}
        def term(self, i): return f"c{i}"
        def lookup(self, t): return self._names.get(t)

    terms = _T(50)
    rng = np.random.default_rng(7)
    s = rng.integers(0, 50, 3000); p = np.zeros(3000, int); o = rng.integers(0, 50, 3000)
    single = partition_columns(s, p, o, terms, 1)[0]
    shards = partition_columns_replicated(s, p, o, terms, 5, replicas=3)
    router = MajorityRouter(shards=shards, terms=terms, replicas=3)
    for c in ("c3", "c17", "c42"):
        assert router.degree(c) == single.degree_of(terms.lookup(c))
        assert router.neighbors(c) == single.out_neighbors(terms.lookup(c))
    assert router.stats["outvoted_peers"] == 0

    # one replica lies about degrees: majority outvotes it, answer unchanged
    class _Liar:
        def __init__(self, real): self._r = real
        def degree_of(self, cid): return self._r.degree_of(cid) + 99
        def out_neighbors(self, cid): return self._r.out_neighbors(cid)
    from packages.brain_link_pool.distributed_tensor_shard import replica_owners
    victim = "c3"
    k_lie = replica_owners(victim, 5, 3)[1]
    shards2 = list(shards); shards2[k_lie] = _Liar(shards[k_lie])
    router2 = MajorityRouter(shards=shards2, terms=terms, replicas=3)
    assert router2.degree(victim) == single.degree_of(terms.lookup(victim))
    assert router2.stats["outvoted_peers"] == 1
