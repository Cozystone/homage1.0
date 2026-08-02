"""RHFC Stage 1: independent holographic/vector-symbolic core.

This package intentionally does not import or mutate existing ATANOR runtime
packages. Stage 1 is a standalone correctness/performance proof surface.
"""

from .fft_binding import bind, fft_magnitude_deviation, make_unitary_key, unbind
from .hypervector import HyperVector, bundle, cosine_similarity, permute, random_bipolar, random_complex
from .semantic_shard_router import SemanticShardRouter, TypeBucketRouter
from .sharded_memory import HashShardRouter, ShardedCleanupMemory, ShardRecallResult, ShardRouter

__all__ = [
    "HyperVector",
    "HashShardRouter",
    "ShardRecallResult",
    "ShardRouter",
    "ShardedCleanupMemory",
    "SemanticShardRouter",
    "TypeBucketRouter",
    "bind",
    "bundle",
    "cosine_similarity",
    "fft_magnitude_deviation",
    "make_unitary_key",
    "permute",
    "random_bipolar",
    "random_complex",
    "unbind",
]
