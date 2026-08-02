from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLOUD_ROOT = PROJECT_ROOT / "data" / "cloud_brain"
INDEX_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def semantic_store_paths(root: str | Path = DEFAULT_CLOUD_ROOT) -> dict[str, Path]:
    base = Path(root)
    store = base / "store"
    index = base / "index"
    return {
        "root": base,
        "store": store,
        "concepts": store / "semantic_concepts.json",
        "relations": store / "semantic_relations.json",
        "evidence": store / "semantic_evidence.jsonl",
        "shards": store / "semantic_growth_shards",
        "shard_index": store / "semantic_growth_shards" / "semantic_growth_shard_index.json",
        "feeder_state": base / "web_seed_feeder_state.json",
        "growth_runs": base / "growth_runs",
        "index": index,
        "status_cache": index / "status_cache.json",
        "graph_sample": index / "fast_graph_sample.json",
        "legacy_graph_sample": index / "graph_sample_fast.json",
        "manifest": index / "manifest.json",
        "chunks": index / "chunks",
    }


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.{os.getpid()}.{time.time_ns()}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    last_error: Exception | None = None
    for attempt in range(60):
        try:
            tmp_path.replace(path)
            last_error = None
            break
        except PermissionError as exc:
            last_error = exc
            time.sleep(min(0.05 * (attempt + 1), 0.5))
    if last_error is not None:
        raise last_error


def path_signature(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
        return {"exists": True, "size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}
    except FileNotFoundError:
        return {"exists": False, "size": 0, "mtime_ns": 0}


def shards_signature(shard_dir: Path) -> dict[str, Any]:
    if not shard_dir.exists():
        return {"count": 0, "size": 0, "latest_mtime_ns": 0}
    count = 0
    size = 0
    latest = 0
    for path in shard_dir.glob("*.json"):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        count += 1
        size += int(stat.st_size)
        latest = max(latest, int(stat.st_mtime_ns))
    return {"count": count, "size": size, "latest_mtime_ns": latest}


def store_signature(root: str | Path = DEFAULT_CLOUD_ROOT) -> dict[str, Any]:
    paths = semantic_store_paths(root)
    return {
        "concepts": path_signature(paths["concepts"]),
        "relations": path_signature(paths["relations"]),
        "evidence": path_signature(paths["evidence"]),
        "shard_index": path_signature(paths["shard_index"]),
        "feeder_state": path_signature(paths["feeder_state"]),
        "shards": shards_signature(paths["shards"]),
    }


def fast_store_signature(root: str | Path = DEFAULT_CLOUD_ROOT) -> dict[str, Any]:
    """Return a bounded freshness signature for request-time reads.

    The full signature intentionally scans every growth shard so rebuild code can
    prove a complete index state. Normal status/graph requests must not do that:
    on large stores it turns a cached read into an O(shard_count) directory walk.
    The shard index is atomically updated when shards are appended, so its
    signature is enough for fast stale detection.
    """

    paths = semantic_store_paths(root)
    return {
        "concepts": path_signature(paths["concepts"]),
        "relations": path_signature(paths["relations"]),
        "evidence": path_signature(paths["evidence"]),
        "shard_index": path_signature(paths["shard_index"]),
        "feeder_state": path_signature(paths["feeder_state"]),
    }


def load_status_cache(root: str | Path = DEFAULT_CLOUD_ROOT) -> dict[str, Any] | None:
    payload = read_json(semantic_store_paths(root)["status_cache"], None)
    return payload if isinstance(payload, dict) else None


def write_status_cache(root: str | Path, payload: dict[str, Any]) -> None:
    write_json(semantic_store_paths(root)["status_cache"], payload)


def load_graph_sample_cache(root: str | Path = DEFAULT_CLOUD_ROOT) -> dict[str, Any] | None:
    paths = semantic_store_paths(root)
    payload = read_json(paths["graph_sample"], None)
    if not isinstance(payload, dict):
        payload = read_json(paths["legacy_graph_sample"], None)
    return payload if isinstance(payload, dict) else None


def write_graph_sample_cache(root: str | Path, payload: dict[str, Any]) -> None:
    write_json(semantic_store_paths(root)["graph_sample"], payload)


def load_manifest(root: str | Path = DEFAULT_CLOUD_ROOT) -> dict[str, Any] | None:
    payload = read_json(semantic_store_paths(root)["manifest"], None)
    return payload if isinstance(payload, dict) else None


def write_manifest(root: str | Path, payload: dict[str, Any]) -> None:
    write_json(semantic_store_paths(root)["manifest"], payload)
