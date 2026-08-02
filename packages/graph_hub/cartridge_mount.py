from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .audit import append_graph_hub_audit_event
from .installer import get_installed_cartridge
from .models import GRAPH_HUB_ROOT, read_json, stable_id, utc_now_iso, write_json


MOUNT_TABLE_PATH = GRAPH_HUB_ROOT / "mounts" / "mounted_cartridges.json"
ACTIVE_CHUNKS_PATH = GRAPH_HUB_ROOT / "mounts" / "active_chunks.json"
DEFAULT_CHUNK_NODE_SIZE = 256
DEFAULT_CHUNK_EDGE_SIZE = 512
MAX_ACTIVE_CARTRIDGES = 3
MAX_ACTIVE_CHUNKS_PER_CARTRIDGE = 16
MAX_MATERIALIZED_NODES = 2000
MAX_MATERIALIZED_EDGES = 4000


@dataclass(frozen=True)
class GraphCartridgeManifest:
    cartridge_id: str
    name: str
    domain: str
    version: str
    namespace: str
    read_only: bool
    node_count: int
    relation_count: int
    chunk_count: int
    merkle_root: str
    created_at: str
    source: str
    trust_state: str
    requires_provider: bool


@dataclass(frozen=True)
class CartridgeChunkRef:
    cartridge_id: str
    chunk_id: str
    namespace: str
    node_start: int
    node_end: int
    relation_start: int
    relation_end: int
    routing_terms: list[str]
    read_only: bool = True
    is_graph_node: bool = False


@dataclass(frozen=True)
class MountedCartridge:
    mount_id: str
    cartridge_id: str
    state: str
    mounted_at: str
    manifest: dict[str, Any]
    chunk_index: list[dict[str, Any]]
    index_state: str
    loaded_chunks: int
    materialized_nodes: int
    materialized_edges: int
    read_only: bool
    local_write: bool
    cloud_merge: bool
    full_cartridge_loaded_at_attach: bool
    background_warmup_state: str


@dataclass(frozen=True)
class ActiveCartridgeChunk:
    cartridge_id: str
    chunk_id: str
    opened_at: str
    materialized_nodes: int
    materialized_edges: int
    temporary: bool
    local_write: bool
    cloud_merge: bool


@dataclass(frozen=True)
class CartridgeMountTable:
    mounted: list[MountedCartridge]
    active_chunks: list[ActiveCartridgeChunk]
    max_active_cartridges: int = MAX_ACTIVE_CARTRIDGES
    max_active_chunks_per_cartridge: int = MAX_ACTIVE_CHUNKS_PER_CARTRIDGE
    max_materialized_nodes: int = MAX_MATERIALIZED_NODES
    max_materialized_edges: int = MAX_MATERIALIZED_EDGES


def _load_mounts() -> dict[str, dict[str, Any]]:
    payload = read_json(MOUNT_TABLE_PATH, {})
    return payload if isinstance(payload, dict) else {}


def _save_mounts(payload: dict[str, dict[str, Any]]) -> None:
    write_json(MOUNT_TABLE_PATH, payload)


def _load_active_chunks() -> dict[str, dict[str, Any]]:
    payload = read_json(ACTIVE_CHUNKS_PATH, {})
    return payload if isinstance(payload, dict) else {}


def _save_active_chunks(payload: dict[str, dict[str, Any]]) -> None:
    write_json(ACTIVE_CHUNKS_PATH, payload)


def _installed_manifest(installed: dict[str, Any]) -> GraphCartridgeManifest:
    cartridge_id = str(installed.get("cartridge_id") or "")
    stats = installed.get("stats") if isinstance(installed.get("stats"), dict) else {}
    node_count = int(stats.get("semantic_nodes") or 0)
    relation_count = int(stats.get("semantic_edges") or 0)
    chunk_count = max(
        1 if node_count or relation_count else 0,
        math.ceil(max(node_count, 1) / DEFAULT_CHUNK_NODE_SIZE),
        math.ceil(max(relation_count, 1) / DEFAULT_CHUNK_EDGE_SIZE),
    )
    version = str(installed.get("version") or "0.1.0")
    checksum_hint = "checksum_valid" if installed.get("checksum_valid") else "checksum_unverified"
    return GraphCartridgeManifest(
        cartridge_id=cartridge_id,
        name=str(installed.get("name") or cartridge_id.replace("_", " ").title()),
        domain=str(installed.get("domain") or "installed_graph_cartridge"),
        version=version,
        namespace=f"cart:{cartridge_id}",
        read_only=True,
        node_count=node_count,
        relation_count=relation_count,
        chunk_count=chunk_count,
        merkle_root=str(installed.get("merkle_root") or stable_id("merkle", f"{cartridge_id}:{version}:{node_count}:{relation_count}")),
        created_at=str(installed.get("installed_at") or utc_now_iso()),
        source=str(installed.get("source") or "local_installed"),
        trust_state="local_installed" if installed.get("checksum_valid", True) else "unverified",
        requires_provider=False,
    )


