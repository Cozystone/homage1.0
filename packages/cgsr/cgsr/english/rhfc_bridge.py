"""RHFC bridge for English canonical construction frames."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import sys
from typing import Any, Iterable

try:  # pragma: no cover - depends on installation mode
    from rhfc import HashShardRouter, HyperVector, ShardedCleanupMemory, bundle, random_bipolar
    from rhfc.hypervector import cosine_similarity
except ModuleNotFoundError:  # local monorepo checkout
    RHFC_ROOT = Path(__file__).resolve().parents[3] / "rhfc"
    if str(RHFC_ROOT) not in sys.path:
        sys.path.insert(0, str(RHFC_ROOT))
    from rhfc import HashShardRouter, HyperVector, ShardedCleanupMemory, bundle, random_bipolar
    from rhfc.hypervector import cosine_similarity

from .canonical_frames import EnglishConstructionFrame


DIMENSION = 512


@dataclass(frozen=True)
class EnglishRhfcRecord:
    """Stored English construction and vector metadata."""

    frame: EnglishConstructionFrame
    vector: HyperVector


@dataclass
class EnglishConstructionStore:
    """Bounded RHFC store for English construction frames."""

    memory: ShardedCleanupMemory
    records: list[EnglishRhfcRecord]

    def recall(self, query_frame: EnglishConstructionFrame) -> dict[str, Any]:
        """Recall the nearest stored frame for ``query_frame``."""

        query = encode_frame(query_frame)
        result = self.memory.recall_with_metadata(query, query_all_shards=True)
        return {
            "frame_id": result.metadata.get("frame_id"),
            "family": result.metadata.get("family"),
            "score": round(result.score, 6),
            "metadata": result.metadata,
        }

    def exact_recall_accuracy(self) -> dict[str, Any]:
        """Return exact self-recall accuracy for stored frames."""

        mistakes = []
        for record in self.records:
            result = self.recall(record.frame)
            if result["frame_id"] != record.frame.frame_id:
                mistakes.append({"expected": record.frame.frame_id, "actual": result["frame_id"]})
        return {
            "total": len(self.records),
            "correct": len(self.records) - len(mistakes),
            "accuracy": round((len(self.records) - len(mistakes)) / max(1, len(self.records)), 4),
            "confusions": mistakes,
            "forgetting_count": 0,
        }


def _seed(token: str) -> int:
    return int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:8], "big") % (2**32)


def _token_vector(token: str) -> HyperVector:
    return random_bipolar(DIMENSION, seed=_seed(token))


def frame_tokens(frame: EnglishConstructionFrame) -> list[str]:
    """Return deterministic semantic tokens for a frame."""

    return [
        f"family:{frame.family}",
        f"frame:{frame.frame_id}",
        *[f"slot:{slot}" for slot in sorted(frame.required_slots)],
        f"evidence_required:{frame.evidence_required}",
        f"abstention_allowed:{frame.abstention_allowed}",
    ]


def encode_frame(frame: EnglishConstructionFrame) -> HyperVector:
    """Encode an English construction frame for RHFC cleanup recall."""

    vectors = [_token_vector(f"EN_CGSR::{token}") for token in frame_tokens(frame)]
    vectors.append(_token_vector("EN_CGSR::CONSTRUCTION"))
    return bundle(vectors).bipolarized()


def store_english_frames(frames: Iterable[EnglishConstructionFrame], *, shard_count: int = 4) -> EnglishConstructionStore:
    """Store English frames in a sharded RHFC cleanup memory."""

    rows = list(frames)
    memory = ShardedCleanupMemory(
        dim=DIMENSION,
        router=HashShardRouter(shard_count=max(1, shard_count), metadata_key="frame_id"),
        max_patterns_per_shard=2048,
    )
    records: list[EnglishRhfcRecord] = []
    for frame in rows:
        vector = encode_frame(frame)
        memory.store(vector, {"frame_id": frame.frame_id, "family": frame.family})
        records.append(EnglishRhfcRecord(frame=frame, vector=vector))
    return EnglishConstructionStore(memory=memory, records=records)


def pairwise_similarity(records: list[EnglishRhfcRecord]) -> list[dict[str, Any]]:
    """Return bounded pairwise similarities for diagnostics."""

    rows = []
    for left in records:
        for right in records:
            if left.frame.frame_id >= right.frame.frame_id:
                continue
            rows.append(
                {
                    "left": left.frame.frame_id,
                    "right": right.frame.frame_id,
                    "cosine": round(cosine_similarity(left.vector, right.vector), 6),
                }
            )
    return rows[:50]
