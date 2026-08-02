from __future__ import annotations

from rhfc.hypervector import random_bipolar
from rhfc.semantic_shard_router import SemanticShardRouter, TypeBucketRouter


def test_semantic_router_is_deterministic() -> None:
    router = SemanticShardRouter(shard_count=16)
    vector = random_bipolar(dim=128, seed=1)
    metadata = {"id": "n1", "type": "keyword"}

    assert router.assign_shard(vector, metadata) == router.assign_shard(vector, metadata)


def test_type_bucket_router_keeps_same_type_in_small_bucket() -> None:
    router = TypeBucketRouter(shard_count=16, bucket_width=2)
    vector = random_bipolar(dim=128, seed=1)
    shards = {
        router.assign_shard(vector, {"id": f"kw_{idx}", "type": "keyword"})
        for idx in range(12)
    }

    assert len(shards) <= 2