def _chunk_refs(manifest: GraphCartridgeManifest) -> list[CartridgeChunkRef]:
    refs: list[CartridgeChunkRef] = []
    for index in range(manifest.chunk_count):
        node_start = index * DEFAULT_CHUNK_NODE_SIZE
        relation_start = index * DEFAULT_CHUNK_EDGE_SIZE
        node_end = min(manifest.node_count, node_start + DEFAULT_CHUNK_NODE_SIZE)
        relation_end = min(manifest.relation_count, relation_start + DEFAULT_CHUNK_EDGE_SIZE)
        refs.append(
            CartridgeChunkRef(
                cartridge_id=manifest.cartridge_id,
                chunk_id=f"{manifest.namespace}:chunk:{index:04d}",
                namespace=manifest.namespace,
                node_start=node_start,
                node_end=node_end,
                relation_start=relation_start,
                relation_end=relation_end,
                routing_terms=[
                    manifest.cartridge_id.lower(),
                    manifest.domain.lower(),
                    manifest.name.lower(),
                ],
            )
        )
    return refs


def _wave_budget(active_cartridges: int, active_chunks: int, nodes: int, edges: int, latency_budget_ms: int = 900) -> dict[str, Any]:
    fanout_pressure = max(1.0, edges / max(nodes, 1))
    attenuation = min(0.92, max(0.28, 1.0 / (1.0 + active_cartridges * 0.18 + active_chunks * 0.06 + fanout_pressure * 0.025)))
    wave_depth = max(2, min(4, int(5 - active_chunks / 6 - fanout_pressure / 12)))
    pruned_edges = max(0, edges - min(edges, MAX_MATERIALIZED_EDGES))
    return {
        "active_cartridges": active_cartridges,
        "active_chunks": active_chunks,
        "wave_depth": wave_depth,
        "attenuation": round(attenuation, 4),
        "nodes_considered": nodes,
        "nodes_materialized": min(nodes, MAX_MATERIALIZED_NODES),
        "pruned_edges": pruned_edges,
        "latency_budget_ms": latency_budget_ms,
        "pair_edges_sent": 0,
        "candidate_pair_edges_sent": 0,
    }


