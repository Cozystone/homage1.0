from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .contributor_node import DEFAULT_CONTRIBUTOR_ROOT, PUBLIC_SHARD_ID, announce_shards, contributor_peer_id, serve_once


DEFAULT_ATTACHMENT_ROOT = Path("data/working_memory/cloud_node_bundles")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _now_epoch() -> int:
    return int(time.time())


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _bundle_path(bundle_id: str, root: str | Path = DEFAULT_ATTACHMENT_ROOT) -> Path:
    return Path(root) / f"{bundle_id}.json"


def _cloud_node_id(seed: str) -> str:
    return f"cbn_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"


def _cloud_edge_id(seed: str) -> str:
    return f"cbe_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"


def _seed_anchor_id(seed: str) -> str:
    return f"seed_anchor_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:18]}"


def create_cloud_node_bundle(
    query: str,
    *,
    contributor_root: str | Path = DEFAULT_CONTRIBUTOR_ROOT,
    attachment_root: str | Path = DEFAULT_ATTACHMENT_ROOT,
    ttl_seconds: int = 1800,
) -> dict[str, Any]:
    if not (Path(contributor_root) / "public_shards" / PUBLIC_SHARD_ID / "shard_manifest.json").exists():
        announce_shards(contributor_root=contributor_root)
    served = serve_once(query, contributor_root=contributor_root)
    nodes = list(served.get("nodes") or [])
    edges = list(served.get("edges") or [])
    peer_id = contributor_peer_id(contributor_root)
    shard_id = str(served.get("shard_id") or PUBLIC_SHARD_ID)
    created_epoch = _now_epoch()
    expires_epoch = created_epoch + ttl_seconds
    seed = json.dumps({"query": query, "peer_id": peer_id, "shard_id": shard_id, "created": created_epoch}, sort_keys=True)
    bundle_id = f"cnb_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"

    concept_to_cloud_id: dict[str, str] = {}
    cloud_nodes: list[dict[str, Any]] = []
    for index, row in enumerate(nodes):
        concept = str(row.get("concept_id") or row.get("label") or row.get("matched_text") or f"cloud-node-{index}")
        cloud_id = _cloud_node_id(f"{peer_id}:{shard_id}:{concept}")
        concept_to_cloud_id[concept] = cloud_id
        cloud_nodes.append(
            {
                "cloud_node_id": cloud_id,
                "id": cloud_id,
                "logical_ordinal": str(index + 1),
                "label": str(row.get("label") or row.get("matched_text") or concept),
                "type": "cloud_attached",
                "source_type": "cloud_attached",
                "concept_id": concept,
                "source_scope": "cloud",
                "trust_state": "seed_aligned",
                "verification_state": "seed_aligned_pending_verification",
                "temporary_attachment": True,
                "visual_layer": "cloud_attached",
                "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires_epoch)),
                "peer_id": peer_id,
                "shard_id": shard_id,
                "writes_to_local_brain": False,
            }
        )

    cloud_edges: list[dict[str, Any]] = []
    for index, row in enumerate(edges):
        source = str(row.get("source") or "")
        target = str(row.get("target") or "")
        source_id = concept_to_cloud_id.get(source) or _cloud_node_id(f"{peer_id}:{shard_id}:{source}")
        target_id = concept_to_cloud_id.get(target) or _cloud_node_id(f"{peer_id}:{shard_id}:{target}")
        cloud_edges.append(
            {
                "cloud_edge_id": _cloud_edge_id(f"{peer_id}:{shard_id}:{source}:{row.get('relation')}:{target}:{index}"),
                "id": _cloud_edge_id(f"{peer_id}:{shard_id}:{source}:{row.get('relation')}:{target}:{index}"),
                "source": source_id,
                "target": target_id,
                "source_concept": source,
                "target_concept": target,
                "relation": str(row.get("relation") or "related_to"),
                "source_type": "cloud_attached",
                "temporary_attachment": True,
                "visual_layer": "cloud_attached",
                "peer_id": peer_id,
                "shard_id": shard_id,
                "writes_to_local_brain": False,
            }
        )

    seed_anchor_concepts = [node.get("concept_id") for node in cloud_nodes[:4] if node.get("concept_id")]
    seed_anchor_nodes = [
        {
            "id": _seed_anchor_id(str(concept)),
            "seed_anchor_id": _seed_anchor_id(str(concept)),
            "label": str(concept),
            "type": "seed_anchor",
            "source_type": "seed_anchor",
            "visual_layer": "seed_anchor",
            "anchor_role": "retrieval_verification_alignment",
            "temporary_attachment": True,
            "writes_to_local_brain": False,
            "source_scope": "seed",
            "trust_state": "seed_anchor",
            "verification_state": "anchor_only",
        }
        for concept in seed_anchor_concepts
    ]

    bundle = {
        "bundle_id": bundle_id,
        "query": query,
        "source": "contributor_node",
        "peer_id": peer_id,
        "shard_id": shard_id,
        "created_at": _now_iso(),
        "ttl_seconds": ttl_seconds,
        "expires_at_epoch": expires_epoch,
        "privacy_scope": "public",
        "writes_to_local_brain": False,
        "seed_anchor_concepts": seed_anchor_concepts,
        "seed_anchor_nodes": seed_anchor_nodes,
        "nodes": cloud_nodes,
        "edges": cloud_edges,
        "attached": False,
        "external_llm_used": False,
        "external_sllm_used": False,
        "rule_based_answer_engine": False,
        "final_answer_generation_claimed": False,
    }
    _write_json(_bundle_path(bundle_id, attachment_root), bundle)
    return bundle


