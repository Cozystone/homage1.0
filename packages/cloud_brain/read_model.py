from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

from .chunk_index import build_chunk_index
from .planetary_topology import MAX_DIRECT_EDGES, planetize_graph_sample
from .status_cache import (
    DEFAULT_CLOUD_ROOT,
    INDEX_VERSION,
    fast_store_signature,
    load_graph_sample_cache,
    load_manifest,
    load_status_cache,
    read_json,
    semantic_store_paths,
    store_signature,
    utc_now_iso,
    write_graph_sample_cache,
    write_manifest,
    write_status_cache,
)


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000.0, 3)


def _candidate_pairs(count: int) -> int | str:
    pairs = count * max(0, count - 1) // 2
    return str(pairs) if pairs > 9_007_199_254_740_991 else pairs


SPHERICAL_LAYOUT_VERSION = "spherical_onion_v2"
SPHERICAL_NODE_RADII = (3.25, 4.45, 5.65, 6.85, 7.85)
SPHERICAL_NODE_LAYERS = ("core", "inner", "middle", "outer", "surface")


def _stable_hash_unit(seed: str, salt: str) -> float:
    import hashlib

    digest = hashlib.sha256(f"{salt}:{seed}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(0xFFFFFFFFFFFF)


def _spherical_onion_position(node_id: str, index: int, total: int) -> tuple[float, float, float, int, str]:
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    count = max(1, total)
    layer_index = int(_stable_hash_unit(node_id, "onion_layer") * len(SPHERICAL_NODE_RADII)) % len(SPHERICAL_NODE_RADII)
    radius = SPHERICAL_NODE_RADII[layer_index]
    z_unit = 1.0 - (2.0 * (index + 0.5) / count)
    z_unit = max(-0.985, min(0.985, z_unit + (_stable_hash_unit(node_id, "z_jitter") - 0.5) * 0.018))
    theta = (index * golden_angle + _stable_hash_unit(node_id, "theta_phase") * 0.31) % (math.pi * 2.0)
    radial = math.sqrt(max(0.0, 1.0 - z_unit * z_unit))
    return (
        round(math.cos(theta) * radial * radius, 5),
        round(z_unit * radius, 5),
        round(math.sin(theta) * radial * radius, 5),
        layer_index,
        SPHERICAL_NODE_LAYERS[layer_index],
    )


def _geometry_metrics(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    coordinates: list[tuple[float, float, float]] = []
    for node in nodes:
        try:
            x = float(node.get("x"))
            y = float(node.get("y"))
            z = float(node.get("z"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(x) and math.isfinite(y) and math.isfinite(z):
            coordinates.append((x, y, z))
    if not coordinates:
        return {
            "x_span": 0.0,
            "y_span": 0.0,
            "z_span": 0.0,
            "radius_min": 0.0,
            "radius_max": 0.0,
            "radius_span": 0.0,
            "spherical_uniformity_score": 0.0,
            "planar_collapse_score": 1.0,
        }
    xs = [value[0] for value in coordinates]
    ys = [value[1] for value in coordinates]
    zs = [value[2] for value in coordinates]
    radii = [math.sqrt((x * x) + (y * y) + (z * z)) for x, y, z in coordinates]
    spans = [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]
    max_span = max(spans) if spans else 0.0
    min_span = min(spans) if spans else 0.0
    radius_min = min(radii)
    radius_max = max(radii)
    radius_span = radius_max - radius_min
    axis_balance = min_span / max(max_span, 0.0001)
    radial_depth = min(1.0, radius_span / max(radius_max, 0.0001))
    uniformity = max(0.0, min(1.0, (axis_balance * 0.72) + (radial_depth * 0.28)))
    return {
        "x_span": round(spans[0], 5),
        "y_span": round(spans[1], 5),
        "z_span": round(spans[2], 5),
        "radius_min": round(radius_min, 5),
        "radius_max": round(radius_max, 5),
        "radius_span": round(radius_span, 5),
        "spherical_uniformity_score": round(uniformity, 5),
        "planar_collapse_score": round(max(0.0, min(1.0, 1.0 - axis_balance)), 5),
    }


def _apply_spherical_onion_layout(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = len(nodes)
    laid_out: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        node_id = str(node.get("id") or node.get("concept_id") or f"node:{index}")
        x, y, z, layer_index, layer_name = _spherical_onion_position(node_id, index, total)
        row = dict(node)
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        row.update(
            {
                "x": x,
                "y": y,
                "z": z,
                "radius": round(math.sqrt((x * x) + (y * y) + (z * z)), 5),
                "spherical_layout_version": SPHERICAL_LAYOUT_VERSION,
                "onion_layer": layer_name,
            }
        )
        row["metadata"] = {
            **metadata,
            "spherical_layout_version": SPHERICAL_LAYOUT_VERSION,
            "onion_layer": layer_name,
            "onion_layer_index": layer_index,
        }
        laid_out.append(row)
    return laid_out


def _read_latest_growth_run(root: str | Path) -> dict[str, Any] | None:
    paths = semantic_store_paths(root)
    runs_dir = paths["growth_runs"]
    if not runs_dir.exists():
        return None
    for path in sorted(runs_dir.glob("*.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True):
        payload = read_json(path, None)
        if isinstance(payload, dict):
            return {
                "run_id": payload.get("run_id"),
                "sentences_processed": payload.get("sentences_processed"),
                "concepts_created": payload.get("concepts_created"),
                "concepts_merged": payload.get("concepts_merged"),
                "relations_created": payload.get("relations_created"),
                "relations_strengthened": payload.get("relations_strengthened"),
                "evidence_added": payload.get("evidence_added"),
            }
    return None


def _read_feeder_state(root: str | Path) -> dict[str, Any]:
    payload = read_json(semantic_store_paths(root)["feeder_state"], {})
    return payload if isinstance(payload, dict) else {}


def _status_from_cache_payload(root: str | Path, cache: dict[str, Any], *, cache_hit: bool, started_at: float) -> dict[str, Any]:
    current_signature = fast_store_signature(root)
    cached_signature = cache.get("store_signature") if isinstance(cache.get("store_signature"), dict) else {}
    cached_signature = {
        key: cached_signature.get(key)
        for key in ("concepts", "relations", "evidence", "shard_index", "feeder_state")
    }
    paths = semantic_store_paths(root)
    shard_index = read_json(paths["shard_index"], {})
    if not isinstance(shard_index, dict):
        shard_index = {}
    feeder_state = _read_feeder_state(root)
    web_seed_active = bool(feeder_state.get("enabled"))
    stale = cached_signature != current_signature
    concept_count = int(cache.get("concepts") or cache.get("node_count") or 0)
    relation_count = int(cache.get("relations") or cache.get("edge_count") or 0)
    shard_concepts = int(shard_index.get("concepts_count") or 0)
    shard_relations = int(shard_index.get("relations_count") or 0)
    main_store_concepts = int(cache.get("main_store_concepts") or 0)
    main_store_relations = int(cache.get("main_store_relations") or 0)
    if shard_concepts > 0:
        concept_count = max(concept_count, shard_concepts + main_store_concepts, shard_concepts)
    if shard_relations > 0:
        relation_count = max(relation_count, shard_relations + main_store_relations, shard_relations)
    evidence_count = int(cache.get("evidence") or 0)
    semantic_ingested = int(feeder_state.get("semantic_ingested") or cache.get("web_seed_semantic_ingested") or 0)
    discovered_sources_added = int(feeder_state.get("discovered_sources_added") or 0)
    performance = dict(cache.get("performance") if isinstance(cache.get("performance"), dict) else {})
    performance.update(
        {
            "cache_hit": cache_hit,
            "status_cache_ms": _elapsed_ms(started_at),
            "sample_load_ms": 0.0,
            "chunk_load_ms": 0.0,
            "payload_build_ms": 0.0,
            "serialization_ms": 0.0,
            "total_ms": _elapsed_ms(started_at),
            "payload_bytes": int(cache.get("payload_bytes") or 0),
            "full_store_scan": False,
            "index_rebuild_during_request": False,
        }
    )
    return {
        **cache,
        "index_version": int(cache.get("index_version") or INDEX_VERSION),
        "proof_store_path": str(semantic_store_paths(root)["store"]),
        "store_path": str(semantic_store_paths(root)["store"]),
        "store_backend": str(cache.get("store_backend") or "local_semantic_proof_store"),
        "concepts": concept_count,
        "relations": relation_count,
        "evidence": evidence_count,
        "node_count": concept_count,
        "edge_count": relation_count,
        "implicit_candidate_pairs": _candidate_pairs(concept_count),
        "last_growth_run": cache.get("last_growth_run") or _read_latest_growth_run(root),
        "old_mirror_snapshot_used_as_live_cloud": False,
        "proof_store_only": True,
        "local_brain_write": False,
        "external_llm_used": False,
        "external_sllm_used": False,
        "global_cloud_claim": False,
        "self_growth_active": web_seed_active,
        "web_seed_feeder_active": web_seed_active,
        "web_seed_feeder_status": feeder_state.get("last_status") or ("listening" if web_seed_active else "disabled"),
        "web_seed_semantic_ingested": semantic_ingested,
        "web_seed_discovered_sources_added": discovered_sources_added,
        "sample_or_proof_data_visible": bool(concept_count or relation_count),
        "data_provenance_label": "semantic_cloud_read_model",
        "read_model_available": cache_hit,
        "read_model_stale": stale,
        "stale": stale,
        "graph_unavailable_reason": cache.get("graph_unavailable_reason"),
        "provenance_summary": {
            "semantic_cloud_proof_store": {
                "concepts": concept_count,
                "relations": relation_count,
                "evidence": evidence_count,
            },
            "manual_sample_ingest": {
                "concepts": concept_count,
                "relations": relation_count,
            },
            "autonomous_growth": {
                "concepts": semantic_ingested,
                "relations": int(feeder_state.get("semantic_relations_created") or 0),
                "frontier_sources_added": discovered_sources_added,
                "active": web_seed_active,
            },
            "mirror_snapshot": {
                "used_as_live_cloud": False,
            },
        },
        "performance": performance,
    }


def load_cloud_read_model_status(root: str | Path = DEFAULT_CLOUD_ROOT) -> dict[str, Any]:
    started_at = time.perf_counter()
    cache = load_status_cache(root)
    if isinstance(cache, dict):
        return _status_from_cache_payload(root, cache, cache_hit=True, started_at=started_at)
    return _status_from_cache_payload(
        root,
        {
            "concepts": 0,
            "relations": 0,
            "evidence": 0,
            "read_model_available": False,
            "read_model_stale": True,
            "graph_unavailable_reason": "cloud_read_model_missing",
            "created_at": utc_now_iso(),
            "store_signature": {},
        },
        cache_hit=False,
        started_at=started_at,
    )


def load_fast_graph_sample(
    root: str | Path = DEFAULT_CLOUD_ROOT,
    *,
    limit_nodes: int = 1200,
    limit_edges: int = 2400,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    status = load_cloud_read_model_status(root)
    sample_started_at = time.perf_counter()
    sample = load_graph_sample_cache(root)
    if not isinstance(sample, dict):
        return {
            "nodes": [],
            "edges": [],
            "bounded": False,
            "proof_store_only": True,
            "read_model_available": False,
            "graph_unavailable_reason": "cloud_graph_sample_index_missing",
            "counts": {
                "concepts": int(status.get("concepts") or 0),
                "relations": int(status.get("relations") or 0),
                "evidence": int(status.get("evidence") or 0),
                "topology": {},
            },
            "performance": {
                "cache_hit": False,
                "status_cache_ms": float((status.get("performance") or {}).get("status_cache_ms") or 0.0),
                "sample_load_ms": _elapsed_ms(sample_started_at),
                "chunk_load_ms": 0.0,
                "payload_build_ms": 0.0,
                "serialization_ms": 0.0,
                "total_ms": _elapsed_ms(started_at),
                "payload_bytes": 0,
                "full_store_scan": False,
                "index_rebuild_during_request": False,
            },
        }

    nodes = _apply_spherical_onion_layout(list(sample.get("nodes") or [])[: max(0, int(limit_nodes))])
    node_ids = {str(node.get("id") or node.get("concept_id")) for node in nodes}
    edges = [
        edge for edge in list(sample.get("edges") or [])
        if str(edge.get("source")) in node_ids and str(edge.get("target")) in node_ids
    ][: max(0, int(limit_edges))]
    counts = dict(sample.get("counts") if isinstance(sample.get("counts"), dict) else {})
    counts.setdefault("concepts", int(status.get("concepts") or 0))
    counts.setdefault("relations", int(status.get("relations") or 0))
    counts.setdefault("evidence", int(status.get("evidence") or 0))
    chunk_started_at = time.perf_counter()
    bounded_chunk_index = build_chunk_index(
        nodes,
        edges,
        logical_node_count=int(counts.get("concepts") or status.get("concepts") or len(nodes)),
        logical_relation_count=int(counts.get("relations") or status.get("relations") or len(edges)),
    )
    chunk_load_ms = _elapsed_ms(chunk_started_at)
    counts["chunks"] = bounded_chunk_index
    counts["spherical_layout"] = {
        "layout_version": SPHERICAL_LAYOUT_VERSION,
        "geometry_metrics": _geometry_metrics(nodes),
        "onion_layers": list(SPHERICAL_NODE_LAYERS),
        "real_materialized_nodes": len(nodes),
        "density_chunks_are_semantic_nodes": False,
    }
    performance = dict(sample.get("performance") if isinstance(sample.get("performance"), dict) else {})
    paths = semantic_store_paths(root)
    sample_path = paths["graph_sample"] if paths["graph_sample"].exists() else paths["legacy_graph_sample"]
    try:
        payload_bytes = int(sample_path.stat().st_size)
    except FileNotFoundError:
        payload_bytes = int(sample.get("payload_bytes") or 0)
    performance.update(
        {
            "cache_hit": True,
            "status_cache_ms": float((status.get("performance") or {}).get("status_cache_ms") or 0.0),
            "sample_load_ms": _elapsed_ms(sample_started_at),
            "chunk_load_ms": chunk_load_ms,
            "payload_build_ms": 0.0,
            "serialization_ms": 0.0,
            "total_ms": _elapsed_ms(started_at),
            "payload_bytes": payload_bytes,
            "full_store_scan": False,
            "index_rebuild_during_request": False,
        }
    )
    return {
        **sample,
        "nodes": nodes,
        "edges": edges,
        "bounded": bool(sample.get("bounded")) or len(list(sample.get("nodes") or [])) > len(nodes) or len(list(sample.get("edges") or [])) > len(edges),
        "proof_store_only": True,
        "read_model_available": True,
        "read_model_stale": bool(status.get("read_model_stale") or status.get("stale")),
        "counts": counts,
        "performance": performance,
    }


def _read_evidence_count(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _build_sample_from_rows(
    concepts: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    *,
    limit_nodes: int,
    limit_edges: int,
) -> dict[str, Any]:
    def sort_key(row: dict[str, Any]) -> tuple[str, str]:
        updated = str(row.get("updated_at") or row.get("created_at") or "")
        return updated, str(row.get("concept_id") or row.get("canonical_name") or "")

    recent_concepts = sorted(concepts, key=sort_key, reverse=True)
    if len(recent_concepts) > limit_nodes:
        recent_quota = max(1, int(limit_nodes * 0.78))
        anchor_quota = max(0, limit_nodes - recent_quota)
        anchor_concepts = concepts[:anchor_quota]
        seen_ids = {str(row.get("concept_id")) for row in anchor_concepts}
        selected = anchor_concepts + [
            row for row in recent_concepts
            if str(row.get("concept_id")) not in seen_ids
        ][:recent_quota]
    else:
        selected = recent_concepts

    nodes = [
        {
            "id": row["concept_id"],
            "label": row.get("canonical_name") or row["concept_id"],
            "concept_id": row["concept_id"],
            "aliases": row.get("aliases", []),
            "language_labels": row.get("language_labels", {}),
            "trust": row.get("trust", 0.5),
            "confidence": row.get("confidence", 0.5),
            "seen_count": row.get("seen_count", 1),
            "source_scope": "cloud",
            "proof_store_only": True,
            "provenance_type": (row.get("metadata", {}).get("provenance_type") if isinstance(row.get("metadata"), dict) else None) or "manual_sample_ingest",
            "source_run_id": row.get("metadata", {}).get("run_id") if isinstance(row.get("metadata"), dict) else None,
            "source_text_hash": (row.get("source_hashes") or [None])[0] if isinstance(row.get("source_hashes"), list) else None,
            "source_label": "Semantic Cloud proof store",
            "is_demo_sample": True,
            "is_autonomous_growth": False,
            "local_brain_write": False,
        }
        for row in selected[:limit_nodes]
        if row.get("concept_id")
    ]
    node_ids = {str(node["id"]) for node in nodes}
    edges = [
        {
            "id": row["relation_id"],
            "source": row["source_concept_id"],
            "target": row["target_concept_id"],
            # relations are stored with 'relation_type' (semantic store) — 'relation'
            # was a KeyError crash when a row lacked the legacy alias. Accept both.
            "relation": row.get("relation") or row.get("relation_type") or "related_to",
            "weight": row.get("weight", 0.5),
            "confidence": row.get("confidence", 0.5),
            "seen_count": row.get("seen_count", 1),
            "source_scope": "cloud",
            "proof_store_only": True,
            "provenance_type": (row.get("metadata", {}).get("provenance_type") if isinstance(row.get("metadata"), dict) else None) or "manual_sample_ingest",
            "source_run_id": row.get("metadata", {}).get("run_id") if isinstance(row.get("metadata"), dict) else None,
            "source_text_hash": (row.get("source_hashes") or [None])[0] if isinstance(row.get("source_hashes"), list) else None,
            "source_label": "Semantic Cloud proof store",
            "is_demo_sample": True,
            "is_autonomous_growth": False,
            "local_brain_write": False,
        }
        for row in relations
        if row.get("relation_id")
        and row.get("source_concept_id") in node_ids
        and row.get("target_concept_id") in node_ids
    ][:limit_edges]
    planetized = planetize_graph_sample(nodes, edges, max_direct_edges=MAX_DIRECT_EDGES)
    planetized_nodes = _apply_spherical_onion_layout(list(planetized.get("nodes") or []))
    return {
        "nodes": planetized_nodes,
        "edges": list(planetized.get("edges") or [])[:limit_edges],
        "topology": {
            **(planetized.get("topology") or {}),
            "spherical_layout_version": SPHERICAL_LAYOUT_VERSION,
            "geometry_metrics": _geometry_metrics(planetized_nodes),
            "onion_layers": list(SPHERICAL_NODE_LAYERS),
        },
    }


def build_cloud_read_model(
    root: str | Path = DEFAULT_CLOUD_ROOT,
    *,
    limit_nodes: int = 1200,
    limit_edges: int = 2400,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    from .semantic_store import SemanticCloudStore

    store = SemanticCloudStore(root)
    shard_concepts, shard_relations = store.load_recent_growth_shards(limit_files=12)
    main_concepts = list(store.load_concepts().values())
    main_relations = list(store.load_relations().values())
    concepts = shard_concepts + [row for row in main_concepts if isinstance(row, dict)]
    relations = shard_relations + [row for row in main_relations if isinstance(row, dict)]
    sample_started_at = time.perf_counter()
    sample = _build_sample_from_rows(concepts, relations, limit_nodes=limit_nodes, limit_edges=limit_edges)
    current_signature = store_signature(root)
    paths = semantic_store_paths(root)
    evidence_count = _read_evidence_count(paths["evidence"])
    shard_index = read_json(paths["shard_index"], {})
    if not isinstance(shard_index, dict):
        shard_index = {}
    logical_concepts = int(shard_index.get("concepts_count") or 0) + len(main_concepts)
    logical_relations = int(shard_index.get("relations_count") or 0) + len(main_relations)
    logical_concepts = max(logical_concepts, len(concepts))
    logical_relations = max(logical_relations, len(relations))
    chunk_started_at = time.perf_counter()
    chunk_index = build_chunk_index(
        sample["nodes"],
        sample["edges"],
        logical_node_count=logical_concepts,
        logical_relation_count=logical_relations,
    )
    status_payload = {
        "index_version": INDEX_VERSION,
        "created_at": utc_now_iso(),
        "store_signature": current_signature,
        "proof_store_path": str(paths["store"]),
        "store_path": str(paths["store"]),
        "store_backend": "local_semantic_proof_store",
        "concepts": logical_concepts,
        "relations": logical_relations,
        "evidence": evidence_count,
        "shard_concepts": int(shard_index.get("concepts_count") or 0),
        "shard_relations": int(shard_index.get("relations_count") or 0),
        "main_store_concepts": len(main_concepts),
        "main_store_relations": len(main_relations),
        "count_source": "shard_index_plus_main_store",
        "node_count": logical_concepts,
        "edge_count": logical_relations,
        "last_growth_run": _read_latest_growth_run(root),
        "old_mirror_snapshot_used_as_live_cloud": False,
        "proof_store_only": True,
        "read_model_available": True,
        "read_model_stale": False,
        "sample_or_proof_data_visible": bool(concepts or relations),
        "performance": {
            "cache_hit": False,
            "status_cache_ms": 0.0,
            "sample_load_ms": round((time.perf_counter() - sample_started_at) * 1000.0, 3),
            "chunk_load_ms": round((time.perf_counter() - chunk_started_at) * 1000.0, 3),
            "payload_build_ms": _elapsed_ms(started_at),
            "serialization_ms": 0.0,
            "total_ms": _elapsed_ms(started_at),
            "payload_bytes": 0,
            "full_store_scan": True,
            "index_rebuild_during_request": False,
        },
    }
    sample_payload = {
        "index_version": INDEX_VERSION,
        "created_at": utc_now_iso(),
        "store_signature": current_signature,
        "nodes": sample["nodes"],
        "edges": sample["edges"],
        "bounded": len(concepts) > limit_nodes or len(relations) > limit_edges,
        "proof_store_only": True,
        "read_model_available": True,
        "compression_used": False,
        "semantic_aggregate_nodes_used": False,
        "counts": {
            "concepts": logical_concepts,
            "relations": logical_relations,
            "evidence": evidence_count,
            "topology": sample["topology"],
            "chunks": chunk_index,
            "spherical_layout": {
                "layout_version": SPHERICAL_LAYOUT_VERSION,
                "geometry_metrics": _geometry_metrics(sample["nodes"]),
                "onion_layers": list(SPHERICAL_NODE_LAYERS),
                "real_materialized_nodes": len(sample["nodes"]),
                "density_chunks_are_semantic_nodes": False,
            },
        },
        "performance": {
            **status_payload["performance"],
            "full_store_scan": True,
        },
    }
    manifest = {
        "index_version": INDEX_VERSION,
        "created_at": utc_now_iso(),
        "store_signature": current_signature,
        "status_cache": paths["status_cache"].name,
        "graph_sample": paths["graph_sample"].name,
        "sample_nodes": len(sample_payload["nodes"]),
        "sample_edges": len(sample_payload["edges"]),
        "logical_nodes": logical_concepts,
        "logical_edges": logical_relations,
        "full_store_scan": True,
        "request_time_rebuild": False,
    }
    write_status_cache(root, status_payload)
    write_graph_sample_cache(root, sample_payload)
    write_manifest(root, manifest)
    return {
        "status": load_cloud_read_model_status(root),
        "sample": load_fast_graph_sample(root, limit_nodes=limit_nodes, limit_edges=limit_edges),
        "manifest": load_manifest(root) or manifest,
        "rebuilt": True,
        "performance": {
            "total_ms": _elapsed_ms(started_at),
            "full_store_scan": True,
            "index_rebuild_during_request": False,
        },
    }
