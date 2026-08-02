from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from .ingestion import DEFAULT_CLOUD_ROOT, cloud_store_status


DEFAULT_CONTRIBUTOR_ROOT = Path("data/cloud_brain/contributor")
PUBLIC_SHARD_ID = "candidate_seed_alignment_001"
CAPABILITIES = [
    "public_fragment_store",
    "seed_alignment",
    "cloud_node_bundle_provider",
    "working_memory_attachment",
]

FORBIDDEN_MARKERS = (
    "C:\\",
    "file://",
    "localhost",
    "127.0.0.1",
    "AppData",
    "payload_vault",
    "homage.db",
    "atanor.db",
    "password",
    "token",
    "secret",
)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _contains_private_marker(value: Any) -> bool:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    lowered = encoded.lower()
    return any(marker.lower() in lowered for marker in FORBIDDEN_MARKERS)


def contributor_peer_id(root: str | Path = DEFAULT_CONTRIBUTOR_ROOT) -> str:
    manifest = Path(root) / "peer_manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("peer_id"):
                return str(data["peer_id"])
        except Exception:
            pass
    seed = os.getenv("ATANOR_CONTRIBUTOR_SEED", "atanor-local-workstation-contributor-001")
    return f"peer_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"


def bridge_local_proof_store(
    *,
    cloud_root: str | Path = DEFAULT_CLOUD_ROOT,
    contributor_root: str | Path = DEFAULT_CONTRIBUTOR_ROOT,
    shard_id: str = PUBLIC_SHARD_ID,
) -> dict[str, Any]:
    cloud_root = Path(cloud_root)
    contributor_root = Path(contributor_root)
    store = cloud_root / "store"
    fragments = _jsonl(store / "cloud_fragments.jsonl")
    nodes = _jsonl(store / "cloud_graph_nodes.jsonl")
    edges = _jsonl(store / "cloud_graph_edges.jsonl")
    safe_rows = {"fragments": fragments, "nodes": nodes, "edges": edges}
    if _contains_private_marker(safe_rows):
        raise ValueError("local proof store contains private markers and cannot be announced")

    peer_id = contributor_peer_id(contributor_root)
    shard_root = contributor_root / "public_shards" / shard_id
    manifest = {
        "schema": "atanor.contributor-shard.v1",
        "shard_id": shard_id,
        "peer_id": peer_id,
        "node_count": str(len(nodes)),
        "edge_count": str(len(edges)),
        "fragment_count": str(len(fragments)),
        "trust_state": "seed_aligned" if fragments else "empty",
        "verification_state": "seed_aligned_pending_verification" if fragments else "empty",
        "privacy_scope": "public",
        "local_brain_private": True,
        "raw_private_uploads_allowed": False,
        "location": {"kind": "peer", "peer_id": peer_id, "endpoint_hint": "local_or_relay"},
        "updated_at": _now_iso(),
    }
    index = {
        "schema": "atanor.contributor-shard-index.v1",
        "shard_id": shard_id,
        "peer_id": peer_id,
        "fragment_ids": [str(row.get("fragment_id")) for row in fragments if row.get("fragment_id")],
        "content_hashes": [str(row.get("content_hash")) for row in fragments if row.get("content_hash")],
        "concepts": [str(row.get("concept_id") or row.get("label")) for row in nodes if row.get("concept_id") or row.get("label")],
        "relations": [str(row.get("relation")) for row in edges if row.get("relation")],
    }
    _write_json(shard_root / "shard_manifest.json", manifest)
    _write_jsonl(shard_root / "fragments.jsonl", fragments)
    _write_jsonl(shard_root / "nodes.jsonl", nodes)
    _write_jsonl(shard_root / "edges.jsonl", edges)
    _write_json(shard_root / "index.json", index)
    return manifest


