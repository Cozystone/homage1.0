"""Merge web-learned candidate knowledge into the production cloud semantic store.

This is the real promotion step (the user's " "): promoted
candidate concepts/relations are appended to the production
:class:`SemanticCloudStore` as a single, idempotent, removable growth shard — so
the Cloud Brain genuinely *contains* the learned knowledge instead of only
surfacing the candidate store.

Safety / reversibility:
- The merge is a discrete growth shard (``promoted_candidates``); removing the two
 shard files and the index entry fully reverses it. No existing rows are
 rewritten.
- Idempotent: re-running with the same shard id replaces that shard (the store's
 shard index accounts for the previous count), so repeated calls keep production
 in sync with the candidate set rather than double-counting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .candidate_read_model import resolve_candidate_store
from .semantic_store import DEFAULT_SEMANTIC_CLOUD_ROOT, SemanticCloudStore, utc_now_iso


PROMOTED_SHARD_ID = "promoted_candidates"


def _load_jsonl(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                import json

                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)
            if len(rows) >= limit:
                break
    return rows


def merge_candidates_to_production(
    candidate_store_path: str | Path | None = None,
    *,
    production_root: str | Path = DEFAULT_SEMANTIC_CLOUD_ROOT,
    max_concepts: int = 20_000,
    max_relations: int = 60_000,
    shard_id: str = PROMOTED_SHARD_ID,
) -> dict[str, Any]:
    """Append the candidate store's concepts/relations as a production growth shard.

    Returns a small audit dict. Never raises on a missing candidate store.
    """

    ref = resolve_candidate_store(candidate_store_path)
    root = getattr(ref, "root", None) or getattr(ref, "path", None)
    if not root:
        return {"merged": False, "reason": "no_candidate_store", "concepts": 0, "relations": 0}
    root = Path(str(root))

    concept_rows = _load_jsonl(root / "concepts.jsonl", limit=max_concepts)
    relation_rows = _load_jsonl(root / "relations.jsonl", limit=max_relations)
    if not concept_rows:
        return {"merged": False, "reason": "empty_candidate_store", "concepts": 0, "relations": 0}

    concepts: dict[str, dict[str, Any]] = {}
    for row in concept_rows:
        cid = str(row.get("concept_id") or "").strip()
        if not cid:
            continue
        concepts[cid] = {
            **row,
            "concept_id": cid,
            "promoted_from": "web_learned_candidate_store",
            "verification_status": "promoted",
            "promoted_at": utc_now_iso(),
        }

    valid_ids = set(concepts)
    relations: dict[str, dict[str, Any]] = {}
    for row in relation_rows:
        source = str(row.get("source_concept_id") or "").strip()
        target = str(row.get("target_concept_id") or "").strip()
        if not source or not target or source not in valid_ids or target not in valid_ids:
            continue
        rid = str(row.get("relation_id") or f"{source}:{target}:{len(relations)}")
        relations[rid] = {**row, "relation_id": rid, "promoted_from": "web_learned_candidate_store"}

    store = SemanticCloudStore(production_root)
    store.save_growth_shard(shard_id, concepts, relations)

    return {
        "merged": True,
        "shard_id": shard_id,
        "production_root": str(production_root),
        "candidate_store_path": str(root),
        "concepts": len(concepts),
        "relations": len(relations),
        "reversible": True,
        "production_store_mutated": True,
        "merged_at": utc_now_iso(),
    }
