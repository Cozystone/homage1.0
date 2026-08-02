from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .memory import build_memory, memory_status


DEFAULT_RAW_DIR = "data/raw"
DEFAULT_CLEANED_DIR = "data/cleaned"
DEFAULT_ONTOLOGY_DIR = "data/ontology"
DEFAULT_MEMORY_DIR = "data/memory"
DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_DECAY_INTERVAL_SECONDS = 3600
DEFAULT_DECAY_FACTOR = 0.95
DEFAULT_PRUNE_THRESHOLD = 0.05
DEFAULT_POTENTIATION_INCREMENT = 0.1
MIN_DISK_FREE_GB = 20.0
MIN_RAM_AVAILABLE_GB = 1.5
SUPPORTED_RAW_EXTENSIONS = {".txt", ".md"}
AUTO_FLUSH_FRAGMENT_COUNT = 50
AUTO_FLUSH_SECONDS = 180.0
ACTIVE_LEARNING_STATES = {"INGESTING", "BAKING", "EXTRACTING", "GRAPH_GROWING", "INDEXING", "PERSISTENT_APPEND_APPLIED"}
IDLE_WAITING_STATES = {"WAITING_FOR_START", "WAITING_FOR_PAYLOADS", "WAITING_FOR_RESOURCES", "IDLE"}

_lock = threading.RLock()
_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None
_worker_memory_dir: str | None = None


def _env_truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _daemon_self_heal_enabled() -> bool:
    if _env_truthy("ATANOR_DISABLE_DAEMON_SELF_HEAL"):
        return False
    return True


