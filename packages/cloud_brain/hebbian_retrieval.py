"""Online Hebbian retrieval — the edges TRAVERSED to answer get stronger, in real time.

This closes the loop the user asked for: activation crosses a few edges to build an answer, and
those exact edges are reinforced so they surface faster next time (LTP); edges never used fade via
the decay/prune tick (LTD, see plasticity_tick). Crucially this is NOT a visual effect — the
reinforced WEIGHT feeds the ranking, so learning actually changes which relations an answer uses.

Why this fits ATANOR's low-compute / trillion-node advantage: each answer reinforces only the
handful of edges on its OWN path — O(path), not O(graph). A dense neural net can't learn online
this cheaply (backprop touches every weight); a weighted graph can, at any scale.

Pure functions — the caller persists the returned edges to the learnable store (never the curated
demo pack).
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .neuroplasticity import decayed_weight, reinforce_traversed


def _rid(relation: dict[str, Any]) -> str:
    return str(relation.get("relation_id") or relation.get("id") or id(relation))


def rank_by_weight(relations: list[dict[str, Any]], now: datetime, *, half_life_days: float = 30.0) -> list[dict[str, Any]]:
    """Relations strongest-first by TIME-DECAYED weight (recent usage/observation wins)."""
    def key(r: dict[str, Any]) -> float:
        return decayed_weight(r.get("weight", 0.5), r.get("updated_at"), now, half_life_days)
    return sorted(relations, key=key, reverse=True)


def select_and_reinforce(
    relations: list[dict[str, Any]],
    now: datetime,
    *,
    max_relations: int = 3,
    amount: float = 0.05,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pick the top edges by weight to USE in the answer, then reinforce exactly those.

    Returns (selected_edges, all_edges_with_updated_weights). The selection is what the answer
    traverses; reinforcing it means the next call ranks it higher — real online learning, bounded
    to the active path. The caller persists `all_edges_with_updated_weights`."""
    ranked = rank_by_weight(relations, now, )
    selected = ranked[:max_relations]
    by_id: dict[str, dict[str, Any]] = {_rid(r): r for r in relations}
    reinforce_traversed(by_id, [_rid(r) for r in selected], now, amount=amount)
    updated = [by_id[_rid(r)] for r in relations]
    # selected edges reflect the freshly-reinforced weights too
    selected_updated = [by_id[_rid(r)] for r in selected]
    return selected_updated, updated


def apply_answer_reinforcement(
    relations_path: str | Path,
    source_concept_id: str,
    now: datetime,
    *,
    max_relations: int = 3,
    amount: float = 0.05,
) -> dict[str, Any]:
    """Persist online learning: reinforce the edges of `source_concept_id` that an answer
    traversed, writing the updated weights back to the JSONL relation store so the NEXT answer
    ranks them higher. Only ever mutates the learnable candidate store — never the curated demo
    pack. Atomic write. Returns which edges were reinforced. No-op (reinforced=0) if absent."""
    path = Path(relations_path)
    if not path.exists():
        return {"reinforced": 0, "reason": "no_store"}
    rows: list[dict[str, Any]] = []
    concept_rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        rows.append(row)
        if str(row.get("source_concept_id")) == str(source_concept_id):
            concept_rows.append(row)
    if len(concept_rows) < 1:
        return {"reinforced": 0, "reason": "concept_not_found"}
    selected, _ = select_and_reinforce(concept_rows, now, max_relations=max_relations, amount=amount)
    bumped = {_rid(r): r for r in selected}
    out = [bumped.get(_rid(r), r) for r in rows]
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for row in out:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, path)  # atomic
    return {"reinforced": len(selected), "relation_ids": [_rid(r) for r in selected]}
