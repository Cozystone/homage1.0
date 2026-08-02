from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .temporal import apply_temporal_weights
from .vault_repository import get_vault_repository

DEFAULT_MEMORY_DIR = "data/memory"
DEFAULT_DB_NAME = "homage.db"
ACTIVE_HASH_LIMIT = 22


def content_hash(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8", errors="ignore")).hexdigest()


def _memory_db_path(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> Path:
    path = Path(memory_dir)
    if path.suffix in {".db", ".sqlite", ".sqlite3"}:
        return path
    return path / DEFAULT_DB_NAME


def _connect_readonly(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> sqlite3.Connection | None:
    db_path = _memory_db_path(memory_dir)
    if not db_path.exists():
        return None
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return bool(row)


def _placeholders(values: Iterable[Any]) -> str:
    return ",".join("?" for _ in values)


def _hash_unit(value: str, salt: str) -> float:
    digest = hashlib.sha256(f"{salt}:{value}".encode("utf-8")).digest()
    integer = int.from_bytes(digest[:8], "big")
    return (integer / ((1 << 64) - 1)) * 2 - 1


def _text_vector(text: str) -> tuple[float, float, float]:
    digest = hashlib.sha256(text.lower().strip().encode("utf-8", errors="ignore")).hexdigest()
    return (_hash_unit(digest, "x"), _hash_unit(digest, "y"), _hash_unit(digest, "z"))


def ghost_store_available(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> bool:
    conn = _connect_readonly(memory_dir)
    if not conn:
        return False
    try:
        if not (_table_exists(conn, "ghost_nodes") and _table_exists(conn, "ghost_edges") and _table_exists(conn, "payload_vault")):
            return False
        row = conn.execute("SELECT COUNT(*) AS count FROM ghost_nodes").fetchone()
        return bool(row and int(row["count"] or 0) > 0)
    finally:
        conn.close()


def ghost_status(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    conn = _connect_readonly(memory_dir)
    if not conn:
        return {
            "system_state": "GHOST SHELL EMPTY",
            "control_plane_hashes": 0,
            "control_plane_edges": 0,
            "payload_vault_records": 0,
            "memory_mode": "disk_absent",
        }
    try:
        counts: dict[str, int] = {}
        for table, key in [
            ("ghost_nodes", "control_plane_hashes"),
            ("ghost_edges", "control_plane_edges"),
            ("payload_vault", "payload_vault_records"),
        ]:
            counts[key] = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]) if _table_exists(conn, table) else 0
        return {
            "system_state": "GHOST SHELL ACTIVE" if counts["control_plane_hashes"] else "GHOST SHELL EMPTY",
            "control_plane_hashes": counts["control_plane_hashes"],
            "control_plane_edges": counts["control_plane_edges"],
            "payload_vault_records": counts["payload_vault_records"],
            "memory_mode": "minimal_hash_topology",
            "data_plane": "payload_vault_sqlite_wal",
        }
    finally:
        conn.close()


class PayloadVault:
    """Disk-bound content-addressed payload store.

    The vault is intentionally queried only after GhostTopology has selected
    target hashes. It is never hydrated into process memory at boot.
    """

    def __init__(self, memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> None:
        self.memory_dir = memory_dir

    def resolve_payloads(
        self,
        hash_list: list[str],
        *,
        limit: int = ACTIVE_HASH_LIMIT,
        hash_weights: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        repository = get_vault_repository(self.memory_dir)
        payloads = repository.resolve_payloads(hash_list, limit=limit)
        return apply_temporal_weights(payloads, hash_weights=hash_weights)


class GhostTopology:
    """Lightweight control-plane graph.

    Nodes returned from this class contain only a SHA-256 hash and 3D vector.
    Edges contain only source hash, target hash, and weight. Raw text remains in
    PayloadVault until resolve_payloads is explicitly called.
    """

    def __init__(self, memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> None:
        self.memory_dir = memory_dir

    def query(
        self,
        query_text: str,
        *,
        max_depth: int = 3,
        max_nodes: int = 512,
        max_edges: int = 2048,
        active_hash_limit: int = ACTIVE_HASH_LIMIT,
    ) -> dict[str, Any]:
        conn = _connect_readonly(self.memory_dir)
        if not conn:
            return self._empty("no_memory", max_depth, max_nodes, max_edges)
        try:
            if not (_table_exists(conn, "ghost_nodes") and _table_exists(conn, "ghost_edges")):
                return self._empty("ghost_tables_missing", max_depth, max_nodes, max_edges)

            max_depth = max(1, int(max_depth))
            max_nodes = max(1, int(max_nodes))
            max_edges = max(1, int(max_edges))
            active_hash_limit = max(1, int(active_hash_limit))
            qx, qy, qz = _text_vector(query_text)
            seed_rows = conn.execute(
                """
                SELECT node_hash, dim0, dim1, dim2
                FROM ghost_nodes
                ORDER BY
                  ((dim0 - ?) * (dim0 - ?)) +
                  ((dim1 - ?) * (dim1 - ?)) +
                  ((dim2 - ?) * (dim2 - ?)) ASC
                LIMIT ?
                """,
                (qx, qx, qy, qy, qz, qz, min(max_nodes, max(active_hash_limit, 24))),
            ).fetchall()
            visited: dict[str, dict[str, Any]] = {}
            scores: dict[str, float] = {}
            frontier: set[str] = set()
            for index, row in enumerate(seed_rows):
                node_hash = str(row["node_hash"])
                visited[node_hash] = self._node_from_row(row)
                scores[node_hash] = 1.0 / (index + 1)
                frontier.add(node_hash)

            edges: dict[tuple[str, str], dict[str, Any]] = {}
            per_depth_limit = max(64, max_edges // max(1, max_depth))
            for depth in range(max_depth):
                if not frontier or len(visited) >= max_nodes or len(edges) >= max_edges:
                    break
                marks = _placeholders(frontier)
                rows = conn.execute(
                    f"""
                    SELECT source_hash, target_hash, weight
                    FROM ghost_edges
                    WHERE source_hash IN ({marks}) OR target_hash IN ({marks})
                    ORDER BY weight DESC
                    LIMIT ?
                    """,
                    (*frontier, *frontier, min(per_depth_limit, max_edges - len(edges))),
                ).fetchall()
                next_frontier: set[str] = set()
                missing_hashes: set[str] = set()
                for row in rows:
                    source_hash = str(row["source_hash"])
                    target_hash = str(row["target_hash"])
                    key = (source_hash, target_hash)
                    weight = float(row["weight"] or 0.0)
                    edges[key] = {
                        "source_hash": source_hash,
                        "target_hash": target_hash,
                        "weight": weight,
                    }
                    edge_score = weight / (depth + 1)
                    for node_hash in (source_hash, target_hash):
                        if node_hash not in visited and len(visited) + len(missing_hashes) < max_nodes:
                            missing_hashes.add(node_hash)
                            next_frontier.add(node_hash)
                        scores[node_hash] = max(scores.get(node_hash, 0.0), edge_score)

                if missing_hashes:
                    marks = _placeholders(missing_hashes)
                    node_rows = conn.execute(
                        f"""
                        SELECT node_hash, dim0, dim1, dim2
                        FROM ghost_nodes
                        WHERE node_hash IN ({marks})
                        LIMIT ?
                        """,
                        (*missing_hashes, max(1, max_nodes - len(visited))),
                    ).fetchall()
                    for row in node_rows:
                        visited[str(row["node_hash"])] = self._node_from_row(row)
                frontier = {node_hash for node_hash in next_frontier if node_hash in visited}

            active_hashes = [
                node_hash
                for node_hash, _score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
                if node_hash in visited
            ][:active_hash_limit]
            active_hash_scores = {
                node_hash: float(score)
                for node_hash, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
                if node_hash in visited
            }
            visible_hashes = [
                node_hash
                for node_hash, _score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
                if node_hash in visited
            ][:max_nodes]
            visible_set = set(visible_hashes)
            kept_edges = [
                edge
                for edge in sorted(edges.values(), key=lambda item: -float(item["weight"]))
                if edge["source_hash"] in visible_set and edge["target_hash"] in visible_set
            ][:max_edges]
            return {
                "state": "completed",
                "system_state": "GHOST SHELL ACTIVE",
                "nodes": [visited[node_hash] for node_hash in visible_hashes],
                "edges": kept_edges,
                "active_hashes": active_hashes,
                "active_hash_scores": active_hash_scores,
                "graph_paths": [[edge["source_hash"], edge["target_hash"]] for edge in kept_edges[:8]],
                "limits": {
                    "max_depth": max_depth,
                    "max_nodes": max_nodes,
                    "max_edges": max_edges,
                    "active_hash_limit": active_hash_limit,
                },
            }
        finally:
            conn.close()

    @staticmethod
    def _node_from_row(row: sqlite3.Row) -> dict[str, Any]:
        node_hash = str(row["node_hash"])
        return {
            "id": node_hash,
            "node_hash": node_hash,
            "label": f"ghost:{node_hash[:12]}",
            "type": "ghost_hash",
            "x": float(row["dim0"] or 0.0),
            "y": float(row["dim1"] or 0.0),
            "z": float(row["dim2"] or 0.0),
            "payload_resolved": False,
        }

    @staticmethod
    def _empty(state: str, max_depth: int, max_nodes: int, max_edges: int) -> dict[str, Any]:
        return {
            "state": state,
            "system_state": "GHOST SHELL EMPTY",
            "nodes": [],
            "edges": [],
            "active_hashes": [],
            "graph_paths": [],
            "limits": {
                "max_depth": max_depth,
                "max_nodes": max_nodes,
                "max_edges": max_edges,
                "active_hash_limit": ACTIVE_HASH_LIMIT,
            },
        }


def query_ghost_rag_context(
    query_text: str,
    memory_dir: str | Path = DEFAULT_MEMORY_DIR,
    *,
    max_depth: int = 3,
    max_nodes: int = 512,
    max_edges: int = 2048,
    active_hash_limit: int = ACTIVE_HASH_LIMIT,
) -> dict[str, Any]:
    topology = GhostTopology(memory_dir)
    subgraph = topology.query(
        query_text,
        max_depth=max_depth,
        max_nodes=max_nodes,
        max_edges=max_edges,
        active_hash_limit=active_hash_limit,
    )
    active_hashes = list(subgraph.get("active_hashes") or [])[:active_hash_limit]
    active_hash_scores = dict(subgraph.get("active_hash_scores") or {})
    fetch_logs = [f"[FETCH] Emitting signal for {len(active_hashes)} hashes..."]
    payloads = PayloadVault(memory_dir).resolve_payloads(active_hashes, limit=active_hash_limit, hash_weights=active_hash_scores)
    fetch_logs.append("[FETCH] Payloads resolved. Synthesizing response.")
    if payloads:
        fetch_logs.append("[TEMPORAL] Applied decay/potentiation weights; newest factual band has priority.")
    docs = [
        {
            "doc_id": str(payload["metadata"].get("doc_id") or payload["metadata"].get("kind") or "payload-vault"),
            "chunk_id": f"{payload['hash_key']}#payload",
            "path": f"payload-vault://{payload['hash_key']}",
            "text": payload["raw_text"],
            "hash_key": payload["hash_key"],
            "metadata": payload["metadata"],
            "score": payload.get("temporal_weight", 0.0),
            "temporal": payload.get("temporal"),
            "temporal_rank": payload.get("temporal_rank"),
            "vault_driver": payload.get("vault_driver"),
        }
        for payload in payloads
        if str(payload.get("raw_text") or "").strip()
    ]
    return {
        **subgraph,
        "payload_docs": docs,
        "resolved_payload_count": len(docs),
        "fetch_logs": fetch_logs,
        "telemetry": {
            **ghost_status(memory_dir),
            "last_signal_hashes": len(active_hashes),
            "last_resolved_payloads": len(docs),
            "fetch_sequence": fetch_logs,
        },
    }
