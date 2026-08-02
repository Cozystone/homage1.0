from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from packages.base_brain.pack_loader import get_semantic_context, load_base_brain_pack
from packages.base_brain.seed_extension import build_seed_graph_v2
from packages.cloud_brain.cloud_node_attachment import graph_overlay
from packages.cloud_brain.contributor_node import contributor_status
from packages.cloud_brain.read_model import load_cloud_read_model_status, load_fast_graph_sample
from packages.cloud_brain.semantic_store import (
    SEMANTIC_STORE_TRUST_STATE,
    SEMANTIC_STORE_VERIFICATION_STATE,
)
from packages.graph_hub.attachment import attachment_graph_payload, list_active_attachments

from .models import LayerResult, RenderableBrainEdge, RenderableBrainNode


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data"
CLOUD_ROOT = DATA_ROOT / "cloud_brain"
BASE_BRAIN_PACK_PATH = DATA_ROOT / "base_brain" / "packs" / "atanor_base_brain_v0.json"
SEED_GRAPH_PATH = DATA_ROOT / "base_brain" / "seed" / "seed_graph_v2.json"

def _stable_position(seed: str, radius: float = 1.0) -> tuple[float, float, float]:
    total = sum(ord(char) for char in seed)
    theta = (total % 360) * math.pi / 180.0
    phi = (((total // 7) % 180) - 90) * math.pi / 180.0
    return (
        round(radius * math.cos(phi) * math.cos(theta), 5),
        round(radius * math.sin(phi), 5),
        round(radius * math.cos(phi) * math.sin(theta), 5),
    )


def _bounded(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    return items[:limit]


def _node(
    node_id: str,
    label: str,
    layer: str,
    source_scope: str,
    *,
    persistent: bool,
    temporary: bool,
    kind: str = "concept",
    radius: float = 1.0,
    trust_state: str = "unknown",
    verification_state: str = "unknown",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    x, y, z = _stable_position(node_id, radius=radius)
    return RenderableBrainNode(
        id=node_id,
        label=label,
        layer=layer,
        source_scope=source_scope,
        persistent=persistent,
        temporary=temporary,
        x=x,
        y=y,
        z=z,
        kind=kind,
        trust_state=trust_state,
        verification_state=verification_state,
        metadata=metadata or {},
    ).to_dict()


def _edge(
    edge_id: str,
    source: str,
    target: str,
    relation: str,
    layer: str,
    source_scope: str,
    *,
    persistent: bool,
    temporary: bool,
    weight: float = 1.0,
    trust_state: str = "unknown",
    verification_state: str = "unknown",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return RenderableBrainEdge(
        id=edge_id,
        source=source,
        target=target,
        relation=relation,
        layer=layer,
        source_scope=source_scope,
        persistent=persistent,
        temporary=temporary,
        weight=weight,
        trust_state=trust_state,
        verification_state=verification_state,
        metadata=metadata or {},
    ).to_dict()


def _apply_explicit_position(node: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    try:
        if row.get("x") is not None and row.get("y") is not None and row.get("z") is not None:
            node["x"] = float(row["x"])
            node["y"] = float(row["y"])
            node["z"] = float(row["z"])
    except (TypeError, ValueError):
        pass
    return node


def _layer_missing(layer: str, reason: str, *, stats: dict[str, Any] | None = None) -> LayerResult:
    return LayerResult(layer=layer, available=False, missing_reason=reason, stats=stats or {})


def materialize_local_user_graph(max_nodes: int, max_edges: int) -> LayerResult:
    local_initialized = os.getenv("ATANOR_LOCAL_BRAIN_INITIALIZED", "").strip().lower() in {"1", "true", "yes", "on"}
    if not local_initialized:
        return LayerResult(
            layer="local_user",
            available=True,
            nodes=[],
            edges=[],
            stats={
                "local_brain_initialized": False,
                "local_total_nodes": 0,
                "local_total_edges": 0,
                "cloud_mirror_excluded_from_local_brain": True,
            },
        )
    try:
        from app.services.alpha_services import alpha_service
    except Exception as exc:
        return _layer_missing("local_user", f"local_alpha_service_unavailable: {exc}", stats={"local_brain_initialized": True})
    graph = alpha_service.memory_graph(limit=max(max_nodes, 1))
    nodes = [
        _node(
            str(row.get("id") or row.get("node_hash") or f"local:{index}"),
            str(row.get("label") or row.get("name") or row.get("id") or f"local {index}"),
            "local_user",
            "local",
            persistent=True,
            temporary=False,
            kind=str(row.get("type") or "local_memory"),
            radius=1.0,
            trust_state=str(row.get("trust_state") or "local"),
            verification_state=str(row.get("verification_state") or "local_persistent"),
            metadata={"raw_layer": row.get("layer")},
        )
        for index, row in enumerate(graph.get("nodes") or [])
    ]
    edges = [
        _edge(
            str(row.get("id") or f"local-edge:{index}"),
            str(row.get("source")),
            str(row.get("target")),
            str(row.get("relation") or row.get("predicate") or "related_to"),
            "local_user",
            "local",
            persistent=True,
            temporary=False,
            weight=float(row.get("weight") or 1.0),
        )
        for index, row in enumerate(graph.get("edges") or [])
        if row.get("source") and row.get("target")
    ]
    return LayerResult(
        layer="local_user",
        available=True,
        nodes=_bounded(nodes, max_nodes),
        edges=_bounded(edges, max_edges),
        stats={"local_brain_initialized": True, "local_total_nodes": len(nodes), "local_total_edges": len(edges)},
        partial=len(nodes) > max_nodes or len(edges) > max_edges,
    )


def materialize_local_base_graph(max_nodes: int, max_edges: int, query: str | None = None) -> LayerResult:
    try:
        pack = load_base_brain_pack(BASE_BRAIN_PACK_PATH)
    except Exception as exc:
        return _layer_missing("local_base", f"base_brain_pack_unavailable: {exc}")
    concepts = get_semantic_context(query or "ATANOR local brain semantic graph", pack, limit=max_nodes) if query else list(pack.semantic_graph.get("concepts") or [])[:max_nodes]
    selected_ids = {str(concept.get("concept_id")) for concept in concepts}
    nodes = [
        _node(
            f"base:{concept.get('concept_id')}",
            str(concept.get("canonical_name") or concept.get("concept_id")),
            "local_base",
            "base",
            persistent=True,
            temporary=False,
            kind="base_concept",
            radius=0.78,
            trust_state="curated_base",
            verification_state="base_pack_v0",
            metadata={"confidence": concept.get("confidence"), "labels": concept.get("labels", {})},
        )
        for concept in concepts
    ]
    edges: list[dict[str, Any]] = []
    for concept in concepts:
        source_id = f"base:{concept.get('concept_id')}"
        for relation in concept.get("relations") or []:
            target = str(relation.get("target") or "")
            if target not in selected_ids:
                continue
            edges.append(
                _edge(
                    f"base-edge:{concept.get('concept_id')}:{relation.get('relation')}:{target}",
                    source_id,
                    f"base:{target}",
                    str(relation.get("relation") or "related_to"),
                    "local_base",
                    "base",
                    persistent=True,
                    temporary=False,
                    weight=float(relation.get("confidence") or 0.75),
                    trust_state="curated_base",
                    verification_state="base_pack_v0",
                )
            )
    return LayerResult(
        layer="local_base",
        available=True,
        nodes=_bounded(nodes, max_nodes),
        edges=_bounded(edges, max_edges),
        stats={"base_brain_nodes": len(nodes), "base_brain_edges": len(edges), "pack_id": pack.pack_id},
        partial=len(nodes) > max_nodes or len(edges) > max_edges,
    )


def materialize_seed_graph(max_nodes: int, max_edges: int) -> LayerResult:
    try:
        if SEED_GRAPH_PATH.exists():
            seed = json.loads(SEED_GRAPH_PATH.read_text(encoding="utf-8"))
        else:
            seed = build_seed_graph_v2()
    except Exception as exc:
        return _layer_missing("seed", f"seed_graph_unavailable: {exc}")
    groups = [
        ("relation", seed.get("relation_primitives") or []),
        ("reasoning", seed.get("reasoning_primitives") or []),
        ("intent", seed.get("answer_intent_primitives") or []),
        ("discourse", seed.get("discourse_anchors") or []),
        ("grounding", seed.get("uncertainty_grounding_primitives") or []),
    ]
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    root_id = "seed:seed_graph_v2"
    nodes.append(_node(root_id, "Seed Graph v2", "seed", "seed", persistent=True, temporary=False, kind="seed_root", radius=0.52, trust_state="curated_seed", verification_state="seed_graph_v2"))
    for group_name, values in groups:
        group_id = f"seed:{group_name}"
        nodes.append(_node(group_id, group_name, "seed", "seed", persistent=True, temporary=False, kind="seed_group", radius=0.58, trust_state="curated_seed", verification_state="seed_graph_v2"))
        edges.append(_edge(f"seed-edge:root:{group_name}", root_id, group_id, "defines_group", "seed", "seed", persistent=True, temporary=False))
        for value in values:
            node_id = f"seed:{group_name}:{value}"
            nodes.append(_node(node_id, str(value), "seed", "seed", persistent=True, temporary=False, kind=f"seed_{group_name}", radius=0.64, trust_state="curated_seed", verification_state="seed_graph_v2"))
            edges.append(_edge(f"seed-edge:{group_name}:{value}", group_id, node_id, "defines", "seed", "seed", persistent=True, temporary=False))
    return LayerResult(
        layer="seed",
        available=True,
        nodes=_bounded(nodes, max_nodes),
        edges=_bounded(edges, max_edges),
        stats={"seed_nodes": len(nodes), "seed_edges": len(edges)},
        partial=len(nodes) > max_nodes or len(edges) > max_edges,
    )


def materialize_working_memory_local(max_nodes: int, max_edges: int) -> LayerResult:
    overlay = graph_overlay()
    anchors = [
        _node(
            str(row.get("id") or row.get("seed_anchor_id") or f"seed-anchor:{index}"),
            str(row.get("label") or row.get("concept_id") or f"seed anchor {index}"),
            "working_memory_local",
            "seed",
            persistent=False,
            temporary=True,
            kind="seed_anchor_overlay",
            radius=0.7,
            trust_state=str(row.get("trust_state") or "seed_anchor"),
            verification_state=str(row.get("verification_state") or "anchor_only"),
            metadata={"writes_to_local_brain": False},
        )
        for index, row in enumerate(overlay.get("seed_anchor_nodes") or [])
    ]
    return LayerResult(
        layer="working_memory_local",
        available=True,
        nodes=_bounded(anchors, max_nodes),
        edges=[],
        stats={
            "working_memory_active": bool(overlay.get("working_memory_overlay", {}).get("active")),
            "seed_anchor_nodes": len(anchors),
            "local_write": False,
            "cloud_attached_counts_as_local": False,
        },
        partial=len(anchors) > max_nodes,
    )


def materialize_local_memory_candidates() -> LayerResult:
    return _layer_missing(
        "local_memory_candidate",
        "no_local_memory_candidate_store_available",
        stats={"local_write": False, "promoted_candidates": 0},
    )


def materialize_semantic_cloud_graph(max_nodes: int, max_edges: int) -> LayerResult:
    semantic_status = load_cloud_read_model_status(CLOUD_ROOT)
    semantic_graph = load_fast_graph_sample(CLOUD_ROOT, limit_nodes=max_nodes, limit_edges=max_edges)
    semantic_counts = semantic_graph.get("counts") if isinstance(semantic_graph.get("counts"), dict) else {}
    chunk_index = semantic_counts.get("chunks") if isinstance(semantic_counts.get("chunks"), dict) else {}
    density_chunks = list(chunk_index.get("density_chunks") or chunk_index.get("chunks") or [])
    if semantic_graph["nodes"] or semantic_graph["edges"]:
        nodes = []
        for index, row in enumerate(semantic_graph["nodes"]):
            row_metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            nodes.append(_apply_explicit_position(
                _node(
                    str(row.get("id") or row.get("concept_id") or f"semantic-cloud:{index}"),
                    str(row.get("label") or row.get("concept_id") or f"semantic concept {index}"),
                    "semantic_cloud",
                    "cloud",
                    persistent=True,
                    temporary=False,
                    kind=str(row_metadata.get("topology_role") or "semantic_cloud_concept"),
                    radius=1.18,
                    # The semantic store accepts public caller text and source
                    # metadata.  Store presence proves persistence, not source
                    # truth, so materialization must not mint verified authority.
                    trust_state=SEMANTIC_STORE_TRUST_STATE,
                    verification_state=SEMANTIC_STORE_VERIFICATION_STATE,
                    metadata={
                        **row_metadata,
                        "concept_id": row.get("concept_id"),
                        "seen_count": row.get("seen_count"),
                        "proof_store_only": True,
                        "caller_metadata_authoritative": False,
                        "independent_source_attestation": False,
                        "provenance_type": row.get("provenance_type") or row_metadata.get("provenance_type") or "manual_sample_ingest",
                        "source_run_id": row.get("source_run_id"),
                        "source_text_hash": row.get("source_text_hash"),
                        "source_label": row.get("source_label") or "Semantic Cloud proof store",
                        "is_demo_sample": bool(row.get("is_demo_sample", True)),
                        "is_autonomous_growth": bool(row.get("is_autonomous_growth", False)),
                        "local_brain_write": False,
                    },
                ),
                row,
            ))
        edges = [
            _edge(
                str(row.get("id") or f"semantic-cloud-edge:{index}"),
                str(row.get("source")),
                str(row.get("target")),
                str(row.get("relation") or "related_to"),
                "semantic_cloud",
                "cloud",
                persistent=True,
                temporary=False,
                weight=float(row.get("weight") or 0.5),
                trust_state=SEMANTIC_STORE_TRUST_STATE,
                verification_state=SEMANTIC_STORE_VERIFICATION_STATE,
                metadata={
                    **(row.get("metadata") if isinstance(row.get("metadata"), dict) else {}),
                    "seen_count": row.get("seen_count"),
                    "proof_store_only": True,
                    "caller_metadata_authoritative": False,
                    "independent_source_attestation": False,
                    "old_mirror_snapshot_used": False,
                    "provenance_type": row.get("provenance_type") or "manual_sample_ingest",
                    "source_run_id": row.get("source_run_id"),
                    "source_text_hash": row.get("source_text_hash"),
                    "source_label": row.get("source_label") or "Semantic Cloud proof store",
                    "is_demo_sample": bool(row.get("is_demo_sample", True)),
                    "is_autonomous_growth": bool(row.get("is_autonomous_growth", False)),
                    "local_brain_write": False,
                },
            )
            for index, row in enumerate(semantic_graph["edges"])
        ]
        stored_edge_count = len(edges)
        implicit_candidate_pairs = len(nodes) * max(0, len(nodes) - 1) // 2
        return LayerResult(
            layer="semantic_cloud",
            available=True,
            nodes=nodes,
            edges=edges,
            stats={
                **semantic_status,
                "semantic_cloud_nodes": len(nodes),
                "semantic_cloud_edges": stored_edge_count,
                "verified_semantic_cloud_edges": 0,
                "implicit_candidate_pairs": implicit_candidate_pairs,
                "candidate_pair_edges_sent": 0,
                "candidate_pair_topology": "planetary_galaxy_implicit_spherical_field",
                "planetary_topology": semantic_counts.get("topology") or {},
                "spherical_lod_shell": chunk_index,
                "density_chunks": density_chunks,
                "visible_scale_chunks": int(chunk_index.get("visible_scale_chunk_count") or len(density_chunks)),
                "scale_chunks_are_semantic_nodes": False,
                "all_nodes_rendered": False,
                "read_model_available": bool(semantic_graph.get("read_model_available")),
                "read_model_stale": bool(semantic_graph.get("read_model_stale")),
                "graph_unavailable_reason": semantic_graph.get("graph_unavailable_reason"),
                "performance": semantic_graph.get("performance") or {},
                "source_is_remote": False,
                "old_mirror_snapshot_used": False,
            },
            partial=bool(semantic_graph.get("bounded")),
        )

    return LayerResult(
        layer="semantic_cloud",
        available=True,
        nodes=[],
        edges=[],
        stats={
            **semantic_status,
            "semantic_cloud_nodes": 0,
            "semantic_cloud_edges": 0,
            "verified_semantic_cloud_edges": 0,
            "implicit_candidate_pairs": 0,
            "candidate_pair_edges_sent": 0,
            "candidate_pair_topology": "planetary_galaxy_implicit_spherical_field",
            "planetary_topology": semantic_counts.get("topology") or {},
            "spherical_lod_shell": chunk_index,
            "density_chunks": density_chunks,
            "visible_scale_chunks": int(chunk_index.get("visible_scale_chunk_count") or len(density_chunks)),
            "scale_chunks_are_semantic_nodes": False,
            "all_nodes_rendered": False,
            "read_model_available": bool(semantic_graph.get("read_model_available")),
            "read_model_stale": bool(semantic_status.get("read_model_stale") or semantic_graph.get("read_model_stale")),
            "graph_unavailable_reason": semantic_graph.get("graph_unavailable_reason") or semantic_status.get("graph_unavailable_reason"),
            "performance": semantic_graph.get("performance") or semantic_status.get("performance") or {},
            "source_is_remote": False,
            "old_mirror_snapshot_used": False,
        },
        partial=True,
    )


def materialize_cloud_attached_graph(max_nodes: int, max_edges: int, layer: str = "cloud_attached") -> LayerResult:
    overlay = graph_overlay()
    nodes = [
        _node(
            str(row.get("id") or row.get("cloud_node_id") or f"cloud-attached:{index}"),
            str(row.get("label") or row.get("concept_id") or f"attached cloud {index}"),
            layer,
            "cloud",
            persistent=False,
            temporary=True,
            kind="cloud_attached",
            radius=1.08,
            trust_state=str(row.get("trust_state") or "seed_aligned"),
            verification_state=str(row.get("verification_state") or "seed_aligned_pending_verification"),
            metadata={
                "bundle_temporary": True,
                "writes_to_local_brain": False,
                "counts_as_local_brain": False,
                "temporary_working_memory": True,
                "promotion_required": "manual",
                "caller_metadata_authoritative": row.get("caller_metadata_authoritative") is True,
                "independent_source_attestation": row.get("independent_source_attestation") is True,
                "authoritative_for_answer": row.get("authoritative_for_answer") is True,
                "is_semantic_node": False,
                "provenance_type": "cloud_attached",
                "source_run_id": row.get("source_run_id") or row.get("bundle_id"),
                "source_text_hash": row.get("source_hash") or row.get("content_hash"),
                "source_label": "Temporary Cloud attached Working Memory overlay",
                "is_demo_sample": False,
                "is_autonomous_growth": False,
                "local_brain_write": False,
            },
        )
        for index, row in enumerate(overlay.get("cloud_attached_nodes") or [])
    ]
    edges = [
        _edge(
            str(row.get("id") or row.get("cloud_edge_id") or f"cloud-attached-edge:{index}"),
            str(row.get("source")),
            str(row.get("target")),
            str(row.get("relation") or "related_to"),
            layer,
            "cloud",
            persistent=False,
            temporary=True,
            weight=0.9,
            # Attachment is a transport state, not a new verification event.
            # Preserve the originating authority labels so an unverified
            # semantic candidate cannot be laundered by entering Working Memory.
            trust_state=str(row.get("trust_state") or "seed_aligned"),
            verification_state=str(row.get("verification_state") or "seed_aligned_pending_verification"),
            metadata={
                "writes_to_local_brain": False,
                "counts_as_local_brain": False,
                "temporary_working_memory": True,
                "promotion_required": "manual",
                "caller_metadata_authoritative": row.get("caller_metadata_authoritative") is True,
                "independent_source_attestation": row.get("independent_source_attestation") is True,
                "authoritative_for_answer": row.get("authoritative_for_answer") is True,
                "provenance_type": "cloud_attached",
                "source_run_id": row.get("source_run_id") or row.get("bundle_id"),
                "source_text_hash": row.get("source_hash") or row.get("content_hash"),
                "source_label": "Temporary Cloud attached Working Memory overlay",
                "is_demo_sample": False,
                "is_autonomous_growth": False,
                "local_brain_write": False,
            },
        )
        for index, row in enumerate(overlay.get("cloud_attached_edges") or [])
        if row.get("source") and row.get("target")
    ]
    return LayerResult(
        layer=layer,
        available=True,
        nodes=_bounded(nodes, max_nodes),
        edges=_bounded(edges, max_edges),
        stats={
            "cloud_attached_nodes": len(nodes),
            "cloud_attached_edges": len(edges),
            "temporary": True,
            "local_write": False,
            "counts_as_local_brain": False,
            "cloud_promotion": "manual_required",
        },
        partial=len(nodes) > max_nodes or len(edges) > max_edges,
    )


def materialize_graph_cartridge_graph(max_nodes: int, max_edges: int) -> LayerResult:
    payload = attachment_graph_payload()
    nodes = [
        _node(
            str(row.get("id") or f"graph-cartridge:{index}"),
            str(row.get("label") or row.get("id") or f"Graph Cartridge {index}"),
            "graph_cartridge",
            "cloud",
            persistent=False,
            temporary=True,
            kind="graph_cartridge_node",
            radius=1.1,
            trust_state=str(row.get("trust_state") or "cartridge_attached"),
            verification_state=str(row.get("verification_state") or "read_only_working_memory"),
            metadata={
                "source_cartridge_id": row.get("source_cartridge_id"),
                "local_brain_write": False,
                "temporary": True,
                "independent_source_attestation": row.get("independent_source_attestation") is True,
                "authoritative_for_answer": row.get("authoritative_for_answer") is True,
                "provenance_type": "graph_cartridge",
                "source_run_id": row.get("source_cartridge_id"),
                "source_text_hash": row.get("source_hash"),
                "source_label": "Installed Graph Cartridge attachment",
                "is_demo_sample": False,
                "is_autonomous_growth": False,
            },
        )
        for index, row in enumerate(payload.get("nodes") or [])
    ]
    edges = [
        _edge(
            str(row.get("id") or f"graph-cartridge-edge:{index}"),
            str(row.get("source")),
            str(row.get("target")),
            str(row.get("relation") or "related_to"),
            "graph_cartridge",
            "cloud",
            persistent=False,
            temporary=True,
            weight=float(row.get("weight") or 0.72),
            trust_state=str(row.get("trust_state") or "cartridge_attached"),
            verification_state=str(row.get("verification_state") or "read_only_working_memory"),
            metadata={
                "source_cartridge_id": row.get("source_cartridge_id"),
                "local_brain_write": False,
                "independent_source_attestation": row.get("independent_source_attestation") is True,
                "authoritative_for_answer": row.get("authoritative_for_answer") is True,
                "provenance_type": "graph_cartridge",
                "source_run_id": row.get("source_cartridge_id"),
                "source_text_hash": row.get("source_hash"),
                "source_label": "Installed Graph Cartridge attachment",
                "is_demo_sample": False,
                "is_autonomous_growth": False,
            },
        )
        for index, row in enumerate(payload.get("edges") or [])
        if row.get("source") and row.get("target")
    ]
    attachments = list_active_attachments()
    return LayerResult(
        layer="graph_cartridge",
        available=True,
        nodes=_bounded(nodes, max_nodes),
        edges=_bounded(edges, max_edges),
        stats={
            "active_cartridges": len([row for row in attachments if row.get("status") == "attached"]),
            "attached_cartridge_nodes": len(nodes),
            "attached_cartridge_edges": len(edges),
            "temporary": True,
            "local_write": False,
        },
        partial=len(nodes) > max_nodes or len(edges) > max_edges,
    )


def materialize_contributor_graph(max_nodes: int, max_edges: int) -> LayerResult:
    try:
        status = contributor_status()
    except Exception as exc:
        return _layer_missing("contributor", f"contributor_status_unavailable: {exc}")
    peer_id = str(status.get("peer_id") or "local-contributor")
    node = _node(
        f"contributor:{peer_id}",
        "Contributor Node",
        "contributor",
        "cloud",
        persistent=False,
        temporary=False,
        kind="contributor_peer",
        radius=1.32,
        trust_state=str(status.get("state") or "viewer_only"),
        verification_state="public_fragment_only",
        metadata={"public_only": True, "private_data_shared": False},
    )
    return LayerResult(layer="contributor", available=True, nodes=[node][:max_nodes], edges=[][:max_edges], stats=status)


def _read_latest_surface_trace() -> dict[str, Any] | None:
    candidates = [
        Path("data/surface_brain/traces/realized_answers.jsonl"),
        Path("data/surface_brain/traces/surface_plans.jsonl"),
        Path("data/surface_brain/proofs/surface_brain_proof.json"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            if path.suffix == ".jsonl":
                rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
                if rows:
                    return rows[-1]
            else:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    return payload
        except Exception:
            continue
    return None


def materialize_surface_trace_summary() -> LayerResult:
    trace = _read_latest_surface_trace()
    if not trace:
        return _layer_missing(
            "surface_trace_summary",
            "surface_trace_summary_unavailable",
            stats={"full_surface_graph_rendered": False, "summary_only": True},
        )
    side_panel = {
        "summary_only": True,
        "full_surface_graph_rendered": False,
        "selected_constructions": trace.get("selected_constructions") or trace.get("surface_constructions") or [],
        "selected_discourse_moves": trace.get("selected_discourse_moves") or trace.get("discourse_moves") or [],
        "q_cortex_used": bool(trace.get("q_cortex_used") or trace.get("q_cortex", {}).get("used")),
        "repair_applied": bool(trace.get("repair", {}).get("applied")),
    }
    return LayerResult(
        layer="surface_trace_summary",
        available=True,
        nodes=[],
        edges=[],
        side_panel=side_panel,
        stats={"surface_summary_available": True, "full_surface_graph_rendered": False, "summary_only": True},
    )
