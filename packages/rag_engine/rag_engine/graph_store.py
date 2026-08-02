from __future__ import annotations

import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .ghost_graph import ghost_status, ghost_store_available, query_ghost_rag_context


DEFAULT_MEMORY_DIR = "data/memory"
DEFAULT_DB_NAME = "homage.db"


def _runtime_graph_limits() -> tuple[int, int, int, str]:
    try:
        from neuro_efficiency import get_runtime_config  # type: ignore

        config = get_runtime_config()
        return (
            int(config.lazy_subgraph_nodes),
            int(config.lazy_subgraph_edges),
            int(config.lazy_subgraph_depth),
            config.tier,
        )
    except Exception:
        return 512, 2048, 3, "fallback"


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for char in text.lower():
        if char.isalnum() or char in {"-", "_"}:
            current.append(char)
        elif current:
            token = "".join(current).strip("-_")
            if token:
                tokens.append(token)
            current = []
    if current:
        token = "".join(current).strip("-_")
        if token:
            tokens.append(token)
    return [token for token in tokens if len(token) > 1 or token.isdigit()]


def _slug(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9가-힣_-]+", "-", label.strip()).strip("-").lower()
    return cleaned[:96] or "node"


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


def graph_store_available(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> bool:
    conn = _connect_readonly(memory_dir)
    if not conn:
        return False
    try:
        return _table_exists(conn, "nodes") or _table_exists(conn, "synaptic_nodes")
    finally:
        conn.close()


def _placeholders(values: Iterable[Any]) -> str:
    return ",".join("?" for _ in values)


def _fetch_seed_nodes(conn: sqlite3.Connection, seed_terms: list[str], limit: int = 24) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []

    def add(row: sqlite3.Row, source_table: str) -> None:
        node_id = str(row["node_id"])
        if node_id in seen:
            return
        rows.append(
            {
                "id": node_id,
                "label": str(row["label"] or node_id),
                "type": str(row["type"] or "concept"),
                "count": int(row["count"] or 0),
                "confidence": float(row["confidence"] or 0.5),
                "source_table": source_table,
            }
        )
        seen.add(node_id)

    terms = [term for term in seed_terms if term]
    if _table_exists(conn, "nodes"):
        for term in terms:
            candidates = conn.execute(
                """
                SELECT node_id, label, type, count, confidence
                FROM nodes
                WHERE node_id = ? OR lower(label) LIKE ?
                ORDER BY count DESC, confidence DESC
                LIMIT 8
                """,
                (_slug(term), f"%{term.lower()}%"),
            ).fetchall()
            for candidate in candidates:
                add(candidate, "nodes")
                if len(rows) >= limit:
                    return rows

    if _table_exists(conn, "synaptic_nodes"):
        for term in terms:
            candidates = conn.execute(
                """
                SELECT node_id, label, type, count, confidence
                FROM synaptic_nodes
                WHERE node_id = ? OR lower(label) LIKE ?
                ORDER BY count DESC, confidence DESC
                LIMIT 8
                """,
                (_slug(term), f"%{term.lower()}%"),
            ).fetchall()
            for candidate in candidates:
                add(candidate, "synaptic_nodes")
                if len(rows) >= limit:
                    return rows

    if rows:
        return rows
    if terms:
        return rows

    if _table_exists(conn, "nodes"):
        for candidate in conn.execute(
            "SELECT node_id, label, type, count, confidence FROM nodes ORDER BY count DESC, confidence DESC LIMIT ?",
            (min(6, limit),),
        ).fetchall():
            add(candidate, "nodes")
    elif _table_exists(conn, "synaptic_nodes"):
        for candidate in conn.execute(
            "SELECT node_id, label, type, count, confidence FROM synaptic_nodes ORDER BY count DESC, confidence DESC LIMIT ?",
            (min(6, limit),),
        ).fetchall():
            add(candidate, "synaptic_nodes")
    return rows


def _fetch_frontier_edges(
    conn: sqlite3.Connection,
    frontier: set[str],
    *,
    remaining_edges: int,
    per_depth_limit: int,
) -> list[dict[str, Any]]:
    if not frontier or remaining_edges <= 0:
        return []
    marks = _placeholders(frontier)
    params = (*frontier, *frontier, min(remaining_edges, per_depth_limit))
    rows: list[dict[str, Any]] = []

    if _table_exists(conn, "relation_stats"):
        for row in conn.execute(
            f"""
            SELECT source, relation, target, count, confidence, p_target_given_source AS probability
            FROM relation_stats
            WHERE source IN ({marks}) OR target IN ({marks})
            ORDER BY confidence DESC, p_target_given_source DESC, count DESC
            LIMIT ?
            """,
            params,
        ).fetchall():
            rows.append(
                {
                    "source": str(row["source"]),
                    "relation": str(row["relation"]),
                    "target": str(row["target"]),
                    "count": int(row["count"] or 0),
                    "confidence": float(row["confidence"] or 0.5),
                    "weight": float(row["probability"] or 0.0),
                    "source_table": "relation_stats",
                }
            )

    if _table_exists(conn, "synaptic_edges") and len(rows) < remaining_edges:
        extra_limit = max(0, min(remaining_edges, per_depth_limit) - len(rows))
        if extra_limit:
            for row in conn.execute(
                f"""
                SELECT source, relation, target, count, confidence, weight
                FROM synaptic_edges
                WHERE source IN ({marks}) OR target IN ({marks})
                ORDER BY weight DESC, confidence DESC, count DESC
                LIMIT ?
                """,
                (*frontier, *frontier, extra_limit),
            ).fetchall():
                rows.append(
                    {
                        "source": str(row["source"]),
                        "relation": str(row["relation"]),
                        "target": str(row["target"]),
                        "count": int(row["count"] or 0),
                        "confidence": float(row["confidence"] or 0.5),
                        "weight": float(row["weight"] or 0.0),
                        "source_table": "synaptic_edges",
                    }
                )
    return rows


def _fetch_nodes_by_id(conn: sqlite3.Connection, node_ids: list[str]) -> list[dict[str, Any]]:
    if not node_ids:
        return []
    marks = _placeholders(node_ids)
    by_id: dict[str, dict[str, Any]] = {}
    if _table_exists(conn, "nodes"):
        for row in conn.execute(
            f"""
            SELECT n.node_id, n.label, n.type, n.count, n.confidence, v.dim0, v.dim1, v.dim2
            FROM nodes n
            LEFT JOIN vector_rows v ON v.node_id = n.node_id
            WHERE n.node_id IN ({marks})
            """,
            tuple(node_ids),
        ).fetchall():
            by_id[str(row["node_id"])] = {
                "id": str(row["node_id"]),
                "label": str(row["label"] or row["node_id"]),
                "type": str(row["type"] or "concept"),
                "count": int(row["count"] or 0),
                "confidence": float(row["confidence"] or 0.5),
                "x": float(row["dim0"] or 0.0),
                "y": float(row["dim1"] or 0.0),
                "z": float(row["dim2"] or 0.0),
                "source_table": "nodes",
            }
    if _table_exists(conn, "synaptic_nodes"):
        missing = [node_id for node_id in node_ids if node_id not in by_id]
        if missing:
            marks = _placeholders(missing)
            for row in conn.execute(
                f"""
                SELECT node_id, label, type, count, confidence
                FROM synaptic_nodes
                WHERE node_id IN ({marks})
                """,
                tuple(missing),
            ).fetchall():
                node_id = str(row["node_id"])
                by_id[node_id] = {
                    "id": node_id,
                    "label": str(row["label"] or node_id),
                    "type": str(row["type"] or "concept"),
                    "count": int(row["count"] or 0),
                    "confidence": float(row["confidence"] or 0.5),
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0,
                    "source_table": "synaptic_nodes",
                }
    for node_id in node_ids:
        by_id.setdefault(
            node_id,
            {
                "id": node_id,
                "label": node_id,
                "type": "concept",
                "count": 0,
                "confidence": 0.35,
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "source_table": "edge_only",
            },
        )
    return [by_id[node_id] for node_id in node_ids if node_id in by_id]


def query_lazy_subgraph(
    seed_terms: list[str] | set[str],
    memory_dir: str | Path = DEFAULT_MEMORY_DIR,
    *,
    max_depth: int = 3,
    max_nodes: int = 512,
    max_edges: int = 2048,
) -> dict[str, Any]:
    """Fetch only a local graph window around seed terms.

    This is the production query path for GraphRAG. It never loads ontology JSON
    or the full graph into process memory; SQLite returns only bounded frontier
    rows for the active query.
    """

    tier_nodes, tier_edges, tier_depth, tier = _runtime_graph_limits()
    max_depth = max(1, min(tier_depth, int(max_depth)))
    max_nodes = max(1, min(tier_nodes, int(max_nodes)))
    max_edges = max(1, min(tier_edges, int(max_edges)))
    if ghost_store_available(memory_dir):
        ghost = query_ghost_rag_context(
            " ".join(str(term) for term in seed_terms),
            memory_dir,
            max_depth=max_depth,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )
        edges = [
            {
                "source_hash": edge["source_hash"],
                "target_hash": edge["target_hash"],
                "weight": edge["weight"],
            }
            for edge in ghost.get("edges", [])
        ]
        return {
            "state": ghost.get("state", "completed"),
            "system_state": "GHOST SHELL ACTIVE",
            "nodes": ghost.get("nodes", []),
            "edges": edges,
            "graph_paths": ghost.get("graph_paths", []),
            "expanded_terms": set(seed_terms),
            "seed_node_ids": ghost.get("active_hashes", []),
            "active_hashes": ghost.get("active_hashes", []),
            "active_hash_scores": ghost.get("active_hash_scores", {}),
            "payload_docs": ghost.get("payload_docs", []),
            "fetch_logs": ghost.get("fetch_logs", []),
            "ghost_shell": ghost.get("telemetry", ghost_status(memory_dir)),
            "limits": {"max_depth": max_depth, "max_nodes": max_nodes, "max_edges": max_edges, "hardware_tier": tier},
        }
    conn = _connect_readonly(memory_dir)
    if not conn:
        return {
            "state": "no_memory",
            "nodes": [],
            "edges": [],
            "graph_paths": [],
            "expanded_terms": set(seed_terms),
            "seed_node_ids": [],
            "limits": {"max_depth": max_depth, "max_nodes": max_nodes, "max_edges": max_edges, "hardware_tier": tier},
        }

    try:
        seed_nodes = _fetch_seed_nodes(conn, list(seed_terms), limit=min(24, max_nodes))
        seed_ids = [node["id"] for node in seed_nodes]
        visited: dict[str, float] = {node["id"]: 1.0 + float(node.get("confidence") or 0.5) for node in seed_nodes}
        frontier = set(seed_ids)
        edges: dict[str, dict[str, Any]] = {}
        per_depth_limit = max(64, max_edges // max(1, max_depth))

        for depth in range(max_depth):
            if not frontier or len(visited) >= max_nodes or len(edges) >= max_edges:
                break
            frontier_edges = _fetch_frontier_edges(
                conn,
                frontier,
                remaining_edges=max_edges - len(edges),
                per_depth_limit=per_depth_limit,
            )
            next_frontier: set[str] = set()
            for edge in frontier_edges:
                edge_id = f"{edge['source']}:{edge['relation']}:{edge['target']}"
                if edge_id in edges:
                    continue
                edges[edge_id] = edge
                edge_score = (float(edge.get("confidence") or 0.5) + float(edge.get("weight") or 0.0)) / (depth + 1)
                for node_id in (edge["source"], edge["target"]):
                    if node_id not in visited and len(visited) < max_nodes:
                        visited[node_id] = edge_score
                        next_frontier.add(node_id)
                    elif node_id in visited:
                        visited[node_id] = max(visited[node_id], edge_score)
            frontier = next_frontier

        sorted_ids = [
            node_id
            for node_id, _score in sorted(visited.items(), key=lambda item: (-item[1], item[0]))[:max_nodes]
        ]
        nodes = _fetch_nodes_by_id(conn, sorted_ids)
        node_id_set = {node["id"] for node in nodes}
        kept_edges = [
            edge
            for edge in sorted(edges.values(), key=lambda item: (-float(item.get("confidence") or 0), -float(item.get("weight") or 0)))
            if edge["source"] in node_id_set and edge["target"] in node_id_set
        ][:max_edges]
        expanded_terms = set(seed_terms)
        for node in nodes[:64]:
            expanded_terms.update(_tokens(f"{node['id']} {node['label']} {node['type']}"))
        for edge in kept_edges[:128]:
            expanded_terms.update(_tokens(f"{edge['source']} {edge['relation']} {edge['target']}"))
        return {
            "state": "completed",
            "nodes": nodes,
            "edges": kept_edges,
            "graph_paths": [[edge["source"], edge["relation"], edge["target"]] for edge in kept_edges[:8]],
            "expanded_terms": expanded_terms,
            "seed_node_ids": seed_ids,
            "limits": {"max_depth": max_depth, "max_nodes": max_nodes, "max_edges": max_edges, "hardware_tier": tier},
        }
    finally:
        conn.close()


def query_lazy_chunks(
    query: str,
    expanded_terms: set[str],
    memory_dir: str | Path = DEFAULT_MEMORY_DIR,
    *,
    limit: int = 256,
) -> list[dict[str, Any]]:
    """Return bounded candidate chunks from SQLite; ranking stays in retriever."""

    if ghost_store_available(memory_dir):
        ghost = query_ghost_rag_context(
            query,
            memory_dir,
            max_depth=3,
            max_nodes=512,
            max_edges=2048,
            active_hash_limit=min(22, max(1, int(limit))),
        )
        chunks: list[dict[str, Any]] = []
        for doc in ghost.get("payload_docs", []):
            text = str(doc.get("text") or "")
            token_counts = Counter(_tokens(text))
            if not token_counts:
                continue
            chunks.append(
                {
                    "doc_id": str(doc.get("doc_id") or "payload-vault"),
                    "chunk_id": str(doc.get("chunk_id") or f"{doc.get('hash_key')}#payload"),
                    "path": str(doc.get("path") or f"payload-vault://{doc.get('hash_key')}"),
                    "text": text,
                    "tokens": token_counts,
                    "token_total": sum(token_counts.values()),
                    "hash_key": doc.get("hash_key"),
                    "metadata": doc.get("metadata", {}),
                    "score": float(doc.get("score") or 0.0),
                    "temporal": doc.get("temporal"),
                    "temporal_rank": doc.get("temporal_rank"),
                    "temporal_weight": float(doc.get("score") or 0.0),
                    "ghost_shell": ghost.get("telemetry", {}),
                }
            )
        chunks.sort(key=lambda item: (-float(item.get("temporal_weight") or 0.0), item["chunk_id"]))
        return chunks

    conn = _connect_readonly(memory_dir)
    if not conn:
        return []
    try:
        if not _table_exists(conn, "chunks"):
            return []
        terms = [term for term in _tokens(query) + sorted(expanded_terms) if len(term) > 1]
        terms = list(dict.fromkeys(terms))[:10]
        if not terms:
            return []
        where = " OR ".join("lower(c.text) LIKE ?" for _ in terms)
        params = [f"%{term.lower()}%" for term in terms]
        rows = conn.execute(
            f"""
            SELECT c.chunk_id, c.doc_id, c.text, c.token_count, d.path
            FROM chunks c
            LEFT JOIN documents d ON d.doc_id = c.doc_id
            WHERE {where}
            ORDER BY c.token_count ASC, c.chunk_id ASC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        chunks: list[dict[str, Any]] = []
        for row in rows:
            text = str(row["text"] or "")
            token_counts = Counter(_tokens(text))
            if not token_counts:
                continue
            chunks.append(
                {
                    "doc_id": str(row["doc_id"]),
                    "chunk_id": str(row["chunk_id"]),
                    "path": str(row["path"] or f"memory://{row['doc_id']}"),
                    "text": text,
                    "tokens": token_counts,
                    "token_total": sum(token_counts.values()),
                }
            )
        return chunks
    finally:
        conn.close()


def graph_inventory(memory_dir: str | Path = DEFAULT_MEMORY_DIR, *, limit: int = 240) -> dict[str, Any]:
    conn = _connect_readonly(memory_dir)
    if not conn:
        return {"nodes": [], "edges": [], "state": "no_memory"}
    try:
        if not _table_exists(conn, "nodes"):
            return {"nodes": [], "edges": [], "state": "empty"}
        node_rows = conn.execute(
            """
            SELECT node_id, label, type, count, confidence
            FROM nodes
            ORDER BY count DESC, confidence DESC, node_id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        node_ids = [str(row["node_id"]) for row in node_rows]
        nodes = [
            {
                "id": str(row["node_id"]),
                "label": str(row["label"] or row["node_id"]),
                "type": str(row["type"] or "concept"),
                "count": int(row["count"] or 0),
                "confidence": float(row["confidence"] or 0.5),
            }
            for row in node_rows
        ]
        edges: list[dict[str, Any]] = []
        if node_ids and _table_exists(conn, "edges"):
            marks = _placeholders(node_ids)
            edge_rows = conn.execute(
                f"""
                SELECT source, relation, target, count, confidence
                FROM edges
                WHERE source IN ({marks}) AND target IN ({marks})
                ORDER BY count DESC, confidence DESC
                LIMIT ?
                """,
                (*node_ids, *node_ids, limit * 2),
            ).fetchall()
            edges = [
                {
                    "source": str(row["source"]),
                    "relation": str(row["relation"]),
                    "target": str(row["target"]),
                    "count": int(row["count"] or 0),
                    "confidence": float(row["confidence"] or 0.5),
                }
                for row in edge_rows
            ]
        return {"nodes": nodes, "edges": edges, "state": "completed"}
    finally:
        conn.close()


def graph_legend(memory_dir: str | Path = DEFAULT_MEMORY_DIR, *, limit: int = 12) -> dict[str, Any]:
    conn = _connect_readonly(memory_dir)
    if not conn:
        return {"types": [], "representatives": [], "edges": [], "state": "no_memory"}
    try:
        if not _table_exists(conn, "nodes"):
            return {"types": [], "representatives": [], "edges": [], "state": "empty"}
        type_rows = conn.execute(
            """
            SELECT type, COUNT(*) AS node_count
            FROM nodes
            GROUP BY type
            ORDER BY node_count DESC, type ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        representatives: list[dict[str, Any]] = []
        for row in type_rows:
            node = conn.execute(
                """
                SELECT node_id, label, type, count, confidence
                FROM nodes
                WHERE type = ?
                ORDER BY count DESC, confidence DESC
                LIMIT 1
                """,
                (row["type"],),
            ).fetchone()
            if node:
                representatives.append(
                    {
                        "id": str(node["node_id"]),
                        "label": str(node["label"] or node["node_id"]),
                        "type": str(node["type"] or "concept"),
                        "count": int(node["count"] or 0),
                        "confidence": float(node["confidence"] or 0.5),
                    }
                )
        types = [{"type": str(row["type"] or "concept"), "count": int(row["node_count"] or 0)} for row in type_rows]
        rep_ids = [node["id"] for node in representatives]
        edges: list[dict[str, Any]] = []
        if rep_ids and _table_exists(conn, "edges"):
            marks = _placeholders(rep_ids)
            edge_rows = conn.execute(
                f"""
                SELECT source, relation, target, count, confidence
                FROM edges
                WHERE source IN ({marks}) OR target IN ({marks})
                ORDER BY count DESC, confidence DESC
                LIMIT ?
                """,
                (*rep_ids, *rep_ids, limit * 2),
            ).fetchall()
            edges = [
                {
                    "source": str(row["source"]),
                    "relation": str(row["relation"]),
                    "target": str(row["target"]),
                    "count": int(row["count"] or 0),
                    "confidence": float(row["confidence"] or 0.5),
                }
                for row in edge_rows
            ]
        return {"types": types, "representatives": representatives, "edges": edges, "state": "completed"}
    finally:
        conn.close()
