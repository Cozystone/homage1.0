"""Brain Link pool — robust, horizontally-scalable merge for distributed learning.

The Brain Link idea: many peers extract concepts/relations in parallel, and the
coordinator MERGES their output into a shared store. Extraction is embarrassingly
parallel (linear in peer count). The merge, however, was the serial bottleneck:
a new store object was built per submit (re-reading the whole dedupe index =
O(n) per batch -> O(n^2) overall) and a single global lock serialized every
write. So adding peers stopped increasing throughput.

This package removes both bottlenecks so "more peers -> proportionally more
throughput" actually holds:
  * PERSISTENT per-shard stores (index loaded once, not per batch).
  * HASH-SHARDED parallel merge (K shards, K independent locks/writers).

Honesty: this is near-LINEAR scaling (Amdahl), never exponential. It scales until
a single coordinator's disk/CPU saturates; beyond that you run more coordinators.
"""

from .sharded_store import ShardedContributedStore

__all__ = ["ShardedContributedStore", "ProcessShardedStore"]


def __getattr__(name: str):
    # lazy: importing the process variant must not spawn anything at import time
    if name == "ProcessShardedStore":
        from .process_sharded_store import ProcessShardedStore

        return ProcessShardedStore
    raise AttributeError(name)
