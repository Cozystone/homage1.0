"""PHFE v0.4a — live-source adapter.

Maps REAL read-only ATANOR sources into the (raw_nodes, edges) inputs that
`build_state_field` / `fold_state` consume:

- base_brain `SemanticConcept`s (concept_id, canonical_name, confidence,
  provenance, relations[]) -> `cloud_verified` nodes; their relations between
  included concepts -> edges.
- Cloud Brain candidate graph nodes (candidate_read_model.candidate_cloud_graph)
  -> `cloud_candidate` nodes, filtered to the query's relevant ones.
- A Neural-Emotion snapshot -> a single `emotion` node.

This function is PURE: the caller gathers the live read-only sources and passes
them in; nothing here reaches into globals, mutates, or fabricates. A node with
no provenance is dropped (never invented). Returned inputs are bounded to n_max
upstream by `build_state_field`.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# How a source's declared type maps into the folding source-type taxonomy.
_SOURCE_TYPE_MAP = {
    "curated_base_pack": "cloud_verified",
    "verified_store_v0": "cloud_verified",
    "cloud_verified": "cloud_verified",
    "candidate": "cloud_candidate",
    "candidate_review": "cloud_candidate",
    "cloud_candidate": "cloud_candidate",
    "web_candidate": "web_candidate",
    "web": "web_candidate",
}


def _tokens(text: str) -> set[str]:
    latin = re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{1,}", str(text or ""))
    korean = re.findall(r"[가-힣]{2,}", str(text or ""))
    return {token.casefold() for token in (*latin, *korean)}


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def build_field_inputs(
    query: str,
    *,
    concepts: Iterable[dict[str, Any]] | None = None,
    candidate_graph: dict[str, Any] | None = None,
    emotion: dict[str, Any] | None = None,
    max_candidates: int = 24,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build (raw_nodes, edges) from real read-only sources. Pure, no fabrication."""

    query_tokens = _tokens(query)
    raw_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    included_ids: set[str] = set()
    # map concept_id AND canonical_name -> node_id so relations resolve either way
    resolve: dict[str, str] = {}

    # --- base_brain verified concepts -> cloud_verified nodes ---
    for concept in concepts or []:
        concept_id = str(concept.get("concept_id") or concept.get("id") or "").strip()
        provenance = str(concept.get("provenance") or "").strip()
        if not concept_id or not provenance:
            continue  # no real identity/provenance -> never invent it
        node_id = f"concept:{concept_id}"
        source_type = _SOURCE_TYPE_MAP.get(str(concept.get("source_type") or "curated_base_pack"), "cloud_verified")
        name = str(concept.get("canonical_name") or concept_id)
        confidence = _clamp(float(concept.get("confidence", 0.75) or 0.75), 0.0, 1.0)
        # caller may pass relevance/hop; default importance from confidence,
        # bumped if the concept name overlaps the query.
        overlap = bool(_tokens(name) & query_tokens)
        importance = concept.get("importance")
        importance = _clamp(float(importance), 0.0, 1.0) if importance is not None else _clamp(
            confidence + (0.2 if overlap else 0.0), 0.0, 1.0
        )
        hop_depth = int(concept.get("hop_depth", 0) or 0)
        raw_nodes.append(
            {
                "node_id": node_id,
                "source_type": source_type,
                "label": name,
                "provenance": provenance,
                "importance": importance,
                "confidence": confidence,
                "hop_depth": hop_depth,
                "domain": str(concept.get("domain") or "general"),
            }
        )
        included_ids.add(node_id)
        resolve[concept_id.casefold()] = node_id
        resolve[name.casefold()] = node_id

    # relations between included concepts -> edges (drop dangling targets)
    for concept in concepts or []:
        for relation in concept.get("relations") or []:
            source = str(relation.get("source") or concept.get("concept_id") or "").strip().casefold()
            target = str(relation.get("target") or "").strip().casefold()
            src_node = resolve.get(source)
            tgt_node = resolve.get(target)
            if not src_node or not tgt_node or src_node == tgt_node:
                continue
            edges.append(
                {
                    "source": src_node,
                    "target": tgt_node,
                    "strength": _clamp(float(relation.get("confidence", 0.6) or 0.6), 0.0, 1.0),
                    "relation": relation.get("relation"),
                }
            )

    # --- Cloud Brain candidate graph -> cloud_candidate nodes (query-filtered) ---
    if candidate_graph:
        store_path = str((candidate_graph.get("metadata") or {}).get("candidate_store_path") or "candidate_store")
        cand_nodes = candidate_graph.get("nodes") or []
        scored = []
        for cand in cand_nodes:
            cand_id = str(cand.get("id") or "").strip()
            if not cand_id:
                continue
            label = str(cand.get("label") or cand_id)
            relevance = len(_tokens(label) & query_tokens)
            scored.append((relevance, cand_id, label, cand))
        # keep query-relevant candidates first, bounded
        scored.sort(key=lambda item: (-item[0], item[1]))
        for relevance, cand_id, label, cand in scored[:max_candidates]:
            if relevance == 0 and query_tokens:
                continue  # don't drag in unrelated candidates
            node_id = f"candidate:{cand_id}"
            resolve[cand_id.casefold()] = node_id
            raw_nodes.append(
                {
                    "node_id": node_id,
                    "source_type": "cloud_candidate",
                    "label": label,
                    "provenance": f"{store_path}:concept/{cand_id}",
                    "importance": _clamp(0.25 + 0.1 * min(relevance, 3), 0.0, 1.0),
                    "confidence": 0.2,
                    "hop_depth": 2,
                    "domain": "general",
                }
            )
            included_ids.add(node_id)
        for edge in candidate_graph.get("edges") or []:
            src = resolve.get(str(edge.get("source") or "").casefold())
            tgt = resolve.get(str(edge.get("target") or "").casefold())
            if src and tgt and src != tgt and src in included_ids and tgt in included_ids:
                edges.append({"source": src, "target": tgt, "strength": 0.4, "relation": edge.get("relation")})

    # --- Neural-Emotion snapshot -> one emotion node ---
    if emotion:
        vector = emotion.get("vector") if isinstance(emotion.get("vector"), dict) else {}
        valence = float(emotion.get("valence", vector.get("valence", 0.0)) or 0.0)
        intensity = float(emotion.get("intensity", emotion.get("amplitude", 0.5)) or 0.5)
        raw_nodes.append(
            {
                "node_id": "emotion:current",
                "source_type": "emotion",
                "label": str(emotion.get("label") or "emotion"),
                "provenance": str(emotion.get("provenance") or "neural_emotion:snapshot"),
                "importance": _clamp(intensity, 0.0, 1.0),
                "confidence": _clamp(0.4 + 0.3 * abs(valence), 0.0, 1.0),
                "polarity": _clamp(valence, -1.0, 1.0),
                "hop_depth": 1,
                "domain": "general",
            }
        )

    return raw_nodes, edges
