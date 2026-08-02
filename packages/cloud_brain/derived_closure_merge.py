# -*- coding: utf-8 -*-
"""Promote the Surgeon-reviewed deductive-closure candidates into production.

Owner approval (2026-07-09): "88K ." These are the is_a edges the
reasoning VM *proved* by transitive closure over the base graph, then the Surgeon
(type-disjointness blade) reviewed — 0%-wrong by construction, contamination
excised. This is the real promotion the gate was holding.

Safety — the healed scab, not a scar:
- Written as ONE reversible growth shard (``derived_isa_closure``). Removing the
 two shard files + the index entry fully reverses it; no existing rows change.
- Idempotent: re-running replaces that shard (the index accounts for the prior
 count), so production stays in sync rather than double-counting.
- It promotes ONLY what already sits in the candidate ledger
 (data/cloud_brain/derived_candidates/{relation}_closure.jsonl), which itself
 only ever received Surgeon-passed pairs. No new derivation happens here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .semantic_store import DEFAULT_SEMANTIC_CLOUD_ROOT, SemanticCloudStore, utc_now_iso

REPO = Path(__file__).resolve().parents[2]
LEDGER_DIR = REPO / "data" / "cloud_brain" / "derived_candidates"
SHARD_ID = "derived_isa_closure"


def _iter_ledger(relation: str, *, cap: int) -> Any:
    path = LEDGER_DIR / f"{relation}_closure.jsonl"
    if not path.exists():
        return
    n = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            s, o = str(row.get("s") or ""), str(row.get("o") or "")
            if s and o and s != o:
                yield s, str(row.get("p") or relation), o
                n += 1
                if n >= cap:
                    return


def merge_derived_closure_to_production(
    relation: str = "is_a",
    *,
    production_root: str | Path = DEFAULT_SEMANTIC_CLOUD_ROOT,
    cap: int = 200_000,
    shard_id: str = SHARD_ID,
) -> dict[str, Any]:
    """Append the Surgeon-reviewed closure ledger as a reversible production
    growth shard. Returns an audit dict. Never raises on an empty ledger."""
    concepts: dict[str, dict[str, Any]] = {}
    relations: dict[str, dict[str, Any]] = {}
    now = utc_now_iso()
    for s, p, o in _iter_ledger(relation, cap=cap):
        for term in (s, o):
            if term not in concepts:
                concepts[term] = {
                    "concept_id": term, "label": term, "name": term,
                    "promoted_from": "derived_closure_surgeon_reviewed",
                    "verification_status": "promoted", "promoted_at": now,
                }
        rid = f"{s}::{p}::{o}"
        relations[rid] = {
            "relation_id": rid, "source_concept_id": s, "target_concept_id": o,
            "relation_type": p, "predicate": p,
            "provenance": f"derived:closure:{p}:surgeon-reviewed",
            "verification_status": "promoted", "promoted_at": now,
        }
    if not relations:
        return {"merged": False, "reason": "empty_ledger", "relation": relation,
                "concepts": 0, "relations": 0}

    store = SemanticCloudStore(production_root)
    store.save_growth_shard(shard_id, concepts, relations)
    return {
        "merged": True, "shard_id": shard_id, "relation": relation,
        "production_root": str(production_root),
        "concepts": len(concepts), "relations": len(relations),
        "reversible": True, "production_store_mutated": True,
        "undo": f"delete data/cloud_brain/semantic_growth_shards/{shard_id}_*.json "
                f"and its entry in semantic_growth_shard_index.json",
        "merged_at": now,
    }
