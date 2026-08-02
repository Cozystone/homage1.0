"""Hash-sharded, persistent, parallel merge for peer-contributed decompositions.

Each shard is a full VerifiedStore living for the process lifetime (its dedupe
index is read ONCE at construction, never per batch). A decomposition is routed
to a shard by a stable hash of its source sentence, so a batch fans out across K
shards that merge concurrently under K independent locks. Net effect: the merge
keeps up with many parallel peers instead of funnelling through one writer.

Trade-off (MEASURED, honest): a whole decomposition is routed by its source, so
the SAME concept extracted from DIFFERENT sentences can land in different shards
and be stored once PER shard. Benchmark: merging the same data into 8 shards
added ~8x the concept rows vs a single store. So shards>1 inflates the candidate
pool's concept count; exact global de-dup must then be applied downstream (at
promotion). Within ONE shard, de-dup is exact (the real VerifiedStore, untouched).
Therefore the DEFAULT is 1 shard (exact de-dup); >1 is an opt-in scaling knob that
only pays off with PROCESS-based workers (threads are GIL-bound — no speedup) AND
ideally concept-key routing to restore de-dup. See bench_process_merge.py.
"""

from __future__ import annotations

import hashlib
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable

from packages.cgsr.cgsr.ingestion.accumulator import VerifiedStore
from packages.cgsr.cgsr.ingestion.decomposer import DecompositionResult
from packages.cloud_brain.continuous_learning import ensure_candidate_store_initialized

_COUNTERS = (
    "concepts_added",
    "relations_added",
    "evidence_added",
    "case_frames_added",
    "concepts_deduped",
    "relations_deduped",
    "evidence_deduped",
    "case_frames_deduped",
)


def _shard_for_key(key: str, shards: int) -> int:
    """Map a row's own dedupe_key to a shard. The SAME key always maps to the SAME
    shard, so a given concept/relation lives in exactly ONE shard -> de-dup stays
    EXACT no matter the shard count (no cross-shard inflation)."""
    if shards <= 1:
        return 0
    if not key:
        return 0
    h = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "big") % shards


def _row_key(row: dict[str, Any], *id_fields: str) -> str:
    key = str(row.get("dedupe_key") or "")
    if key:
        return key
    for f in id_fields:
        v = row.get(f)
        if v:
            return str(v)
    return ""


