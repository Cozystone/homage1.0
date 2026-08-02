from __future__ import annotations

import pytest

from rhfc.hypervector import cosine_similarity, random_bipolar
from rhfc.sharded_memory import HashShardRouter, ShardedCleanupMemory


def test_hash_router_is_deterministic() -> None:
    router = HashShardRouter(shard_count=8)
    vector = random_bipolar(dim=128, seed=1)
    metadata = {"id": "node_a"}

    assert router.assign_shard(vector, metadata) == router.assign_shard(vector, metadata)


def test_sharded_memory_splits_when_shard_capacity_is_reached() -> None:
    memory = ShardedCleanupMemory(
        dim=128,
        router=HashShardRouter(shard_count=2),
        max_patterns_per_shard=3,
    )
    for idx in range(8):
        memory.store(random_bipolar(dim=128, seed=idx), {"id": f"node_{idx}"})

    counts = memory.shard_counts()
    assert counts["patterns"] == 8
    assert len(memory.shards) >= 3
    assert all(len(shard.patterns) <= 3 for shard in memory.shards.values())


def test_sharded_memory_recall_returns_matching_pattern() -> None:
    memory = ShardedCleanupMemory(
        dim=256,
        router=HashShardRouter(shard_count=4),
        max_patterns_per_shard=16,
    )
    target = random_bipolar(dim=256, seed=42)
    for idx in range(20):
        pattern = target if idx == 7 else random_bipolar(dim=256, seed=idx)
        memory.store(pattern, {"id": f"node_{idx}"})

    result = memory.recall_with_metadata(target, query_all_shards=True)

    assert result.metadata["id"] == "node_7"
    assert cosine_similarity(result.vector, target) > 0.9
    assert result.queried_shards == len(memory.shards)


def test_cloud_scale_estimate_is_bounded_by_shard_size() -> None:
    memory = ShardedCleanupMemory(
        dim=1024,
        router=HashShardRouter(shard_count=128),
        max_patterns_per_shard=131_072,
    )
    estimate = memory.estimate_cloud_scale(22_530_240)

    assert estimate["estimated_shards"] == 172
    assert estimate["estimated_memory_gib"] == pytest.approx(171.89208984375)
