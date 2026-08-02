from __future__ import annotations

import asyncio
import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .graph_store import DEFAULT_MEMORY_DIR, _memory_db_path


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _edge_id(source: str, relation: str, target: str) -> str:
    digest = hashlib.sha256(f"{source}\0{relation}\0{target}".encode("utf-8")).hexdigest()
    return f"edge-{digest[:32]}"


def _clamp01(value: Any, default: float = 0.5) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    return max(0.0, min(1.0, numeric))


def _normalize_relation(value: Any) -> str:
    return str(value or "related_to").strip().lower().replace(" ", "_") or "related_to"


def _connect_write(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> sqlite3.Connection:
    db_path = _memory_db_path(memory_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    _init_replay_schema(conn)
    return conn


def _init_replay_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS nodes (
          node_id TEXT PRIMARY KEY,
          label TEXT NOT NULL,
          type TEXT NOT NULL,
          count INTEGER NOT NULL DEFAULT 0,
          confidence REAL NOT NULL DEFAULT 0.5,
          evidence_doc_ids TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS edges (
          edge_id TEXT PRIMARY KEY,
          source TEXT NOT NULL,
          relation TEXT NOT NULL,
          target TEXT NOT NULL,
          confidence REAL NOT NULL,
          count INTEGER NOT NULL DEFAULT 1,
          evidence_doc_ids TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS relation_stats (
          source TEXT NOT NULL,
          relation TEXT NOT NULL,
          target TEXT NOT NULL,
          count INTEGER NOT NULL,
          p_target_given_source REAL NOT NULL,
          p_relation_given_source_target REAL NOT NULL,
          recency_weight REAL NOT NULL,
          source_quality_weight REAL NOT NULL,
          activation_weight REAL NOT NULL,
          confidence REAL NOT NULL,
          PRIMARY KEY(source, relation, target)
        );
        CREATE TABLE IF NOT EXISTS synaptic_nodes (
          node_id TEXT PRIMARY KEY,
          label TEXT NOT NULL,
          type TEXT NOT NULL,
          count INTEGER NOT NULL DEFAULT 0,
          confidence REAL NOT NULL DEFAULT 0.5,
          evidence_doc_ids TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS synaptic_edges (
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
        CREATE TABLE IF NOT EXISTS working_memory_edges (
          edge_id TEXT PRIMARY KEY,
          source TEXT NOT NULL,
          relation TEXT NOT NULL,
          target TEXT NOT NULL,
          confidence REAL NOT NULL,
          weight REAL NOT NULL,
          count INTEGER NOT NULL DEFAULT 1,
          source_peer_id TEXT,
          evidence_json TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS query_traces (
          trace_id INTEGER PRIMARY KEY AUTOINCREMENT,
          query TEXT NOT NULL,
          result_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS replay_events (
          event_id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_type TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_working_memory_edges_score
          ON working_memory_edges(confidence, weight, count);
        CREATE INDEX IF NOT EXISTS idx_synaptic_edges_source ON synaptic_edges(source);
        CREATE INDEX IF NOT EXISTS idx_synaptic_edges_target ON synaptic_edges(target);
        CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
        CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
        """
    )


@dataclass(frozen=True)
class ReplaySummary:
    state: str
    selected_edges: int
    merged_edges: int
    cleared_working_edges: int
    pseudo_traces: int
    idle_gate: str
    tier: str
    memory_db: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _config_value(config: Any | None, name: str, default: Any) -> Any:
    return getattr(config, name, default) if config is not None else default


def _edge_from_fragment(edge: dict[str, Any], source_peer_id: str) -> dict[str, Any] | None:
    source = str(edge.get("source") or edge.get("source_id") or edge.get("from") or edge.get("subject") or "").strip()
    target = str(edge.get("target") or edge.get("target_id") or edge.get("to") or edge.get("object") or "").strip()
    relation = _normalize_relation(edge.get("relation") or edge.get("predicate") or edge.get("type"))
    if not source or not target or source == target:
        return None
    confidence = _clamp01(edge.get("confidence", edge.get("weight", 0.5)))
    weight = max(0.01, _clamp01(edge.get("weight", confidence), confidence))
    return {
        "edge_id": _edge_id(source, relation, target),
        "source": source,
        "relation": relation,
        "target": target,
        "confidence": confidence,
        "weight": weight,
        "source_peer_id": source_peer_id,
        "evidence_json": json.dumps(edge.get("evidence") or edge.get("evidence_doc_ids") or [], ensure_ascii=False),
    }


def _upsert_working_edges(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    now = _now()
    for row in rows:
        conn.execute(
            """
            INSERT INTO working_memory_edges(
              edge_id, source, relation, target, confidence, weight, count,
              source_peer_id, evidence_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(edge_id) DO UPDATE SET
              confidence = MAX(working_memory_edges.confidence, excluded.confidence),
              weight = MIN(1.0, working_memory_edges.weight + excluded.weight * 0.1),
              count = working_memory_edges.count + 1,
              source_peer_id = COALESCE(excluded.source_peer_id, working_memory_edges.source_peer_id),
              updated_at = excluded.updated_at
            """,
            (
                row["edge_id"],
                row["source"],
                row["relation"],
                row["target"],
                row["confidence"],
                row["weight"],
                row["source_peer_id"],
                row["evidence_json"],
                now,
                now,
            ),
        )
    return len(rows)


async def ingest_working_memory_fragment(
    fragment: Any,
    *,
    memory_dir: str | Path = DEFAULT_MEMORY_DIR,
) -> dict[str, Any]:
    """Store a verified fragment as short-term working memory."""

    source_peer_id = str(getattr(fragment, "source_peer_id", ""))
    rows = [
        parsed
        for edge in list(getattr(fragment, "edges", []) or [])
        if isinstance(edge, dict)
        for parsed in [_edge_from_fragment(edge, source_peer_id)]
        if parsed is not None
    ]

    def write() -> dict[str, Any]:
        conn = _connect_write(memory_dir)
        try:
            inserted = _upsert_working_edges(conn, rows)
            conn.execute(
                "INSERT INTO replay_events(event_type, payload_json, created_at) VALUES (?, ?, ?)",
                (
                    "working_memory_ingest",
                    json.dumps(
                        {
                            "fragment_id": str(getattr(fragment, "fragment_id", "")),
                            "source_peer_id": source_peer_id,
                            "edge_count": inserted,
                        },
                        ensure_ascii=False,
                    ),
                    _now(),
                ),
            )
            conn.commit()
            return {"state": "completed", "working_edges": inserted}
        finally:
            conn.close()

    return await asyncio.to_thread(write)


def _select_replay_edges(conn: sqlite3.Connection, *, top_percent: float, min_confidence: float, max_edges: int) -> list[sqlite3.Row]:
    total = conn.execute(
        "SELECT COUNT(*) AS total FROM working_memory_edges WHERE confidence >= ?",
        (min_confidence,),
    ).fetchone()["total"]
    if total <= 0:
        return []
    selected = max(1, min(max_edges, math.ceil(total * top_percent)))
    return conn.execute(
        """
        SELECT edge_id, source, relation, target, confidence, weight, count, source_peer_id, evidence_json
        FROM working_memory_edges
        WHERE confidence >= ?
        ORDER BY (confidence * weight * (1 + count)) DESC, updated_at DESC
        LIMIT ?
        """,
        (min_confidence, selected),
    ).fetchall()


def _upsert_node(conn: sqlite3.Connection, node_id: str, confidence: float) -> None:
    now = _now()
    conn.execute(
        """
        INSERT INTO nodes(node_id, label, type, count, confidence, evidence_doc_ids)
        VALUES (?, ?, 'concept', 1, ?, '[]')
        ON CONFLICT(node_id) DO UPDATE SET
          count = nodes.count + 1,
          confidence = MAX(nodes.confidence, excluded.confidence)
        """,
        (node_id, node_id, confidence),
    )
    conn.execute(
        """
        INSERT INTO synaptic_nodes(node_id, label, type, count, confidence, evidence_doc_ids, created_at, updated_at)
        VALUES (?, ?, 'concept', 1, ?, '[]', ?, ?)
        ON CONFLICT(node_id) DO UPDATE SET
          count = synaptic_nodes.count + 1,
          confidence = MAX(synaptic_nodes.confidence, excluded.confidence),
          updated_at = excluded.updated_at
        """,
        (node_id, node_id, confidence, now, now),
    )


def _merge_long_term_edge(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    now = _now()
    confidence = _clamp01(row["confidence"])
    weight = _clamp01(row["weight"], confidence)
    replay_weight = max(0.01, confidence * weight)
    edge_id = str(row["edge_id"])
    source = str(row["source"])
    relation = str(row["relation"])
    target = str(row["target"])
    _upsert_node(conn, source, confidence)
    _upsert_node(conn, target, confidence)
    conn.execute(
        """
        INSERT INTO edges(edge_id, source, relation, target, confidence, count, evidence_doc_ids)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(edge_id) DO UPDATE SET
          confidence = MAX(edges.confidence, excluded.confidence),
          count = edges.count + excluded.count,
          evidence_doc_ids = excluded.evidence_doc_ids
        """,
        (edge_id, source, relation, target, confidence, int(row["count"] or 1), str(row["evidence_json"] or "[]")),
    )
    conn.execute(
        """
        INSERT INTO relation_stats(
          source, relation, target, count, p_target_given_source,
          p_relation_given_source_target, recency_weight, source_quality_weight,
          activation_weight, confidence
        )
        VALUES (?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?)
        ON CONFLICT(source, relation, target) DO UPDATE SET
          count = relation_stats.count + excluded.count,
          p_target_given_source = MIN(1.0, MAX(relation_stats.p_target_given_source, excluded.p_target_given_source)),
          p_relation_given_source_target = MIN(1.0, MAX(relation_stats.p_relation_given_source_target, excluded.p_relation_given_source_target)),
          recency_weight = 1.0,
          activation_weight = MIN(1.0, relation_stats.activation_weight + 0.05),
          confidence = MAX(relation_stats.confidence, excluded.confidence)
        """,
        (source, relation, target, int(row["count"] or 1), replay_weight, replay_weight, confidence, replay_weight, confidence),
    )
    conn.execute(
        """
        INSERT INTO synaptic_edges(
          edge_id, source, relation, target, weight, count, confidence,
          evidence_doc_ids, created_at, updated_at, last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(edge_id) DO UPDATE SET
          weight = MIN(1.0, synaptic_edges.weight + excluded.weight * 0.1),
          count = synaptic_edges.count + excluded.count,
          confidence = MAX(synaptic_edges.confidence, excluded.confidence),
          evidence_doc_ids = excluded.evidence_doc_ids,
          updated_at = excluded.updated_at,
          last_seen_at = excluded.last_seen_at
        """,
        (edge_id, source, relation, target, replay_weight, int(row["count"] or 1), confidence, str(row["evidence_json"] or "[]"), now, now, now),
    )
    conn.execute(
        """
        INSERT INTO query_traces(query, result_json, created_at)
        VALUES (?, ?, ?)
        """,
        (
            f"{source} {relation} {target}",
            json.dumps(
                {
                    "kind": "generative_replay_trace",
                    "source": source,
                    "relation": relation,
                    "target": target,
                    "confidence": confidence,
                    "weight": replay_weight,
                },
                ensure_ascii=False,
            ),
            now,
        ),
    )


def _capacity_from_broker(broker: Any | None) -> tuple[str, bool]:
    if broker is None:
        try:
            from app.services.edge_compute_broker import default_edge_compute_broker  # type: ignore

            broker = default_edge_compute_broker
        except Exception:
            return "unknown", False
    try:
        capacity = broker.current_capacity()
        return str(capacity.tier), bool(capacity.idle)
    except Exception:
        return "unknown", False


def _consolidate_sync(
    *,
    memory_dir: str | Path,
    config: Any | None,
    broker: Any | None,
    force: bool,
) -> ReplaySummary:
    tier, idle = _capacity_from_broker(broker)
    allowed_tiers = {"tier_s", "tier_1_m", "tier_1_s", "tier_2_a", "tier_1", "tier_2"}
    if not force and (not idle or tier not in allowed_tiers):
        return ReplaySummary(
            state="skipped_not_idle",
            selected_edges=0,
            merged_edges=0,
            cleared_working_edges=0,
            pseudo_traces=0,
            idle_gate="closed",
            tier=tier,
            memory_db=str(_memory_db_path(memory_dir)),
        )

    conn = _connect_write(memory_dir)
    try:
        top_percent = max(0.001, min(1.0, float(_config_value(config, "replay_top_percent", 0.05))))
        min_confidence = max(0.0, min(1.0, float(_config_value(config, "replay_min_confidence", 0.62))))
        max_edges = max(1, int(_config_value(config, "replay_max_edges_per_cycle", _config_value(config, "max_edges", 8192))))
        rows = _select_replay_edges(conn, top_percent=top_percent, min_confidence=min_confidence, max_edges=max_edges)
        if not rows:
            return ReplaySummary(
                state="empty",
                selected_edges=0,
                merged_edges=0,
                cleared_working_edges=0,
                pseudo_traces=0,
                idle_gate="open" if force or idle else "closed",
                tier=tier,
                memory_db=str(_memory_db_path(memory_dir)),
            )
        for row in rows:
            _merge_long_term_edge(conn, row)
        edge_ids = [str(row["edge_id"]) for row in rows]
        placeholders = ",".join("?" for _ in edge_ids)
        conn.execute(f"DELETE FROM working_memory_edges WHERE edge_id IN ({placeholders})", tuple(edge_ids))
        summary = ReplaySummary(
            state="completed",
            selected_edges=len(rows),
            merged_edges=len(rows),
            cleared_working_edges=len(rows),
            pseudo_traces=len(rows),
            idle_gate="forced" if force else "open",
            tier=tier,
            memory_db=str(_memory_db_path(memory_dir)),
        )
        conn.execute(
            "INSERT INTO replay_events(event_type, payload_json, created_at) VALUES (?, ?, ?)",
            ("generative_replay_consolidation", json.dumps(summary.to_dict(), ensure_ascii=False), _now()),
        )
        conn.commit()
        return summary
    finally:
        conn.close()


async def consolidate_working_memory(
    *,
    memory_dir: str | Path = DEFAULT_MEMORY_DIR,
    config: Any | None = None,
    broker: Any | None = None,
    force: bool = False,
) -> ReplaySummary:
    """Consolidate top-confidence working memory into long-term graph tables."""

    return await asyncio.to_thread(
        _consolidate_sync,
        memory_dir=memory_dir,
        config=config,
        broker=broker,
        force=force,
    )


class LocalGenerativeReplayDaemon:
    def __init__(
        self,
        *,
        memory_dir: str | Path = DEFAULT_MEMORY_DIR,
        config: Any | None = None,
        broker: Any | None = None,
        interval_seconds: float | None = None,
    ) -> None:
        self.memory_dir = memory_dir
        self.config = config
        self.broker = broker
        self.interval_seconds = float(interval_seconds or _config_value(config, "replay_interval_seconds", 300.0))
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.last_summary: ReplaySummary | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def run_once_if_idle(self, *, force: bool = False) -> ReplaySummary:
        self.last_summary = await consolidate_working_memory(
            memory_dir=self.memory_dir,
            config=self.config,
            broker=self.broker,
            force=force,
        )
        return self.last_summary

    async def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="homage-generative-replay")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
        self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once_if_idle()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(1.0, self.interval_seconds))
            except TimeoutError:
                continue
