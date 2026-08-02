"""Streaming plasticity maintenance — O(1) memory per row ( P4, the LSM insight).

The old maintenance loaded the ENTIRE relations.jsonl (96MB on the 1GB VM),
processed it in memory, and rewrote the whole file — the exact pattern that
OOM-killed the VM before. The LSM-tree lesson (RocksDB): never hold the store;
stream it. Two passes, both line-streamed:

 pass 1: aggregate predicate stats (tiny dict) via a row GENERATOR —
 predicate_informativeness already accepts an iterable;
 pass 2: re-stream rows, blend/decay each one independently, append kept rows
 to a tmp file INCREMENTALLY, batch pruned rows to the cold archive
 (reversible forgetting, P2), atomic-replace at the end.

Peak memory = one row + the predicate-stats dict, regardless of store size.
Semantics identical to neuroplasticity.plasticity_tick (verified by test).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .neuroplasticity import archive_pruned, decayed_weight, predicate_informativeness

_ARCHIVE_BATCH = 500


def _rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # torn tail line: skip, never crash maintenance


def streaming_plasticity_tick(rel_path: str | Path, now: datetime, *,
                              half_life_days: float = 30.0, prune_floor: float = 0.05,
                              info_blend: float = 0.5,
                              archive_root: str | Path | None = None) -> dict[str, Any]:
    """Stream-process one relations.jsonl; returns the same stats dict shape as
    plasticity_tick(...)['stats'] plus 'archived'."""
    rel_path = Path(rel_path)
    if not rel_path.exists():
        return {"in": 0, "kept": 0, "pruned": 0, "distinct_predicates": 0, "archived": 0}

    # pass 1 — predicate stats over a generator (no list materialization)
    scores = predicate_informativeness(_rows(rel_path))

    # pass 2 — per-row blend + decay + prune, incremental write
    tmp = rel_path.with_suffix(".jsonl.tmp")
    seen = kept = 0
    prune_batch: list[dict[str, Any]] = []
    archived = 0
    archive_dir = Path(archive_root) if archive_root else rel_path.parent

    def _flush_pruned() -> None:
        nonlocal archived, prune_batch
        if prune_batch:
            archived += archive_pruned(archive_dir, prune_batch, now)
            prune_batch = []

    with tmp.open("w", encoding="utf-8") as out:
        for row in _rows(rel_path):
            seen += 1
            pred = str(row.get("relation") or "")
            if pred == "IS_A":
                info = 1.0                    # taxonomy stays strong
            elif pred.endswith("_OF"):
                info = 0.0                    # parse-structure labels decay away
            else:
                info = scores.get(pred, 0.5)
            w0 = float(row.get("weight") if row.get("weight") is not None else info)
            new = dict(row)
            new["weight"] = round((1 - info_blend) * w0 + info_blend * info, 4)
            new["info_weight"] = info
            dw = decayed_weight(new["weight"], new.get("updated_at"), now,
                                half_life_days=half_life_days)
            if dw < prune_floor:
                prune_batch.append(new)
                if len(prune_batch) >= _ARCHIVE_BATCH:
                    _flush_pruned()
                continue
            new["weight"] = round(dw, 4)
            out.write(json.dumps(new, ensure_ascii=False) + "\n")
            kept += 1
    _flush_pruned()
    tmp.replace(rel_path)
    return {"in": seen, "kept": kept, "pruned": seen - kept,
            "distinct_predicates": len(scores), "archived": archived}
