"""Semantic shard router for RHFC Stage 4.

This router uses existing node metadata such as ``type`` or ``category`` as
the first routing key, then hashes within that semantic bucket.  It is a small
verified baseline, not a learned clustering model.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from .hypervector import HyperVector
from .sharded_memory import ShardRouter


@dataclass(frozen=True)
class SemanticShardRouter(ShardRouter):
    """Route by semantic metadata first and hash second."""

    shard_count: int
    semantic_key: str = "type"
    overflow_salt_key: str = "id"

    def __post_init__(self) -> None:
        if self.shard_count <= 0:
            raise ValueError("shard_count must be positive")

    def assign_shard(self, pattern: HyperVector, metadata: dict[str, Any]) -> int:
        """Return a deterministic shard id from metadata."""

        semantic = str(metadata.get(self.semantic_key) or metadata.get("category") or metadata.get("kind") or "unknown")
        overflow = str(metadata.get(self.overflow_salt_key) or metadata.get("node_id") or "")
        payload = f"{semantic}|{overflow}".encode("utf-8")
        digest = hashlib.sha256(payload).digest()
        return int.from_bytes(digest[:8], "big") % self.shard_count


@dataclass(frozen=True)
class TypeBucketRouter(ShardRouter):
    """Route each metadata type to a stable bucket range.

    ``bucket_width`` controls secondary hash spreading within a type bucket.
    With width 1, every type maps to one shard.  Larger widths let crowded
    types split deterministically.
    """

    shard_count: int
    bucket_width: int = 2
    semantic_key: str = "type"

    def __post_init__(self) -> None:
        if self.shard_count <= 0:
            raise ValueError("shard_count must be positive")
        if self.bucket_width <= 0:
            raise ValueError("bucket_width must be positive")

    def assign_shard(self, pattern: HyperVector, metadata: dict[str, Any]) -> int:
        semantic = str(metadata.get(self.semantic_key) or metadata.get("category") or metadata.get("kind") or "unknown")
        semantic_hash = int.from_bytes(hashlib.sha256(semantic.encode("utf-8")).digest()[:8], "big")
        base = (semantic_hash % max(1, self.shard_count // self.bucket_width)) * self.bucket_width
        node_key = str(metadata.get("id") or metadata.get("node_id") or "")
        offset = int.from_bytes(hashlib.sha256(node_key.encode("utf-8")).digest()[:8], "big") % self.bucket_width
        return (base + offset) % self.shard_count
