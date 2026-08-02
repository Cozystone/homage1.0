from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .planetary_topology import MAX_DIRECT_EDGES, planetize_graph_sample


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEMANTIC_CLOUD_ROOT = PROJECT_ROOT / "data" / "cloud_brain"
STORE_BACKEND = "local_semantic_proof_store"
# The semantic store accepts caller-supplied text and descriptive metadata. Store
# persistence therefore proves only that a candidate was recorded; it is not an
# independent source attestation and cannot authorize answer grounding by itself.
SEMANTIC_STORE_TRUST_STATE = "semantic_candidate_store"
SEMANTIC_STORE_VERIFICATION_STATE = "caller_unverified_v0"
_CACHE_TTL_SECONDS = 2.0
_STATUS_CACHE: dict[str, Any] = {"key": None, "expires_at": 0.0, "payload": None}
_GRAPH_SAMPLE_CACHE: dict[str, Any] = {}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _path_signature(path: Path) -> tuple[bool, int, int]:
    try:
        stat = path.stat()
        return True, int(stat.st_size), int(stat.st_mtime_ns)
    except FileNotFoundError:
        return False, 0, 0


def _shards_signature(shard_dir: Path) -> tuple[int, int, int]:
    if not shard_dir.exists():
        return 0, 0, 0
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
    return count, size, latest


def _store_signature(paths: dict[str, Path]) -> tuple[Any, ...]:
    feeder_path = paths["root"] / "web_seed_feeder_state.json"
    return (
        _path_signature(paths["concepts"]),
        _path_signature(paths["relations"]),
        _path_signature(paths["evidence"]),
        _path_signature(feeder_path),
        _shards_signature(paths["shards"]),
    )


def _clear_semantic_store_cache() -> None:
    _STATUS_CACHE["key"] = None
    _STATUS_CACHE["expires_at"] = 0.0
    _STATUS_CACHE["payload"] = None
    _GRAPH_SAMPLE_CACHE.clear()


def _count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _count_json_object_entries(path: Path) -> int:
    """Count top-level JSON object entries without loading the whole store."""
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.rstrip()
            if line.startswith('  "') and stripped.endswith("{"):
                count += 1
    return count


def _count_shard_entries(shard_dir: Path, suffix: str) -> int:
    index_path = shard_dir / "semantic_growth_shard_index.json"
    index_payload = _read_json(index_path, {})
    index_key = f"{suffix}_count"
    if isinstance(index_payload, dict) and isinstance(index_payload.get(index_key), int):
        return int(index_payload[index_key])
    if not shard_dir.exists():
        return 0
    total = 0
    for path in shard_dir.glob(f"*_{suffix}.json"):
        total += _count_json_object_entries(path)
    return total


def semantic_store_paths(root: str | Path = DEFAULT_SEMANTIC_CLOUD_ROOT) -> dict[str, Path]:
    base = Path(root)
    store = base / "store"
    store.mkdir(parents=True, exist_ok=True)
    return {
        "root": base,
        "store": store,
        "concepts": store / "semantic_concepts.json",
        "relations": store / "semantic_relations.json",
        "evidence": store / "semantic_evidence.jsonl",
        "shards": store / "semantic_growth_shards",
        "shard_index": store / "semantic_growth_shards" / "semantic_growth_shard_index.json",
        "growth_runs": base / "growth_runs",
        "proofs": base / "proofs",
        "semantic_ingest": base / "semantic_ingest",
    }


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _read_feeder_state(root: Path) -> dict[str, Any]:
    payload = _read_json(root / "web_seed_feeder_state.json", {})
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Any) -> None:
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
    _clear_semantic_store_cache()


class _StoreFileLock:
    def __init__(self, path: Path, *, timeout_seconds: float = 10.0):
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.fd: int | None = None

    def __enter__(self) -> "_StoreFileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode("utf-8"))
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.timeout_seconds:
                        try:
                            self.path.unlink(missing_ok=True)
                        except PermissionError:
                            time.sleep(0.05)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for semantic store lock: {self.path}")
                time.sleep(0.025)

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.path.unlink(missing_ok=True)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    _clear_semantic_store_cache()


