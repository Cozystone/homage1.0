"""Shard-aware cleanup memory for RHFC Stage 3.

This module keeps the Stage 2.5 conclusion explicit: one flat Hopfield
cleanup layer is fine for small Local Brain state, but Cloud Brain scale must
route queries into bounded shards.  The router interface is intentionally
replaceable so a future semantic-cluster router can be added without changing
the cleanup memory API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import hashlib
from typing import Any, Iterable

import numpy as np

from .cleanup_memory import ModernHopfieldMemory
from .hypervector import HyperVector, cosine_similarity


class ShardRouter(ABC):
    """Assign cleanup patterns to bounded shards."""

    @abstractmethod
    def assign_shard(self, pattern: HyperVector, metadata: dict[str, Any]) -> int:
        """Return the preferred shard id for a pattern and its metadata."""


@dataclass(frozen=True)
class HashShardRouter(ShardRouter):
    """Deterministic placeholder router based on metadata or vector content.

    This is not a semantic router.  It is a small, replaceable default that
    distributes patterns evenly enough for memory-bound validation.  A future
    SemanticClusterShardRouter should use real domain/ontology clusters.
    """

    shard_count: int
    metadata_key: str = "id"

    def __post_init__(self) -> None:
        if self.shard_count <= 0:
            raise ValueError("shard_count must be positive")

    def assign_shard(self, pattern: HyperVector, metadata: dict[str, Any]) -> int:
        key = metadata.get(self.metadata_key) or metadata.get("node_id")
        if key is None:
            key = np.real(pattern.values[: min(64, pattern.dim)]).tobytes()
        payload = key if isinstance(key, bytes) else str(key).encode("utf-8")
        digest = hashlib.sha256(payload).digest()
        return int.from_bytes(digest[:8], "big") % self.shard_count


@dataclass
class ShardRecallResult:
    """Recall result with shard provenance."""

    vector: HyperVector
    shard_id: int
    pattern_index: int
    score: float
    metadata: dict[str, Any]
    queried_shards: int


@dataclass
class _ShardState:
    patterns: list[HyperVector] = field(default_factory=list)
    metadata: list[dict[str, Any]] = field(default_factory=list)
    memory: ModernHopfieldMemory | None = None
    dirty: bool = False

    def rebuild_if_needed(self) -> None:
        if self.dirty or self.memory is None:
            self.memory = ModernHopfieldMemory.store(self.patterns)
            self.dirty = False


@dataclass
class ShardedCleanupMemory:
    """Bounded collection of Hopfield cleanup memories.

    Store operations keep every shard below ``max_patterns_per_shard`` by
    probing for the next shard with available capacity.  Recall can query a
    routed shard when metadata is available, or all shards for diagnostics.
    """

    dim: int
    router: ShardRouter
    max_patterns_per_shard: int = 131_072
    shards: dict[int, _ShardState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.dim <= 0:
            raise ValueError("dim must be positive")
        if self.max_patterns_per_shard <= 0:
            raise ValueError("max_patterns_per_shard must be positive")

    def store(self, pattern: HyperVector, metadata: dict[str, Any] | None = None) -> int:
        """Store one pattern and return its assigned shard id."""

        if pattern.dim != self.dim:
            raise ValueError("pattern dimension mismatch")
        row_metadata = dict(metadata or {})
        preferred = self.router.assign_shard(pattern, row_metadata)
        shard_id = self._first_available_shard(preferred)
        shard = self.shards.setdefault(shard_id, _ShardState())
        shard.patterns.append(pattern)
        shard.metadata.append(row_metadata)
        shard.dirty = True
        return shard_id

    def store_many(self, rows: Iterable[tuple[HyperVector, dict[str, Any]]]) -> dict[str, int]:
        """Store many patterns and return shard counts."""

        for pattern, metadata in rows:
            self.store(pattern, metadata)
        return self.shard_counts()

    def recall(self, query: HyperVector, metadata: dict[str, Any] | None = None) -> HyperVector:
        """Recall the best matching pattern as a hypervector."""

        return self.recall_with_metadata(query, metadata).vector

    def recall_with_metadata(
        self,
        query: HyperVector,
        metadata: dict[str, Any] | None = None,
        *,
        query_all_shards: bool = False,
    ) -> ShardRecallResult:
        """Recall the best matching pattern and return provenance details."""

        if query.dim != self.dim:
            raise ValueError("query dimension mismatch")
        if not self.shards:
            raise ValueError("cannot recall from an empty sharded memory")
        shard_ids = self._candidate_shards(query, metadata, query_all_shards)
        best: ShardRecallResult | None = None
        for shard_id in shard_ids:
            shard = self.shards.get(shard_id)
            if shard is None or not shard.patterns:
                continue
            shard.rebuild_if_needed()
            assert shard.memory is not None
            recalled = shard.memory.recall(query)
            index = shard.memory.nearest_index(query)
            score = cosine_similarity(query.normalized(), HyperVector(shard.memory.patterns[index], "bipolar"))
            result = ShardRecallResult(
                vector=recalled,
                shard_id=shard_id,
                pattern_index=index,
                score=score,
                metadata=shard.metadata[index],
                queried_shards=len(shard_ids),
            )
            if best is None or result.score > best.score:
                best = result
        if best is None:
            raise ValueError("no populated shard matched the query")
        return best

    def shard_counts(self) -> dict[str, int]:
        """Return total pattern and shard counts."""

        return {
            "shards": len(self.shards),
            "patterns": sum(len(shard.patterns) for shard in self.shards.values()),
            "max_patterns_per_shard": self.max_patterns_per_shard,
        }

    def estimate_cloud_scale(self, logical_patterns: int, *, bytes_per_value: int = 8) -> dict[str, float | int]:
        """Estimate memory and shard count for a logical pattern count."""

        if logical_patterns < 0:
            raise ValueError("logical_patterns must be non-negative")
        shard_count = int(np.ceil(logical_patterns / self.max_patterns_per_shard)) if logical_patterns else 0
        total_bytes = int(logical_patterns) * int(self.dim) * int(bytes_per_value)
        return {
            "logical_patterns": int(logical_patterns),
            "dim": int(self.dim),
            "estimated_shards": shard_count,
            "estimated_memory_gib": total_bytes / float(1024**3),
            "bytes_per_value": int(bytes_per_value),
        }

    def _first_available_shard(self, preferred: int) -> int:
        shard_count = getattr(self.router, "shard_count", max(1, len(self.shards) or 1))
        for offset in range(max(1, int(shard_count))):
            shard_id = (preferred + offset) % max(1, int(shard_count))
            shard = self.shards.get(shard_id)
            if shard is None or len(shard.patterns) < self.max_patterns_per_shard:
                return shard_id
        new_shard_id = max(self.shards.keys(), default=-1) + 1
        return new_shard_id

    def _candidate_shards(
        self,
        query: HyperVector,
        metadata: dict[str, Any] | None,
        query_all_shards: bool,
    ) -> list[int]:
        if query_all_shards or metadata is None:
            return sorted(self.shards)
        preferred = self.router.assign_shard(query, metadata)
        if preferred in self.shards:
            return [preferred]
        return sorted(self.shards)
