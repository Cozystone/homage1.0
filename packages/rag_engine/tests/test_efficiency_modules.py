from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass

import pytest

from rag_engine.context_stub import UnconfiguredSsmContextRouter
from rag_engine.replay_daemon import consolidate_working_memory, ingest_working_memory_fragment
from rag_engine.self_correction import verify_fragment_consistency


@dataclass
class Fragment:
    fragment_id: str
    source_peer_id: str
    edges: list[dict]


@dataclass
class RuntimeConfig:
    max_edges: int = 128
    contradiction_threshold: float = 0.2
    trust_penalty_on_contradiction: float = 0.25
    trust_store_path: object = None
    replay_top_percent: float = 1.0
    replay_min_confidence: float = 0.5
    replay_max_edges_per_cycle: int = 32
    ssm_ingest_chunk_tokens: int = 4
    ssm_max_depth: int = 2


def _seed_contradiction_db(db_path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
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
    conn.execute(
        """
        INSERT INTO synaptic_edges(
          edge_id, source, relation, target, weight, count, confidence,
          evidence_doc_ids, created_at, updated_at, last_seen_at
        )
        VALUES ('e1', 'node-b', 'parent', 'node-a', 1.0, 12, 0.95, '[]', 'now', 'now', 'now')
        """
    )
    conn.commit()
    conn.close()


def test_self_correction_blocks_inverse_parent_conflict_and_lowers_trust(tmp_path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _seed_contradiction_db(memory_dir / "homage.db")
    config = RuntimeConfig(trust_store_path=tmp_path / "peer_trust.json")
    fragment = Fragment(
        fragment_id="frag-conflict",
        source_peer_id="peer-bad",
        edges=[{"source": "node-a", "relation": "parent", "target": "node-b", "confidence": 0.9}],
    )

    report = asyncio.run(verify_fragment_consistency(fragment, memory_dir=memory_dir, config=config))

    assert report.accepted is False
    assert report.contradiction_count == 1
    assert report.contradiction_score > config.contradiction_threshold
    trust = json.loads((tmp_path / "peer_trust.json").read_text(encoding="utf-8"))
    assert trust["peer-bad"] == pytest.approx(0.75)


def test_replay_consolidates_high_confidence_working_memory_edges(tmp_path) -> None:
    memory_dir = tmp_path / "memory"
    fragment = Fragment(
        fragment_id="frag-replay",
        source_peer_id="peer-good",
        edges=[
            {"source": "GraphRAG", "relation": "uses", "target": "KnowledgeGraph", "confidence": 0.92, "weight": 0.8}
        ],
    )

    ingest = asyncio.run(ingest_working_memory_fragment(fragment, memory_dir=memory_dir))
    summary = asyncio.run(consolidate_working_memory(memory_dir=memory_dir, config=RuntimeConfig(), force=True))

    assert ingest["working_edges"] == 1
    assert summary.state == "completed"
    assert summary.merged_edges == 1
    conn = sqlite3.connect(memory_dir / "homage.db")
    try:
        working_count = conn.execute("SELECT COUNT(*) FROM working_memory_edges").fetchone()[0]
        synaptic_count = conn.execute("SELECT COUNT(*) FROM synaptic_edges").fetchone()[0]
        trace_count = conn.execute("SELECT COUNT(*) FROM query_traces").fetchone()[0]
    finally:
        conn.close()
    assert working_count == 0
    assert synaptic_count == 1
    assert trace_count == 1


def test_ssm_context_router_chunks_stream_without_loading_model() -> None:
    router = UnconfiguredSsmContextRouter(config=RuntimeConfig(), backend_name="mamba_stub")

    route = router.build_route([{"doc_id": "doc-a", "text": "one two three four five six seven"}])

    assert route.complexity == "O(N)"
    assert route.max_window_tokens == 4
    assert [chunk.token_count for chunk in route.chunks] == [4, 3]
    assert route.total_tokens == 7
