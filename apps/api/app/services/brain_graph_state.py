from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


RECENT_WINDOW_SECONDS = 600
STALE_AFTER_SECONDS = 600


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_seconds(value: Any, now: datetime) -> int | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return max(0, int((now - parsed).total_seconds()))


def _snapshot_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8", errors="ignore")).hexdigest()
    return f"{prefix}-{digest[:16]}"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return bool(row)


def _count_table(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _max_time(conn: sqlite3.Connection, table: str, column: str, where_sql: str = "", params: tuple[Any, ...] = ()) -> str | None:
    if not _table_exists(conn, table):
        return None
    row = conn.execute(f"SELECT MAX({column}) AS value FROM {table} {where_sql}", params).fetchone()
    return str(row["value"]) if row and row["value"] else None


def _event_count_since(
    conn: sqlite3.Connection,
    table: str,
    event_types: tuple[str, ...],
    since_iso: str,
    *,
    time_column: str = "created_at",
) -> int:
    if not event_types or not _table_exists(conn, table):
        return 0
    placeholders = ",".join("?" for _ in event_types)
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS value
        FROM {table}
        WHERE event_type IN ({placeholders}) AND {time_column} >= ?
        """,
        (*event_types, since_iso),
    ).fetchone()
    return int(row["value"] if row else 0)


def _ingested_file_count_since(conn: sqlite3.Connection, since_iso: str) -> int:
    if not _table_exists(conn, "ingested_files"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS value
        FROM ingested_files
        WHERE status = 'ingested' AND ingested_at >= ?
        """,
        (since_iso,),
    ).fetchone()
    return int(row["value"] if row else 0)


def _learning_event_count_since(conn: sqlite3.Connection, event_types: tuple[str, ...], since_iso: str) -> int:
    return _event_count_since(conn, "learning_events", event_types, since_iso)


def _build_empty_states(now: datetime, daemon: dict[str, Any] | None = None) -> dict[str, Any]:
    loaded_at = _iso(now)
    daemon = daemon or {}
    ingest_status = "unavailable" if not daemon else str(daemon.get("stream_state") or daemon.get("state") or "idle").lower()
    return {
        "cloud": {
            "schema": "atanor.cloud-brain-graph-state.v1",
            "source": "unavailable",
            "public_cloud_backend_enabled": False,
            "local_daemon_backed": False,
            "cloud_total_nodes": 0,
            "cloud_total_relations": 0,
            "cloud_graph_version": "ghost-0-0-0",
            "cloud_snapshot_id": _snapshot_id("cloud", loaded_at, 0, 0),
            "cloud_last_ingest_at": None,
            "cloud_last_patch_merge_at": None,
            "cloud_nodes_added_recently": 0,
            "cloud_relations_added_recently": 0,
            "cloud_fragments_merged_recently": 0,
            "cloud_sources_rejected_recently": 0,
            "ingest_status": ingest_status,
            "sync_status": "unavailable",
            "graph_state_loaded_at": loaded_at,
            "graph_snapshot_created_at": None,
            "graph_state_age_seconds": None,
            "is_stale": False,
            "is_growing": False,
            "real_counts": True,
            "fake_growth_counters": False,
            "growth_explanation": "Cloud Brain graph store is unavailable; no growth telemetry can be reported.",
        },
        "local": {
            "schema": "atanor.local-brain-graph-state.v1",
            "source": "unavailable",
            "local_total_nodes": 0,
            "local_total_relations": 0,
            "local_snapshot_id": _snapshot_id("local", loaded_at, 0, 0),
            "local_last_learning_at": daemon.get("last_tick_at"),
            "local_nodes_added_recently": 0,
            "local_relations_added_recently": 0,
        },
    }