class ShardedContributedStore:
    """Persistent K-shard merge with ROW-LEVEL (concept-key) routing.

    Each ROW is routed by its OWN dedupe_key, so identical rows always converge on
    one shard and de-dup is exact at any shard count. Shards are persistent
    VerifiedStores (index loaded once). The in-process pool is threaded (GIL-bound
    merge -> correctness, not speedup); true multicore merge is the process-based
    variant (see process_sharded_store / bench_process_merge)."""

    def __init__(self, root: str | Path, *, shards: int = 1, max_workers: int | None = None) -> None:
        self.root = Path(root)
        self.shards = max(1, int(shards))
        self._stores: list[VerifiedStore] = []
        self._locks: list[threading.RLock] = []
        for i in range(self.shards):
            sroot = self.root / f"shard_{i:02d}"
            ensure_candidate_store_initialized(sroot)
            # Persistent: the dedupe index is loaded HERE, once, not per batch.
            self._stores.append(VerifiedStore(sroot))
            self._locks.append(threading.RLock())
        workers = max_workers if max_workers is not None else self.shards
        self._pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="contrib-merge")
        self._totals: dict[str, int] = {c: 0 for c in _COUNTERS}
        self._totals["batches"] = 0
        self._totals_lock = threading.Lock()

    def _route_rows(self, decompositions: Iterable[DecompositionResult]) -> dict[int, list[DecompositionResult]]:
        """Split a batch into per-shard DecompositionResults by ROW dedupe_key.
        Evidence routes by source_hash; concepts/relations/case_frames by their own
        dedupe_key. accumulate() processes each collection independently, so a
        per-shard bundle of only that shard's rows is valid and de-dups exactly."""
        concepts: dict[int, list[dict[str, Any]]] = defaultdict(list)
        relations: dict[int, list[dict[str, Any]]] = defaultdict(list)
        frames: dict[int, list[dict[str, Any]]] = defaultdict(list)
        evidence: dict[int, list[dict[str, Any]]] = defaultdict(list)
        k = self.shards
        for d in decompositions:
            ev = getattr(d, "evidence", None)
            if ev:
                evidence[_shard_for_key(str(ev.get("source_hash") or ev.get("dedupe_key") or ""), k)].append(ev)
            for row in (getattr(d, "concepts", None) or []):
                concepts[_shard_for_key(_row_key(row, "concept_id"), k)].append(row)
            for row in (getattr(d, "relations", None) or []):
                relations[_shard_for_key(_row_key(row, "relation_id"), k)].append(row)
            for row in (getattr(d, "case_frames", None) or []):
                frames[_shard_for_key(_row_key(row, "frame_id"), k)].append(row)
        bundles: dict[int, list[DecompositionResult]] = {}
        touched = set(concepts) | set(relations) | set(frames) | set(evidence)
        for s in touched:
            items = [DecompositionResult(evidence=ev) for ev in evidence.get(s, [])]
            if concepts.get(s) or relations.get(s) or frames.get(s):
                items.append(DecompositionResult(
                    concepts=concepts.get(s, []),
                    relations=relations.get(s, []),
                    case_frames=frames.get(s, []),
                ))
            bundles[s] = items
        return bundles

    def _merge_one_shard(self, sidx: int, group: list[DecompositionResult]) -> dict[str, int]:
        with self._locks[sidx]:
            # Skip the per-batch manifest recount (O(shard size)); the sharded
            # store reports growth from in-memory _totals and flushes manifests on
            # demand. This removes a second O(n^2)-as-it-grows wall from the hot path.
            res = self._stores[sidx].accumulate(group, update_manifest=False)
        out: dict[str, int] = {}
        for c in _COUNTERS:
            out[c] = int(getattr(res, c, 0) or 0)
        return out

    def flush_manifests(self) -> None:
        """Refresh each shard's on-disk manifest counts (the recount we skip per
        batch). Call when accurate on-disk manifests are wanted (e.g. before an
        offline read of the shard dirs)."""
        for i in range(self.shards):
            with self._locks[i]:
                try:
                    self._stores[i].update_manifest()
                except Exception:
                    continue

    def accumulate(self, decompositions: Iterable[DecompositionResult]) -> dict[str, Any]:
        """Row-route a batch to shards and merge them. Returns the aggregated
        added/deduped counts for THIS batch. One failing shard never sinks the
        rest of the batch."""
        bundles = self._route_rows(decompositions)
        if not bundles:
            return {c: 0 for c in _COUNTERS}

        agg: dict[str, int] = {c: 0 for c in _COUNTERS}
        futures = {self._pool.submit(self._merge_one_shard, sidx, grp): sidx for sidx, grp in bundles.items()}
        for fut in futures:
            try:
                part = fut.result()
            except Exception:
                continue  # a shard error is isolated; the rest of the batch still lands
            for c in _COUNTERS:
                agg[c] += part.get(c, 0)

        with self._totals_lock:
            for c in _COUNTERS:
                self._totals[c] += agg[c]
            self._totals["batches"] += 1
        return agg

    def totals(self) -> dict[str, int]:
        with self._totals_lock:
            return dict(self._totals)

    def status(self) -> dict[str, Any]:
        t = self.totals()
        return {
            "architecture": "persistent_hash_sharded_parallel_merge",
            "shards": self.shards,
            "root": str(self.root),
            "concepts_added_total": t["concepts_added"],
            "relations_added_total": t["relations_added"],
            "evidence_added_total": t["evidence_added"],
            "batches_merged": t["batches"],
            "deduped": {
                "concepts": t["concepts_deduped"],
                "relations": t["relations_deduped"],
                "evidence": t["evidence_deduped"],
            },
        }