class SemanticCloudStore:
    def __init__(self, root: str | Path = DEFAULT_SEMANTIC_CLOUD_ROOT):
        self.root = Path(root)
        self.paths = semantic_store_paths(self.root)
        for key in ["growth_runs", "proofs", "semantic_ingest", "shards"]:
            self.paths[key].mkdir(parents=True, exist_ok=True)

    def load_concepts(self) -> dict[str, dict[str, Any]]:
        payload = _read_json(self.paths["concepts"], {})
        return payload if isinstance(payload, dict) else {}

    def save_concepts(self, concepts: dict[str, dict[str, Any]]) -> None:
        with _StoreFileLock(self.paths["store"] / "semantic_store.lock"):
            existing = self.load_concepts()
            if existing:
                merged = dict(existing)
                merged.update(concepts)
                concepts = merged
            _write_json(self.paths["concepts"], concepts)

    def load_relations(self) -> dict[str, dict[str, Any]]:
        payload = _read_json(self.paths["relations"], {})
        return payload if isinstance(payload, dict) else {}

    def save_relations(self, relations: dict[str, dict[str, Any]]) -> None:
        with _StoreFileLock(self.paths["store"] / "semantic_store.lock"):
            existing = self.load_relations()
            if existing:
                merged = dict(existing)
                merged.update(relations)
                relations = merged
            _write_json(self.paths["relations"], relations)

    def save_graph_snapshot(self, concepts: dict[str, dict[str, Any]], relations: dict[str, dict[str, Any]]) -> None:
        """Persist a caller-owned full graph snapshot under one store lock."""
        with _StoreFileLock(self.paths["store"] / "semantic_store.lock"):
            _write_json(self.paths["concepts"], concepts)
            _write_json(self.paths["relations"], relations)

    def save_growth_shard(
        self,
        shard_id: str,
        concepts: dict[str, dict[str, Any]],
        relations: dict[str, dict[str, Any]],
    ) -> None:
        """Persist a small append-style growth shard without rewriting the full store."""
        safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in shard_id)[:96]
        self.paths["shards"].mkdir(parents=True, exist_ok=True)
        with _StoreFileLock(self.paths["store"] / "semantic_store.lock"):
            _write_json(self.paths["shards"] / f"{safe_id}_concepts.json", concepts)
            _write_json(self.paths["shards"] / f"{safe_id}_relations.json", relations)
            index_payload = _read_json(self.paths["shard_index"], {})
            if not isinstance(index_payload, dict):
                index_payload = {}
            shard_files = index_payload.setdefault("shards", {})
            if not isinstance(shard_files, dict):
                shard_files = {}
                index_payload["shards"] = shard_files
            previous = shard_files.get(safe_id) if isinstance(shard_files.get(safe_id), dict) else {}
            prev_concepts = int(previous.get("concepts") or 0) if isinstance(previous, dict) else 0
            prev_relations = int(previous.get("relations") or 0) if isinstance(previous, dict) else 0
            shard_files[safe_id] = {
                "concepts": len(concepts),
                "relations": len(relations),
                "updated_at": utc_now_iso(),
            }
            index_payload["concepts_count"] = int(index_payload.get("concepts_count") or 0) - prev_concepts + len(concepts)
            index_payload["relations_count"] = int(index_payload.get("relations_count") or 0) - prev_relations + len(relations)
            _write_json(self.paths["shard_index"], index_payload)

    def load_recent_growth_shards(self, limit_files: int = 8) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not self.paths["shards"].exists():
            return [], []
        concept_files = sorted(
            self.paths["shards"].glob("*_concepts.json"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )[:limit_files]
        concepts: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []
        for concept_path in concept_files:
            concept_payload = _read_json(concept_path, {})
            if isinstance(concept_payload, dict):
                concepts.extend(row for row in concept_payload.values() if isinstance(row, dict))
            relation_path = concept_path.with_name(concept_path.name.replace("_concepts.json", "_relations.json"))
            relation_payload = _read_json(relation_path, {})
            if isinstance(relation_payload, dict):
                relations.extend(row for row in relation_payload.values() if isinstance(row, dict))
        return concepts, relations

    def load_evidence(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.paths["evidence"])

    def add_evidence(self, evidence: dict[str, Any]) -> bool:
        with _StoreFileLock(self.paths["store"] / "semantic_store.lock"):
            rows = self.load_evidence()
            source_hash = str(evidence.get("source_hash") or "")
            if source_hash and any(str(row.get("source_hash")) == source_hash for row in rows):
                return False
            _append_jsonl(self.paths["evidence"], evidence)
            return True

    def status(self) -> dict[str, Any]:
        from .read_model import load_cloud_read_model_status

        return load_cloud_read_model_status(self.root)

    def graph_sample(self, limit_nodes: int = 1000, limit_edges: int = 3000) -> dict[str, Any]:
        from .read_model import load_fast_graph_sample

        return load_fast_graph_sample(self.root, limit_nodes=limit_nodes, limit_edges=limit_edges)

    def latest_growth_run(self) -> dict[str, Any] | None:
        runs = sorted(self.paths["growth_runs"].glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in runs:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    return {
                        "run_id": payload.get("run_id"),
                        "sentences_processed": payload.get("sentences_processed"),
                        "concepts_created": payload.get("concepts_created"),
                        "concepts_merged": payload.get("concepts_merged"),
                        "relations_created": payload.get("relations_created"),
                        "relations_strengthened": payload.get("relations_strengthened"),
                        "evidence_added": payload.get("evidence_added"),
                    }
            except Exception:
                continue
        return None


def get_semantic_cloud_growth_status(root: str | Path = DEFAULT_SEMANTIC_CLOUD_ROOT) -> dict[str, Any]:
    return SemanticCloudStore(root).status()
