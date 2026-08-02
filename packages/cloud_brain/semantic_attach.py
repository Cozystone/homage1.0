from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .cloud_node_attachment import DEFAULT_ATTACHMENT_ROOT
from .semantic_dedupe import normalize_concept_name
from .semantic_store import (
    DEFAULT_SEMANTIC_CLOUD_ROOT,
    SEMANTIC_STORE_TRUST_STATE,
    SEMANTIC_STORE_VERIFICATION_STATE,
    SemanticCloudStore,
)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _score_query(query: str, concept: dict[str, Any]) -> float:
    query_norm = normalize_concept_name(query)
    names = [concept.get("canonical_name", ""), *(concept.get("aliases") or [])]
    score = 0.0
    for name in names:
        normalized = normalize_concept_name(str(name))
        if normalized and normalized in query_norm:
            score += 2.0
        if normalized and query_norm in normalized:
            score += 1.0
    return score + min(float(concept.get("seen_count") or 0) * 0.05, 0.5)


def attach_semantic_cloud_for_query(
    query: str,
    limit: int = 8,
    *,
    cloud_root: str | Path = DEFAULT_SEMANTIC_CLOUD_ROOT,
    attachment_root: str | Path = DEFAULT_ATTACHMENT_ROOT,
) -> dict[str, Any]:
    store = SemanticCloudStore(cloud_root)
    concepts = list(store.load_concepts().values())
    relations = list(store.load_relations().values())
    ranked = sorted(concepts, key=lambda item: _score_query(query, item), reverse=True)
    selected = [item for item in ranked if _score_query(query, item) > 0][:limit] or ranked[:limit]
    selected_ids = {item["concept_id"] for item in selected}
    selected_relations = [
        row for row in relations
        if row.get("source_concept_id") in selected_ids or row.get("target_concept_id") in selected_ids
    ][: max(limit * 2, 1)]
    for row in selected_relations:
        selected_ids.add(str(row.get("source_concept_id")))
        selected_ids.add(str(row.get("target_concept_id")))
    concept_map = {item["concept_id"]: item for item in concepts if item["concept_id"] in selected_ids}
    bundle_id = f"cnb_semantic_{hashlib.sha256((query + str(time.time())).encode('utf-8')).hexdigest()[:18]}"
    nodes = [
        {
            "id": f"scn:{concept_id}",
            "cloud_node_id": f"scn:{concept_id}",
            "label": concept.get("canonical_name") or concept_id,
            "concept_id": concept_id,
            "source_scope": "cloud",
            "source_type": "semantic_cloud",
            "visual_layer": "cloud_attached",
            "temporary_attachment": True,
            "trust_state": SEMANTIC_STORE_TRUST_STATE,
            "verification_state": SEMANTIC_STORE_VERIFICATION_STATE,
            "caller_metadata_authoritative": False,
            "independent_source_attestation": False,
            "authoritative_for_answer": False,
            "writes_to_local_brain": False,
        }
        for concept_id, concept in concept_map.items()
    ]
    edges = [
        {
            "id": f"sce:{row['relation_id']}",
            "cloud_edge_id": f"sce:{row['relation_id']}",
            "source": f"scn:{row['source_concept_id']}",
            "target": f"scn:{row['target_concept_id']}",
            "relation": row.get("relation") or "related_to",
            "source_type": "semantic_cloud",
            "visual_layer": "cloud_attached",
            "temporary_attachment": True,
            "trust_state": SEMANTIC_STORE_TRUST_STATE,
            "verification_state": SEMANTIC_STORE_VERIFICATION_STATE,
            "caller_metadata_authoritative": False,
            "independent_source_attestation": False,
            "authoritative_for_answer": False,
            "writes_to_local_brain": False,
        }
        for row in selected_relations
        if row.get("source_concept_id") in concept_map and row.get("target_concept_id") in concept_map
    ]
    root = Path(attachment_root)
    root.mkdir(parents=True, exist_ok=True)
    bundle = {
        "bundle_id": bundle_id,
        "query": query,
        "source": "semantic_cloud_proof_store",
        "privacy_scope": "public",
        "writes_to_local_brain": False,
        "seed_anchor_nodes": [],
        "nodes": nodes,
        "edges": edges,
        "attached": True,
        "attached_at": _now_iso(),
        "ttl_seconds": 1800,
        "expires_at_epoch": int(time.time()) + 1800,
        "external_llm_used": False,
        "external_sllm_used": False,
        "independent_source_attestation": False,
        "authoritative_for_answer": False,
    }
    (root / f"{bundle_id}.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "query": query,
        "attached_nodes": nodes,
        "attached_edges": edges,
        "working_memory_updated": True,
        "local_brain_write": False,
        "temporary": True,
        "cloud_attached_counts_as_local": False,
        "independent_source_attestation": False,
        "authoritative_for_answer": False,
        "bundle_id": bundle_id,
    }
