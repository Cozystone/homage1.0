"""Process-based shard workers: the true multicore merge (Phase 2-5).

The threaded ShardedContributedStore is correctness-only (GIL-bound, no speedup).
This variant gives each shard to a DEDICATED WORKER PROCESS that owns it for the
process lifetime: the shard's dedupe index is loaded ONCE in the worker, and
merges for different shards run on different CPU cores. Rows are routed by their
OWN dedupe_key (identical rows always converge on one shard), so de-dup stays
EXACT at any worker count — the concept-inflation trap of source-routed sharding
does not apply here.

Transport is one duplex Pipe per worker with a per-worker lock held for the
request/response round trip, so any number of API threads can call accumulate()
concurrently and each worker still sees a strict message sequence.

Honesty: near-linear scaling until the coordinator's disk saturates; workers are
daemons and die with the API process. Manifests are flushed on demand, not per
batch (same O(n^2) wall avoidance as the threaded store).
"""

from __future__ import annotations

import multiprocessing as mp
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .sharded_store import _COUNTERS, _row_key, _shard_for_key


def _worker_main(shard_root: str, conn: Any) -> None:
    """Worker entrypoint (module-level: picklable under Windows spawn). Owns ONE
    shard store for its whole life; answers merge/flush/stop messages in order."""
    from packages.cgsr.cgsr.ingestion.accumulator import VerifiedStore
    from packages.cgsr.cgsr.ingestion.decomposer import DecompositionResult
    from packages.cloud_brain.continuous_learning import ensure_candidate_store_initialized

    root = Path(shard_root)
    ensure_candidate_store_initialized(root)
    store = VerifiedStore(root)  # dedupe index loaded once, here
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            break
        op = msg.get("op")
        if op == "stop":
            try:
                conn.send({"ok": True})
            except Exception:
                pass
            break
        if op == "flush":
            try:
                store.update_manifest()
                conn.send({"ok": True})
            except Exception as exc:
                conn.send({"ok": False, "error": str(exc)})
            continue
        if op == "merge":
            try:
                bundle = msg["bundle"]
                items = [DecompositionResult(evidence=ev) for ev in bundle.get("evidence") or []]
                if bundle.get("concepts") or bundle.get("relations") or bundle.get("case_frames"):
                    items.append(DecompositionResult(
                        concepts=bundle.get("concepts") or [],
                        relations=bundle.get("relations") or [],
                        case_frames=bundle.get("case_frames") or [],
                    ))
                res = store.accumulate(items, update_manifest=False)
                conn.send({c: int(getattr(res, c, 0) or 0) for c in _COUNTERS})
            except Exception as exc:
                conn.send({"error": str(exc)})
            continue
        conn.send({"error": f"unknown op {op!r}"})


class ProcessShardedStore:
    """K persistent worker processes, each owning one shard; row-level concept-key
    routing in the coordinator keeps global de-dup exact."""

    def __init__(self, root: str | Path, *, shards: int = 2) -> None:
        self.root = Path(root)
        self.shards = max(1, int(shards))
        ctx = mp.get_context("spawn")
        self._conns: list[Any] = []
        self._conn_locks: list[threading.Lock] = []
        self._procs: list[Any] = []
        for i in range(self.shards):
            parent, child = ctx.Pipe(duplex=True)
            proc = ctx.Process(
                target=_worker_main,
                args=(str(self.root / f"shard_{i:02d}"), child),
                daemon=True,
                name=f"contrib-shard-{i:02d}",
            )
            proc.start()
            child.close()
            self._conns.append(parent)
            self._conn_locks.append(threading.Lock())
            self._procs.append(proc)
        self._totals: dict[str, int] = {c: 0 for c in _COUNTERS}
        self._totals["batches"] = 0
        self._totals_lock = threading.Lock()

    # -- routing (mirror of ShardedContributedStore, but building plain-dict
    #    bundles so payloads cross the process boundary as-is) --
    def _route_rows(self, decompositions: Iterable[Any]) -> dict[int, dict[str, list]]:
        bundles: dict[int, dict[str, list]] = defaultdict(
            lambda: {"concepts": [], "relations": [], "case_frames": [], "evidence": []})
        k = self.shards
        for d in decompositions:
            get = d.get if isinstance(d, dict) else lambda f, _d=d: getattr(_d, f, None)
            ev = get("evidence")
            if ev:
                key = str(ev.get("source_hash") or ev.get("dedupe_key") or "")
                bundles[_shard_for_key(key, k)]["evidence"].append(ev)
            for row in (get("concepts") or []):
                bundles[_shard_for_key(_row_key(row, "concept_id"), k)]["concepts"].append(row)
            for row in (get("relations") or []):
                bundles[_shard_for_key(_row_key(row, "relation_id"), k)]["relations"].append(row)
            for row in (get("case_frames") or []):
                bundles[_shard_for_key(_row_key(row, "frame_id"), k)]["case_frames"].append(row)
        return dict(bundles)

    def _call(self, sidx: int, msg: dict[str, Any]) -> dict[str, Any]:
        with self._conn_locks[sidx]:
            self._conns[sidx].send(msg)
            return self._conns[sidx].recv()

    def accumulate(self, decompositions: Iterable[Any]) -> dict[str, Any]:
        """Route a batch by row dedupe_key and merge shards IN PARALLEL (each on
        its own worker core). Synchronous: returns this batch's aggregated counts."""
        bundles = self._route_rows(decompositions)
        agg: dict[str, int] = {c: 0 for c in _COUNTERS}
        if not bundles:
            return agg
        # fan out: send to every touched worker first, then collect, so shard
        # merges genuinely overlap instead of round-tripping one by one
        results: dict[int, dict[str, Any]] = {}
        threads: list[threading.Thread] = []

        def _one(s: int, b: dict[str, list]) -> None:
            try:
                results[s] = self._call(s, {"op": "merge", "bundle": b})
            except Exception as exc:
                results[s] = {"error": str(exc)}

        for sidx, bundle in bundles.items():
            t = threading.Thread(target=_one, args=(sidx, bundle), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=120)
        for part in results.values():
            if "error" in part:
                continue  # one failing shard never sinks the rest of the batch
            for c in _COUNTERS:
                agg[c] += int(part.get(c, 0) or 0)
        with self._totals_lock:
            for c in _COUNTERS:
                self._totals[c] += agg[c]
            self._totals["batches"] += 1
        return agg

    def flush_manifests(self) -> None:
        for i in range(self.shards):
            try:
                self._call(i, {"op": "flush"})
            except Exception:
                continue

    def totals(self) -> dict[str, int]:
        with self._totals_lock:
            return dict(self._totals)

    def status(self) -> dict[str, Any]:
        t = self.totals()
        return {
            "architecture": "process_shard_workers_conceptkey_routing",
            "shards": self.shards,
            "workers_alive": sum(1 for p in self._procs if p.is_alive()),
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

    def close(self) -> None:
        for i in range(self.shards):
            try:
                self._call(i, {"op": "stop"})
            except Exception:
                pass
        for p in self._procs:
            try:
                p.join(timeout=5)
            except Exception:
                pass