def _mount_table_metadata(mounts: dict[str, dict[str, Any]] | None = None, active: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    mounts = _load_mounts() if mounts is None else mounts
    active = _load_active_chunks() if active is None else active
    active_cartridges = {str(row.get("cartridge_id")) for row in active.values() if row.get("cartridge_id")}
    return {
        "mounted_cartridges": len(mounts),
        "active_cartridges": len(active_cartridges),
        "active_chunks": len(active),
        "max_active_cartridges": MAX_ACTIVE_CARTRIDGES,
        "max_active_chunks_per_cartridge": MAX_ACTIVE_CHUNKS_PER_CARTRIDGE,
        "max_materialized_nodes": MAX_MATERIALIZED_NODES,
        "max_materialized_edges": MAX_MATERIALIZED_EDGES,
        "normal_graph_full_store_scan": False,
        "pair_edges_sent": 0,
    }


def _visualization_metadata(cartridge_id: str, *, active_chunks: int = 0, materialized_nodes: int = 0) -> dict[str, Any]:
    return {
        "render_role": "mounted_cartridge_satellite",
        "cartridge_id": cartridge_id,
        "cloud_brain_merge_visual": False,
        "local_brain_merge_visual": False,
        "mounted_namespace_visible": True,
        "active_chunk_halo": active_chunks > 0,
        "active_chunk_halo_color": "violet" if active_chunks > 0 else "none",
        "density_chunk_role": "blue_gray_render_container",
        "materialized_nodes": materialized_nodes,
    }


def attach_cartridge_namespace(cartridge_id: str) -> dict[str, Any]:
    start = time.perf_counter()
    installed = get_installed_cartridge(cartridge_id)
    if not installed:
        return {
            "cartridge_id": cartridge_id,
            "state": "unavailable",
            "reason": "not_installed",
            "loaded_chunks": 0,
            "materialized_nodes": 0,
            "read_only": True,
            "local_write": False,
            "cloud_merge": False,
        }
    if not installed.get("enabled", True):
        return {
            "cartridge_id": cartridge_id,
            "state": "unavailable",
            "reason": "disabled",
            "loaded_chunks": 0,
            "materialized_nodes": 0,
            "read_only": True,
            "local_write": False,
            "cloud_merge": False,
        }
    mounts = _load_mounts()
    if cartridge_id not in mounts and len(mounts) >= MAX_ACTIVE_CARTRIDGES:
        return {
            "cartridge_id": cartridge_id,
            "state": "unavailable",
            "reason": "mount_budget_exceeded",
            "loaded_chunks": 0,
            "materialized_nodes": 0,
            "read_only": True,
            "local_write": False,
            "cloud_merge": False,
            "mount_table": _mount_table_metadata(mounts),
        }
    manifest = _installed_manifest(installed)
    chunk_refs = _chunk_refs(manifest)
    mounted = MountedCartridge(
        mount_id=stable_id("gcm", f"{cartridge_id}:{manifest.version}"),
        cartridge_id=cartridge_id,
        state="mounted",
        mounted_at=utc_now_iso(),
        manifest=asdict(manifest),
        chunk_index=[asdict(ref) for ref in chunk_refs],
        index_state="portable_index_ready",
        loaded_chunks=0,
        materialized_nodes=0,
        materialized_edges=0,
        read_only=True,
        local_write=False,
        cloud_merge=False,
        full_cartridge_loaded_at_attach=False,
        background_warmup_state="ready",
    )
    mounts[cartridge_id] = asdict(mounted)
    _save_mounts(mounts)
    attach_ms = round((time.perf_counter() - start) * 1000, 3)
    append_graph_hub_audit_event("cartridge_mounted", cartridge_id, {"attach_ms": attach_ms, "loaded_chunks": 0, "cloud_merge": False})
    return {
        "cartridge_id": cartridge_id,
        "state": "mounted",
        "namespace": manifest.namespace,
        "loaded_chunks": 0,
        "materialized_nodes": 0,
        "materialized_edges": 0,
        "read_only": True,
        "local_write": False,
        "cloud_merge": False,
        "attach_ms": attach_ms,
        "manifest": asdict(manifest),
        "chunk_count": manifest.chunk_count,
        "index_state": "portable_index_ready",
        "background_warmup_state": "ready",
        "full_cartridge_loaded_at_attach": False,
        "mount_table": _mount_table_metadata(mounts),
        "visualization": _visualization_metadata(cartridge_id),
    }

def detach_cartridge_namespace(cartridge_id: str) -> dict[str, Any]:
    start = time.perf_counter()
    mounts = _load_mounts()
    removed = mounts.pop(cartridge_id, None)
    _save_mounts(mounts)
    active = _load_active_chunks()
    closed = 0
    for key in list(active):
        if active[key].get("cartridge_id") == cartridge_id:
            active.pop(key, None)
            closed += 1
    _save_active_chunks(active)
    detach_ms = round((time.perf_counter() - start) * 1000, 3)
    append_graph_hub_audit_event("cartridge_unmounted", cartridge_id, {"had_mount": bool(removed), "active_chunks_closed": closed, "detach_ms": detach_ms})
    return {
        "cartridge_id": cartridge_id,
        "state": "detached",
        "active_chunks_closed": closed,
        "working_memory_cleared": True,
        "local_write": False,
        "cloud_merge": False,
        "detach_ms": detach_ms,
    }


def list_mounted_cartridges() -> list[dict[str, Any]]:
    mounts = _load_mounts()
    active = _load_active_chunks()
    rows: list[dict[str, Any]] = []
    for cartridge_id, mount in mounts.items():
        active_count = sum(1 for row in active.values() if row.get("cartridge_id") == cartridge_id)
        materialized_nodes = sum(int(row.get("materialized_nodes") or 0) for row in active.values() if row.get("cartridge_id") == cartridge_id)
        rows.append({
            **mount,
            "active_chunks": active_count,
            "materialized_nodes": materialized_nodes,
            "mount_table": _mount_table_metadata(mounts, active),
            "visualization": _visualization_metadata(cartridge_id, active_chunks=active_count, materialized_nodes=materialized_nodes),
        })
    return rows


def select_cartridge_chunks(query: str, max_chunks: int = 4) -> dict[str, Any]:
    bounded_max = max(1, min(int(max_chunks or 4), MAX_ACTIVE_CHUNKS_PER_CARTRIDGE))
    mounts = _load_mounts()
    if not mounts:
        return {
            "state": "not_configured",
            "query": query,
            "selected_chunks": [],
            "local_write": False,
            "cloud_merge": False,
            "pair_edges_sent": 0,
        }
    terms = {term.lower() for term in query.replace("?", " ").replace(",", " ").split() if len(term) > 1}
    selected: list[dict[str, Any]] = []
    for mount in mounts.values():
        for ref in mount.get("chunk_index") or []:
            haystack = " ".join(str(term) for term in ref.get("routing_terms") or [])
            score = sum(1 for term in terms if term in haystack)
            if score <= 0 and not selected:
                score = 0
            selected.append({**ref, "score": score})
    selected.sort(key=lambda row: (-int(row.get("score") or 0), str(row.get("chunk_id") or "")))
    bounded_selection: list[dict[str, Any]] = []
    selected_cartridges: set[str] = set()
    for row in selected:
        row_cartridge = str(row.get("cartridge_id") or "")
        if row_cartridge not in selected_cartridges and len(selected_cartridges) >= MAX_ACTIVE_CARTRIDGES:
            continue
        selected_cartridges.add(row_cartridge)
        bounded_selection.append(row)
        if len(bounded_selection) >= bounded_max:
            break
    selected = bounded_selection
    active_cartridges = len({str(row.get("cartridge_id")) for row in selected})
    budget = _wave_budget(active_cartridges, len(selected), 0, 0)
    return {
        "state": "chunks_selected" if selected else "unavailable",
        "query": query,
        "selected_chunks": selected,
        "active_chunks": len(selected),
        "max_active_cartridges": MAX_ACTIVE_CARTRIDGES,
        "max_active_chunks_per_cartridge": MAX_ACTIVE_CHUNKS_PER_CARTRIDGE,
        "wave_budget": budget,
        "local_write": False,
        "cloud_merge": False,
        "pair_edges_sent": 0,
        "full_store_scan": False,
        "materialized_nodes": 0,
        "mount_table": _mount_table_metadata(mounts),
    }


def _load_installed_payload(cartridge_id: str) -> dict[str, Any]:
    installed = get_installed_cartridge(cartridge_id)
    if not installed:
        raise FileNotFoundError(f"not_installed:{cartridge_id}")
    path = Path(str(installed.get("path") or ""))
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        raise FileNotFoundError(f"unavailable:{cartridge_id}")
    return payload


def materialize_cartridge_chunk(cartridge_id: str, chunk_id: str, max_nodes: int = 1000, max_edges: int = 2000) -> dict[str, Any]:
    start = time.perf_counter()
    mounts = _load_mounts()
    mount = mounts.get(cartridge_id)
    if not mount:
        return {
            "cartridge_id": cartridge_id,
            "chunk_id": chunk_id,
            "state": "not_configured",
            "nodes": [],
            "edges": [],
            "local_write": False,
            "cloud_merge": False,
            "pair_edges_sent": 0,
        }
    chunk_refs = mount.get("chunk_index") or []
    ref = next((row for row in chunk_refs if row.get("chunk_id") == chunk_id), None)
    if not ref:
        return {
            "cartridge_id": cartridge_id,
            "chunk_id": chunk_id,
            "state": "unavailable",
            "reason": "missing_chunk_index",
            "nodes": [],
            "edges": [],
            "local_write": False,
            "cloud_merge": False,
            "pair_edges_sent": 0,
        }
    active = _load_active_chunks()
    active_key = f"{cartridge_id}:{chunk_id}"
    active_for_cartridge = [row for row in active.values() if row.get("cartridge_id") == cartridge_id]
    if active_key not in active and len(active_for_cartridge) >= MAX_ACTIVE_CHUNKS_PER_CARTRIDGE:
        return {
            "cartridge_id": cartridge_id,
            "chunk_id": chunk_id,
            "state": "budget_exceeded",
            "reason": "max_active_chunks_per_cartridge",
            "nodes": [],
            "edges": [],
            "materialized_nodes": 0,
            "materialized_edges": 0,
            "working_memory_temporary": True,
            "read_only": True,
            "local_write": False,
            "cloud_merge": False,
            "pair_edges_sent": 0,
            "full_store_scan": False,
            "mount_table": _mount_table_metadata(mounts, active),
        }
    payload = _load_installed_payload(cartridge_id)
    semantic = ((payload.get("contents") or {}).get("semantic_graph") or {})
    node_limit = max(0, min(int(max_nodes or 0), MAX_MATERIALIZED_NODES))
    edge_limit = max(0, min(int(max_edges or 0), MAX_MATERIALIZED_EDGES))
    raw_nodes = list(semantic.get("nodes") or [])[int(ref.get("node_start") or 0): int(ref.get("node_end") or 0)]
    raw_edges = list(semantic.get("edges") or [])[int(ref.get("relation_start") or 0): int(ref.get("relation_end") or 0)]
    nodes = [
        {
            **node,
            "id": f"{mount['manifest']['namespace']}:{node.get('id')}",
            "source_id": node.get("id"),
            "layer": "graph_cartridge_chunk",
            "temporary": True,
            "read_only": True,
            "local_brain_write": False,
            "cloud_merge": False,
            "source_cartridge_id": cartridge_id,
        }
        for node in raw_nodes[:node_limit]
    ]
    node_ids = {str(node.get("source_id")) for node in nodes}
    edges = []
    fanout: dict[str, int] = {}
    for edge in raw_edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in node_ids or target not in node_ids:
            continue
        if fanout.get(source, 0) >= 32:
            continue
        edges.append(
            {
                **edge,
                "id": f"{mount['manifest']['namespace']}:edge:{edge.get('id')}",
                "source": f"{mount['manifest']['namespace']}:{source}",
                "target": f"{mount['manifest']['namespace']}:{target}",
                "source_id": source,
                "target_id": target,
                "layer": "graph_cartridge_chunk",
                "temporary": True,
                "read_only": True,
                "local_brain_write": False,
                "cloud_merge": False,
                "source_cartridge_id": cartridge_id,
            }
        )
        fanout[source] = fanout.get(source, 0) + 1
        if len(edges) >= edge_limit:
            break
    materialize_ms = round((time.perf_counter() - start) * 1000, 3)
    active[active_key] = asdict(ActiveCartridgeChunk(
        cartridge_id=cartridge_id,
        chunk_id=chunk_id,
        opened_at=utc_now_iso(),
        materialized_nodes=len(nodes),
        materialized_edges=len(edges),
        temporary=True,
        local_write=False,
        cloud_merge=False,
    ))
    _save_active_chunks(active)
    wave_budget = _wave_budget(len({row.get("cartridge_id") for row in active.values()}), len(active), len(nodes), len(edges))
    append_graph_hub_audit_event("cartridge_chunk_materialized", cartridge_id, {"chunk_id": chunk_id, "nodes": len(nodes), "edges": len(edges), "materialize_ms": materialize_ms})
    return {
        "cartridge_id": cartridge_id,
        "chunk_id": chunk_id,
        "state": "materialized",
        "nodes": nodes,
        "edges": edges,
        "materialized_nodes": len(nodes),
        "materialized_edges": len(edges),
        "working_memory_temporary": True,
        "read_only": True,
        "local_write": False,
        "cloud_merge": False,
        "pair_edges_sent": 0,
        "candidate_pair_edges_sent": 0,
        "full_store_scan": False,
        "wave_budget": wave_budget,
        "materialize_ms": materialize_ms,
        "mount_table": _mount_table_metadata(mounts, active),
        "visualization": _visualization_metadata(cartridge_id, active_chunks=sum(1 for row in active.values() if row.get("cartridge_id") == cartridge_id), materialized_nodes=len(nodes)),
    }