def register_local_contributor(
    *,
    contributor_root: str | Path = DEFAULT_CONTRIBUTOR_ROOT,
    cloud_root: str | Path = DEFAULT_CLOUD_ROOT,
) -> dict[str, Any]:
    contributor_root = Path(contributor_root)
    peer_id = contributor_peer_id(contributor_root)
    shard = bridge_local_proof_store(cloud_root=cloud_root, contributor_root=contributor_root)
    manifest = {
        "schema": "atanor.contributor-peer.v1",
        "peer_id": peer_id,
        "peer_kind": "local_workstation",
        "capabilities": CAPABILITIES,
        "public_shards": [shard],
        "local_brain_private": True,
        "raw_private_uploads_allowed": False,
        "network_state": "active_single_peer",
        "registered_at": _now_iso(),
        "last_heartbeat_at": _now_iso(),
    }
    _write_json(contributor_root / "peer_manifest.json", manifest)
    return manifest


def heartbeat(*, contributor_root: str | Path = DEFAULT_CONTRIBUTOR_ROOT) -> dict[str, Any]:
    root = Path(contributor_root)
    peer_id = contributor_peer_id(root)
    manifest_path = root / "peer_manifest.json"
    manifest = register_local_contributor(contributor_root=root) if not manifest_path.exists() else json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["last_heartbeat_at"] = _now_iso()
    manifest["network_state"] = "active_single_peer"
    _write_json(manifest_path, manifest)
    return {"peer_id": peer_id, "heartbeat": "ok", "network_state": "active_single_peer", "last_heartbeat_at": manifest["last_heartbeat_at"]}


def announce_shards(*, contributor_root: str | Path = DEFAULT_CONTRIBUTOR_ROOT, cloud_root: str | Path = DEFAULT_CLOUD_ROOT) -> dict[str, Any]:
    manifest = register_local_contributor(contributor_root=contributor_root, cloud_root=cloud_root)
    shards = manifest.get("public_shards", [])
    return {
        "peer_id": manifest["peer_id"],
        "announced": True,
        "network_state": "active_single_peer",
        "public_shards_announced": len(shards),
        "shards": shards,
        "cloudflare_broker_role": "metadata_index_only",
        "heavy_payload_storage": "contributor_node",
    }


def contributor_status(*, contributor_root: str | Path = DEFAULT_CONTRIBUTOR_ROOT, cloud_root: str | Path = DEFAULT_CLOUD_ROOT) -> dict[str, Any]:
    root = Path(contributor_root)
    manifest_path = root / "peer_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else register_local_contributor(contributor_root=root, cloud_root=cloud_root)
    store = cloud_store_status(cloud_root)
    return {
        "available": True,
        "network_state": "active_single_peer",
        "local_peer_registered": True,
        "local_peer_id": manifest["peer_id"],
        "public_shards_announced": len(manifest.get("public_shards", [])),
        "cloudflare_broker_role": "metadata_index_only",
        "heavy_payload_storage": "contributor_node",
        "local_brain_private": True,
        "raw_private_uploads_allowed": False,
        "proof_store_fragments": int(store.get("proof_ingested_fragments") or 0),
    }


def serve_once(query: str = "", *, contributor_root: str | Path = DEFAULT_CONTRIBUTOR_ROOT) -> dict[str, Any]:
    root = Path(contributor_root)
    peer_id = contributor_peer_id(root)
    shard_root = root / "public_shards" / PUBLIC_SHARD_ID
    if not shard_root.exists():
        register_local_contributor(contributor_root=root)
    fragments = _jsonl(shard_root / "fragments.jsonl")
    nodes = _jsonl(shard_root / "nodes.jsonl")
    edges = _jsonl(shard_root / "edges.jsonl")
    return {
        "peer_id": peer_id,
        "network_state": "active_single_peer",
        "query": query,
        "shard_id": PUBLIC_SHARD_ID,
        "fragments": fragments[:5],
        "nodes": nodes,
        "edges": edges,
        "writes_to_local_brain": False,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ATANOR local contributor node")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--heartbeat", action="store_true")
    parser.add_argument("--announce-shards", action="store_true")
    parser.add_argument("--serve-once", action="store_true")
    parser.add_argument("--query", default="")
    args = parser.parse_args(argv)
    if args.heartbeat:
        result = heartbeat()
    elif args.announce_shards:
        result = announce_shards()
    elif args.serve_once:
        result = serve_once(args.query)
    else:
        result = register_local_contributor()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
