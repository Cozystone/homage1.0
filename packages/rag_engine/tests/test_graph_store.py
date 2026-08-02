from __future__ import annotations

import sqlite3

from rag_engine import graph_store


def _seed_synaptic_db(db_path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE synaptic_nodes (
          node_id TEXT PRIMARY KEY,
          label TEXT NOT NULL,
          type TEXT NOT NULL,
          count INTEGER NOT NULL DEFAULT 0,
          confidence REAL NOT NULL DEFAULT 0.5,
          evidence_doc_ids TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE synaptic_edges (
          edge_id TEXT PRIMARY KEY,
          source TEXT NOT NULL,
          relation TEXT NOT NULL,
          target TEXT NOT NULL,
          weight REAL NOT NULL,
          count INTEGER NOT NULL DEFAULT 1,
          confidence REAL NOT NULL DEFAULT 0.5,
          evidence_doc_ids TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL
        );
        """
    )
    for index in range(12):
        conn.execute(
            """
            INSERT INTO synaptic_nodes(node_id, label, type, count, confidence, created_at, updated_at)
            VALUES (?, ?, 'concept', ?, 0.8, 'now', 'now')
            """,
            (f"node-{index}", f"GraphRAG node {index}", index + 1),
        )
    for index in range(11):
        conn.execute(
            """
            INSERT INTO synaptic_edges(edge_id, source, relation, target, weight, count, confidence, created_at, updated_at, last_seen_at)
            VALUES (?, ?, 'relates', ?, 1.0, 1, 0.9, 'now', 'now', 'now')
            """,
            (f"edge-{index}", f"node-{index}", f"node-{index + 1}"),
        )
    conn.commit()
    conn.close()


def test_lazy_subgraph_never_exceeds_runtime_hardware_limit(tmp_path, monkeypatch) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _seed_synaptic_db(memory_dir / "homage.db")
    monkeypatch.setattr(graph_store, "_runtime_graph_limits", lambda: (3, 2, 1, "test-tier"))

    result = graph_store.query_lazy_subgraph(["GraphRAG"], memory_dir, max_nodes=500, max_edges=500, max_depth=3)

    assert result["limits"] == {"max_depth": 1, "max_nodes": 3, "max_edges": 2, "hardware_tier": "test-tier"}
    assert len(result["nodes"]) <= 3
    assert len(result["edges"]) <= 2