def _web_seed_on_tick_enabled() -> bool:
    return _env_truthy("ATANOR_WEB_SEED_FEEDER_ON_TICK")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _memory_root(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> Path:
    return Path(memory_dir)


def _resolved_memory_dir(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> str:
    return str(Path(memory_dir).resolve())


def _db_path(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> Path:
    return _memory_root(memory_dir) / "homage.db"


def _concept_db_path(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> Path:
    return _memory_root(memory_dir) / "canonical_concepts.sqlite3"


def _state_path(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> Path:
    return _memory_root(memory_dir) / "daemon_state.json"


def _checkpoint_dir(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> Path:
    return _memory_root(memory_dir) / "daemon_checkpoints"


def _default_state() -> dict[str, Any]:
    return {
        "mode": "local-daemon",
        "module": "hippocampus-continuous-learning",
        "state": "idle",
        "desired_running": False,
        "resume_after_reboot": True,
        "resume_needed": False,
        "worker_alive": False,
        "started_at": None,
        "last_heartbeat_at": None,
        "last_tick_at": None,
        "last_checkpoint_at": None,
        "last_decay_at": None,
        "last_input_fingerprint": None,
        "last_round_action": None,
        "last_round_message": "No long-running local learner has been started.",
        "stream_state": "PAUSED",
        "queue_state": "WAITING_FOR_START",
        "ingestion_mode": "persistent_append",
        "last_error": None,
        "interval_seconds": DEFAULT_INTERVAL_SECONDS,
        "decay_interval_seconds": DEFAULT_DECAY_INTERVAL_SECONDS,
        "decay_factor": DEFAULT_DECAY_FACTOR,
        "prune_threshold": DEFAULT_PRUNE_THRESHOLD,
        "potentiation_increment": DEFAULT_POTENTIATION_INCREMENT,
        "total_runtime_seconds": 0,
        "daemon_uptime_seconds": 0,
        "active_learning_seconds": 0,
        "idle_waiting_seconds": 0,
        "cumulative_learning_seconds": 0,
        "cumulative_runtime_seconds": 0,
        "display_learning_seconds": 0,
        "timing_state": "IDLE",
        "last_timing_update_at": None,
        "total_rounds": 0,
        "learned_rounds": 0,
        "idle_rounds": 0,
        "ingested_file_count": 0,
        "last_ingested_files": [],
        "latest_event_count": 0,
        "latest_node_count": 0,
        "latest_edge_count": 0,
        "synaptic_node_count": 0,
        "synaptic_edge_count": 0,
        "avg_synaptic_weight": 0.0,
        "resource_warning": None,
        "raw_dir": DEFAULT_RAW_DIR,
        "cleaned_dir": DEFAULT_CLEANED_DIR,
        "ontology_dir": DEFAULT_ONTOLOGY_DIR,
        "watch_dirs": [DEFAULT_RAW_DIR, DEFAULT_CLEANED_DIR, DEFAULT_ONTOLOGY_DIR],
        "neo4j": {
            "enabled": bool(os.environ.get("NEO4J_URI")),
            "available": False,
            "last_error": None,
        },
        "reboot_resilience": {
            "state_file": str(_state_path()),
            "checkpoint_dir": str(_checkpoint_dir()),
            "sqlite_wal": str(_db_path()),
            "heartbeat_interval_seconds": DEFAULT_INTERVAL_SECONDS,
            "checkpoint_interval_seconds": 300,
            "resume_contract": "Restart local FastAPI and call /api/learning/daemon/resume; the daemon resumes from SQLite WAL, events.jsonl, and daemon_state.json.",
        },
        "llm_policy": {
            "external_llm": False,
            "local_quantized_llm": False,
            "pretrained_generation_weights": False,
        },
    }


def _read_state(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    path = _state_path(memory_dir)
    if not path.exists():
        return _default_state()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        loaded = {}
    state = _default_state()
    state.update(loaded)
    state["neo4j"] = {**_default_state()["neo4j"], **dict(loaded.get("neo4j") or {})}
    state["reboot_resilience"] = {
        **_default_state()["reboot_resilience"],
        **dict(loaded.get("reboot_resilience") or {}),
    }
    state["llm_policy"] = {
        **_default_state()["llm_policy"],
        **dict(loaded.get("llm_policy") or {}),
    }
    raw_dir = str(state.get("raw_dir") or DEFAULT_RAW_DIR)
    cleaned_dir = str(state.get("cleaned_dir") or DEFAULT_CLEANED_DIR)
    ontology_dir = str(state.get("ontology_dir") or DEFAULT_ONTOLOGY_DIR)
    watch_dirs = list(state.get("watch_dirs") or [])
    for required in [raw_dir, cleaned_dir, ontology_dir]:
        if required not in watch_dirs:
            watch_dirs.append(required)
    state["watch_dirs"] = watch_dirs
    _normalize_timing_fields(state)
    return state


def _write_state(state: dict[str, Any], memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> None:
    root = _memory_root(memory_dir)
    root.mkdir(parents=True, exist_ok=True)
    target = _state_path(memory_dir)
    temp = target.with_name(f"{target.stem}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(5):
        try:
            temp.replace(target)
            return
        except PermissionError:
            time.sleep(0.025 * (attempt + 1))
    pending = target.with_name(f"{target.stem}.pending.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.json")
    try:
        temp.replace(pending)
    except OSError:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _connect(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> sqlite3.Connection:
    root = _memory_root(memory_dir)
    root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path(memory_dir))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    _init_synaptic_schema(conn)
    return conn


def _init_synaptic_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
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
        CREATE TABLE IF NOT EXISTS ingested_files (
          file_fingerprint TEXT PRIMARY KEY,
          original_path TEXT NOT NULL,
          cleaned_path TEXT NOT NULL,
          byte_count INTEGER NOT NULL,
          node_count INTEGER NOT NULL DEFAULT 0,
          edge_count INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL,
          ingested_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS learning_events (
          event_id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_type TEXT NOT NULL,
          subject_id TEXT,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_synaptic_edges_source ON synaptic_edges(source);
        CREATE INDEX IF NOT EXISTS idx_synaptic_edges_target ON synaptic_edges(target);
        CREATE INDEX IF NOT EXISTS idx_synaptic_edges_weight ON synaptic_edges(weight);
        """
    )


def _worker_alive() -> bool:
    return bool(_worker_thread and _worker_thread.is_alive())


def _worker_matches(memory_dir: str | Path) -> bool:
    return _worker_alive() and _worker_memory_dir == _resolved_memory_dir(memory_dir)


def _spawn_worker_locked(memory_dir: str | Path, interval_seconds: int) -> None:
    global _worker_thread, _worker_memory_dir
    interval_seconds = max(5, min(3600, int(interval_seconds or DEFAULT_INTERVAL_SECONDS)))
    resolved_memory_dir = _resolved_memory_dir(memory_dir)
    if _worker_alive() and _worker_memory_dir == resolved_memory_dir:
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(
        target=_worker_entry,
        args=(resolved_memory_dir, interval_seconds),
        daemon=True,
        name="homage-hippocampus-daemon",
    )
    _worker_memory_dir = resolved_memory_dir
    _worker_thread.start()


def _json_set(existing: str | None, additions: list[str] | set[str] | tuple[str, ...]) -> str:
    try:
        current = set(json.loads(existing or "[]"))
    except json.JSONDecodeError:
        current = set()
    current.update(str(item) for item in additions if str(item))
    return json.dumps(sorted(current), ensure_ascii=False)


def _write_learning_event(conn: sqlite3.Connection, event_type: str, subject_id: str | None, payload: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO learning_events(event_type, subject_id, payload_json, created_at) VALUES (?, ?, ?, ?)",
        (event_type, subject_id, json.dumps(payload, ensure_ascii=False), utc_now_iso()),
    )


class _AutoFlush:
    def __init__(self, conn: sqlite3.Connection, *, max_fragments: int = AUTO_FLUSH_FRAGMENT_COUNT, max_seconds: float = AUTO_FLUSH_SECONDS) -> None:
        self.conn = conn
        self.max_fragments = max(1, int(max_fragments))
        self.max_seconds = max(1.0, float(max_seconds))
        self.pending = 0
        self.last_flush = time.monotonic()
        self.flush_count = 0

    def mark(self, fragments: int = 1) -> None:
        self.pending += max(1, int(fragments))
        now = time.monotonic()
        if self.pending >= self.max_fragments or now - self.last_flush >= self.max_seconds:
            self.flush()

    def flush(self) -> None:
        if self.pending <= 0:
            return
        self.conn.commit()
        self.pending = 0
        self.last_flush = time.monotonic()
        self.flush_count += 1


def _file_fingerprint(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    digest = hashlib.sha256()
    digest.update(path.name.encode("utf-8", errors="ignore"))
    digest.update(len(data).to_bytes(8, "big", signed=False))
    digest.update(hashlib.sha256(data).digest())
    return {
        "fingerprint": digest.hexdigest(),
        "byte_count": len(data),
    }


def _input_fingerprint(watch_dirs: list[str] | tuple[str, ...]) -> dict[str, Any]:
    digest = hashlib.sha256()
    file_count = 0
    byte_count = 0
    extensions = {".txt", ".md", ".json"}
    for raw_dir in watch_dirs:
        root = Path(raw_dir)
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file() and item.suffix.lower() in extensions):
            try:
                data = path.read_bytes()
            except OSError:
                continue
            file_count += 1
            byte_count += len(data)
            digest.update(str(path.as_posix()).encode("utf-8", errors="ignore"))
            digest.update(len(data).to_bytes(8, "big", signed=False))
            digest.update(hashlib.sha256(data).digest())
    return {
        "fingerprint": digest.hexdigest(),
        "file_count": file_count,
        "byte_count": byte_count,
        "watch_dirs": list(watch_dirs),
    }


def _resource_snapshot(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    root = _memory_root(memory_dir)
    root.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(root.resolve().anchor or ".")
    snapshot: dict[str, Any] = {
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "ram_available_gb": None,
        "ram_total_gb": None,
    }
    try:
        import psutil  # type: ignore

        memory = psutil.virtual_memory()
        snapshot["ram_available_gb"] = round(memory.available / (1024**3), 2)
        snapshot["ram_total_gb"] = round(memory.total / (1024**3), 2)
    except Exception:
        pass
    return snapshot


def _resource_blocker(snapshot: dict[str, Any]) -> str | None:
    disk_free = float(snapshot.get("disk_free_gb") or 0)
    ram_available = snapshot.get("ram_available_gb")
    if disk_free < MIN_DISK_FREE_GB:
        return f"disk_free_below_{MIN_DISK_FREE_GB:g}gb"
    if ram_available is not None and float(ram_available) < MIN_RAM_AVAILABLE_GB:
        return f"ram_available_below_{MIN_RAM_AVAILABLE_GB:g}gb"
    return None


def _run_cloud_brain_web_seed_feeder() -> dict[str, Any]:
    try:
        from packages.cloud_brain.web_seed_feeder import run_once

        env_value = (
            os.environ.get("ATANOR_WEB_SEED_FEEDER_ENABLED")
            or os.environ.get("ATANOR_CLOUD_BRAIN_WEB_SEED_ENABLED")
            or "1"
        ).strip().lower()
        force_enabled = env_value not in {"0", "false", "no", "off"}
        result = run_once(force_enabled=force_enabled)
        return {
            "available": True,
            "enabled": bool(result.enabled),
            "status": result.status,
            "sources_checked": int(result.sources_checked),
            "fragments_created": int(result.fragments_created),
            "fragments_rejected": int(result.fragments_rejected),
            "semantic_ingested": int(result.semantic_ingested),
            "semantic_concepts_created": int(result.semantic_concepts_created),
            "semantic_relations_created": int(result.semantic_relations_created),
            "semantic_relations_strengthened": int(getattr(result, "semantic_relations_strengthened", 0) or 0),
            "anna_metadata_records": int(getattr(result, "anna_metadata_records", 0) or 0),
            "anna_metadata_rejected": int(getattr(result, "anna_metadata_rejected", 0) or 0),
            "discovered_sources_added": int(getattr(result, "discovered_sources_added", 0) or 0),
            "max_sources_checked_per_run": int(getattr(result, "max_sources_checked_per_run", 0) or 0),
            "crawler_cursor": int(getattr(result, "crawler_cursor", 0) or 0),
            "last_run_at": result.last_run_at,
            "last_error": result.last_error,
            "local_brain_write": False,
        }
    except Exception as exc:
        return {
            "available": False,
            "enabled": False,
            "status": "error",
            "sources_checked": 0,
            "fragments_created": 0,
            "fragments_rejected": 0,
            "semantic_ingested": 0,
            "semantic_concepts_created": 0,
            "semantic_relations_created": 0,
            "semantic_relations_strengthened": 0,
            "last_run_at": utc_now_iso(),
            "last_error": str(exc),
            "local_brain_write": False,
        }


def _skipped_cloud_brain_web_seed_feeder() -> dict[str, Any]:
    return {
        "available": True,
        "enabled": False,
        "status": "skipped",
        "sources_checked": 0,
        "fragments_created": 0,
        "fragments_rejected": 0,
        "semantic_ingested": 0,
        "semantic_concepts_created": 0,
        "semantic_relations_created": 0,
        "semantic_relations_strengthened": 0,
        "anna_metadata_records": 0,
        "anna_metadata_rejected": 0,
        "discovered_sources_added": 0,
        "max_sources_checked_per_run": 0,
        "crawler_cursor": 0,
        "last_run_at": utc_now_iso(),
        "last_error": None,
        "local_brain_write": False,
    }


def _merge_runtime(state: dict[str, Any]) -> dict[str, Any]:
    return _merge_timing(state)


def _synaptic_status(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    if not _db_path(memory_dir).exists():
        return {"synaptic_node_count": 0, "synaptic_edge_count": 0, "avg_synaptic_weight": 0.0, "ingested_file_count": 0}
    conn = _connect(memory_dir)
    row = conn.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM synaptic_nodes) AS node_count,
          (SELECT COUNT(*) FROM synaptic_edges) AS edge_count,
          (SELECT COALESCE(AVG(weight), 0) FROM synaptic_edges) AS avg_weight,
          (SELECT COUNT(*) FROM ingested_files WHERE status = 'ingested') AS ingested_file_count
        """
    ).fetchone()
    conn.close()
    return {
        "synaptic_node_count": int(row["node_count"]),
        "synaptic_edge_count": int(row["edge_count"]),
        "avg_synaptic_weight": round(float(row["avg_weight"] or 0), 5),
        "ingested_file_count": int(row["ingested_file_count"]),
    }


def _safe_memory_status(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    try:
        return memory_status(str(memory_dir))
    except sqlite3.OperationalError:
        root = _memory_root(memory_dir)
        return {
            "state": "idle",
            "db_path": str(root / "homage.db"),
            "event_log_path": str(root / "events.jsonl"),
            "document_count": 0,
            "chunk_count": 0,
            "node_count": 0,
            "edge_count": 0,
            "event_count": 0,
            "vector_count": 0,
            "transition_count": 0,
            "cooccurrence_count": 0,
            "phrase_count": 0,
            "predicate_count": 0,
            "built_at": None,
        }


def _timing_category(state: dict[str, Any]) -> str:
    timing_state = str(state.get("timing_state") or "").upper()
    queue_state = str(state.get("queue_state") or "").upper()
    if timing_state in ACTIVE_LEARNING_STATES or queue_state in ACTIVE_LEARNING_STATES:
        return "active"
    if timing_state in IDLE_WAITING_STATES or queue_state in IDLE_WAITING_STATES:
        return "idle"
    if state.get("desired_running") and str(state.get("state") or "").lower() == "running":
        return "idle"
    return "paused"


def _normalize_timing_fields(state: dict[str, Any]) -> dict[str, Any]:
    legacy_learning = int(float(state.get("cumulative_learning_seconds") or 0))
    legacy_runtime = int(float(state.get("total_runtime_seconds") or state.get("cumulative_runtime_seconds") or 0))
    active = int(float(state.get("active_learning_seconds") or legacy_learning or 0))
    runtime = int(float(state.get("cumulative_runtime_seconds") or legacy_runtime or 0))
    idle = int(float(state.get("idle_waiting_seconds") or max(0, runtime - active)))
    state["active_learning_seconds"] = max(0, active)
    state["cumulative_learning_seconds"] = max(0, active)
    state["display_learning_seconds"] = max(0, active)
    state["cumulative_runtime_seconds"] = max(0, runtime)
    state["total_runtime_seconds"] = max(0, runtime)
    state["idle_waiting_seconds"] = max(0, idle)
    state["daemon_uptime_seconds"] = max(0, int(float(state.get("daemon_uptime_seconds") or 0)))
    state["timing_state"] = str(state.get("timing_state") or "IDLE")
    return state


def _accumulate_timing_delta(state: dict[str, Any], elapsed_seconds: float, category: str) -> dict[str, Any]:
    _normalize_timing_fields(state)
    delta = max(0, int(elapsed_seconds))
    if delta <= 0:
        return state
    state["cumulative_runtime_seconds"] = int(state.get("cumulative_runtime_seconds") or 0) + delta
    state["total_runtime_seconds"] = int(state.get("cumulative_runtime_seconds") or 0)
    if category == "active":
        state["active_learning_seconds"] = int(state.get("active_learning_seconds") or 0) + delta
    elif category == "idle":
        state["idle_waiting_seconds"] = int(state.get("idle_waiting_seconds") or 0) + delta
    state["cumulative_learning_seconds"] = int(state.get("active_learning_seconds") or 0)
    state["display_learning_seconds"] = int(state.get("active_learning_seconds") or 0)
    return state


def _merge_timing(state: dict[str, Any], now_ts: float | None = None) -> dict[str, Any]:
    now_ts = time.time() if now_ts is None else now_ts
    _normalize_timing_fields(state)
    started_ts = _parse_iso(state.get("started_at"))
    state["daemon_uptime_seconds"] = max(0, int(now_ts - started_ts)) if started_ts and state.get("desired_running") else 0
    last_update_ts = _parse_iso(state.get("last_timing_update_at"))
    category = _timing_category(state)
    if state.get("desired_running") and last_update_ts is not None:
        _accumulate_timing_delta(state, now_ts - last_update_ts, category)
    if state.get("desired_running"):
        state["last_timing_update_at"] = datetime.fromtimestamp(now_ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not state.get("current_learning_phase"):
        if category == "active":
            state["current_learning_phase"] = "learning"
        elif str(state.get("queue_state") or "").upper() == "WAITING_FOR_RESOURCES":
            state["current_learning_phase"] = "waiting_for_resources"
        elif category == "idle":
            state["current_learning_phase"] = "waiting_for_payloads"
        else:
            state["current_learning_phase"] = "paused"
    return state


def _refresh_counts(state: dict[str, Any], memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    status = _safe_memory_status(memory_dir)
    synaptic = _synaptic_status(memory_dir)
    state["latest_event_count"] = int(status.get("event_count") or 0)
    state["latest_node_count"] = int(status.get("node_count") or 0)
    state["latest_edge_count"] = int(status.get("edge_count") or 0)
    state.update(synaptic)
    return state


def _unique_cleaned_path(source: Path, cleaned_dir: Path, fingerprint: str) -> Path:
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in source.stem).strip("-") or "raw"
    candidate = cleaned_dir / f"{safe_stem}-{fingerprint[:10]}{source.suffix.lower()}"
    counter = 1
    while candidate.exists():
        candidate = cleaned_dir / f"{safe_stem}-{fingerprint[:10]}-{counter}{source.suffix.lower()}"
        counter += 1
    return candidate


def _run_ontology(input_dir: str, output_dir: str, concept_db_path: str | Path | None = None) -> dict[str, Any]:
    from ontology_forge import run_ontology

    return run_ontology(input_dir, output_dir, concept_db_path=concept_db_path)


def _upsert_sqlite_synapses(
    conn: sqlite3.Connection,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    increment: float = DEFAULT_POTENTIATION_INCREMENT,
) -> dict[str, int]:
    now = utc_now_iso()
    node_count = 0
    edge_count = 0
    flush = _AutoFlush(conn)
    for node in nodes:
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            continue
        existing = conn.execute("SELECT evidence_doc_ids, count FROM synaptic_nodes WHERE node_id = ?", (node_id,)).fetchone()
        evidence = _json_set(existing["evidence_doc_ids"] if existing else None, node.get("evidence_doc_ids") or [])
        count = int(existing["count"] if existing else 0) + max(1, int(node.get("count") or 1))
        conn.execute(
            """
            INSERT INTO synaptic_nodes(node_id, label, type, count, confidence, evidence_doc_ids, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
              label = excluded.label,
              type = excluded.type,
              count = ?,
              confidence = MAX(synaptic_nodes.confidence, excluded.confidence),
              evidence_doc_ids = ?,
              updated_at = excluded.updated_at
            """,
            (
                node_id,
                str(node.get("label") or node_id),
                str(node.get("type") or "concept"),
                count,
                float(node.get("confidence") or 0.5),
                evidence,
                now,
                now,
                count,
                evidence,
            ),
        )
        node_count += 1
        flush.mark()

    for edge in edges:
        source = str(edge.get("source") or "").strip()
        relation = str(edge.get("relation") or "relates").strip() or "relates"
        target = str(edge.get("target") or "").strip()
        if not source or not target:
            continue
        edge_id = f"{source}:{relation}:{target}"
        confidence = float(edge.get("confidence") or 0.5)
        existing = conn.execute("SELECT evidence_doc_ids FROM synaptic_edges WHERE edge_id = ?", (edge_id,)).fetchone()
        evidence = _json_set(existing["evidence_doc_ids"] if existing else None, edge.get("evidence_doc_ids") or [])
        conn.execute(
            """
            INSERT INTO synaptic_edges(edge_id, source, relation, target, weight, count, confidence, evidence_doc_ids, created_at, updated_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
            ON CONFLICT(edge_id) DO UPDATE SET
              weight = synaptic_edges.weight + ?,
              count = synaptic_edges.count + 1,
              confidence = MAX(synaptic_edges.confidence, excluded.confidence),
              evidence_doc_ids = ?,
              updated_at = excluded.updated_at,
              last_seen_at = excluded.last_seen_at
            """,
            (
                edge_id,
                source,
                relation,
                target,
                max(increment, confidence),
                confidence,
                evidence,
                now,
                now,
                now,
                increment,
                evidence,
            ),
        )
        edge_count += 1
        flush.mark()

    _write_learning_event(
        conn,
        "synapses_potentiated",
        None,
        {"node_count": node_count, "edge_count": edge_count, "increment": increment, "auto_flushes": flush.flush_count},
    )
    flush.flush()
    return {"nodes": node_count, "edges": edge_count}


class _Neo4jSink:
    def __init__(self) -> None:
        self.uri = os.environ.get("NEO4J_URI")
        self.user = os.environ.get("NEO4J_USER", "neo4j")
        self.password = os.environ.get("NEO4J_PASSWORD")
        self.database = os.environ.get("NEO4J_DATABASE")
        self._driver = None
        self.error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.uri and self.password)

    def _connect(self):
        if not self.enabled:
            return None
        if self._driver:
            return self._driver
        try:
            from neo4j import GraphDatabase  # type: ignore

            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            return self._driver
        except Exception as exc:
            self.error = str(exc)
            return None

    def upsert(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]], increment: float) -> dict[str, Any]:
        driver = self._connect()
        if not driver:
            return {"enabled": self.enabled, "available": False, "error": self.error}
        query = """
        UNWIND $nodes AS node
        MERGE (n:Concept {id: node.id})
        ON CREATE SET n.created_at = $now, n.count = 0
        SET n.label = node.label,
            n.type = node.type,
            n.count = coalesce(n.count, 0) + coalesce(node.count, 1),
            n.confidence = CASE WHEN coalesce(n.confidence, 0) > node.confidence THEN n.confidence ELSE node.confidence END,
            n.updated_at = $now
        WITH 1 AS ignored
        UNWIND $edges AS edge
        MERGE (s:Concept {id: edge.source})
        MERGE (t:Concept {id: edge.target})
        MERGE (s)-[r:RELATED {relation: edge.relation}]->(t)
        ON CREATE SET r.created_at = $now, r.weight = edge.weight, r.count = 1
        ON MATCH SET r.weight = coalesce(r.weight, 0) + $increment,
                     r.count = coalesce(r.count, 0) + 1
        SET r.confidence = CASE WHEN coalesce(r.confidence, 0) > edge.confidence THEN r.confidence ELSE edge.confidence END,
            r.updated_at = $now,
            r.last_seen_at = $now
        """
        payload_nodes = [
            {
                "id": str(node.get("id")),
                "label": str(node.get("label") or node.get("id")),
                "type": str(node.get("type") or "concept"),
                "count": int(node.get("count") or 1),
                "confidence": float(node.get("confidence") or 0.5),
            }
            for node in nodes
            if node.get("id")
        ]
        payload_edges = [
            {
                "source": str(edge.get("source")),
                "relation": str(edge.get("relation") or "relates"),
                "target": str(edge.get("target")),
                "weight": max(increment, float(edge.get("confidence") or 0.5)),
                "confidence": float(edge.get("confidence") or 0.5),
            }
            for edge in edges
            if edge.get("source") and edge.get("target")
        ]
        try:
            with (driver.session(database=self.database) if self.database else driver.session()) as session:
                session.execute_write(lambda tx: tx.run(query, nodes=payload_nodes, edges=payload_edges, increment=increment, now=utc_now_iso()).consume())
            return {"enabled": True, "available": True, "error": None}
        except Exception as exc:
            self.error = str(exc)
            return {"enabled": True, "available": False, "error": self.error}

    def decay(self, factor: float, threshold: float) -> dict[str, Any]:
        driver = self._connect()
        if not driver:
            return {"enabled": self.enabled, "available": False, "error": self.error}
        query = """
        MATCH ()-[r:RELATED]->()
        SET r.weight = coalesce(r.weight, 0) * $factor,
            r.decayed_at = $now
        WITH r
        WHERE r.weight < $threshold
        DELETE r
        WITH count(r) AS pruned
        MATCH (n:Concept)
        WHERE NOT (n)--()
        DELETE n
        RETURN pruned
        """
        try:
            with (driver.session(database=self.database) if self.database else driver.session()) as session:
                result = session.execute_write(lambda tx: list(tx.run(query, factor=factor, threshold=threshold, now=utc_now_iso())))
            pruned = int(result[0]["pruned"]) if result else 0
            return {"enabled": True, "available": True, "error": None, "pruned_edges": pruned}
        except Exception as exc:
            self.error = str(exc)
            return {"enabled": True, "available": False, "error": self.error}


def _neo4j_sink() -> _Neo4jSink:
    return _Neo4jSink()


def ingest_raw_documents(
    *,
    raw_dir: str = DEFAULT_RAW_DIR,
    cleaned_dir: str = DEFAULT_CLEANED_DIR,
    ontology_dir: str = DEFAULT_ONTOLOGY_DIR,
    memory_dir: str = DEFAULT_MEMORY_DIR,
    increment: float = DEFAULT_POTENTIATION_INCREMENT,
    max_files: int | None = None,
    min_file_age_seconds: float = 0.5,
) -> dict[str, Any]:
    raw_root = Path(raw_dir)
    cleaned_root = Path(cleaned_dir)
    ontology_root = Path(ontology_dir)
    memory_root = _memory_root(memory_dir)
    raw_root.mkdir(parents=True, exist_ok=True)
    cleaned_root.mkdir(parents=True, exist_ok=True)
    ontology_root.mkdir(parents=True, exist_ok=True)
    memory_root.mkdir(parents=True, exist_ok=True)

    candidates = [
        path
        for path in sorted(raw_root.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_RAW_EXTENSIONS
        and time.time() - path.stat().st_mtime >= min_file_age_seconds
    ]
    if max_files is not None:
        candidates = candidates[:max_files]
    if not candidates:
        return {
            "state": "listening_stream",
            "queue_state": "WAITING_FOR_PAYLOADS",
            "ingestion_mode": "persistent_append",
            "ingested": 0,
            "duplicates": 0,
            "files": [],
            "nodes": 0,
            "edges": 0,
            "neo4j": None,
        }

    conn = _connect(memory_dir)
    neo4j = _neo4j_sink()
    ingest_flush = _AutoFlush(conn)
    ingested_files: list[dict[str, Any]] = []
    duplicate_count = 0
    total_nodes = 0
    total_edges = 0
    neo4j_status: dict[str, Any] | None = None

    for raw_file in candidates:
        fingerprint = _file_fingerprint(raw_file)
        file_hash = fingerprint["fingerprint"]
        existing = conn.execute("SELECT status, cleaned_path FROM ingested_files WHERE file_fingerprint = ?", (file_hash,)).fetchone()
        cleaned_path = _unique_cleaned_path(raw_file, cleaned_root, file_hash)
        shutil.move(str(raw_file), str(cleaned_path))
        if existing:
            duplicate_count += 1
            _write_learning_event(
                conn,
                "raw_duplicate_moved",
                file_hash,
                {"cleaned_path": str(cleaned_path), "original_ingest": str(existing["cleaned_path"])},
            )
            ingest_flush.mark()
            continue

        batch_dir = memory_root / "ingest_batches" / file_hash[:16]
        batch_ontology_dir = memory_root / "ingest_ontology" / file_hash[:16]
        batch_dir.mkdir(parents=True, exist_ok=True)
        batch_copy = batch_dir / cleaned_path.name
        shutil.copy2(cleaned_path, batch_copy)

        result = _run_ontology(str(batch_dir), str(batch_ontology_dir), _concept_db_path(memory_dir))
        nodes = list(result.get("nodes") or [])
        edges = list(result.get("edges") or [])
        upserted = _upsert_sqlite_synapses(conn, nodes, edges, increment=increment)
        neo4j_status = neo4j.upsert(nodes, edges, increment)
        conn.execute(
            """
            INSERT INTO ingested_files(file_fingerprint, original_path, cleaned_path, byte_count, node_count, edge_count, status, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (file_hash, str(raw_file), str(cleaned_path), fingerprint["byte_count"], len(nodes), len(edges), "ingested", utc_now_iso()),
        )
        _write_learning_event(
            conn,
            "raw_file_ingested",
            file_hash,
            {"original_path": str(raw_file), "cleaned_path": str(cleaned_path), "nodes": len(nodes), "edges": len(edges)},
        )
        ingest_flush.mark()
        ingested_files.append(
            {
                "fingerprint": file_hash,
                "original_path": str(raw_file),
                "cleaned_path": str(cleaned_path),
                "nodes": len(nodes),
                "edges": len(edges),
            }
        )
        total_nodes += upserted["nodes"]
        total_edges += upserted["edges"]

    ingest_flush.flush()
    conn.commit()
    conn.close()

    if ingested_files:
        _run_ontology(str(cleaned_root), str(ontology_root), _concept_db_path(memory_dir))
        build_memory(cleaned_dir=str(cleaned_root), ontology_dir=str(ontology_root), memory_dir=memory_dir)

    return {
        "state": "persistent_append" if ingested_files else "listening_stream",
        "queue_state": "PERSISTENT_APPEND_APPLIED" if ingested_files else "WAITING_FOR_PAYLOADS",
        "ingestion_mode": "persistent_append",
        "projection_refresh": "background_compaction" if ingested_files else "not_required",
        "ingested": len(ingested_files),
        "duplicates": duplicate_count,
        "files": ingested_files,
        "nodes": total_nodes,
        "edges": total_edges,
        "neo4j": neo4j_status,
    }


def run_synaptic_decay(
    memory_dir: str = DEFAULT_MEMORY_DIR,
    *,
    factor: float = DEFAULT_DECAY_FACTOR,
    threshold: float = DEFAULT_PRUNE_THRESHOLD,
) -> dict[str, Any]:
    factor = max(0.0, min(1.0, float(factor)))
    threshold = max(0.0, float(threshold))
    conn = _connect(memory_dir)
    before = conn.execute("SELECT COUNT(*) AS count FROM synaptic_edges").fetchone()["count"]
    conn.execute("UPDATE synaptic_edges SET weight = weight * ?, updated_at = ?", (factor, utc_now_iso()))
    pruned_rows = conn.execute("SELECT edge_id FROM synaptic_edges WHERE weight < ?", (threshold,)).fetchall()
    pruned_ids = [row["edge_id"] for row in pruned_rows]
    conn.executemany("DELETE FROM synaptic_edges WHERE edge_id = ?", [(edge_id,) for edge_id in pruned_ids])
    conn.execute(
        """
        DELETE FROM synaptic_nodes
        WHERE node_id NOT IN (SELECT source FROM synaptic_edges)
          AND node_id NOT IN (SELECT target FROM synaptic_edges)
        """
    )
    after = conn.execute("SELECT COUNT(*) AS count FROM synaptic_edges").fetchone()["count"]
    _write_learning_event(
        conn,
        "synaptic_decay",
        None,
        {"factor": factor, "threshold": threshold, "before_edges": before, "after_edges": after, "pruned_edges": len(pruned_ids)},
    )
    conn.commit()
    conn.close()
    neo4j_status = _neo4j_sink().decay(factor, threshold)
    return {
        "state": "completed",
        "factor": factor,
        "threshold": threshold,
        "before_edges": int(before),
        "after_edges": int(after),
        "pruned_edges": len(pruned_ids),
        "neo4j": neo4j_status,
    }


def daemon_status(memory_dir: str = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    with _lock:
        memory_dir = _resolved_memory_dir(memory_dir)
        state = _merge_timing(_read_state(memory_dir))
        alive = _worker_matches(memory_dir)
        if (
            state.get("desired_running")
            and not alive
            and _daemon_self_heal_enabled()
            and state.get("state") not in {"failed", "stopped", "guarded_pause"}
        ):
            interval_seconds = int(state.get("interval_seconds") or DEFAULT_INTERVAL_SECONDS)
            state.update(
                {
                    "state": "running",
                    "resume_needed": False,
                    "last_heartbeat_at": utc_now_iso(),
                    "last_round_action": "self_healing_resume",
                    "last_round_message": "Self-healing wake-up restarted the continuous ingestion worker.",
                    "stream_state": "LISTENING_STREAM",
                    "queue_state": "WAITING_FOR_PAYLOADS",
                }
            )
            _write_state(state, memory_dir)
            _spawn_worker_locked(memory_dir, interval_seconds)
            alive = _worker_matches(memory_dir)
        state["worker_alive"] = alive
        if state.get("desired_running") and not alive and state.get("state") not in {"failed", "guarded_pause"}:
            state["state"] = "resume_needed"
            state["resume_needed"] = True
            state["last_round_message"] = (
                "Local FastAPI was restarted or the daemon worker is not alive. "
                "Call resume to continue from the persisted memory store."
            )
        else:
            state["resume_needed"] = False
        if state.get("state") == "guarded_pause":
            state["stream_state"] = "PAUSED_BY_GUARD"
            if state.get("queue_state") in {None, "WAITING_FOR_START", "WAITING_FOR_PAYLOADS"}:
                state["queue_state"] = "WAITING_FOR_RESOURCES"
        elif state.get("desired_running") and state.get("state") != "failed":
            state["stream_state"] = "LISTENING_STREAM"
            if state.get("queue_state") in {None, "WAITING_FOR_START"}:
                state["queue_state"] = "WAITING_FOR_PAYLOADS"
        else:
            state["stream_state"] = "PAUSED" if state.get("state") != "failed" else "STOPPED_BY_GUARD"
        state["resource_snapshot"] = _resource_snapshot(memory_dir)
        state["checkpoint_count"] = len(list(_checkpoint_dir(memory_dir).glob("*.json"))) if _checkpoint_dir(memory_dir).exists() else 0
        state["local_required"] = True
        state["deployment_policy"] = "The Vercel deployment stays a small viewer; real Cloud Brain learning runs only beside local FastAPI."
        _refresh_counts(state, memory_dir)
        _normalize_timing_fields(state)
        _write_state(state, memory_dir)
        return state


def daemon_checkpoint(memory_dir: str = DEFAULT_MEMORY_DIR, reason: str = "manual") -> dict[str, Any]:
    with _lock:
        root = _checkpoint_dir(memory_dir)
        root.mkdir(parents=True, exist_ok=True)
        state = _read_state(memory_dir)
        conn = _connect(memory_dir)
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        conn.close()
        snapshot = {
            "created_at": utc_now_iso(),
            "reason": reason,
            "daemon": state,
            "memory": _safe_memory_status(memory_dir),
            "synaptic": _synaptic_status(memory_dir),
        }
        filename = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{reason.replace(' ', '-')[:32]}.json"
        (root / filename).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        state["last_checkpoint_at"] = snapshot["created_at"]
        state["last_checkpoint_path"] = str(root / filename)
        _write_state(state, memory_dir)
        return daemon_status(memory_dir)


def tick_daemon(
    memory_dir: str = DEFAULT_MEMORY_DIR,
    force: bool = False,
    run_decay: bool = True,
    run_web_seed_feeder: bool | None = None,
) -> dict[str, Any]:
    with _lock:
        tick_started = time.monotonic()
        state = _merge_timing(_read_state(memory_dir))
        snapshot = _resource_snapshot(memory_dir)
        blocker = _resource_blocker(snapshot)
        now = utc_now_iso()
        if blocker:
            state.update(
                {
                    "state": "guarded_pause",
                    "desired_running": True,
                    "last_error": blocker,
                    "resource_warning": blocker,
                    "last_heartbeat_at": now,
                    "last_round_action": "resource_guard_pause",
                    "last_round_message": (
                        "Resource guard paused the continuous ingestion worker. "
                        "It will retry automatically when RAM or disk pressure recovers."
                    ),
                    "stream_state": "PAUSED_BY_GUARD",
                    "queue_state": "WAITING_FOR_RESOURCES",
                    "resource_snapshot": snapshot,
                }
            )
            _write_state(_refresh_counts(state, memory_dir), memory_dir)
            return daemon_status(memory_dir)

        ingest_result = ingest_raw_documents(
            raw_dir=str(state.get("raw_dir") or DEFAULT_RAW_DIR),
            cleaned_dir=str(state.get("cleaned_dir") or DEFAULT_CLEANED_DIR),
            ontology_dir=str(state.get("ontology_dir") or DEFAULT_ONTOLOGY_DIR),
            memory_dir=memory_dir,
            increment=float(state.get("potentiation_increment") or DEFAULT_POTENTIATION_INCREMENT),
            min_file_age_seconds=0.0 if force else 0.5,
        )
        should_run_web_seed = _web_seed_on_tick_enabled() if run_web_seed_feeder is None else bool(run_web_seed_feeder)
        web_seed_result = _run_cloud_brain_web_seed_feeder() if should_run_web_seed else _skipped_cloud_brain_web_seed_feeder()
        watch_dirs = list(state.get("watch_dirs") or [DEFAULT_RAW_DIR, DEFAULT_CLEANED_DIR, DEFAULT_ONTOLOGY_DIR])
        fingerprint = _input_fingerprint(watch_dirs)
        memory = _safe_memory_status(memory_dir)
        decay_result = None
        last_decay = _parse_iso(state.get("last_decay_at")) or 0
        due_for_decay = run_decay and (time.time() - last_decay >= float(state.get("decay_interval_seconds") or DEFAULT_DECAY_INTERVAL_SECONDS))
        if due_for_decay:
            decay_result = run_synaptic_decay(
                memory_dir,
                factor=float(state.get("decay_factor") or DEFAULT_DECAY_FACTOR),
                threshold=float(state.get("prune_threshold") or DEFAULT_PRUNE_THRESHOLD),
            )
            state["last_decay_at"] = now

        needs_build = (
            force
            or ingest_result.get("ingested", 0) > 0
            or state.get("last_input_fingerprint") != fingerprint["fingerprint"]
            or memory.get("state") != "completed"
        )
        if needs_build:
            _run_ontology(
                str(state.get("cleaned_dir") or DEFAULT_CLEANED_DIR),
                str(state.get("ontology_dir") or DEFAULT_ONTOLOGY_DIR),
                _concept_db_path(memory_dir),
            )
            result = build_memory(
                cleaned_dir=str(state.get("cleaned_dir") or DEFAULT_CLEANED_DIR),
                ontology_dir=str(state.get("ontology_dir") or DEFAULT_ONTOLOGY_DIR),
                memory_dir=memory_dir,
            )
            action = "persistent_append_delta_indexed" if ingest_result.get("ingested") else "append_only_projection_refreshed"
            message = (
                f"Persistent append absorbed {ingest_result.get('ingested', 0)} raw files; "
                f"projection now exposes {result.get('node_count', 0)} nodes and {result.get('edge_count', 0)} edges."
            )
            state["learned_rounds"] = int(state.get("learned_rounds") or 0) + 1
        else:
            result = memory
            action = "listening_stream_no_new_payload"
            message = "Continuous ingestion stream is awake; no new payloads arrived this tick."
            state["idle_rounds"] = int(state.get("idle_rounds") or 0) + 1

        active_work = bool(
            ingest_result.get("ingested", 0)
            or needs_build
            or decay_result
            or int(web_seed_result.get("semantic_ingested") or 0) > 0
            or int(web_seed_result.get("fragments_created") or 0) > 0
        )
        _accumulate_timing_delta(state, time.monotonic() - tick_started, "active" if active_work else "idle")

        state.update(
            {
                "state": "running" if state.get("desired_running") else "idle",
                "stream_state": "LISTENING_STREAM" if state.get("desired_running") else "PAUSED",
                "queue_state": "PERSISTENT_APPEND_APPLIED" if active_work else "WAITING_FOR_PAYLOADS",
                "timing_state": "GRAPH_GROWING" if active_work else "IDLE",
                "current_learning_phase": "learning" if active_work else "waiting_for_payloads",
                "ingestion_mode": "persistent_append",
                "last_heartbeat_at": now,
                "last_tick_at": now,
                "last_input_fingerprint": fingerprint["fingerprint"],
                "last_input_file_count": fingerprint["file_count"],
                "last_input_bytes": fingerprint["byte_count"],
                "last_round_action": action,
                "last_round_message": message,
                "last_error": None,
                "resource_warning": None,
                "total_rounds": int(state.get("total_rounds") or 0) + 1,
                "last_ingest_result": ingest_result,
                "last_web_seed_result": web_seed_result,
                "last_decay_result": decay_result,
                "last_ingested_files": ingest_result.get("files", []),
                "resource_snapshot": snapshot,
                "latest_event_count": int(result.get("event_count") or 0),
                "latest_node_count": int(result.get("node_count") or 0),
                "latest_edge_count": int(result.get("edge_count") or 0),
            }
        )
        _write_state(_merge_runtime(_refresh_counts(state, memory_dir)), memory_dir)
        return daemon_status(memory_dir)


async def _async_worker_loop(memory_dir: str, interval_seconds: int) -> None:
    while not _stop_event.is_set():
        try:
            await asyncio.to_thread(tick_daemon, memory_dir)
        except RuntimeError as exc:
            if _is_interpreter_shutdown(exc):
                break
            raise
        status = daemon_status(memory_dir)
        if status.get("state") == "failed":
            break
        last_checkpoint = _parse_iso(status.get("last_checkpoint_at")) or 0
        if time.time() - last_checkpoint >= 300:
            try:
                await asyncio.to_thread(daemon_checkpoint, memory_dir, "auto")
            except RuntimeError as exc:
                if _is_interpreter_shutdown(exc):
                    break
                raise
        try:
            await asyncio.wait_for(asyncio.to_thread(_stop_event.wait, interval_seconds), timeout=interval_seconds + 1)
        except asyncio.TimeoutError:
            pass


def _worker_entry(memory_dir: str, interval_seconds: int) -> None:
    try:
        asyncio.run(_async_worker_loop(memory_dir, interval_seconds))
    except RuntimeError as exc:
        if not _is_interpreter_shutdown(exc):
            raise


def _is_interpreter_shutdown(exc: RuntimeError) -> bool:
    message = str(exc)
    return "cannot schedule new futures after shutdown" in message or "cannot schedule new futures after interpreter shutdown" in message


def start_daemon(memory_dir: str = DEFAULT_MEMORY_DIR, interval_seconds: int = DEFAULT_INTERVAL_SECONDS, resume: bool = True) -> dict[str, Any]:
    global _worker_thread, _worker_memory_dir
    interval_seconds = max(5, min(3600, int(interval_seconds or DEFAULT_INTERVAL_SECONDS)))
    with _lock:
        memory_dir = _resolved_memory_dir(memory_dir)
        if _worker_alive() and not _worker_matches(memory_dir):
            _stop_event.set()
            if _worker_thread:
                _worker_thread.join(timeout=2)
            _worker_thread = None
            _worker_memory_dir = None
        if _worker_matches(memory_dir):
            return daemon_status(memory_dir)
        state = _read_state(memory_dir)
        if not resume:
            state = _default_state()
        now = utc_now_iso()
        state.update(
            {
                "state": "running",
                "desired_running": True,
                "resume_needed": False,
                "started_at": state.get("started_at") if resume and state.get("started_at") else now,
                "last_heartbeat_at": now,
                "interval_seconds": interval_seconds,
                "stream_state": "LISTENING_STREAM",
                "queue_state": "WAITING_FOR_PAYLOADS",
                "timing_state": "IDLE",
                "current_learning_phase": "waiting_for_payloads",
                "last_timing_update_at": now,
                "ingestion_mode": "persistent_append",
                "last_error": None,
                "last_round_message": "Continuous ingestion stream is awake and listening for payloads.",
            }
        )
        state["reboot_resilience"] = {
            **state.get("reboot_resilience", {}),
            "state_file": str(_state_path(memory_dir)),
            "checkpoint_dir": str(_checkpoint_dir(memory_dir)),
            "sqlite_wal": str(_db_path(memory_dir)),
            "heartbeat_interval_seconds": interval_seconds,
        }
        _write_state(state, memory_dir)
        _spawn_worker_locked(memory_dir, interval_seconds)
        return daemon_status(memory_dir)


def resume_daemon(memory_dir: str = DEFAULT_MEMORY_DIR, interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> dict[str, Any]:
    return start_daemon(memory_dir=memory_dir, interval_seconds=interval_seconds, resume=True)


def stop_daemon(memory_dir: str = DEFAULT_MEMORY_DIR, reason: str = "manual") -> dict[str, Any]:
    global _worker_thread, _worker_memory_dir
    with _lock:
        memory_dir = _resolved_memory_dir(memory_dir)
        _stop_event.set()
        state = _read_state(memory_dir)
        state.update(
            {
                "state": "stopped",
                "desired_running": False,
                "resume_needed": False,
                "last_heartbeat_at": utc_now_iso(),
                "timing_state": "IDLE",
                "current_learning_phase": "stopped",
                "last_round_message": f"Local Cloud Brain hippocampus daemon stopped: {reason}.",
            }
        )
        _write_state(_merge_runtime(state), memory_dir)
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=2)
    if not _worker_alive():
        _worker_thread = None
        _worker_memory_dir = None
    return daemon_checkpoint(memory_dir, f"stop-{reason}")


if os.environ.get("ATANOR_AUTOSTART_DAEMON") == "1" or os.environ.get("HOMAGE_AUTOSTART_DAEMON") == "1":
    saved = _read_state(DEFAULT_MEMORY_DIR)
    if saved.get("desired_running"):
        start_daemon(DEFAULT_MEMORY_DIR, int(saved.get("interval_seconds") or DEFAULT_INTERVAL_SECONDS), resume=True)