def attach_bundle(bundle_id: str, *, attachment_root: str | Path = DEFAULT_ATTACHMENT_ROOT) -> dict[str, Any]:
    path = _bundle_path(bundle_id, attachment_root)
    if not path.exists():
        raise FileNotFoundError(f"cloud node bundle not found: {bundle_id}")
    bundle = _read_json(path)
    bundle["attached"] = True
    bundle["attached_at"] = _now_iso()
    _write_json(path, bundle)
    return bundle


def detach_bundle(bundle_id: str, *, attachment_root: str | Path = DEFAULT_ATTACHMENT_ROOT) -> dict[str, Any]:
    """Detach = the bundle stops being attached. Deleting its file is HOUSEKEEPING, and
    housekeeping must never fail an answer.

    Measured 2026-07-17 (seal battery, errors=1 on both splits; found only after the
    watchdog's DEVNULL'd stderr was fixed): the chat path runs this inside
    run_local_cloud_exchange, and on Windows the unlink raced the learner sidecar holding
    the same file — PermissionError [WinError 32] escaped through _chat_atanor_dispatch and
    the whole request 500'd. The user lost an answer they could have had, because a temp
    file could not be removed at that instant.

    So: mark detached first (that is the semantic act, and it persists), then TRY to remove.
    A failed removal leaves a file that list_bundles already filters out by `attached` and
    cleanup_expired_bundles collects later — the same durability contract the rest of this
    module runs on. Reported in the result rather than raised, so it stays visible.
    """
    path = _bundle_path(bundle_id, attachment_root)
    if not path.exists():
        return {"bundle_id": bundle_id, "detached": True, "already_removed": True}
    bundle = _read_json(path)
    file_removed = True
    remove_error = None
    try:
        bundle["attached"] = False
        bundle["detached_at"] = _now_iso()
        _write_json(path, bundle)
    except OSError as exc:  # even the mark can lose the race; detach still holds in-memory
        remove_error = f"{type(exc).__name__}"
    try:
        path.unlink()
    except OSError as exc:  # WinError 32 (another process holds it) and friends
        file_removed = False
        remove_error = f"{type(exc).__name__}"
    return {"bundle_id": bundle_id, "detached": True,
            "removed_nodes": len(bundle.get("nodes") or []),
            "removed_edges": len(bundle.get("edges") or []),
            "file_removed": file_removed,
            **({"remove_error": remove_error} if remove_error else {})}