def build_brain_graph_states(
    *,
    daemon: dict[str, Any] | None,
    memory: dict[str, Any] | None,
    now: datetime | None = None,
    recent_window_seconds: int = RECENT_WINDOW_SECONDS,
    stale_after_seconds: int = STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    """Return separate Cloud Brain and Local Brain graph telemetry.

    In local companion mode, Cloud Brain is not a deployed public graph backend.
    The operator uses a local-daemon-backed Cloud Brain control-plane mirror,
    so the returned payload explicitly labels that source and never invents
    growth counters.
    """

    now = now or _utc_now()
    loaded_at = _iso(now)
    daemon = daemon or {}
    memory = memory or {}
    db_path = Path(str(memory.get("db_path") or "data/memory/homage.db"))
    if not db_path.exists():
        return _build_empty_states(now, daemon)

    since_iso = _iso(now - timedelta(seconds=max(1, int(recent_window_seconds))))
    with _connect(db_path) as conn:
        ghost_nodes = _count_table(conn, "ghost_nodes")
        ghost_edges = _count_table(conn, "ghost_edges")
        payloads = _count_table(conn, "payload_vault")
        local_nodes = _count_table(conn, "nodes")
        local_edges = _count_table(conn, "edges")
        memory_events = _count_table(conn, "memory_events")
        recent_cloud_nodes = _event_count_since(conn, "memory_events", ("node_imported",), since_iso)
        recent_cloud_edges = _event_count_since(conn, "memory_events", ("edge_imported",), since_iso)
        recent_fragments = _ingested_file_count_since(conn, since_iso) + _event_count_since(
            conn,
            "memory_events",
            ("document_imported", "chunk_indexed"),
            since_iso,
        )
        rejected_sources = _learning_event_count_since(
            conn,
            ("source_rejected", "raw_file_rejected", "datagate_rejected"),
            since_iso,
        )
        last_ingest_at = _max_time(conn, "ingested_files", "ingested_at", "WHERE status = 'ingested'")
        last_document_import_at = _max_time(conn, "memory_events", "created_at", "WHERE event_type = ?", ("document_imported",))
        last_patch_at = _max_time(
            conn,
            "memory_events",
            "created_at",
            "WHERE event_type IN ('node_imported','edge_imported','document_imported','chunk_indexed')",
        )
        last_learning_at = _max_time(conn, "learning_events", "created_at")

    cloud_total_nodes = ghost_nodes or int(memory.get("ghost_hash_count") or memory.get("node_count") or 0)
    cloud_total_relations = ghost_edges or int(memory.get("ghost_edge_count") or memory.get("edge_count") or 0)
    local_brain_initialized = os.getenv("ATANOR_LOCAL_BRAIN_INITIALIZED", "").strip().lower() in {"1", "true", "yes", "on"}
    # The current SQLite Ghost Shell is the local-daemon-backed Cloud Brain mirror.
    # Do not present that shared/public mirror as the user's private Local Brain.
    local_total_nodes = (local_nodes or int(memory.get("node_count") or 0)) if local_brain_initialized else 0
    local_total_relations = (local_edges or int(memory.get("edge_count") or 0)) if local_brain_initialized else 0
    last_ingest_at = last_ingest_at or last_document_import_at or daemon.get("last_tick_at")
    graph_snapshot_created_at = last_patch_at or memory.get("built_at") or last_ingest_at
    graph_age = _age_seconds(graph_snapshot_created_at, now)
    is_growing = recent_cloud_nodes > 0 or recent_cloud_edges > 0 or recent_fragments > 0
    is_stale = bool(graph_age is not None and graph_age > stale_after_seconds and not is_growing)
    daemon_alive = bool(daemon.get("worker_alive") or daemon.get("desired_running"))
    queue_state = str(daemon.get("queue_state") or "").upper()
    stream_state = str(daemon.get("stream_state") or daemon.get("state") or "idle")

    if is_growing:
        ingest_status = "running"
        explanation = "Cloud Brain mirror is receiving real graph patches from the local companion."
    elif daemon_alive and "WAITING" in queue_state:
        ingest_status = "listening"
        explanation = "Continuous ingestion is awake, but no new payloads arrived in the recent window."
    elif daemon_alive:
        ingest_status = stream_state.lower()
        explanation = "Learning daemon is alive; current tick did not create new Cloud Brain graph patches."
    else:
        ingest_status = "idle"
        explanation = "Cloud Brain ingestion worker is not running, so the graph cannot grow."

    cloud_version = f"ghost-{cloud_total_nodes}-{cloud_total_relations}-{memory_events}"
    cloud_snapshot = _snapshot_id("cloud", cloud_version, graph_snapshot_created_at, payloads)
    local_snapshot = _snapshot_id("local", local_total_nodes, local_total_relations, last_learning_at or memory.get("built_at"))

    return {
        "cloud": {
            "schema": "atanor.cloud-brain-graph-state.v1",
            "source": "local_daemon_backed_cloud_brain",
            "public_cloud_backend_enabled": False,
            "local_daemon_backed": True,
            "cloud_total_nodes": cloud_total_nodes,
            "cloud_total_relations": cloud_total_relations,
            "cloud_graph_version": cloud_version,
            "cloud_snapshot_id": cloud_snapshot,
            "cloud_last_ingest_at": last_ingest_at,
            "cloud_last_patch_merge_at": last_patch_at,
            "cloud_nodes_added_recently": recent_cloud_nodes,
            "cloud_relations_added_recently": recent_cloud_edges,
            "cloud_fragments_merged_recently": recent_fragments,
            "cloud_sources_rejected_recently": rejected_sources,
            "ingest_status": ingest_status,
            "sync_status": "local_daemon_backed" if daemon_alive else "local_daemon_unavailable",
            "graph_state_loaded_at": loaded_at,
            "graph_snapshot_created_at": graph_snapshot_created_at,
            "graph_state_age_seconds": graph_age,
            "is_stale": is_stale,
            "is_growing": is_growing,
            "real_counts": True,
            "fake_growth_counters": False,
            "growth_explanation": explanation,
            "payload_vault_records": payloads,
        },
        "local": {
            "schema": "atanor.local-brain-graph-state.v1",
            "source": "private_local_brain" if local_brain_initialized else "not_initialized",
            "local_brain_initialized": local_brain_initialized,
            "local_brain_empty": not local_brain_initialized,
            "local_total_nodes": local_total_nodes,
            "local_total_relations": local_total_relations,
            "local_snapshot_id": local_snapshot,
            "local_last_learning_at": (last_learning_at or daemon.get("last_tick_at") or memory.get("built_at")) if local_brain_initialized else None,
            "local_nodes_added_recently": recent_cloud_nodes if local_brain_initialized else 0,
            "local_relations_added_recently": recent_cloud_edges if local_brain_initialized else 0,
            "cloud_mirror_nodes_excluded": cloud_total_nodes,
            "cloud_mirror_relations_excluded": cloud_total_relations,
        },
        "audit": {
            "operator_graph_source": "local-daemon-backed Cloud Brain control-plane mirror",
            "render_graph_endpoint": "/api/graph/subgraph",
            "render_graph_store": "local companion SQLite Ghost Shell mirror",
            "public_cloud_backend_enabled": False,
            "uses_fallback_sample_graph": False,
            "uses_fake_growth_counters": False,
            "recent_window_seconds": recent_window_seconds,
            "stale_after_seconds": stale_after_seconds,
        },
    }