def list_bundles(*, attachment_root: str | Path = DEFAULT_ATTACHMENT_ROOT, include_detached: bool = False) -> dict[str, Any]:
    root = Path(attachment_root)
    root.mkdir(parents=True, exist_ok=True)
    cleanup_expired_bundles(attachment_root=root)
    bundles = []
    for path in sorted(root.glob("cnb_*.json")):
        try:
            bundle = _read_json(path)
        except (FileNotFoundError, json.JSONDecodeError):
            # RACE: overlay_status polls this while a concurrent detach unlinks a bundle (or a
            # concurrent write is caught mid-flush) between the glob and the read. A LISTING must
            # skip the transient, never 500 — the recurring FileNotFoundError here read as the
            # engine going unhealthy and drove ~hourly watchdog restarts (measured 2026-07-18).
            continue
        if include_detached or bundle.get("attached"):
            bundles.append(bundle)
    active = [bundle for bundle in bundles if bundle.get("attached")]
    active_ids = [bundle["bundle_id"] for bundle in active]
    cloud_node_count = sum(len(bundle.get("nodes") or []) for bundle in active)
    cloud_edge_count = sum(len(bundle.get("edges") or []) for bundle in active)
    seed_anchor_count = sum(len(bundle.get("seed_anchor_nodes") or []) for bundle in active)
    return {
        "bundles": bundles,
        "active_bundle_ids": active_ids,
        "cloud_attached_nodes": cloud_node_count,
        "cloud_attached_edges": cloud_edge_count,
        "seed_anchor_nodes": seed_anchor_count,
        "working_memory_overlay": {
            "active": bool(active),
            "bundle_ids": active_ids,
            "cloud_attached_nodes": cloud_node_count,
            "cloud_attached_edges": cloud_edge_count,
            "seed_anchor_nodes": seed_anchor_count,
            "writes_to_local_brain": False,
            "detachable": True,
        },
        "writes_to_local_brain": False,
    }


def graph_overlay(*, attachment_root: str | Path = DEFAULT_ATTACHMENT_ROOT) -> dict[str, Any]:
    listed = list_bundles(attachment_root=attachment_root)
    active = [bundle for bundle in listed["bundles"] if bundle.get("attached")]
    nodes = [node for bundle in active for node in bundle.get("nodes", [])]
    edges = [edge for bundle in active for edge in bundle.get("edges", [])]
    seed_anchor_nodes = [node for bundle in active for node in bundle.get("seed_anchor_nodes", [])]
    return {
        "cloud_attached_nodes": nodes,
        "cloud_attached_edges": edges,
        "seed_anchor_nodes": seed_anchor_nodes,
        "working_memory_overlay": {
            "active": bool(active),
            "bundle_ids": [bundle["bundle_id"] for bundle in active],
            "cloud_attached_nodes": len(nodes),
            "cloud_attached_edges": len(edges),
            "seed_anchor_nodes": len(seed_anchor_nodes),
            "writes_to_local_brain": False,
            "detachable": True,
        },
        "counts": {
            "cloud_attached_nodes": len(nodes),
            "cloud_attached_edges": len(edges),
            "seed_anchor_nodes": len(seed_anchor_nodes),
        },
    }


def cleanup_expired_bundles(*, attachment_root: str | Path = DEFAULT_ATTACHMENT_ROOT) -> dict[str, Any]:
    root = Path(attachment_root)
    root.mkdir(parents=True, exist_ok=True)
    now = _now_epoch()
    removed: list[str] = []
    for path in root.glob("cnb_*.json"):
        try:
            bundle = _read_json(path)
        except Exception:
            continue
        if int(bundle.get("expires_at_epoch") or 0) <= now:
            try:
                path.unlink(missing_ok=True)             # a concurrent cleanup/detach may beat us
                removed.append(str(bundle.get("bundle_id") or path.stem))
            except PermissionError:
                # WinError 32: the bundle is open in a concurrent reader (list_bundles) — on Windows
                # an open file can't be unlinked. Leave it; the next sweep (or detach) removes it.
                # Measured 2026-07-18: this raised out of a worker thread and read as engine error.
                continue
    return {"removed": removed, "removed_count": len(removed), "writes_to_local_brain": False}


def retrieval_trace_for_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "working_memory_overlay": {
            "enabled": True,
            "cloud_bundle_id": bundle.get("bundle_id"),
            "cloud_attached_nodes": len(bundle.get("nodes") or []),
            "cloud_attached_edges": len(bundle.get("edges") or []),
            "used_for_retrieval": True,
            "source": bundle.get("source"),
            "peer_id": bundle.get("peer_id"),
            "shard_id": bundle.get("shard_id"),
            "writes_to_local_brain": False,
            "detachable": True,
        }
    }
